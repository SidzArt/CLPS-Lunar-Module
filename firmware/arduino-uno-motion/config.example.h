#pragma once
// Copy to config.h and enable ONLY the driver option verified on your bench hardware.

// UNCOMMENT EXACTLY ONE after bench inspection:
// #define BYJ_DRIVER_ULN2003_4WIRE
// #define BYJ_DRIVER_BIPOLAR_STEP_DIR

// CNC Shield v3 default Uno pin assignments (verify shield silkscreen!)
#define NEMA_STEP_PIN       2
#define NEMA_DIR_PIN        5
#define STEPPER_ENABLE_PIN  8

// Physical safety pins
#define ESTOP_PIN           3   // Hardware INT1 active-LOW normally-closed E-stop button
#define LIMIT_SWITCH_PIN    9   // Hard mechanical travel limit interlock (active-LOW)

// BYJ pin assignments (for chosen verified driver)
#define BYJ_STEP_PIN        4
#define BYJ_DIR_PIN         7
#define BYJ_IN1_PIN         10
#define BYJ_IN2_PIN         11
#define BYJ_IN3_PIN         12
#define BYJ_IN4_PIN         13

// Conservative step limits (align with DB motor_calibration_profiles)
#define NEMA_MAX_STEP_RATE         2000
#define NEMA_ACCELERATION          500
#define BYJ_MAX_STEP_RATE          800
#define BYJ_ACCELERATION           300
#define MAX_ALLOWED_COMMAND_STEPS  200000L

