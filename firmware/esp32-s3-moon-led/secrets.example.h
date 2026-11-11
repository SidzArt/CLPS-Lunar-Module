#pragma once
// Copy to secrets.h on the operator workstation (secrets.h is gitignored).

#define WIFI_SSID         "REPLACE_WITH_LAB_SSID"
#define WIFI_PASSWORD     "REPLACE_WITH_LAB_WIFI_PASSWORD"
#define CODEX_HMAC_SECRET "REPLACE_WITH_CODEX_SHARED_SECRET"

// Uncomment ONLY after physical Moon globe LED strip wiring and external 5V PSU are verified:
// #define BENCH_VERIFIED_LED_TOPOLOGY
#define LED_DATA_PIN  48
#define LED_COUNT     26

