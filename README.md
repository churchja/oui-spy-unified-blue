# Flock-You: oui-spy-flock-you-enhanced

INTERACTIVE https://flockyou.netlify.app/

🛰️ FLOCK-YOU: Open-source BLE wardriving for privacy auditing.
Turn your ESP32-S3 into a "digital bird dog" that identifies, estimates distance, and logs the coordinates of Flock cameras and Raven sensors.

# FLOCK-YOU
> **The digital bird dog for your pocket.** Detect, geotag, and map hidden surveillance hardware in real-time.
> [**View the Dashboard & Setup Guide →**](https://flockyou.netlify.app/)


Fork of [colonelpanichacks/oui-spy-unified-blue](https://github.com/colonelpanichacks/oui-spy-unified-blue) with targeted fixes for **Flock-You mode (Mode 4)** — GPS lock loss during wardriving, WiFi dropout on Android, muffled buzzer audio, and added **RSSI distance estimation** with a configurable path-loss model. The Flock Safety BLE OUI detection list is also kept synced with the latest [nite-oui-collection](https://github.com/nitekry/nite-oui-collection) research.

For full documentation on all four firmware modes (Detector, Foxhunter, Flock-You, Sky Spy), the boot selector, flashing with `flash.py`, hardware pinout, and the broader OUI-SPY ecosystem, see the **[original project README](https://github.com/colonelpanichacks/oui-spy-unified-blue)**.

This fork's source changes are limited to a single file (**`src/raw/flockyou.cpp`**), plus two helper scripts at the repo root for managing OUI-list syncs and deployments: `patch_ouis.py` and `update_and_flash.sh`.

---

## What Changed

### Flock Safety OUI List Sync (current: 42 prefixes)

The BLE MAC-prefix detection list is synced with the latest research from @NitekryDPaul's [nite-oui-collection](https://github.com/nitekry/nite-oui-collection) plus Michael / DeFlockJoplin's drive-test additions. The list expanded from the original 20 prefixes to **42 active OUIs**, with three known-false-positive prefixes explicitly demoted.

| Group | Count | Source |
|---|---|---|
| Original promiscuous-mode set | 29 | @NitekryDPaul |
| April 2026 additions | 12 | @NitekryDPaul (nite-oui-collection) |
| Joplin drive-test addition (`82:6b:f2`) | 1 | Michael / DeFlockJoplin |
| **Net active prefixes** | **42** | |

**Demoted prefixes (not in the active list):**

| Prefix | Reason |
|---|---|
| `f8:a2:d6` | Hit on a Sony Media Player — false positive |
| `cc:cc:cc` | No observed Flock hits — likely placeholder/test value |
| `00:0c:e7` | Possible MediaTek false positive |

**Known conflicts to expect:** `08:3a:88` has a BLE Ring doorbell collision and will produce occasional false positives in BLE-only mode. Cross-check with WiFi-side detection if available.

**Full active OUI list** (case-insensitive substring match on the first 8 chars of each BLE MAC):

```
70:c9:4e  3c:91:80  d8:f3:bc  80:30:49  b8:35:32
14:5a:fc  74:4c:a1  08:3a:88  9c:2f:9d  c0:35:32
94:08:53  e4:aa:ea  f4:6a:dd  24:b2:b9  00:f4:8d
d0:39:57  e8:d0:fc  e0:4f:43  b8:1e:a4  70:08:94
58:8e:81  ec:1b:bd  3c:71:bf  58:00:e3  90:35:ea
5c:93:a2  64:6e:69  48:27:ea  a4:cf:12  04:0d:84
f0:82:c0  1c:34:f1  38:5b:44  94:34:69  b4:e3:f9
b4:1e:52  14:b5:cd  94:2a:6f  f4:e2:c6  d4:11:d6
e0:0a:f6  82:6b:f2
```

**Tooling for future syncs:**

- `patch_ouis.py` — surgical Python script that locates the `mac_prefixes[]` array in `src/raw/flockyou.cpp`, writes a timestamped backup, and atomically replaces the array. Refuses to operate on a modified or already-patched file. Defaults to dry-run; pass `--apply` to commit.
- `update_and_flash.sh` — interactive orchestrator that wraps the full pipeline: pull from origin → preview patch → apply patch → PlatformIO build → commit + push → port-detect and flash → optional serial monitor. Confirmation gate at every destructive stage. Skip flags: `--skip-git`, `--skip-patch`, `--skip-build`, `--skip-flash`.

### RSSI Distance Estimation

Every detection now shows an estimated distance in meters based on the received signal strength, using the log-distance path-loss model:

```
distance = 10 ^ ((txPower - RSSI) / (10 × n))
```

Where `txPower` is the reference power at 1 meter (-59 dBm default for BLE) and `n` is the path-loss exponent that models signal attenuation in different environments.

**Dashboard changes:**

- Each detection card shows `~Xm` in yellow next to the RSSI value
- The **Tools** tab has four environment preset buttons and a manual slider
- Distance is included in JSON, CSV, and KML exports
- Settings are saved to NVS and persist across reboots

**Presets:**

| Preset | Exponent (n) | Use case |
|--------|-------------|----------|
| **HIGHWAY** | 2.2 | Interstate/highway wardriving at 50-85 mph. Cameras are pole-mounted with clear line of sight. Minimal obstructions. |
| **SUBURBAN** | 2.5 | Mixed residential/commercial roads. Some obstructions from buildings and vegetation. Good general-purpose default. |
| **URBAN** | 3.0 | City streets with buildings, parked cars, and infrastructure creating multipath reflections. |
| **DENSE** | 3.5 | Dense urban or areas with significant obstructions between you and the camera. |

The slider allows manual tuning from 1.6 (pure open air) to 4.5 (heavy indoor attenuation) in 0.1 steps. If the default distance numbers feel consistently off, adjust the exponent until they match your observed reality — lower for open areas, higher for obstructed ones.

**API:**

- `GET /api/settings` — returns current path-loss exponent and TX power as JSON
- `GET /api/settings?pl_n=2.2` — sets the exponent and saves to NVS

### WiFi Dropout Fix (Android Auto-Switch Prevention)

Android detects that the `flockyou` AP has no internet and silently switches back to mobile data, severing the GPS pipeline. The fix adds proper handlers for connectivity check URLs from Android, GrapheneOS, Apple, Windows, and Firefox. Returning the expected responses tells the OS "this network has internet" and prevents the switch.

This eliminates the "Wi-Fi has no internet access" warning and the captive portal popup on most devices.

### GPS Auto-Recovery

The browser Geolocation API's `watchPosition` would silently stop delivering updates when Chrome backgrounded the tab, the phone screen locked, or the OS throttled location services.

- **Health monitor** — checks every 10 seconds, auto-restarts the watch if GPS goes stale (20-second threshold)
- **Relaxed timing** — `maximumAge` 15s, `timeout` 30s for device-only GPS (GrapheneOS)
- **Manual restart** — tapping the GPS card always restarts, even after a previous success
- **Send failure tracking** — shows "SEND" (yellow) after 3 consecutive failed fetch calls
- **Accuracy display** — shows meters when >50m

### Buzzer LEDC Fix

- Explicit LEDC channel 0 initialization in `setup()` before boot audio
- All `tone()`/`noTone()` replaced with direct `ledcSetup()`/`ledcWrite()` control
- Eliminates the `LEDC is not initialized` error

### Security Audit Fixes

- **XSS prevention** — BLE device names are HTML-escaped before rendering in the dashboard
- **Expanded name sanitization** — strips `<`, `>`, `&`, and control characters in addition to `"` and `\`
- **Null terminator safety** — Raven UUID copy guaranteed null-terminated
- **Division by zero guard** — `fyCaw()` returns early if duration < 8ms
- **Deprecated API fix** — ArduinoJson `containsKey` replaced with modern `is<T>()` API

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

- **Set the path-loss exponent before driving** — tap Tools, then HIGHWAY for interstate or URBAN for city streets
- **Disable mobile data** as a belt-and-suspenders measure — even with the connectivity check fix, this guarantees Android stays on the `flockyou` AP
- **Keep Chrome in the foreground** — the GPS health monitor auto-restarts on background, but foreground is more reliable
- **Check GPS before driving** — confirm green "OK" on the GPS card before heading out

---

## Troubleshooting

**GPS shows "DENIED" after following all steps:**
Chrome cached a previous denial. Open an **Incognito tab** to `192.168.4.1` to test with clean permissions. To fix permanently: Chrome → Settings → Privacy and security → Clear browsing data → Advanced → check only "Site settings" → Clear data.

**GPS shows "..." and never turns green:**
Device-only GPS can take 30–60 seconds for a cold fix, especially indoors. Move near a window or outside. The firmware allows up to 30 seconds per attempt and retries automatically.

**Still getting "Wi-Fi has no internet access":**
This should be resolved by the connectivity check fix. If it persists, disable mobile data before connecting to `flockyou`.

**Distance estimates seem wrong:**
Adjust the path-loss exponent in Tools. If distances are consistently too short, increase n. If too long, decrease n. The model is an approximation — BLE signal strength varies with antenna orientation, obstructions, and multipath reflections.

**`chrome://flags` setting disappeared:**
GrapheneOS Chrome updates can reset flags. Re-enter `http://192.168.4.1` and relaunch.

**Verifying GPS without a Flock camera nearby:**
Open a second Chrome tab to `http://192.168.4.1/api/stats` — if `gps_valid` is `true` and `gps_age` is under 5000, GPS is streaming.

**Serial monitor shows `LEDC is not initialized`:**
You're running the original firmware. Rebuild and reflash with `pio run -t upload`.

**PlatformIO flashes the wrong device:**
Find the ESP32's port with `ls /dev/cu.usb*` and specify it: `pio run -t upload --upload-port /dev/cu.usbmodem1101`

**Ring doorbell appearing as a Flock hit:**
Expected — the `08:3a:88` OUI is on both. Cross-check the detection's BLE manufacturer ID (Flock advertises XUNTONG `0x09C8`); Ring devices won't.

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

A clean boot shows:

```
========================================
  FLOCK-YOU Surveillance Detector
  Buzzer: ON
  Path-loss n: 2.5
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
- **[NitekryDPaul](https://github.com/nitekry)** — Flock Safety OUI research and the [nite-oui-collection](https://github.com/nitekry/nite-oui-collection) dataset that powers the 42-prefix active list
- **[DeFlockJoplin](https://github.com/DeflockJoplin)** — Joplin drive-test field validation, the `82:6b:f2` OUI contribution, and the wildcard-probe-request signature research
- **[wgreenberg](https://github.com/wgreenberg)** — Flock Safety BLE manufacturer ID research ([flock-you](https://github.com/wgreenberg/flock-you))
