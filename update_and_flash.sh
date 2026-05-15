#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${HOME}/Downloads/GitHub/oui-spy-unified-blue"
PIO_ENV="seeed_xiao_esp32s3"
FALLBACK_PORT="/dev/cu.usbmodem1101"
COMMIT_MSG="flockyou: sync OUI list with NitekryDPaul / nite-oui-collection

- Added 22 OUIs from @NitekryDPaul promiscuous-mode set + April 2026 additions
- Added 82:6b:f2 from Michael / DeFlockJoplin (Joplin drive-test)
- Removed cc:cc:cc (upstream demotion: no observed hits)
- Net OUI count: 20 -> 42

Patched via patch_ouis.py."

ASSUME_YES="false"; SKIP_GIT="false"; SKIP_FLASH="false"
SKIP_BUILD="false"; ERASE_FLASH="false"; SKIP_PATCH="false"

for arg in "$@"; do
    case "$arg" in
        --yes|-y)     ASSUME_YES="true" ;;
        --skip-git)   SKIP_GIT="true" ;;
        --skip-flash) SKIP_FLASH="true" ;;
        --skip-build) SKIP_BUILD="true" ;;
        --skip-patch) SKIP_PATCH="true" ;;
        --erase)      ERASE_FLASH="true" ;;
        *) echo "Unknown arg: $arg" >&2; exit 2 ;;
    esac
done

c_red()    { printf '\033[31m%s\033[0m' "$*"; }
c_green()  { printf '\033[32m%s\033[0m' "$*"; }
c_yellow() { printf '\033[33m%s\033[0m' "$*"; }
c_blue()   { printf '\033[34m%s\033[0m' "$*"; }
c_bold()   { printf '\033[1m%s\033[0m' "$*"; }

stage()   { echo ""; echo "$(c_blue '===')  $(c_bold "$*")"; echo ""; }
die()     { echo ""; echo "  $(c_red 'ABORT:') $*" >&2; exit 1; }
confirm() {
    local prompt="${1:-Continue?}"
    if [[ "$ASSUME_YES" == "true" ]]; then
        echo "  [--yes] auto-confirm: $prompt"; return 0
    fi
    read -r -p "  $(c_yellow '?') $prompt [y/N] " reply
    [[ "$reply" =~ ^[Yy]$ ]]
}

stage "Preflight"
[[ -d "$REPO_DIR" ]] || die "Repo not found: $REPO_DIR"
cd "$REPO_DIR"
echo "  repo:    $REPO_DIR"
echo "  branch:  $(git rev-parse --abbrev-ref HEAD)"
echo "  remote:  $(git remote get-url origin 2>/dev/null || echo NONE)"
[[ -f "patch_ouis.py" ]] || die "patch_ouis.py not at repo root."
[[ -f "src/raw/flockyou.cpp" ]] || die "src/raw/flockyou.cpp not found."
command -v pio >/dev/null 2>&1 || command -v platformio >/dev/null 2>&1 \
    || die "PlatformIO CLI not in PATH. Install: brew install platformio"

if ! git diff --quiet || ! git diff --cached --quiet; then
    echo ""
    echo "  $(c_yellow 'warn:')  Working tree has uncommitted changes:"
    git status --short | sed 's/^/      /'
    echo ""
    confirm "Proceed anyway?" || die "User aborted at preflight."
fi

if [[ "$SKIP_GIT" != "true" ]]; then
    stage "1. Pull latest from origin"
    current_branch=$(git rev-parse --abbrev-ref HEAD)
    echo "  fetching origin..."
    git fetch origin --quiet
    behind=$(git rev-list --count "HEAD..origin/${current_branch}" 2>/dev/null || echo "0")
    if [[ "$behind" -gt "0" ]]; then
        echo "  local is $behind commit(s) behind origin/${current_branch}"
        confirm "Pull --rebase?" \
            && git pull --rebase origin "$current_branch" \
            || echo "  skipped pull"
    else
        echo "  $(c_green 'ok') up to date with origin/${current_branch}"
    fi
fi

if [[ "$SKIP_PATCH" != "true" ]]; then
stage "2. Patch preview (dry-run)"
python3 patch_ouis.py 2>&1 | head -60
echo "  ..."
echo ""
confirm "Apply the patch?" || die "User aborted at patch preview."

stage "3. Apply patch"
python3 patch_ouis.py --apply
count=$(awk '/static const char\* mac_prefixes/,/^};/' src/raw/flockyou.cpp \
        | grep -oE '"[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}"' | wc -l | tr -d ' ')
echo "  patched OUI count: $count"
[[ "$count" == "42" ]] || die "Expected 42 OUIs, got $count."
echo "  $(c_green 'ok') OUI count verified"
fi

if [[ "$SKIP_BUILD" != "true" ]]; then
    stage "4. Build with PlatformIO"
    confirm "Run pio run -e $PIO_ENV ?" || die "User aborted at build."
    pio run -e "$PIO_ENV" || die "Build failed. Backup is in backup-*-ouis-pre/"
    echo "  $(c_green 'ok') build succeeded"
fi

if [[ "$SKIP_GIT" != "true" ]]; then
    stage "5. Commit + push"
    if git diff --quiet src/raw/flockyou.cpp; then
        echo "  flockyou.cpp shows no diff vs HEAD - already committed?"
    else
        git add src/raw/flockyou.cpp
        if ! git ls-files --error-unmatch patch_ouis.py >/dev/null 2>&1; then
            confirm "Also commit patch_ouis.py (new to repo)?" && git add patch_ouis.py
        fi
        echo ""
        echo "  Files staged:"
        git diff --cached --stat | sed 's/^/      /'
        echo ""
        confirm "Commit and push to origin/$(git rev-parse --abbrev-ref HEAD)?" || {
            echo "  skipped commit - files remain staged"
            SKIP_PUSH="true"
        }
        if [[ "${SKIP_PUSH:-false}" != "true" ]]; then
            git commit -m "$COMMIT_MSG"
            git push origin "$(git rev-parse --abbrev-ref HEAD)"
            echo "  $(c_green 'ok') pushed to GitHub"
        fi
    fi
fi

if [[ "$SKIP_FLASH" != "true" ]]; then
    stage "6. Flash to XIAO ESP32-S3"
    port=""
    for candidate in /dev/cu.usbmodem* /dev/cu.SLAB_USBtoUART /dev/cu.wchusbserial*; do
        [[ -e "$candidate" ]] && { port="$candidate"; break; }
    done
    if [[ -z "$port" ]]; then
        echo "  no USB serial device auto-detected"
        [[ -e "$FALLBACK_PORT" ]] || die "No ESP32 plugged in."
        port="$FALLBACK_PORT"
    fi
    echo "  port:    $port"

    if [[ "$ERASE_FLASH" == "true" ]]; then
        confirm "$(c_red 'ERASE ALL FLASH') (NVS/SPIFFS data lost)?" \
            && pio run -e "$PIO_ENV" -t erase --upload-port "$port"
    fi

    confirm "Upload firmware to $port?" || die "User aborted at flash."
    pio run -e "$PIO_ENV" -t upload --upload-port "$port"
    echo "  $(c_green 'ok') flash complete"
    echo ""
    echo "  Listen for 4 ascending beeps. AP: oui-spy / ouispy123"
    if confirm "Open serial monitor now?"; then
        pio device monitor -e "$PIO_ENV" --port "$port" || true
    fi
fi

stage "Done"
