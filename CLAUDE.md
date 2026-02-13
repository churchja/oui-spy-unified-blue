# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Hard Rules — DO NOT VIOLATE

### Never modify global PlatformIO packages
- **NEVER** modify, rename, delete, or overwrite files in `~/.platformio/packages/`. This is a shared global directory that affects ALL PlatformIO projects on the system.
- If a build needs a different framework version, use `platform_packages` overrides in `platformio.ini` — never manually swap framework directories.
- If two targets need incompatible frameworks, use **separate project directories**, not the same shared package directory.

### Never make system-wide changes for project-local problems
- Scope all changes to the project directory. If a workaround requires touching files outside the project, stop and find a project-local solution instead.
- Before modifying anything in `~/.platformio/`, `~/.config/`, or any global path, ask the user for explicit permission and explain the blast radius.

### Always clean build after framework changes
- If the PlatformIO framework package was modified or reinstalled for any reason, always run `pio run -t clean` before building. Stale bootloader binaries from a wrong framework cause unrecoverable boot loops (`ets_loader.c 78`).

### Verify hardware claims with manufacturer documentation
- Do not assume GPIO mappings, onboard peripherals (LEDs, NeoPixels), or antenna configurations based on similar boards. Always verify against the manufacturer's official documentation (e.g., Seeed Wiki) before writing code that depends on specific hardware features.

## Project Overview

OUI-SPY Unified Blue is a multi-mode firmware for the **Seeed Studio XIAO ESP32-S3**. It provides a unified bootloader with 4 selectable firmware modes for surveillance device detection and drone monitoring, all running on a single device with a WiFi-based boot selector.

**Modes:** Detector (BLE scanner with OUI/MAC watchlists), Foxhunter (RSSI proximity tracker), Flock-You (Flock Safety / Raven surveillance device detector), Sky Spy (FAA Remote ID / Open Drone ID drone detector).

## Build & Flash Commands

```bash
pio run                     # Build firmware
pio run -t upload           # Build and flash via USB
pio run -t clean            # Clean build artifacts
pio device monitor          # Serial monitor (115200 baud)
python flash.py             # Flash pre-compiled bin from firmware/ folder
python flash.py --erase     # Full erase before flashing
```

Build output: `.pio/build/seeed_xiao_esp32s3/firmware.bin`

There are no automated tests. Validation is done by flashing to hardware and testing each mode.

## Architecture

### Unified Bootloader (`src/main.cpp`)

The entry point. On boot it checks the BOOT button (GPIO 0), reads the stored mode from NVS, and dispatches to the selected mode's `setup()`/`loop()` functions. Mode 0 (Selector) serves a WiFi AP with a web UI for choosing modes and configuring AP credentials/buzzer. Holding BOOT for 2s from any mode returns to the selector.

### Mode Wrapper Pattern

Each mode's original standalone firmware lives unmodified in `src/raw/`. Wrapper files (`src/mode_*.cpp`) encapsulate them using this pattern to avoid linker symbol collisions:

```cpp
#define setup modename_ns_setup
#define loop  modename_ns_loop
namespace {
    #include "raw/modename.cpp"    // Original firmware included verbatim
}
#undef setup
#undef loop
void modename_setup() { modename_ns_setup(); }
void modename_loop()  { modename_ns_loop(); }
```

The `#define` renames Arduino's `setup`/`loop`, the anonymous namespace gives all symbols internal linkage, and the exported `modename_setup()`/`modename_loop()` functions are declared in `src/modes.h` and called from `main.cpp`.

**Critical:** Files in `src/raw/` are excluded from direct compilation via `src_filter = +<*> -<raw/>` in `platformio.ini`. They are only compiled through `#include` in the wrapper files. Do not add them to the build filter.

### Mode-to-File Mapping

| Mode | ID | Wrapper | Implementation | AP |
|------|----|---------|----------------|----|
| Selector | 0 | `main.cpp` | `main.cpp` | `oui-spy` / `ouispy123` |
| Detector | 1 | `mode_detector.cpp` | `raw/detector.cpp` | `snoopuntothem` / `astheysnoopuntous` |
| Foxhunter | 2 | `mode_foxhunter.cpp` | `raw/foxhunter.cpp` | `foxhunter` / `foxhunter` |
| Flock-You | 4 | `mode_flockyou.cpp` | `raw/flockyou.cpp` | `flockyou` / `flockyou123` |
| Sky Spy | 5 | `mode_skyspy.cpp` | `raw/skyspy.cpp` | No AP (passive WiFi scanner) |

Note: Mode IDs 3 is skipped intentionally.

### Key Patterns

- **NVS persistence:** `Preferences` library stores mode selection (`"unified-mode"` namespace), AP credentials (`"ouispy-ap"`), and buzzer state (`"ouispy-bz"`). Always call `prefs.end()` after use.
- **WiFi factory reset on boot:** `esp_wifi_restore()` clears stale NVS WiFi config every boot before mode init.
- **MAC randomization:** Random locally-administered MAC generated on each boot via `esp_random()`.
- **Async web servers:** All modes with dashboards use `ESPAsyncWebServer` on port 80 at `192.168.4.1`.
- **BLE scanning:** NimBLE library with `NimBLEAdvertisedDeviceCallbacks` for advertisement processing.
- **Buzzer audio:** LEDC PWM on GPIO 3 (inverted logic). Frequencies range from 600 Hz (heartbeat) to 3000 Hz (confirmation).
- **LED:** GPIO 21 has inverted logic (LOW = ON). Optional NeoPixel on GPIO 4.
- **Embedded HTML:** Stored as `PROGMEM` raw string literals with `%PLACEHOLDER%` template substitution.
- **Device cooldowns:** Detection modes use timed cooldowns (3s or 30s) to prevent alert spam on the same device.
- **Sky Spy differs:** Uses WiFi promiscuous mode (not BLE) to capture ASTM F3411 Open Drone ID frames. The OpenDroneID parser is in `src/opendroneid.h/c` and `src/wifi.c`.

### Hardware

**Board:** Seeed Studio XIAO ESP32-S3 with PSRAM. Custom partition table: ~6MB app + ~2MB LittleFS (`partitions.csv`).

| GPIO | Function |
|------|----------|
| 0 | BOOT button (hold 2s → return to selector) |
| 3 | Piezo buzzer (PWM, inverted logic) |
| 4 | NeoPixel LED (optional) |
| 21 | Onboard LED (inverted logic) |

### Dependencies (managed by PlatformIO)

- `NimBLE-Arduino` ^1.4.0 — BLE scanning
- `ESP Async WebServer` ^3.0.6 — Web interfaces
- `ArduinoJson` ^7.0.4 — JSON serialization
- `Adafruit NeoPixel` ^1.12.0 — LED control

## ESP32-C6 Experimental Branch

An experimental standalone Flock-You build for the XIAO ESP32-C6 exists on the `esp32c6-flockyou` branch (release: `esp32c6-v1.0`). It is NOT on master. If working on C6 support in the future, use a **separate project directory** to avoid framework conflicts with the S3 build.

## Git Identity (this repo)

- user.name: suteny0r
- user.email: suteny0r@gmail.com
- Fork remote: https://github.com/suteny0r/oui-spy-unified-blue

### Never push to upstream origin
- This is a fork. `origin` points to the upstream repo (`colonelpanichacks/oui-spy-unified-blue`) which we do **not** have write access to.
- **ALWAYS** push to `fork` (e.g., `git push fork master`), **NEVER** to `origin`.
- When creating PRs, push the branch to `fork` first, then open the PR against the upstream.
