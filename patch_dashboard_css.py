#!/usr/bin/env python3
"""
patch_dashboard_css.py — compact the FLOCK-YOU dashboard CSS

Reduces font sizes and tightens padding in the embedded HTML so more
detection cards fit on screen at once. Same surgical pattern as
patch_ouis.py: locates each CSS rule, makes the replacement, refuses
if anything doesn't match exactly.

Changes (per-rule diff):
  Header / stats bar:
    .hd                padding 10px 14px  ->  8px 12px
    .hd h1             22px               ->  18px
    .hd .sub           11px               ->  10px
    .st                padding 8px 12px   ->  6px 10px,  gap 8px -> 6px
    .sc                padding 6px        ->  4px
    .sc .n             22px               ->  18px
    .sc .l             10px               ->  9px

  Tab bar:
    .tb button         padding 9px        ->  7px,  font 13px -> 11px

  Detection cards (the big win for screen density):
    .cn                padding 10px       ->  7px
    .det               padding 10px       ->  7px,  margin-bottom 8px -> 5px
    .det .mac          14px               ->  12px
    .det .nm           13px               ->  11px
    .det .inf          gap 5px            ->  4px,  font 12px -> 11px,  margin-top 5px -> 3px
    .det .inf span     padding 3px 6px    ->  2px 5px

Run with --dry-run (default) to preview. Pass --apply to write.
Refuses to operate on a file where any of the source patterns is
missing or appears more than once.
"""

import argparse
import datetime
import difflib
import shutil
import sys
from pathlib import Path

TARGET = Path("src/raw/flockyou.cpp")

# Each entry: (description, old, new)
# Patterns chosen to be unique within the CSS block. Order matters only
# in that we want clear error messages if one fails.
REPLACEMENTS = [
    (
        ".hd padding",
        ".hd{background:#1a0033;padding:10px 14px;border-bottom:2px solid #ec4899;flex-shrink:0}",
        ".hd{background:#1a0033;padding:8px 12px;border-bottom:2px solid #ec4899;flex-shrink:0}",
    ),
    (
        ".hd h1",
        ".hd h1{font-size:22px;color:#ec4899;letter-spacing:3px}",
        ".hd h1{font-size:18px;color:#ec4899;letter-spacing:3px}",
    ),
    (
        ".hd .sub",
        ".hd .sub{font-size:11px;color:#8b5cf6;margin-top:2px}",
        ".hd .sub{font-size:10px;color:#8b5cf6;margin-top:2px}",
    ),
    (
        ".st",
        ".st{display:flex;gap:8px;padding:8px 12px;background:rgba(139,92,246,.08);border-bottom:1px solid rgba(139,92,246,.19);flex-shrink:0}",
        ".st{display:flex;gap:6px;padding:6px 10px;background:rgba(139,92,246,.08);border-bottom:1px solid rgba(139,92,246,.19);flex-shrink:0}",
    ),
    (
        ".sc",
        ".sc{flex:1;text-align:center;padding:6px;border:1px solid rgba(139,92,246,.25);border-radius:5px}",
        ".sc{flex:1;text-align:center;padding:4px;border:1px solid rgba(139,92,246,.25);border-radius:5px}",
    ),
    (
        ".sc .n",
        ".sc .n{font-size:22px;font-weight:bold;color:#ec4899}",
        ".sc .n{font-size:18px;font-weight:bold;color:#ec4899}",
    ),
    (
        ".sc .l",
        ".sc .l{font-size:10px;color:#8b5cf6;margin-top:2px}",
        ".sc .l{font-size:9px;color:#8b5cf6;margin-top:2px}",
    ),
    (
        ".tb button",
        ".tb button{flex:1;padding:9px;text-align:center;cursor:pointer;color:#8b5cf6;border:none;background:none;font-family:inherit;font-size:13px;font-weight:bold;letter-spacing:1px}",
        ".tb button{flex:1;padding:7px;text-align:center;cursor:pointer;color:#8b5cf6;border:none;background:none;font-family:inherit;font-size:11px;font-weight:bold;letter-spacing:1px}",
    ),
    (
        ".cn",
        ".cn{flex:1;overflow-y:auto;padding:10px}",
        ".cn{flex:1;overflow-y:auto;padding:7px}",
    ),
    (
        ".det",
        ".det{background:rgba(45,27,105,.4);border:1px solid rgba(139,92,246,.25);border-radius:7px;padding:10px;margin-bottom:8px}",
        ".det{background:rgba(45,27,105,.4);border:1px solid rgba(139,92,246,.25);border-radius:7px;padding:7px;margin-bottom:5px}",
    ),
    (
        ".det .mac",
        ".det .mac{color:#ec4899;font-weight:bold;font-size:14px}",
        ".det .mac{color:#ec4899;font-weight:bold;font-size:12px}",
    ),
    (
        ".det .nm",
        ".det .nm{color:#c084fc;font-size:13px;margin-left:4px}",
        ".det .nm{color:#c084fc;font-size:11px;margin-left:4px}",
    ),
    (
        ".det .inf",
        ".det .inf{display:flex;flex-wrap:wrap;gap:5px;margin-top:5px;font-size:12px}",
        ".det .inf{display:flex;flex-wrap:wrap;gap:4px;margin-top:3px;font-size:11px}",
    ),
    (
        ".det .inf span",
        ".det .inf span{background:rgba(139,92,246,.15);padding:3px 6px;border-radius:4px}",
        ".det .inf span{background:rgba(139,92,246,.15);padding:2px 5px;border-radius:4px}",
    ),
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
    patched = original

    # Pre-flight: verify every old pattern exists exactly once.
    failures = []
    for label, old, _new in REPLACEMENTS:
        n = patched.count(old)
        if n == 0:
            failures.append(f"  - {label!r}: NOT FOUND (already patched? or upstream changed CSS)")
        elif n > 1:
            failures.append(f"  - {label!r}: found {n} times, expected 1")
    if failures:
        print("ERROR: cannot patch — preflight failures:", file=sys.stderr)
        for f in failures:
            print(f, file=sys.stderr)
        return 3

    # Apply.
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
        n=2,
    ))
    print(diff)
    print(f"\n--- summary ---")
    print(f"replacements applied: {len(REPLACEMENTS)}")

    if not args.apply:
        print("\nDRY RUN — no files written. Re-run with --apply to commit.")
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    backup_dir = root / f"backup-{stamp}-css-pre"
    backup_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(target, backup_dir / target.name)
    print(f"\nBackup written to: {backup_dir}/{target.name}")

    target.write_text(patched)
    print(f"Patched: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
