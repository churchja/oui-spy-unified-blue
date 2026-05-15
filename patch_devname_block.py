#!/usr/bin/env python3
"""
patch_devname_block.py — drop the BLE device name to its own line

Detection cards currently render as:
    [aa:bb:cc:dd:ee:ff DEVICE_NAME_HERE]   <- overflows on long names
    [RSSI: -80   ~21m   mac_prefix   x1]
    [GPS]

Names like 'DBC350_E0:3D:C1' or 'ResMed 016575' push the card wider
than the phone viewport because the name span is inline with the MAC.

This patch:
  1. Flips `.det .nm` from inline -> block (drops name to its own line)
  2. Adds word-break: break-all so unbroken strings like 'DBC350_E0:3D:C1'
     wrap at character boundaries instead of overflowing
  3. Adds small margin-top so MAC and name aren't crammed together

After: cards become
    [aa:bb:cc:dd:ee:ff]
    [DEVICE_NAME_HERE]
    [RSSI: -80   ~21m   mac_prefix   x1]
    [GPS]

Same surgical pattern as patch_ouis.py / patch_dashboard_css.py: refuses
to operate if the source pattern is missing or appears more than once.
Default is dry-run; pass --apply to write.
"""

import argparse
import datetime
import difflib
import shutil
import sys
from pathlib import Path

TARGET = Path("src/raw/flockyou.cpp")

OLD = ".det .nm{color:#c084fc;font-size:11px;margin-left:4px}"
NEW = ".det .nm{color:#c084fc;font-size:11px;display:block;margin-top:2px;word-break:break-all}"


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
    n = original.count(OLD)
    if n == 0:
        print(f"ERROR: target rule not found.\n"
              f"  Expected: {OLD}\n"
              f"  The CSS may have changed since this patch was written, "
              f"or the file is already patched.", file=sys.stderr)
        return 3
    if n > 1:
        print(f"ERROR: target rule appears {n} times; expected exactly 1. "
              f"Aborting to be safe.", file=sys.stderr)
        return 4

    patched = original.replace(OLD, NEW, 1)

    diff = "".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        patched.splitlines(keepends=True),
        fromfile=f"a/{TARGET}",
        tofile=f"b/{TARGET}",
        n=2,
    ))
    print(diff)

    if not args.apply:
        print("DRY RUN — no files written. Re-run with --apply to commit.")
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    backup_dir = root / f"backup-{stamp}-devname-pre"
    backup_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(target, backup_dir / target.name)
    print(f"Backup written to: {backup_dir}/{target.name}")

    target.write_text(patched)
    print(f"Patched: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
