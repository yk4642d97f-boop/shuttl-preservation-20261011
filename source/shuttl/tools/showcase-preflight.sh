#!/usr/bin/env bash
# Read-only preflight for a local Shuttl showcase. It never changes the project.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IOS="$ROOT/iOS"
PASS=0
WARN=0
FAIL=0

pass() { PASS=$((PASS + 1)); printf 'PASS  %s\n' "$1"; }
warn() { WARN=$((WARN + 1)); printf 'WARN  %s\n' "$1"; }
fail() { FAIL=$((FAIL + 1)); printf 'FAIL  %s\n' "$1"; }

printf 'Shuttl showcase preflight\n'
printf 'Project: %s\n\n' "$ROOT"

# Device pairing and signing
DEVICE_ID=""
DEVICES=""
if command -v xcrun >/dev/null 2>&1; then
    DEVICES="$(xcrun devicectl list devices 2>/dev/null || true)"
    DEVICE_ID="$(printf '%s\n' "$DEVICES" | awk '/iPhone 16 Pro/ {print $0}' \
        | grep -oE '[0-9A-Fa-f-]{36}' | head -1)"
    if [ -n "$DEVICE_ID" ]; then
        DEVICE_APPS="$(xcrun devicectl device info apps --device "$DEVICE_ID" 2>/dev/null || true)"
        if printf '%s\n' "$DEVICE_APPS" | grep -q 'Apps installed:'; then
            pass 'iPhone 16 Pro is paired and reachable through CoreDevice'
        else
            warn 'iPhone 16 Pro is paired but CoreDevice could not query its installed apps'
        fi
    else
        fail 'iPhone 16 Pro is not paired; connect it and enable Developer Mode'
    fi
else
    fail 'xcrun is unavailable; install Xcode command line tools'
fi

if security find-identity -v -p codesigning 2>/dev/null | grep -q 'Apple Development'; then
    pass 'Apple Development signing identity is available'
else
    fail 'No Apple Development signing identity is available in the keychain'
fi

# Ensure the expected app identity is installed on the phone.
PROJECT_BUNDLE_ID="$(awk '/PRODUCT_BUNDLE_IDENTIFIER:/ {gsub(/[[:space:]]/, "", $2); print $2; exit}' \
    "$IOS/project.yml" 2>/dev/null)"
if [ -n "$DEVICE_ID" ] && [ -n "$PROJECT_BUNDLE_ID" ]; then
    INSTALLED_BUNDLE_ID="$(xcrun devicectl device info apps --device "$DEVICE_ID" 2>/dev/null \
        | awk '$1 == "Shuttl" {print $2; exit}')"
    if [ "$INSTALLED_BUNDLE_ID" = "$PROJECT_BUNDLE_ID" ]; then
        pass "Installed Shuttl bundle matches project ($PROJECT_BUNDLE_ID)"
    elif [ -n "$INSTALLED_BUNDLE_ID" ]; then
        fail "Installed bundle is $INSTALLED_BUNDLE_ID; project expects $PROJECT_BUNDLE_ID"
    else
        warn 'Shuttl is not installed on the paired iPhone'
    fi
else
    warn 'Could not determine project or device bundle identity'
fi

# Bundled assets and permission descriptions
if [ -d "$IOS/Resources/Models/ShuttleTracker.mlpackage" ]; then
    MODEL_SIZE="$(du -sh "$IOS/Resources/Models/ShuttleTracker.mlpackage" 2>/dev/null | awk '{print $1}')"
    pass "Core ML package is present ($MODEL_SIZE)"
else
    fail 'ShuttleTracker.mlpackage is missing'
fi

if plutil -extract NSCameraUsageDescription raw -o - "$IOS/Resources/Info.plist" >/dev/null 2>&1 && \
   plutil -extract NSMicrophoneUsageDescription raw -o - "$IOS/Resources/Info.plist" >/dev/null 2>&1; then
    pass 'Camera and microphone permission descriptions are present'
else
    fail 'Camera or microphone permission description is missing'
fi

# Local backend services
if curl -fsS --max-time 3 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    pass 'Local API health check passed'
else
    fail 'Local API is not responding on port 8000'
fi

if nc -z 127.0.0.1 5432 >/dev/null 2>&1; then
    pass 'Postgres is reachable on port 5432'
else
    warn 'Postgres is not reachable on port 5432; required for server-backed analysis'
fi

if nc -z 127.0.0.1 6379 >/dev/null 2>&1; then
    pass 'Redis is reachable on port 6379'
else
    warn 'Redis is not reachable on port 6379; required for Celery analysis jobs'
fi

if ps aux | grep -E '[c]elery .*app\.worker' >/dev/null 2>&1; then
    pass 'Celery worker process is running'
else
    warn 'Celery worker is not running; server analysis jobs will remain queued'
fi

# Physical-device networking: use the interface selected by the default route.
API_URL="$(plutil -extract ShuttlAPIBaseURL raw -o - "$IOS/Resources/Info.plist" 2>/dev/null || true)"
DEFAULT_IFACE="$(route -n get default 2>/dev/null | awk '/interface:/{print $2; exit}')"
LAN_IP=""
if [ -n "$DEFAULT_IFACE" ]; then
    LAN_IP="$(ipconfig getifaddr "$DEFAULT_IFACE" 2>/dev/null || true)"
fi

if [ -n "$API_URL" ]; then
    API_HOST="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.urlparse(sys.argv[1]).hostname or "")' "$API_URL")"
    if [ -z "$LAN_IP" ]; then
        warn "App API URL is $API_URL; no default-route LAN IPv4 address was found"
    elif [ "$API_HOST" = "$LAN_IP" ]; then
        pass "App API host matches the Mac LAN address ($LAN_IP)"
    elif curl -fsS --max-time 3 "$API_URL/health" >/dev/null 2>&1; then
        pass "Configured API host $API_HOST is reachable"
    else
        warn "App API host $API_HOST is stale/unreachable; update to http://$LAN_IP:8000 before live upload"
    fi
else
    warn 'App API URL could not be read from Info.plist'
fi

if [ -n "$LAN_IP" ]; then
    pass "Mac default-route address is $LAN_IP ($DEFAULT_IFACE)"
    if lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | grep -Eq '\*:8000|0\.0\.0\.0:8000'; then
        pass 'API is listening on the LAN interface'
    else
        warn 'API may be bound only to localhost; iPhone requests may fail'
    fi
else
    warn 'No active default-route LAN IPv4 address found; use the offline demo path'
fi

# On-device migration status
if [ -f "$IOS/Packages/ShuttlCore/Package.swift" ]; then
    if grep -q 'ShuttlCore' "$IOS/Shuttl.xcodeproj/project.pbxproj" 2>/dev/null || \
       grep -q 'ShuttlCore' "$IOS/project.yml" 2>/dev/null; then
        pass 'ShuttlCore package is referenced by the app project'
    else
        warn 'ShuttlCore exists but is not yet referenced by the Xcode project'
    fi
else
    warn 'On-device ShuttlCore package has not been created yet'
fi

printf '\nSummary: %d pass, %d warning, %d failure\n' "$PASS" "$WARN" "$FAIL"
if [ "$FAIL" -gt 0 ]; then exit 1; fi
exit 0
