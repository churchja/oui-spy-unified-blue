#!/usr/bin/env python3
"""
patch_conflict_suppression.py — suppress false positives on conflict OUIs

Adds corroboration logic to the BLE detection callback in
src/raw/flockyou.cpp so that MAC-prefix matches on known-collision
OUIs (currently just 08:3a:88, which is shared with BLE Ring
doorbells) only count as detections when a second signal — device
name, manufacturer ID, or Raven UUID — also matches the same device.

Additionally, devices on conflict OUIs whose advertised name matches
a known false-positive pattern (e.g. "DBC" for Ring doorbells) are
discarded entirely, even if they would otherwise weak-match.

Real Flock cameras on a conflict OUI will still register: every real
Flock device also broadcasts at least one of:
    - device name containing "Flock", "Penguin", "Pigvision", or
      "FS Ext Battery"
    - manufacturer ID 0x09C8 (XUNTONG)
    - a Raven service UUID

So the patch suppresses lone-OUI Ring/Sony/etc hits without losing
real Flock detections.

Behaviour on non-conflict OUIs is unchanged — the other 41 prefixes
still trigger detections on MAC prefix alone, exactly as before.

Same surgical pattern as the other patch_* scripts: refuses if any
source pattern is missing or appears more than once, dry-run by
default, writes a timestamped backup before applying.
"""

import argparse
import datetime
import difflib
import shutil
import sys
from pathlib import Path

TARGET = Path("src/raw/flockyou.cpp")

# ---------------------------------------------------------------------------
# Change 1: insert conflict_prefixes[] array and helper after mac_prefixes[].
#
# We anchor on the closing of the mac_prefixes array plus the blank line and
# the device_name_patterns comment that immediately follow it.
# ---------------------------------------------------------------------------

CONFLICT_INSERT_ANCHOR = """    // Michael / DeFlockJoplin — drive-test in Joplin
    "82:6b:f2"
};

// BLE device name patterns (matched case-insensitive substring)"""

CONFLICT_INSERT_REPLACEMENT = """    // Michael / DeFlockJoplin — drive-test in Joplin
    "82:6b:f2"
};

// MAC prefixes that are known to collide with non-Flock devices.
// A MAC-prefix match on one of these OUIs is treated as a WEAK signal
// and only counts as a detection if corroborated by device name,
// manufacturer ID, or Raven UUID on the same advertisement.
//
//   08:3a:88 — shared with BLE Ring doorbells (and HP devices)
static const char* conflict_prefixes[] = {
    "08:3a:88"
};

// Name patterns that, when seen on a conflict-OUI device, indicate
// a known false-positive product. If a conflict-OUI advertisement
// also carries one of these names, it is discarded outright — no
// detection is recorded even if other methods would otherwise fire.
//
//   "DBC" — Ring doorbells advertise as "DBC350_xx:xx:xx" etc.
static const char* conflict_name_blocklist[] = {
    "DBC"
};

static bool isConflictPrefix(const uint8_t* mac) {
    char mac_str[9];
    snprintf(mac_str, sizeof(mac_str), "%02x:%02x:%02x", mac[0], mac[1], mac[2]);
    for (size_t i = 0; i < sizeof(conflict_prefixes)/sizeof(conflict_prefixes[0]); i++) {
        if (strncasecmp(mac_str, conflict_prefixes[i], 8) == 0) return true;
    }
    return false;
}

static bool isBlocklistedName(const char* name) {
    if (!name || !name[0]) return false;
    for (size_t i = 0; i < sizeof(conflict_name_blocklist)/sizeof(conflict_name_blocklist[0]); i++) {
        if (strcasestr(name, conflict_name_blocklist[i])) return true;
    }
    return false;
}

// BLE device name patterns (matched case-insensitive substring)"""

# ---------------------------------------------------------------------------
# Change 2: rewrite the four-method detection block in the BLE callback so
# that MAC-prefix matches on conflict OUIs are held as weak matches and
# only confirmed if a corroborating method also fires.
# ---------------------------------------------------------------------------

CALLBACK_ANCHOR = """        bool detected = false;
        const char* method = "";
        bool isRaven = false;
        const char* ravenFW = "";

        // 1. Check MAC prefix against known Flock Safety OUIs
        if (checkMACPrefix(mac)) {
            detected = true;
            method = "mac_prefix";
        }

        // 2. Check BLE device name patterns
        if (!detected && !name.empty() && checkDeviceName(name.c_str())) {
            detected = true;
            method = "device_name";
        }

        // 3. Check BLE manufacturer company IDs (from wgreenberg/flock-you)
        if (!detected) {
            for (int i = 0; i < (int)dev->getManufacturerDataCount(); i++) {
                std::string data = dev->getManufacturerData(i);
                if (data.size() >= 2) {
                    uint16_t code = ((uint16_t)(uint8_t)data[1] << 8) |
                                     (uint16_t)(uint8_t)data[0];
                    if (checkManufacturerID(code)) {
                        detected = true;
                        method = "ble_mfr_id";
                        break;
                    }
                }
            }
        }

        // 4. Check Raven gunshot detector service UUIDs
        if (!detected) {
            char detUUID[41] = {0};
            if (checkRavenUUID(dev, detUUID)) {
                detected = true;
                method = "raven_uuid";
                isRaven = true;
                ravenFW = estimateRavenFW(dev);
            }
        }"""

CALLBACK_REPLACEMENT = """        bool detected = false;
        const char* method = "";
        bool isRaven = false;
        const char* ravenFW = "";

        // Conflict-OUI false-positive suppression:
        //   - A MAC-prefix hit on a conflict OUI (e.g. 08:3a:88) is held as
        //     a WEAK match. It only counts if a stronger signal also fires.
        //   - If the device's name matches a known false-positive pattern
        //     (e.g. "DBC*" for Ring), the advertisement is discarded
        //     outright, no matter what other methods would match.
        bool conflictOUI = false;
        bool weakMacMatch = false;

        // 1. Check MAC prefix against known Flock Safety OUIs
        if (checkMACPrefix(mac)) {
            conflictOUI = isConflictPrefix(mac);
            // Short-circuit: blocklisted name on a conflict OUI is a hard reject
            if (conflictOUI && !name.empty() && isBlocklistedName(name.c_str())) {
                return;  // Known false positive — don't process further
            }
            if (conflictOUI) {
                weakMacMatch = true;  // Held pending corroboration
            } else {
                detected = true;
                method = "mac_prefix";
            }
        }

        // 2. Check BLE device name patterns
        if (!detected && !name.empty() && checkDeviceName(name.c_str())) {
            detected = true;
            method = weakMacMatch ? "mac_prefix+name" : "device_name";
            weakMacMatch = false;  // Corroborated
        }

        // 3. Check BLE manufacturer company IDs (from wgreenberg/flock-you)
        if (!detected) {
            for (int i = 0; i < (int)dev->getManufacturerDataCount(); i++) {
                std::string data = dev->getManufacturerData(i);
                if (data.size() >= 2) {
                    uint16_t code = ((uint16_t)(uint8_t)data[1] << 8) |
                                     (uint16_t)(uint8_t)data[0];
                    if (checkManufacturerID(code)) {
                        detected = true;
                        method = weakMacMatch ? "mac_prefix+mfr" : "ble_mfr_id";
                        weakMacMatch = false;  // Corroborated
                        break;
                    }
                }
            }
        }

        // 4. Check Raven gunshot detector service UUIDs
        if (!detected) {
            char detUUID[41] = {0};
            if (checkRavenUUID(dev, detUUID)) {
                detected = true;
                method = weakMacMatch ? "mac_prefix+uuid" : "raven_uuid";
                weakMacMatch = false;  // Corroborated
                isRaven = true;
                ravenFW = estimateRavenFW(dev);
            }
        }

        // If we get here with weakMacMatch still set, no other method fired.
        // Suppress the detection — lone conflict-OUI hits are not counted.
        // (detected stays false, so the block below is skipped.)"""


REPLACEMENTS = [
    ("conflict_prefixes array + helpers", CONFLICT_INSERT_ANCHOR, CONFLICT_INSERT_REPLACEMENT),
    ("BLE callback corroboration logic", CALLBACK_ANCHOR, CALLBACK_REPLACEMENT),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually write changes (default: dry-run)")
    ap.add_argument("--root", default=".",
                    help="repo root (default: cwd)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    target = root / TARGET
    if not target.is_file():
        print(f"ERROR: {target} not found. Run from repo root.", file=sys.stderr)
        return 2

    original = target.read_text()

    # Preflight: every anchor must appear exactly once, and no replacement
    # text may already be present (refuse to operate on already-patched files).
    failures = []
    for label, old, new in REPLACEMENTS:
        n_old = original.count(old)
        n_new = original.count(new)
        if n_new > 0:
            failures.append(f"  - {label!r}: replacement text already present "
                            f"({n_new} occurrence(s)) — file appears already patched")
            continue
        if n_old == 0:
            failures.append(f"  - {label!r}: anchor NOT FOUND")
        elif n_old > 1:
            failures.append(f"  - {label!r}: anchor found {n_old} times, expected 1")

    if failures:
        print("ERROR: cannot patch — preflight failures:", file=sys.stderr)
        for f in failures:
            print(f, file=sys.stderr)
        print("\nIf the file is already patched, no action needed. Otherwise, "
              "the source may have drifted from what this patch expects.",
              file=sys.stderr)
        return 3

    patched = original
    for _label, old, new in REPLACEMENTS:
        patched = patched.replace(old, new, 1)

    if patched == original:
        print("No changes needed.")
        return 0

    diff = "".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        patched.splitlines(keepends=True),
        fromfile=f"a/{TARGET}",
        tofile=f"b/{TARGET}",
        n=3,
    ))
    print(diff)
    print(f"\n--- summary ---")
    print(f"replacements applied: {len(REPLACEMENTS)}")
    print(f"  1. Added conflict_prefixes[] array + isConflictPrefix() + isBlocklistedName()")
    print(f"  2. Rewrote BLE callback to require corroboration on conflict OUIs")
    print(f"")
    print(f"Effect:")
    print(f"  - Lone 08:3a:88 hits (Ring doorbells, etc) will no longer register")
    print(f"  - 08:3a:88 with name starting 'DBC' is hard-rejected (Ring)")
    print(f"  - 08:3a:88 WITH a Flock name/mfr/UUID still registers (method tagged 'mac_prefix+...')")
    print(f"  - All other 41 OUIs unchanged — single MAC-prefix match still counts")

    if not args.apply:
        print("\nDRY RUN — no files written. Re-run with --apply to commit.")
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    backup_dir = root / f"backup-{stamp}-conflict-suppression-pre"
    backup_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(target, backup_dir / target.name)
    print(f"\nBackup written to: {backup_dir}/{target.name}")

    target.write_text(patched)
    print(f"Patched: {target}")
    print(f"\nNext: rebuild and flash with `pio run -t upload` "
          f"(or use ./update_and_flash.sh)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
