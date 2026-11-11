# ESP32-S3 Moon LED Controller (`moon_led_s3`)

- **Role:** Drives the 13-region physical lunar globe LED indicators over HMAC-SHA256 authenticated LAN HTTP.
- **Verification Status:** `UNVERIFIED ON BENCH` (`BENCH_VERIFIED_LED_TOPOLOGY` compile guard intentionally active until physical LED pin/pixel layout is confirmed).

## Safety & Telemetry Rules
- Reported telemetry sets `battery_voltage_available: false` and `battery_voltage_v: null` because no physical battery voltage ADC circuit is connected/verified.
- Never power high-brightness LED strips solely through the ESP32-S3 USB 3.3 V regulator.
- Build after creating verified `secrets.h`:
  ```bash
  cp secrets.example.h secrets.h
  arduino-cli compile --profile codex_moon_led_s3
  ```

