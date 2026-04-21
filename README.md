# Flock-You GPS & Buzzer Fix Fork

Fork of [colonelpanichacks/oui-spy-unified-blue](https://github.com/colonelpanichacks/oui-spy-unified-blue) with targeted fixes for **Flock-You mode (Mode 4)** — specifically GPS lock loss during wardriving, WiFi dropout on Android, and muffled buzzer audio on boot.

For full documentation on all four firmware modes (Detector, Foxhunter, Flock-You, Sky Spy), the boot selector, flashing with `flash.py`, hardware pinout, and the broader OUI-SPY ecosystem, see the **[original project README](https://github.com/colonelpanichacks/oui-spy-unified-blue)**.

This fork changes a single file: **`src/raw/flockyou.cpp`**

---

## Why This Fork Exists

Flock-You's GPS wardriving feature relies on the browser Geolocation API to tag surveillance device detections with coordinates. During real-world wardriving sessions, two problems caused most detections to lose their GPS tags:

1. **WiFi dropout** — Android detected that the `flockyou` AP had no internet and silently switched back to mobile data, severing the GPS pipeline entirely
2. **GPS watch dying** — Chrome's `watchPosition` would stop delivering updates when the screen locked or the tab backgrounded, with no recovery mechanism

In testing, only 8 out of 47 detections (17%) were GPS-tagged. The remaining 39 lost their coordinates to these two issues.

The buzzer also threw `LEDC is not initialized` errors on boot, producing muffled audio.

These fixes improve Flock-You for all Android users and include a complete setup guide for **GrapheneOS**, where additional privacy controls make GPS configuration less obvious.

---

## What Changed

### WiFi Dropout Fix (Android Auto-Switch Prevention)

Android checks specific URLs to determine if a WiFi network has internet access. When those checks fail, Android silently switches back to mobile data — killing the GPS pipeline between the phone and the ESP32. The `flockyou` AP's captive portal DNS already redirects all domains to `192.168.4.1`, but the web server was returning HTML redirects instead of the expected responses.

The fix adds proper handlers for connectivity check URLs from all major platforms:

- **Android / GrapheneOS** — responds to `/generate_204` and `/gen_204` with HTTP 204, which is the exact response Android expects to confirm internet connectivity
- **Apple** — responds to `/hotspot-detect.html` and `/library/test/success.html` with the expected success page
- **Windows** — responds to `/ncsi.txt` and `/connecttest.txt` with the expected test strings
- **Firefox** — responds to `/success.txt` with the expected response

The catch-all handler also pattern-matches any connectivity check URLs that might arrive via unexpected paths. This prevents the "Wi-Fi has no internet access" warning and stops Android from switching away from the `flockyou` AP during wardriving sessions.

### GPS Auto-Recovery

The browser Geolocation API's `watchPosition` call would silently stop delivering updates when Chrome backgrounded the tab, the phone screen locked, or the OS throttled location services. Once GPS went stale, the ESP32 had no way to know and new detections stopped getting tagged.

- **Health monitor** — checks every 10 seconds whether GPS is still alive. If the last fix is older than 20 seconds, the watch is torn down and restarted automatically before the ESP32's 30-second stale threshold expires
- **Relaxed timing** — `maximumAge` increased from 5s to 15s, `timeout` from 15s to 30s, giving device-only GPS (no network assist) enough time to acquire satellites
- **Manual restart** — tapping the GPS card now always restarts the watch, even if GPS was previously working
- **Send failure tracking** — after 3 consecutive failed `fetch` calls to `/api/gps`, the indicator shows "SEND" (yellow) so you know the ESP32 isn't receiving coordinates
- **Smarter UI state** — the stats poll no longer overrides JavaScript-managed GPS state
- **Accuracy display** — shows accuracy in meters when >50m
- **Fixed alert text** — double-escaped `\n` now renders as actual line breaks

### Buzzer LEDC Fix

The boot crow caw sounded muffled and threw `LEDC is not initialized` errors because `tone()` was called before the ESP32's LEDC peripheral was ready.

- Explicit LEDC channel 0 initialization in `setup()` before any audio plays
- All `tone()`/`noTone()` calls replaced with direct `ledcSetup()`/`ledcWrite()` control
- Eliminates the `LEDC is not initialized` error and produces clean crow caw audio on boot

---

## GPS Indicator States

| Indicator | Color | Meaning |
|-----------|-------|---------|
| **TAP** | Red | GPS not started — tap the card to begin |
| **...** | Yellow | Acquiring GPS fix |
| **OK** | Green | GPS active, accuracy <50m |
| **~25m** | Green | GPS active, showing accuracy in meters |
| **WAIT** | Yellow | Timeout, retrying automatically |
| **LOST** | Yellow | Health monitor detected stale GPS, restarting watch |
| **SEND** | Yellow | GPS fix acquired but fetch to ESP32 failing |
| **DENIED** | Red | Browser denied location permission — see setup below |
| **N/A** | Red | Geolocation API not available in this browser |

---

## GrapheneOS Setup Guide

GPS wardriving in Flock-You requires the browser Geolocation API over HTTP. GrapheneOS has additional privacy controls that need specific configuration. Tested on a **Pixel 7a running GrapheneOS** with sandboxed Google Play Services.

### 1. Enable Location Rerouting

Chrome's location requests go through Google Play Services, but on GrapheneOS, sandboxed Play Services doesn't have privileged location access. Requests silently fail unless rerouted.

**Settings → Apps → Sandboxed Google Play → Google Play Services → Reroute location requests to OS → Enable**

### 2. Grant Chrome Location Permission

**Settings → Apps → Chrome → Permissions → Location → "Allow while using the app"**

### 3. Chrome Flag for Insecure Origins

The Geolocation API requires HTTPS, but the ESP32 serves over HTTP. Chrome has a flag to allow specific local IPs.

1. Open Chrome → navigate to `chrome://flags`
2. Search **"Insecure origins treated as secure"**
3. Enter `http://192.168.4.1` in the text field
4. Set dropdown to **Enabled**
5. Tap **Relaunch**

### 4. Chrome Site Permissions

**Chrome → three dots → Settings → Site settings → Location:**

- Set to **"Sites can ask for your location"**
- Under "How to show requests," set to **"Expand all requests"** — this prevents Chrome from silently suppressing the permission prompt for HTTP sites

### 5. Use Chrome — Not the Captive Portal

When you connect to the `flockyou` WiFi AP, Android may show a "Sign in to flockyou" captive portal popup. **This is a restricted WebView that does not support the Geolocation API.** GPS will always be denied in the captive portal.

With the WiFi dropout fix, you should no longer see the captive portal popup or the "Wi-Fi has no internet access" warning. If it does appear:

1. Tap the three dots → **"Use this network as is"**
2. Open the **Chrome app** separately
3. Navigate to `http://192.168.4.1`
4. Tap the **GPS card** in the stats bar
5. Chrome prompts for location permission → tap **Allow**
6. GPS indicator turns green

### 6. Wardriving Tips

- **Disable mobile data** as a belt-and-suspenders measure — even with the connectivity check fix, turning off mobile data guarantees Android can't switch away from the `flockyou` AP
- **Keep Chrome in the foreground** — if you switch apps, the GPS watch may slow down or stop. The health monitor will restart it, but foreground delivery is more reliable
- **Check GPS before driving** — confirm the indicator shows green "OK" before heading out. Open a second tab to `http://192.168.4.1/api/stats` and verify `gps_valid` is `true`

---

## Troubleshooting

**GPS shows "DENIED" after following all steps:**
Chrome cached a previous denial. Open an **Incognito tab** to `192.168.4.1` to test with clean permissions. To fix permanently: Chrome → Settings → Privacy and security → Clear browsing data → Advanced → check only "Site settings" → Clear data.

**GPS shows "..." and never turns green:**
Device-only GPS can take 30–60 seconds for a cold fix, especially indoors. Move near a window or outside. The firmware allows up to 30 seconds per attempt and retries automatically.

**Still getting "Wi-Fi has no internet access":**
This should be resolved by the connectivity check fix. If it persists, disable mobile data before connecting to `flockyou` — Android can't switch to what isn't available.

**`chrome://flags` setting disappeared:**
GrapheneOS Chrome updates can reset flags. Re-enter `http://192.168.4.1` and relaunch.

**Verifying GPS without a Flock camera nearby:**
Open a second Chrome tab to `http://192.168.4.1/api/stats` — if `gps_valid` is `true` and `gps_age` is under 5000, coordinates are streaming to the ESP32 and will tag any future detections.

**Serial monitor shows `LEDC is not initialized`:**
You're running the original firmware, not the patched version. Rebuild and reflash with `pio run -t upload`.

**PlatformIO flashes the wrong device:**
If `pio run -t upload` picks the wrong USB device, find the ESP32's port with `ls /dev/cu.usb*` and specify it: `pio run -t upload --upload-port /dev/cu.usbmodem1101`

---

## Building from Source

Only the Flock-You source file was modified. Build and flash with [PlatformIO](https://platformio.org/):

```bash
pip3 install platformio
cd oui-spy-unified-blue
pio run
pio run -t upload
```

Monitor serial output (optional):

```bash
pio device monitor
```

A clean boot should show no LEDC errors:

```
========================================
  FLOCK-YOU Surveillance Detector
  Buzzer: ON
  GPS: auto-detect (L76K on D6/D7)
========================================
[FLOCK-YOU] BLE scanning ACTIVE
[FLOCK-YOU] *caw caw caw*
[FLOCK-YOU] AP: flockyou / flockyou123
[FLOCK-YOU] Ready - no WiFi connection needed, BLE + AP only
```

---

## Credits

- **[colonelpanichacks](https://github.com/colonelpanichacks)** — OUI-SPY Unified firmware and the Flock-You detection engine
- **[wgreenberg](https://github.com/wgreenberg)** — Flock Safety BLE manufacturer ID research ([flock-you](https://github.com/wgreenberg/flock-you))
