// CODEX Sub-Controller 2: Arduino Uno Motion Controller
// Role: Executes bounded trapezoidal step motions for NEMA 17 + BYJ motors upon receiving
// CRC16-CCITT verified binary UART frames from the ESP32 Wi-Fi bridge.
//
// CRITICAL SAFETY WARNINGS:
// 1. Uno uses 5 V logic. Connect through a verified 5V <-> 3.3V level shifter to ESP32 UART.
// 2. A 5-wire unipolar BYJ motor CANNOT be plugged directly into an A4988/DRV8825 CNC Shield
//    without documented ULN2003 driver wiring or verified bipolar conversion.
// 3. Copy config.example.h -> config.h and enable BENCH_VERIFIED_BYJ_DRIVER only after bench check.

#include <AccelStepper.h>
#include <avr/wdt.h>
#include "config.h"

#if !defined(BYJ_DRIVER_ULN2003_4WIRE) && !defined(BYJ_DRIVER_BIPOLAR_STEP_DIR)
#error "SAFETY BLOCK: Verify physical BYJ driver (ULN2003 4-wire vs bipolar STEP/DIR) in config.h before flashing Uno."
#endif

static const uint16_t UART_SOF         = 0xAA55;
static const uint8_t  UART_VERSION     = 0x01;
static const uint8_t  MSG_PING         = 0x01;
static const uint8_t  MSG_MOTION_CMD   = 0x02;
static const uint8_t  MSG_ESTOP        = 0x03;
static const uint8_t  MSG_ACK          = 0x81;
static const uint8_t  MSG_NACK         = 0x82;
static const uint8_t  MSG_FAULT        = 0x83;

// Independent NEMA 17 driver (CNC Shield STEP/DIR interface)
AccelStepper nemaStepper(AccelStepper::DRIVER, NEMA_STEP_PIN, NEMA_DIR_PIN);

#if defined(BYJ_DRIVER_BIPOLAR_STEP_DIR)
AccelStepper byjStepper(AccelStepper::DRIVER, BYJ_STEP_PIN, BYJ_DIR_PIN);
#elif defined(BYJ_DRIVER_ULN2003_4WIRE)
AccelStepper byjStepper(AccelStepper::HALF4WIRE, BYJ_IN1_PIN, BYJ_IN3_PIN, BYJ_IN2_PIN, BYJ_IN4_PIN);
#endif

static volatile bool g_estopLatched = false;
static uint32_t g_lastSeq = 0;

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

void disableAllMotorPowerOutputs() {
    digitalWrite(STEPPER_ENABLE_PIN, HIGH); // Active-LOW disable on CNC Shield
    nemaStepper.stop();
    byjStepper.stop();
    nemaStepper.disableOutputs();
    byjStepper.disableOutputs();
}

void triggerEmergencyStop() {
    g_estopLatched = true;
    disableAllMotorPowerOutputs();
}

void isrPhysicalEstop() {
    g_estopLatched = true;
}

void sendUartResponse(uint8_t msgType, uint32_t seq, const char* text) {
    uint16_t len = (uint16_t)min((size_t)128, strlen(text));
    uint8_t frame[140];
    frame[0] = (uint8_t)(UART_SOF & 0xFF);
    frame[1] = (uint8_t)((UART_SOF >> 8) & 0xFF);
    frame[2] = UART_VERSION;
    frame[3] = msgType;
    frame[4] = (uint8_t)(seq & 0xFF);
    frame[5] = (uint8_t)((seq >> 8) & 0xFF);
    frame[6] = (uint8_t)((seq >> 16) & 0xFF);
    frame[7] = (uint8_t)((seq >> 24) & 0xFF);
    frame[8] = (uint8_t)(len & 0xFF);
    frame[9] = (uint8_t)((len >> 8) & 0xFF);
    memcpy(frame + 10, text, len);
    uint16_t crc = crc16_ccitt(frame + 2, 8 + len);
    frame[10 + len] = (uint8_t)(crc & 0xFF);
    frame[11 + len] = (uint8_t)((crc >> 8) & 0xFF);
    Serial.write(frame, 12 + len);
    Serial.flush();
}

bool limitsTriggered() {
    return (digitalRead(LIMIT_SWITCH_PIN) == LOW);
}

bool parseCompactMotionPayload(const char* buf, long& nDir, long& nSteps, long& nUs, long& bDir, long& bSteps, long& bUs, long& dur) {
    return sscanf(buf, "N:%ld:%ld:%ld|B:%ld:%ld:%ld|T:%ld", &nDir, &nSteps, &nUs, &bDir, &bSteps, &bUs, &dur) == 7;
}

void processCompletedUartFrame(uint8_t msgType, uint32_t seq, const uint8_t* payload, uint16_t len) {
    if (msgType == MSG_ESTOP) {
        triggerEmergencyStop();
        sendUartResponse(MSG_ACK, seq, "ESTOP_OK");
        return;
    }

    if (g_estopLatched || digitalRead(ESTOP_PIN) == LOW) {
        triggerEmergencyStop();
        sendUartResponse(MSG_FAULT, seq, "ESTOP_LATCHED");
        return;
    }

    if (msgType == MSG_PING) {
        sendUartResponse(MSG_ACK, seq, "PONG");
        return;
    }

    if (msgType == MSG_MOTION_CMD) {
        if (seq <= g_lastSeq) {
            sendUartResponse(MSG_NACK, seq, "REPLAY_SEQ");
            return;
        }
        char text[129];
        uint16_t copyLen = min((uint16_t)128, len);
        memcpy(text, payload, copyLen);
        text[copyLen] = '\0';

        long nDir = 1, nSteps = 0, nUs = 0, bDir = 1, bSteps = 0, bUs = 0, dur = 0;
        if (!parseCompactMotionPayload(text, nDir, nSteps, nUs, bDir, bSteps, bUs, dur)) {
            sendUartResponse(MSG_NACK, seq, "BAD_PAYLOAD");
            return;
        }
        if (nSteps < 0 || bSteps < 0 || nSteps > MAX_ALLOWED_COMMAND_STEPS || bSteps > MAX_ALLOWED_COMMAND_STEPS) {
            sendUartResponse(MSG_NACK, seq, "STEP_LIMIT_EXCEEDED");
            return;
        }
        if (limitsTriggered()) {
            disableAllMotorPowerOutputs();
            sendUartResponse(MSG_FAULT, seq, "HARD_LIMIT_ACTIVE");
            return;
        }

        g_lastSeq = seq;
        float nRate = (nUs > 0) ? min((float)NEMA_MAX_STEP_RATE, 1000000.0f / (float)nUs) : (float)NEMA_MAX_STEP_RATE;
        float bRate = (bUs > 0) ? min((float)BYJ_MAX_STEP_RATE, 1000000.0f / (float)bUs) : (float)BYJ_MAX_STEP_RATE;

        digitalWrite(STEPPER_ENABLE_PIN, LOW); // Active-LOW enable CNC Shield
        nemaStepper.setMaxSpeed(nRate);
        nemaStepper.setAcceleration((float)NEMA_ACCELERATION);
        byjStepper.setMaxSpeed(bRate);
        byjStepper.setAcceleration((float)BYJ_ACCELERATION);

        nemaStepper.move((nDir ? 1L : -1L) * nSteps);
        byjStepper.move((bDir ? 1L : -1L) * bSteps);
        sendUartResponse(MSG_ACK, seq, "MOTION_STARTED");
        return;
    }

    sendUartResponse(MSG_NACK, seq, "UNKNOWN_MSG");
}

void pollUartFrames() {
    static uint8_t rxBuf[272];
    static size_t rxLen = 0;

    while (Serial.available()) {
        uint8_t b = (uint8_t)Serial.read();
        if (rxLen == 0 && b != (uint8_t)(UART_SOF & 0xFF)) {
            continue;
        }
        if (rxLen == 1 && b != (uint8_t)((UART_SOF >> 8) & 0xFF)) {
            rxLen = 0;
            continue;
        }
        if (rxLen < sizeof(rxBuf)) {
            rxBuf[rxLen++] = b;
        } else {
            rxLen = 0;
            continue;
        }
        if (rxLen >= 10) {
            uint16_t payloadLen = (uint16_t)rxBuf[8] | ((uint16_t)rxBuf[9] << 8);
            if (payloadLen > 256) {
                rxLen = 0;
                continue;
            }
            if (rxLen == (size_t)(12 + payloadLen)) {
                uint8_t version = rxBuf[2];
                uint8_t msgType = rxBuf[3];
                uint32_t seq = (uint32_t)rxBuf[4]
                    | ((uint32_t)rxBuf[5] << 8)
                    | ((uint32_t)rxBuf[6] << 16)
                    | ((uint32_t)rxBuf[7] << 24);
                uint16_t rxCrc = (uint16_t)rxBuf[10 + payloadLen] | ((uint16_t)rxBuf[11 + payloadLen] << 8);
                uint16_t calcCrc = crc16_ccitt(rxBuf + 2, 8 + payloadLen);
                rxLen = 0;

                if (version != UART_VERSION || rxCrc != calcCrc) {
                    sendUartResponse(MSG_NACK, seq, "CRC_OR_VER_ERR");
                } else {
                    processCompletedUartFrame(msgType, seq, rxBuf + 10, payloadLen);
                }
            }
        }
    }
}

void setup() {
    wdt_disable();
    Serial.begin(115200);

    pinMode(STEPPER_ENABLE_PIN, OUTPUT);
    digitalWrite(STEPPER_ENABLE_PIN, HIGH); // Start disabled safely
    pinMode(ESTOP_PIN, INPUT_PULLUP);
    pinMode(LIMIT_SWITCH_PIN, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(ESTOP_PIN), isrPhysicalEstop, FALLING);

    wdt_enable(WDTO_2S);
}

void loop() {
    wdt_reset();
    if (g_estopLatched || digitalRead(ESTOP_PIN) == LOW) {
        triggerEmergencyStop();
    } else if (limitsTriggered() && (nemaStepper.distanceToGo() != 0 || byjStepper.distanceToGo() != 0)) {
        disableAllMotorPowerOutputs();
    } else {
        nemaStepper.run();
        byjStepper.run();
    }
    pollUartFrames();
}

