/*
 * mode_utils - shared radio-reset preamble + AP-state diagnostics.
 *
 * Every mode's exported <mode>_setup() calls ouispy_mode_preamble() first.
 * That guarantees:
 *   1. WiFi.persistent(false) — the Arduino wrapper will NOT write SSID back
 *      to ESP32-native NVS the next time softAP() is called. Without this,
 *      every softAP call pollutes the NVS auto-restore slot with the mode's
 *      SSID, which then reappears on subsequent boots (this is what caused
 *      the "flockyou AP after picking BLE Sniff" symptom the user reported).
 *   2. WiFi.mode(WIFI_OFF) + esp_wifi_restore() — nuke any AP or STA config
 *      that main.cpp's boot-time wipe missed, or that a prior mode left up.
 *
 * After each mode's setup() returns, main.cpp calls ouispy_log_ap_state()
 * so the serial log shows the REAL SSID / IP / MAC that came up — not just
 * whatever the mode intended.
 */

#include <Arduino.h>
#include <WiFi.h>
#include <esp_wifi.h>

extern "C" {
    esp_err_t esp_wifi_restore(void);
}

void ouispy_mode_preamble(const char* modeName) {
    Serial.printf("[MODE PREAMBLE] '%s': WiFi.persistent(false), WIFI_OFF, esp_wifi_restore()\n",
                  modeName ? modeName : "?");
    Serial.flush();
    WiFi.persistent(false);
    WiFi.softAPdisconnect(true);
    WiFi.disconnect(true, true);
    WiFi.mode(WIFI_OFF);
    delay(150);
    esp_wifi_restore();
    delay(80);
    Serial.printf("[MODE PREAMBLE] '%s': radio state reset\n", modeName ? modeName : "?");
    Serial.flush();
}

// Log the ACTUAL AP state after a mode has finished setup. Called from
// main.cpp so we can see what really came up, not what the mode intended.
// Returns true if an AP is running with a non-empty SSID.
bool ouispy_log_ap_state(const char* modeName, bool expectAP) {
    String ssid = WiFi.softAPSSID();
    IPAddress ip = WiFi.softAPIP();
    String mac = WiFi.softAPmacAddress();
    uint8_t stations = WiFi.softAPgetStationNum();

    if (ssid.length() > 0) {
        Serial.printf("[%s] AP LIVE  ssid='%s'  ip=%s  mac=%s  stations=%u\n",
                      modeName ? modeName : "?", ssid.c_str(),
                      ip.toString().c_str(), mac.c_str(), (unsigned)stations);
    } else {
        Serial.printf("[%s] AP DOWN  (no active softAP)\n", modeName ? modeName : "?");
    }
    Serial.flush();

    if (expectAP && ssid.length() == 0) {
        Serial.printf("[%s] FATAL: expected softAP but none is up. Starting recovery AP.\n",
                      modeName ? modeName : "?");
        Serial.flush();
        WiFi.persistent(false);
        WiFi.mode(WIFI_AP);
        delay(120);
        bool ok = WiFi.softAP("oui-spy-recovery");
        Serial.printf("[%s] recovery softAP('oui-spy-recovery') = %s  ip=%s  mac=%s\n",
                      modeName ? modeName : "?", ok ? "OK" : "FAIL",
                      WiFi.softAPIP().toString().c_str(),
                      WiFi.softAPmacAddress().c_str());
        Serial.flush();
        return false;
    }
    return ssid.length() > 0;
}
