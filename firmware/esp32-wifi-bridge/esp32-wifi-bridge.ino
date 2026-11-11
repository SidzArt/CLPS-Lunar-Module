// CODEX Sub-Controller 1: ESP32 Wi-Fi Bridge & Framed UART Relay
// Role: Accepts HMAC-SHA256 authenticated Protocol v1 commands over LAN HTTP
// and relays CRC16-protected binary UART frames to the Arduino Uno motion controller.
//
// ELECTRICAL SAFETY:
//   ESP32 UART uses 3.3 V logic; Arduino Uno uses 5 V logic.
//   NEVER connect Uno TX directly to ESP32 RX without a verified level shifter.

#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoJson.h>
#include <HardwareSerial.h>
#include <mbedtls/md.h>
#include "secrets.h"

#define FIRMWARE_VERSION "codex-bridge-v1.0.0-unverified"
#define FIRMWARE_TARGET  "esp32"

// HardwareSerial UART2 pins connecting through 3.3V<->5V level shifter to Arduino Uno
#define UNO_UART_RX_PIN 16
#define UNO_UART_TX_PIN 17
#define UNO_UART_BAUD   115200

// Framed binary UART constants (must match backend protocol.py & arduino-uno-motion.ino)
static const uint16_t UART_SOF         = 0xAA55;
static const uint8_t  UART_VERSION     = 0x01;
static const uint8_t  MSG_PING         = 0x01;
static const uint8_t  MSG_MOTION_CMD   = 0x02;
static const uint8_t  MSG_ESTOP        = 0x03;
static const uint8_t  MSG_STATUS_REQ   = 0x04;
static const uint8_t  MSG_ACK          = 0x81;
static const uint8_t  MSG_NACK         = 0x82;
static const uint8_t  MSG_FAULT        = 0x83;

WebServer server(80);
HardwareSerial UnoSerial(2);

static bool g_uart_ok = false;
static bool g_estop_latched = false;
static uint32_t g_last_sequence = 0;

// Bounded ring buffer for replay protection
static const size_t NONCE_RING_SIZE = 32;
static String g_seen_nonces[NONCE_RING_SIZE];
static size_t g_nonce_write_idx = 0;

static unsigned long g_last_uno_ping_ms = 0;
static unsigned long g_last_wifi_attempt_ms = 0;

uint16_t crc16_ccitt(const uint8_t* data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; ++i) {
        crc ^= (uint16_t)data[i] << 8;
        for (uint8_t b = 0; b < 8; ++b) {
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
        }
    }
    return crc;
}

bool constant_time_hex_equal(const String& a, const String& b) {
    if (a.length() != b.length() || a.length() == 0) {
        return false;
    }
    uint8_t diff = 0;
    for (size_t i = 0; i < a.length(); ++i) {
        diff |= (uint8_t)(tolower((unsigned char)a[i]) ^ tolower((unsigned char)b[i]));
    }
    return diff == 0;
}

bool compute_hmac_sha256_hex(const String& message, String& out_hex) {
    uint8_t hmac_result[32];
    mbedtls_md_context_t ctx;
    mbedtls_md_init(&ctx);
    const mbedtls_md_info_t* info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    if (!info) {
        mbedtls_md_free(&ctx);
        return false;
    }
    mbedtls_md_setup(&ctx, info, 1);
    mbedtls_md_hmac_starts(&ctx, (const unsigned char*)CODEX_HMAC_SECRET, strlen(CODEX_HMAC_SECRET));
    mbedtls_md_hmac_update(&ctx, (const unsigned char*)message.c_str(), message.length());
    mbedtls_md_hmac_finish(&ctx, hmac_result);
    mbedtls_md_free(&ctx);

    char hex_buf[65];
    for (int i = 0; i < 32; ++i) {
        snprintf(hex_buf + (i * 2), 3, "%02x", hmac_result[i]);
    }
    hex_buf[64] = '\0';
    out_hex = String(hex_buf);
    return true;
}

bool nonce_seen_before(const String& nonce) {
    for (size_t i = 0; i < NONCE_RING_SIZE; ++i) {
        if (g_seen_nonces[i].length() > 0 && g_seen_nonces[i] == nonce) {
            return true;
        }
    }
    return false;
}

void record_nonce(const String& nonce) {
    g_seen_nonces[g_nonce_write_idx] = nonce;
    g_nonce_write_idx = (g_nonce_write_idx + 1) % NONCE_RING_SIZE;
}

bool send_uart_frame_and_wait_ack(uint8_t msg_type, uint32_t seq, const uint8_t* payload, uint16_t len, uint8_t& out_resp_type) {
    if (len > 256) {
        return false;
    }
    uint8_t frame[272];
    // SOF little-endian: 0x55, 0xAA (equals uint16_t 0xAA55 LE)
    frame[0] = (uint8_t)(UART_SOF & 0xFF);
    frame[1] = (uint8_t)((UART_SOF >> 8) & 0xFF);
    frame[2] = UART_VERSION;
    frame[3] = msg_type;
    frame[4] = (uint8_t)(seq & 0xFF);
    frame[5] = (uint8_t)((seq >> 8) & 0xFF);
    frame[6] = (uint8_t)((seq >> 16) & 0xFF);
    frame[7] = (uint8_t)((seq >> 24) & 0xFF);
    frame[8] = (uint8_t)(len & 0xFF);
    frame[9] = (uint8_t)((len >> 8) & 0xFF);
    if (len > 0 && payload != nullptr) {
        memcpy(frame + 10, payload, len);
    }
    uint16_t crc = crc16_ccitt(frame + 2, 8 + len);
    frame[10 + len] = (uint8_t)(crc & 0xFF);
    frame[11 + len] = (uint8_t)((crc >> 8) & 0xFF);

    while (UnoSerial.available()) {
        UnoSerial.read();
    }
    UnoSerial.write(frame, 12 + len);
    UnoSerial.flush();

    // Await framed response header + payload + CRC within 500 ms
    unsigned long start_ms = millis();
    uint8_t rx[272];
    size_t rx_idx = 0;
    while ((millis() - start_ms) < 500) {
        while (UnoSerial.available() && rx_idx < sizeof(rx)) {
            rx[rx_idx++] = (uint8_t)UnoSerial.read();
        }
        if (rx_idx >= 12) {
            uint16_t r_sof = (uint16_t)rx[0] | ((uint16_t)rx[1] << 8);
            if (r_sof != UART_SOF) {
                return false;
            }
            uint16_t r_len = (uint16_t)rx[8] | ((uint16_t)rx[9] << 8);
            if (r_len <= 256 && rx_idx >= (size_t)(12 + r_len)) {
                uint16_t r_crc = (uint16_t)rx[10 + r_len] | ((uint16_t)rx[11 + r_len] << 8);
                uint16_t calc_crc = crc16_ccitt(rx + 2, 8 + r_len);
                if (r_crc != calc_crc) {
                    return false;
                }
                out_resp_type = rx[3];
                return true;
            }
        }
        delay(2);
    }
    return false;
}

bool verify_request_hmac(JsonDocument& doc, bool allow_estop_bypass_seq) {
    String cmd_id = server.header("X-Codex-Command-Id");
    String ts = server.header("X-Codex-Timestamp");
    String nonce = server.header("X-Codex-Nonce");
    String seq_str = server.header("X-Codex-Sequence");
    String provided_sig = server.header("X-Codex-Signature");

    if (cmd_id.isEmpty() || ts.isEmpty() || nonce.isEmpty() || seq_str.isEmpty() || provided_sig.isEmpty()) {
        return false;
    }

    uint32_t seq = (uint32_t)seq_str.toInt();
    if (!allow_estop_bypass_seq) {
        if (nonce_seen_before(nonce) || seq <= g_last_sequence) {
            return false;
        }
    }

    // Production note: canonical JSON body must match sorted-key backend serializer
    String canonical_body;
    serializeJson(doc, canonical_body);
    String signing_input = cmd_id + "." + ts + "." + nonce + "." + seq_str + "." + canonical_body;
    String expected_sig;
    if (!compute_hmac_sha256_hex(signing_input, expected_sig)) {
        return false;
    }
    if (!constant_time_hex_equal(expected_sig, provided_sig)) {
        return false;
    }

    record_nonce(nonce);
    if (seq > g_last_sequence) {
        g_last_sequence = seq;
    }
    return true;
}

void handle_health() {
    JsonDocument doc;
    doc["controller_key"] = "wifi_bridge";
    doc["firmware_version"] = FIRMWARE_VERSION;
    doc["firmware_target"] = FIRMWARE_TARGET;
    doc["uart_ok"] = g_uart_ok;
    doc["estop_latched"] = g_estop_latched;
    doc["last_sequence"] = g_last_sequence;
    doc["battery_voltage_available"] = false;
    doc["battery_voltage_v"] = nullptr;

    String out;
    serializeJson(doc, out);
    server.send(200, "application/json", out);
}

void handle_command() {
    if (!server.hasArg("plain")) {
        server.send(400, "application/json", "{\"ack_status\":\"rejected\",\"message\":\"Empty body\"}");
        return;
    }
    JsonDocument doc;
    if (deserializeJson(doc, server.arg("plain")) != DeserializationError::Ok) {
        server.send(400, "application/json", "{\"ack_status\":\"rejected\",\"message\":\"Invalid JSON\"}");
        return;
    }
    if (!verify_request_hmac(doc, false)) {
        server.send(401, "application/json", "{\"ack_status\":\"rejected\",\"message\":\"Auth or replay guard failed\"}");
        return;
    }
    if (g_estop_latched) {
        server.send(409, "application/json", "{\"ack_status\":\"estopped\",\"message\":\"Bridge E-STOP latched\"}");
        return;
    }

    // Relay compact Uno motion command ASCII inside CRC16-protected binary UART frame
    JsonObject nema = doc["motor_commands"]["nema17"];
    JsonObject byj = doc["motor_commands"]["byj"];
    int dur = doc["motor_commands"]["permitted_move_seconds"] | 10;
    int n_dir = (nema["hardware_direction"] | 1) >= 0 ? 1 : 0;
    int b_dir = (byj["hardware_direction"] | 1) >= 0 ? 1 : 0;

    char compact[96];
    int clen = snprintf(
        compact,
        sizeof(compact),
        "N:%d:%ld:%ld|B:%d:%ld:%ld|T:%d",
        n_dir,
        (long)(nema["total_steps"] | 0),
        (long)(nema["step_interval_us"] | 0),
        b_dir,
        (long)(byj["total_steps"] | 0),
        (long)(byj["step_interval_us"] | 0),
        dur
    );
    uint8_t resp_type = 0;
    uint32_t seq = (uint32_t)(doc["sequence_number"] | 0);
    bool relayed = send_uart_frame_and_wait_ack(MSG_MOTION_CMD, seq, (const uint8_t*)compact, (uint16_t)clen, resp_type);
    g_uart_ok = relayed && (resp_type == MSG_ACK);

    if (!g_uart_ok) {
        server.send(502, "application/json", "{\"ack_status\":\"fault\",\"message\":\"Arduino Uno UART relay failed\"}");
        return;
    }
    server.send(200, "application/json", "{\"ack_status\":\"accepted\",\"message\":\"Motion command relayed to Uno\"}");
}

void handle_estop() {
    g_estop_latched = true;
    uint8_t resp_type = 0;
    const char estop_msg[] = "ESTOP!";
    send_uart_frame_and_wait_ack(MSG_ESTOP, g_last_sequence + 1, (const uint8_t*)estop_msg, 6, resp_type);
    server.send(200, "application/json", "{\"ack_status\":\"estopped\",\"message\":\"E-STOP relayed to Uno and latched\"}");
}

void ensure_wifi_connected() {
    if (WiFi.status() == WL_CONNECTED) {
        return;
    }
    unsigned long now = millis();
    if (now - g_last_wifi_attempt_ms < 5000) {
        return;
    }
    g_last_wifi_attempt_ms = now;
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void setup() {
    Serial.begin(115200);
    UnoSerial.begin(UNO_UART_BAUD, SERIAL_8N1, UNO_UART_RX_PIN, UNO_UART_TX_PIN);

    const char* header_keys[] = {
        "X-Codex-Command-Id",
        "X-Codex-Timestamp",
        "X-Codex-Nonce",
        "X-Codex-Sequence",
        "X-Codex-Signature"
    };
    server.collectHeaders(header_keys, 5);
    server.on("/health", HTTP_GET, handle_health);
    server.on("/codex/command", HTTP_POST, handle_command);
    server.on("/codex/estop", HTTP_POST, handle_estop);
    server.begin();

    ensure_wifi_connected();
}

void loop() {
    ensure_wifi_connected();
    server.handleClient();

    if (millis() - g_last_uno_ping_ms >= 5000) {
        g_last_uno_ping_ms = millis();
        uint8_t resp_type = 0;
        g_uart_ok = send_uart_frame_and_wait_ack(MSG_PING, g_last_sequence, nullptr, 0, resp_type) && (resp_type == MSG_ACK);
    }
}

