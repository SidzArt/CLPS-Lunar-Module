# ESP32 Wi-Fi Bridge (`wifi_bridge`)

- **Role:** Receives HMAC-SHA256 authenticated Protocol v1 commands from the FastAPI backend and relays CRC16-CCITT binary UART frames (`0xAA55`, `VER=0x01`) to the Arduino Uno motion controller.
- **Verification Status:** `UNVERIFIED ON BENCH` (pending physical board assembly, level-shifter verification, and `arduino-cli` compilation on lab host).

## Critical Electrical Requirement
- ESP32 UART pins operate at **3.3 V**; Arduino Uno operates at **5 V**.
- Insert a verified **5 V ↔ 3.3 V UART level shifter** on `UNO_UART_RX_PIN` (GPIO16) / `UNO_UART_TX_PIN` (GPIO17) with shared signal ground before powering both boards.

## Provisioning & Build
```bash
cp secrets.example.h secrets.h
arduino-cli compile --profile codex_bridge
arduino-cli upload --profile codex_bridge -p /dev/cu.usbserial-0001
```

