#!/usr/bin/env python3
"""
patch_ouis.py — surgical update of the Flock Safety OUI list in flockyou.cpp

Brings churchja/oui-spy-unified-blue's mac_prefixes[] in line with
colonelpanichacks/oui-spy-unified-blue commit eda4b96
("flockyou (BLE): sync OUI list with @NitekryDPaul / nite-oui-collection").

Changes:
  - Adds 22 OUIs missing from this fork
  - Removes cc:cc:cc (upstream demotion: "no observed hits")
  - Replaces the prefix comment block with upstream provenance notes
  - Does NOT touch RSSI estimation, audio frequencies, GPS handling, or
    anything else that's diverged. Surgical OUI swap only.

Workflow:
  1. Reads src/raw/flockyou.cpp
  2. Writes a timestamped backup to backup-YYYYMMDD-HHMM-ouis-pre/
  3. Locates the `static const char* mac_prefixes[] = { ... };` block
  4. Replaces it with the new block
  5. Prints a unified diff for review

Run with --dry-run to preview without writing. Default IS dry-run; pass
--apply to actually modify the file.
"""

import argparse
import datetime
import difflib
import re
import shutil
import sys
from pathlib import Path

TARGET = Path("src/raw/flockyou.cpp")

# Upstream commit eda4b96 — the authoritative comment + OUI block.
NEW_BLOCK = '''// Known Flock Safety MAC address prefixes (OUIs).
//
// Research credit: OrdoOuroborous / @NitekryDPaul
//   GitHub: https://github.com/nitekry
//   Source of truth: https://github.com/nitekry/nite-oui-collection
//   Status tracker:  groups/flockers/my_tested_flock.md in that repo
//
// Plus 82:6b:f2 — contributed by Michael / DeFlockJoplin during a
// drive-test in Joplin; the 12th camera in the field run used this
// OUI and wasn't in @NitekryDPaul's original 30.
//
// Notes on demoted entries (intentionally absent below):
//   - f8:a2:d6 -> hit on a Sony Media Player, marked Removed
//   - cc:cc:cc -> no observed hits, marked Removed
//   - 00:0c:e7 -> possible MediaTek false positive, marked Removed
// Notes on flagged entries (still tracked):
//   - 08:3a:88 has a known BLE Ring conflict; expect occasional
//     Ring-doorbell false positives in BLE mode.
static const char* mac_prefixes[] = {
    // @NitekryDPaul original promiscuous-mode set (29 OUIs)
    "70:c9:4e", "3c:91:80", "d8:f3:bc", "80:30:49", "b8:35:32",
    "14:5a:fc", "74:4c:a1", "08:3a:88", "9c:2f:9d", "c0:35:32",
    "94:08:53", "e4:aa:ea", "f4:6a:dd", "24:b2:b9", "00:f4:8d",
    "d0:39:57", "e8:d0:fc", "e0:4f:43", "b8:1e:a4", "70:08:94",
    "58:8e:81", "ec:1b:bd", "3c:71:bf", "58:00:e3", "90:35:ea",
    "5c:93:a2", "64:6e:69", "48:27:ea", "a4:cf:12",
    // @NitekryDPaul April 2026 additions (nite-oui-collection)
    "04:0d:84", "f0:82:c0", "1c:34:f1", "38:5b:44", "94:34:69",
    "b4:e3:f9", "b4:1e:52", "14:b5:cd", "94:2a:6f", "f4:e2:c6",
    "d4:11:d6", "e0:0a:f6",
    // Michael / DeFlockJoplin — drive-test in Joplin
    "82:6b:f2"
};'''

# Match the OLD block: from the "// Known Flock Safety" comment line
# down through the closing `};` of the mac_prefixes array. Tight enough
# to not catch other arrays in the file.
OLD_BLOCK_RE = re.compile(
    r"// Known Flock Safety MAC address prefixes \(OUIs\)\n"
    r"static const char\* mac_prefixes\[\] = \{[\s\S]*?\n\};",
    re.MULTILINE,
)


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

    matches = OLD_BLOCK_RE.findall(original)
    if len(matches) == 0:
        print("ERROR: mac_prefixes[] block not found. File may already be "
              "patched or modified.", file=sys.stderr)
        return 3
    if len(matches) > 1:
        print(f"ERROR: found {len(matches)} matching blocks; aborting to be "
              "safe.", file=sys.stderr)
        return 4

    patched = OLD_BLOCK_RE.sub(NEW_BLOCK, original)

    if patched == original:
        print("No changes needed — already up to date.")
        return 0

    # Unified diff for review
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        patched.splitlines(keepends=True),
        fromfile=f"a/{TARGET}",
        tofile=f"b/{TARGET}",
        n=3,
    )
    diff_text = "".join(diff)
    print(diff_text)

    # OUI count sanity check
    new_count = patched.count('"') // 2 - original.count('"') // 2 \
                + sum(1 for _ in re.finditer(r'"[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}"', original))
    new_block_count = len(re.findall(r'"[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}"', NEW_BLOCK))
    print(f"\n--- summary ---")
    print(f"new OUI count in mac_prefixes[]: {new_block_count}")

    if not args.apply:
        print("\nDRY RUN — no files written. Re-run with --apply to commit.")
        return 0

    # Backup
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    backup_dir = root / f"backup-{stamp}-ouis-pre"
    backup_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(target, backup_dir / target.name)
    print(f"\nBackup written to: {backup_dir}/{target.name}")

    target.write_text(patched)
    print(f"Patched: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
