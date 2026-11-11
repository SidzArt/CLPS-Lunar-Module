// CODEX Sub-Controller 3: ESP32-S3 Moon LED Controller
// Role: Receives HMAC-SHA256 authenticated Protocol v1 commands over Wi-Fi and maps
// 1..13 Moon region pixel selections onto physical lunar model LEDs.
//
// SAFETY & VERIFICATION:
//   Exact LED pixel count, GPIO data pin, strip voltage level shifting (3.3V -> 5V if WS2812B),
//   and 13-region physical wiring MUST be confirmed before enabling BENCH_VERIFIED_LED_TOPOLOGY.

#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoJson.h>
#include <Adafruit_NeoPixel.h>
#include <mbedtls/md.h>
#include "secrets.h"

#ifndef BENCH_VERIFIED_LED_TOPOLOGY
#error "SAFETY BLOCK: Verify LED_DATA_PIN, LED_COUNT, external 5V PSU, and 13-region layout in secrets.h before flashing ESP32-S3."
#endif

#define FIRMWARE_VERSION "codex-moon-led-s3-v1.0.0-unverified"
#define FIRMWARE_TARGET  "esp32s3"

WebServer server(80);
Adafruit_NeoPixel strip(LED_COUNT, LED_DATA_PIN, NEO_GRB + NEO_KHZ800);

static bool g_estop_latched = false;
static uint32_t g_last_sequence = 0;
static const size_t NONCE_RING_SIZE = 32;
static String g_seen_nonces[NONCE_RING_SIZE];
static size_t g_nonce_write_idx = 0;
static unsigned long g_last_wifi_attempt_ms = 0;

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
        for (size_t i = 0; i < NONCE_RING_SIZE; ++i) {
            if (g_seen_nonces[i] == nonce) {
                return false;
            }
        }
        if (seq <= g_last_sequence) {
            return false;
        }
    }

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

    g_seen_nonces[g_nonce_write_idx] = nonce;
    g_nonce_write_idx = (g_nonce_write_idx + 1) % NONCE_RING_SIZE;
    if (seq > g_last_sequence) {
        g_last_sequence = seq;
    }
    return true;
}

void clear_all_leds() {
    strip.clear();
    strip.show();
}

void handle_health() {
    JsonDocument doc;
    doc["controller_key"] = "moon_led_s3";
    doc["firmware_version"] = FIRMWARE_VERSION;
    doc["firmware_target"] = FIRMWARE_TARGET;
    doc["led_controller_ok"] = true;
    doc["estop_latched"] = g_estop_latched;
    doc["last_sequence"] = g_last_sequence;
    // Never fabricate battery telemetry without verified ADC divider hardware
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
        clear_all_leds();
        server.send(409, "application/json", "{\"ack_status\":\"estopped\",\"message\":\"Moon LED E-STOP latched\"}");
        return;
    }

    int region_index = doc["moon_led"]["region_index"] | 0;
    if (region_index < 1 || region_index > 13) {
        server.send(400, "application/json", "{\"ack_status\":\"rejected\",\"message\":\"Invalid region_index\"}");
        return;
    }

    JsonArray pixels = doc["moon_led"]["pixel_indices"];
    if (pixels.isNull() || pixels.size() == 0) {
        server.send(400, "application/json", "{\"ack_status\":\"rejected\",\"message\":\"Missing pixel_indices\"}");
        return;
    }

    strip.clear();
    for (JsonVariant v : pixels) {
        int px = v.as<int>();
        if (px >= 0 && px < LED_COUNT) {
            strip.setPixelColor((uint16_t)px, strip.Color(245, 194, 66)); // Lunar gold accent
        }
    }
    strip.show();
    server.send(200, "application/json", "{\"ack_status\":\"completed\",\"message\":\"Moon LED region illuminated\"}");
}

void handle_estop() {
    g_estop_latched = true;
    clear_all_leds();
    server.send(200, "application/json", "{\"ack_status\":\"estopped\",\"message\":\"Moon LEDs blanked and E-STOP latched\"}");
}

void ensure_wifi_connected() {
    if (WiFi.status() == WL_CONNECTED) {
        return;
    }
    if (millis() - g_last_wifi_attempt_ms < 5000) {
        return;
    }
    g_last_wifi_attempt_ms = millis();
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void setup() {
    Serial.begin(115200);
    strip.begin();
    clear_all_leds();

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
}

