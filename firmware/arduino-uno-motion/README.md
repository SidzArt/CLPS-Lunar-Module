# Arduino Uno Motion Controller (`motion_uno`)

- **Role:** Runs NEMA 17 + BYJ trapezoidal step profiles via `AccelStepper` upon CRC16-CCITT binary UART commands from ESP32 bridge, with AVR watchdog (`avr/wdt.h`), hard limit switch polling, and interrupt-driven E-STOP.
- **Verification Status:** `UNVERIFIED ON BENCH` (`config.h` intentionally forces compile-time `#error` until `BYJ_DRIVER_ULN2003_4WIRE` vs `BYJ_DRIVER_BIPOLAR_STEP_DIR` is confirmed on physical hardware).

## Safety & Wiring Checklist
1. Confirm exact BYJ motor model & driver (NEVER plug a 5-wire unipolar 28BYJ-48 directly onto an A4988/DRV8825 CNC Shield socket).
2. Insert bidirectional **5 V ↔ 3.3 V UART level shifter** between Uno RX/TX and ESP32 UART2.
3. Verify separate regulated motor power supply, Vref driver current limits, common ground, and physical NC E-STOP wired to `ESTOP_PIN` (`D3`).
4. Compile after copying verified `config.example.h` -> `config.h`:
   ```bash
   arduino-cli compile --profile codex_motion_uno
   ```

