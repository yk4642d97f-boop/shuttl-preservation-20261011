#!/bin/bash
set -u

# Shuttl free-provisioning renewal helper. All mutable state lives outside the source tree.
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_ROOT="${SHUTTL_PROJECT_ROOT:-$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)}"
IOS_DIR="$PROJECT_ROOT/iOS"
PROJECT="$IOS_DIR/Shuttl.xcodeproj"
SCHEME="Shuttl"
CONFIGURATION="Release"
BUNDLE_ID="com.ycyangcong.shuttl"
DEVELOPMENT_TEAM="F878S66X7Q"
DEVICE_UDID="00008140-001159211A3B801C"
COREDEVICE_ID="0F92DDA9-7A87-4F05-8368-0E834177D8F3"
STATE_DIR="$HOME/Library/Application Support/ShuttlResign"
SNAPSHOT_DIR="$STATE_DIR/apps"
LOG_FILE="$HOME/Library/Logs/shuttl-resign.log"
LOCK_DIR="$STATE_DIR/.lock"
RUN_ID="$(date '+%Y%m%d-%H%M%S')-$$"
RUN_LOG="${TMPDIR:-/tmp}/shuttl-resign-${RUN_ID}.log"
# One fixed, incremental derived-data dir (per-run dirs grew ~190 MB per refresh).
RESIGN_DERIVED_DATA="$IOS_DIR/build/resign/dd"
SNAPSHOT_KEEP=3
LOG_MAX_BYTES=5000000
FORCE=0
PROFILE_EXPIRY_EPOCH=0
PROFILE_EXPIRY_TEXT=""
PROFILE_PATH=""
PROFILE_PLIST=""
PROFILE_CERT_SHA1S=""
IDENTITY=""
LOCK_ACQUIRED=0
RUN_LOG_APPENDED=0
FALLBACK_TMP=""
PROJECT_UNREADABLE=0
# Test hook only: pretend "now" is this epoch (decision logic tests without waiting days).
now_epoch() { printf '%s\n' "${SHUTTL_RESIGN_TEST_NOW:-$(date +%s)}"; }

mkdir -p "$STATE_DIR" "$SNAPSHOT_DIR" "$(dirname "$LOG_FILE")"
# Keep the log bounded: every build appends ~0.5 MB of xcodebuild output.
if [[ -f "$LOG_FILE" ]] && (( $(stat -f %z "$LOG_FILE" 2>/dev/null || echo 0) > LOG_MAX_BYTES )); then
    mv -f "$LOG_FILE" "$LOG_FILE.1"
fi

log() {
    local line
    line="$(date '+%Y-%m-%d %H:%M:%S') $*"
    printf '%s\n' "$line" | tee -a "$LOG_FILE"
}

append_run_log() {
    if (( RUN_LOG_APPENDED == 0 )) && [[ -s "$RUN_LOG" ]]; then
        {
            printf '%s\n' "----- command output ($RUN_ID) -----"
            cat "$RUN_LOG"
            printf '%s\n' "----- end command output ($RUN_ID) -----"
        } >>"$LOG_FILE"
        : >"$RUN_LOG"
        RUN_LOG_APPENDED=1
    fi
}

run_logged() {
    "$@" >>"$RUN_LOG" 2>&1
    return $?
}

notify_user() {
    local title="$1"
    local message="$2"
    osascript - "$message" "$title" <<'APPLESCRIPT' >/dev/null 2>&1 || true
on run argv
    display notification (item 1 of argv) with title (item 2 of argv)
end run
APPLESCRIPT
}

cleanup() {
    append_run_log
    rm -f "$PROFILE_PLIST" "$RUN_LOG"
    [[ -n "$FALLBACK_TMP" && -d "$FALLBACK_TMP" ]] && rm -rf "$FALLBACK_TMP"
    if (( LOCK_ACQUIRED == 1 )); then
        rm -f "$LOCK_DIR/pid" "$LOCK_DIR/run"
        rmdir "$LOCK_DIR" 2>/dev/null || true
    fi
}
trap cleanup EXIT
# Without an explicit exit, bash runs the INT/TERM trap and then carries on with the script.
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ "${1:-}" == "--force" ]]; then
    FORCE=1
elif [[ "${1:-}" != "" ]]; then
    printf '用法: %s [--force]\n' "$0" >&2
    exit 2
fi

lock_is_stale() {
    local owner="" age
    age=$(( $(date +%s) - $(stat -f %m "$LOCK_DIR" 2>/dev/null || date +%s) ))
    [[ -f "$LOCK_DIR/pid" ]] && owner="$(<"$LOCK_DIR/pid")"
    if [[ ! "$owner" =~ ^[0-9]+$ ]]; then
        # The owner may be between mkdir and writing its PID; only a crash leaves it like this for long.
        (( age > 600 ))
        return
    fi
    kill -0 "$owner" 2>/dev/null || return 0
    # PIDs are reused (e.g. after a reboot): a live PID only counts if it is still this script.
    ps -p "$owner" -o command= 2>/dev/null | grep -Fq 'resign.sh' || return 0
    # A healthy run takes minutes; anything older than 4 h is wedged (e.g. a keychain prompt).
    (( age > 14400 ))
}

acquire_lock() {
    if mkdir "$LOCK_DIR" 2>/dev/null; then
        LOCK_ACQUIRED=1
    else
        lock_is_stale || return 1
        rm -f "$LOCK_DIR/pid" "$LOCK_DIR/run"
        rmdir "$LOCK_DIR" 2>/dev/null || return 1
        mkdir "$LOCK_DIR" 2>/dev/null || return 1
        LOCK_ACQUIRED=1
    fi
    printf '%s\n' "$$" >"$LOCK_DIR/pid"
    printf '%s\n' "$RUN_ID" >"$LOCK_DIR/run"
}

if ! acquire_lock; then
    log "跳过：另一个 Shuttl 续签任务正在运行。"
    exit 0
fi

if [[ ! -d "$PROJECT" ]]; then
    log "失败：找不到工程 $PROJECT"
    exit 1
fi

# Do not compete with a developer's build. The lock above also serializes our own runs.
IOS_DIR_PHYSICAL="$(cd "$IOS_DIR" 2>/dev/null && pwd -P || printf '%s' "$IOS_DIR")"
other_project_build_running() {
    local pid command_line cwd
    for pid in $(pgrep -x xcodebuild 2>/dev/null || true); do
        [[ "$pid" == "$$" ]] && continue
        # launchd gives us no locale; plain `ps` then prints the CJK path as M-e... escapes.
        command_line="$(LC_ALL=en_US.UTF-8 ps -p "$pid" -o command= 2>/dev/null || true)"
        # lsof also escapes non-ASCII (\xe5...) without a UTF-8 locale, and reports the physical path.
        cwd="$(LC_ALL=en_US.UTF-8 lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)"
        # Only this checkout counts: a bare "Shuttl.xcodeproj" also matches other agents'
        # mirror copies (e.g. /tmp/ios-mirror) and would postpone renewal indefinitely.
        if [[ "$command_line" == *"$PROJECT_ROOT"* || ( -n "$cwd" && "$cwd" == "$IOS_DIR_PHYSICAL"* ) ]]; then
            return 0
        fi
    done
    return 1
}

profile_expiry_from_app() {
    local app="$1"
    local plist
    plist="$(mktemp "${TMPDIR:-/tmp}/shuttl-app-profile.XXXXXX")"
    if ! security cms -D -i "$app/embedded.mobileprovision" >"$plist" 2>/dev/null; then
        rm -f "$plist"
        return 1
    fi
    local app_id team expiry
    app_id="$(plutil -extract Entitlements.application-identifier raw -o - "$plist" 2>/dev/null || true)"
    team="$(plutil -extract TeamIdentifier.0 raw -o - "$plist" 2>/dev/null || true)"
    expiry="$(plutil -extract ExpirationDate raw -o - "$plist" 2>/dev/null || true)"
    rm -f "$plist"
    [[ "$app_id" == "$DEVELOPMENT_TEAM.$BUNDLE_ID" && "$team" == "$DEVELOPMENT_TEAM" && -n "$expiry" ]] || return 1
    date -j -u -f '%Y-%m-%dT%H:%M:%SZ' "$expiry" '+%s' 2>/dev/null || return 1
}

format_expiry() {
    local epoch="$1"
    date -r "$epoch" '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null || printf '%s' "$epoch"
}

# Snapshots are named Shuttl-<YYYYmmdd-HHMMSS>-<pid>.app, so name order is install order.
# (Directory mtimes are copied from the source by ditto and cannot be used.)
find_latest_snapshot() {
    local candidate epoch
    while IFS= read -r candidate; do
        epoch="$(profile_expiry_from_app "$candidate" 2>/dev/null || true)"
        if [[ -n "$epoch" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done < <(find "$SNAPSHOT_DIR" -maxdepth 1 -type d -name 'Shuttl-*.app' 2>/dev/null | sort -r)
    return 1
}

# Newest by the main executable's mtime (codesign rewrites it, so a re-signed snapshot
# counts as new as the moment it was signed).
find_last_local_app() {
    local candidate best=""
    while IFS= read -r -d '' candidate; do
        [[ -f "$candidate/Info.plist" && -x "$candidate/Shuttl" ]] || continue
        if [[ -z "$best" || "$candidate/Shuttl" -nt "$best/Shuttl" ]]; then
            best="$candidate"
        fi
    done < <(
        find "$SNAPSHOT_DIR" -maxdepth 1 -type d -name 'Shuttl-*.app' -print0 2>/dev/null
        find "$IOS_DIR/build" -path "*/${CONFIGURATION}-iphoneos/Shuttl.app" ! -path "$IOS_DIR/build/resign/*" -type d -print0 2>/dev/null
    )
    [[ -n "$best" ]] && printf '%s\n' "$best"
}

installed_identity_sha1s() {
    security find-identity -v -p codesigning 2>/dev/null | awk '{print $2}' | grep -E '^[0-9A-F]{40}$' || true
}

# SHA-1 of every certificate embedded in a decoded profile plist.
profile_cert_sha1s() {
    local plist="$1" i=0 b64
    b64="$(mktemp "${TMPDIR:-/tmp}/shuttl-cert.XXXXXX")"
    while plutil -extract "DeveloperCertificates.$i" raw -o - "$plist" >"$b64" 2>/dev/null; do
        base64 -D -i "$b64" 2>/dev/null | shasum -a 1 2>/dev/null | awk '{print toupper($1)}'
        i=$((i + 1))
    done
    rm -f "$b64"
}

profile_is_valid_for_app() {
    local profile="$1"
    local plist="$2"
    local app_id team expiry provisioned_device
    security cms -D -i "$profile" >"$plist" 2>/dev/null || return 1
    app_id="$(plutil -extract Entitlements.application-identifier raw -o - "$plist" 2>/dev/null || true)"
    team="$(plutil -extract TeamIdentifier.0 raw -o - "$plist" 2>/dev/null || true)"
    expiry="$(plutil -extract ExpirationDate raw -o - "$plist" 2>/dev/null || true)"
    provisioned_device="$(plutil -extract ProvisionedDevices xml1 -o - "$plist" 2>/dev/null || true)"
    [[ "$app_id" == "$DEVELOPMENT_TEAM.$BUNDLE_ID" && "$team" == "$DEVELOPMENT_TEAM" && -n "$expiry" ]] || return 1
    [[ "$(date -j -u -f '%Y-%m-%dT%H:%M:%SZ' "$expiry" '+%s' 2>/dev/null || printf 0)" -gt "$(now_epoch)" ]] || return 1
    printf '%s\n' "$provisioned_device" | grep -Fq "$DEVICE_UDID" || return 1
    # A profile whose certificate is not in this keychain cannot be signed with:
    # the app would be rejected by the phone even though codesign succeeds.
    local sha installed
    installed="$(installed_identity_sha1s)"
    [[ -n "$installed" ]] || return 1
    for sha in $(profile_cert_sha1s "$plist"); do
        if printf '%s\n' "$installed" | grep -Fxq "$sha"; then
            return 0
        fi
    done
    return 1
}

find_newest_profile() {
    local profile plist candidate expiry epoch best_epoch=0 best=""
    while IFS= read -r -d '' profile; do
        plist="$(mktemp "${TMPDIR:-/tmp}/shuttl-profile.XXXXXX")"
        if profile_is_valid_for_app "$profile" "$plist"; then
            expiry="$(plutil -extract ExpirationDate raw -o - "$plist" 2>/dev/null || true)"
            epoch="$(date -j -u -f '%Y-%m-%dT%H:%M:%SZ' "$expiry" '+%s' 2>/dev/null || printf 0)"
            if (( epoch > best_epoch )); then
                best_epoch=$epoch
                best="$profile"
            fi
        fi
        rm -f "$plist"
    done < <(find "$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles" -maxdepth 1 -type f -name '*.mobileprovision' -print0 2>/dev/null)
    [[ -n "$best" ]] || return 1
    printf '%s\n' "$best"
}

# Prefer the identity that matches the chosen profile's certificate (its SHA-1 is a valid
# codesign identity argument); fall back to the first Apple Development identity.
choose_identity() {
    local sha installed
    installed="$(installed_identity_sha1s)"
    for sha in $PROFILE_CERT_SHA1S; do
        if printf '%s\n' "$installed" | grep -Fxq "$sha"; then
            printf '%s\n' "$sha"
            return 0
        fi
    done
    local identity_line
    identity_line="$(security find-identity -v -p codesigning 2>/dev/null | awk -F'"' '/Apple Development:/{print $2; exit}')"
    [[ -n "$identity_line" ]] || return 1
    printf '%s\n' "$identity_line"
}

check_device() {
    local output state
    output="$(xcrun devicectl list devices 2>&1)" || {
        log "手机不可达：devicectl 查询失败。"
        return 1
    }
    # The State column is one word. Matching a substring treats "unavailable" as available.
    state="$(printf '%s\n' "$output" | awk -v id="$COREDEVICE_ID" '$0 ~ id {for (i=1;i<=NF;i++) if ($i==id) {print $(i+1); exit}}')"
    case "$state" in
        available|connected|ready) return 0 ;;
        "")
            log "手机不可达：devicectl 列表中没有该设备。"
            return 1 ;;
        *)
            log "手机不可达：设备状态为 ${state}。"
            return 1 ;;
    esac
}

# Look for the usual "your Xcode login expired" signatures in this run's xcodebuild output.
account_problem_hint() {
    if grep -qE "No Account for Team|no signing certificate|No profiles for|requires a development team|Your session has expired|not logged in|Communication with Apple failed|Failed to register bundle identifier" "$RUN_LOG" 2>/dev/null; then
        printf '%s' "可能是 Xcode 里的 Apple ID 登录已过期：打开 Xcode → Settings → Accounts 重新登录。"
    fi
}

# At most one notification per 6 h, so an hourly check never spams the user.
warn_throttled() {
    local kind="$1" message="$2" stamp last=0 now
    stamp="$STATE_DIR/last-warned-$kind"
    now="$(now_epoch)"
    [[ -f "$stamp" ]] && last="$(<"$stamp")"
    [[ "$last" =~ ^[0-9]+$ ]] || last=0
    if (( now - last < 21600 )); then
        log "已跳过重复提醒（${kind}）。"
        return 0
    fi
    printf '%s\n' "$now" >"$stamp"
    notify_user "Shuttl" "$message"
    log "已发送提醒（${kind}）：${message}"
}

maybe_warn_unreachable() {
    local expiry="$1"
    local remaining=$((expiry - $(now_epoch)))
    if (( remaining < 86400 )); then
        warn_throttled unreachable "Shuttl 快要过期了：请把手机连上这台电脑（同一 Wi-Fi 或数据线）"
    fi
}

# The phone was reachable but we could not obtain a newer profile.
maybe_warn_cannot_renew() {
    local expiry="$1" reason="$2"
    local remaining=$((expiry - $(now_epoch)))
    if (( remaining < 86400 )); then
        warn_throttled cannot-renew "Shuttl 快要过期了，自动续期没成功：${reason}"
    fi
}

prepare_profile() {
    PROFILE_PATH="$(find_newest_profile 2>/dev/null || true)"
    [[ -n "$PROFILE_PATH" ]] || return 1
    PROFILE_PLIST="$(mktemp "${TMPDIR:-/tmp}/shuttl-profile-selected.XXXXXX")"
    security cms -D -i "$PROFILE_PATH" >"$PROFILE_PLIST" 2>/dev/null || return 1
    PROFILE_EXPIRY_TEXT="$(plutil -extract ExpirationDate raw -o - "$PROFILE_PLIST" 2>/dev/null || true)"
    PROFILE_EXPIRY_EPOCH="$(date -j -u -f '%Y-%m-%dT%H:%M:%SZ' "$PROFILE_EXPIRY_TEXT" '+%s' 2>/dev/null || printf 0)"
    PROFILE_CERT_SHA1S="$(profile_cert_sha1s "$PROFILE_PLIST" | tr '\n' ' ')"
    [[ "$PROFILE_EXPIRY_EPOCH" -gt "$(now_epoch)" ]] || return 1
    return 0
}

# Entitlements to re-sign with: take the app's own, so a re-sign never changes them
# (the profile's are broader, e.g. keychain-access-groups F878S66X7Q.*, which would
# move the Keychain access group the app writes tokens into).
entitlements_for_app() {
    local app="$1" out="$2"
    if codesign -d --entitlements - --xml "$app" 2>/dev/null | plutil -convert xml1 -o "$out" - 2>/dev/null; then
        if [[ "$(plutil -extract application-identifier raw -o - "$out" 2>/dev/null || true)" == "$DEVELOPMENT_TEAM.$BUNDLE_ID" ]]; then
            return 0
        fi
    fi
    plutil -extract Entitlements xml1 -o "$out" "$PROFILE_PLIST" 2>/dev/null || return 1
    log "提示：无法读取原 app 的 entitlements，改用 profile 中的 entitlements。"
    return 0
}

app_embedded_profile_uuid() {
    local app="$1" plist uuid=""
    plist="$(mktemp "${TMPDIR:-/tmp}/shuttl-emb.XXXXXX")"
    if security cms -D -i "$app/embedded.mobileprovision" >"$plist" 2>/dev/null; then
        uuid="$(plutil -extract UUID raw -o - "$plist" 2>/dev/null || true)"
    fi
    rm -f "$plist"
    printf '%s' "$uuid"
}

prune_snapshots() {
    local keep_recorded="" candidate count=0
    [[ -f "$STATE_DIR/last-installed-app" ]] && keep_recorded="$(<"$STATE_DIR/last-installed-app")"
    while IFS= read -r candidate; do
        [[ "$candidate" == "$keep_recorded" ]] && continue
        count=$((count + 1))
        if (( count > SNAPSHOT_KEEP )); then
            rm -rf "$candidate"
        fi
    done < <(find "$SNAPSHOT_DIR" -maxdepth 1 -type d -name 'Shuttl-*.app' 2>/dev/null | sort -r)
}

resign_app() {
    local app="$1"
    local entitlements="$2"
    local item
    [[ -d "$app" ]] || return 1
    cp -f "$PROFILE_PATH" "$app/embedded.mobileprovision" || return 1

    # Sign nested code before the app bundle. Preserve the profile's entitlements for the app.
    while IFS= read -r -d '' item; do
        codesign --force --sign "$IDENTITY" --timestamp=none "$item" >>"$RUN_LOG" 2>&1 || return 1
    done < <(find "$app" -depth \( -name '*.dylib' -o -name '*.framework' -o -name '*.appex' -o -name '*.xpc' \) -print0 2>/dev/null)
    codesign --force --sign "$IDENTITY" --entitlements "$entitlements" --timestamp=none "$app" >>"$RUN_LOG" 2>&1 || return 1
    codesign --verify --deep --strict --verbose=2 "$app" >>"$RUN_LOG" 2>&1 || return 1
    return 0
}

copy_snapshot() {
    local app="$1"
    local snapshot="$SNAPSHOT_DIR/Shuttl-$RUN_ID.app"
    if ! ditto "$app" "$snapshot"; then
        log "失败：无法保存成功安装快照 ${snapshot}。"
        return 1
    fi
    printf '%s\n' "$snapshot" >"$STATE_DIR/last-installed-app"
    printf '%s\n' "$PROFILE_EXPIRY_EPOCH" >"$STATE_DIR/last-expiration-epoch"
    printf '%s\n' "$PROFILE_EXPIRY_TEXT" >"$STATE_DIR/last-expiration"
    printf '%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >"$STATE_DIR/last-installed-at"
    printf '%s\n' "$snapshot" 
}

install_and_verify() {
    local app="$1"
    local install_output
    install_output="$(xcrun devicectl device install app --device "$COREDEVICE_ID" "$app" 2>&1)" || {
        log "安装失败。"
        printf '%s\n' "$install_output" >>"$RUN_LOG"
        return 1
    }
    printf '%s\n' "$install_output" >>"$RUN_LOG"
    if ! xcrun devicectl device info apps --device "$COREDEVICE_ID" 2>>"$RUN_LOG" | grep -Fq "$BUNDLE_ID"; then
        log "安装后验证失败：设备上找不到 ${BUNDLE_ID}。"
        return 1
    fi
    return 0
}

launch_app() {
    xcrun devicectl device process launch --device "$COREDEVICE_ID" "$BUNDLE_ID" >>"$RUN_LOG" 2>&1
}

log "开始检查（force=${FORCE}）。"

# The recorded install is authoritative. find_latest_snapshot compares directory mtimes,
# which ditto copies from the source, so it can pick an older snapshot.
LAST_APP=""
if [[ -f "$STATE_DIR/last-installed-app" ]]; then
    LAST_APP="$(<"$STATE_DIR/last-installed-app")"
fi
if [[ -z "$LAST_APP" || ! -d "$LAST_APP" ]]; then
    LAST_APP="$(find_latest_snapshot 2>/dev/null || true)"
fi
if [[ -z "$LAST_APP" || ! -d "$LAST_APP" ]]; then
    # A pre-existing local build is useful for fallback, but not an install record.
    LAST_APP="$(find_last_local_app 2>/dev/null || true)"
fi
INSTALL_RECORDED=0
if [[ -f "$STATE_DIR/last-installed-at" && -f "$STATE_DIR/last-installed-app" ]]; then
    RECORDED_APP="$(<"$STATE_DIR/last-installed-app")"
    [[ -d "$RECORDED_APP" ]] && INSTALL_RECORDED=1
fi
LAST_EXPIRY=""
if [[ -n "$LAST_APP" && -d "$LAST_APP" ]]; then
    LAST_EXPIRY="$(profile_expiry_from_app "$LAST_APP" 2>/dev/null || true)"
fi
if [[ -z "$LAST_EXPIRY" && -f "$STATE_DIR/last-expiration-epoch" ]]; then
    LAST_EXPIRY="$(<"$STATE_DIR/last-expiration-epoch")"
fi

NOW="$(now_epoch)"
[[ "$LAST_EXPIRY" =~ ^[0-9]+$ ]] || LAST_EXPIRY=""
NEEDS_REFRESH=0
if (( FORCE == 1 )); then
    NEEDS_REFRESH=1
    log "需要续签：收到 --force。"
elif (( INSTALL_RECORDED == 0 )); then
    NEEDS_REFRESH=1
    log "需要续签：没有成功安装记录。"
elif [[ -z "$LAST_EXPIRY" ]]; then
    NEEDS_REFRESH=1
    log "需要续签：成功安装快照中没有可读取的有效 profile。"
elif (( LAST_EXPIRY - NOW < 172800 )); then
    NEEDS_REFRESH=1
    log "需要续签：现有 profile 将在 $(format_expiry "$LAST_EXPIRY") 到期（少于 48 小时）。"
else
    log "无需续签：现有 profile 到期时间为 $(format_expiry "$LAST_EXPIRY")。"
    exit 0
fi

if ! check_device; then
    if [[ -n "$LAST_EXPIRY" ]]; then
        maybe_warn_unreachable "$LAST_EXPIRY"
    fi
    log "手机不可达，本次不构建、不安装；等待下一次运行。"
    exit 0
fi

# Only now (a build is actually due) do we yield to a developer's build; the next run retries.
if other_project_build_running; then
    log "跳过：检测到该 Shuttl 工程正在由另一个 xcodebuild 构建，下次运行再试。"
    exit 0
fi

# launchd jobs run /bin/bash without "Files and Folders" access to ~/Downloads: the
# directory is visible but every read fails with EPERM, so xcodebuild cannot run.
if ! head -c 1 "$PROJECT/project.pbxproj" >/dev/null 2>&1; then
    PROJECT_UNREADABLE=1
    log "无法读取工程文件（macOS 隐私权限：后台任务不能读取「下载」文件夹）。跳过构建，只尝试 fallback。"
fi

RESIGN_ONLY="${SHUTTL_RESIGN_TEST_FALLBACK:-0}"
BUILT_APP=""
BUILD_STATUS=1
if [[ "$RESIGN_ONLY" == "1" ]]; then
    log "测试模式：跳过 xcodebuild，直接验证 fallback 重新签名路径。"
elif (( PROJECT_UNREADABLE == 1 )); then
    :
else
    # Remove per-run derived-data dirs left by earlier versions of this script (only names it generated).
    for old in "$IOS_DIR/build/resign"/*; do
        [[ -d "$old" && "$(basename "$old")" =~ ^[0-9]{8}-[0-9]{6}-[0-9]+$ ]] && rm -rf "$old"
    done
    log "开始构建：单独的 derived-data 路径 ${RESIGN_DERIVED_DATA}。"
    mkdir -p "$RESIGN_DERIVED_DATA"
    run_logged xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration "$CONFIGURATION" -destination "id=$DEVICE_UDID" -derivedDataPath "$RESIGN_DERIVED_DATA" -allowProvisioningUpdates DEVELOPMENT_TEAM="$DEVELOPMENT_TEAM"
    BUILD_STATUS=$?
    if (( BUILD_STATUS == 0 )); then
        BUILT_APP="$RESIGN_DERIVED_DATA/Build/Products/${CONFIGURATION}-iphoneos/Shuttl.app"
        if [[ ! -d "$BUILT_APP" ]]; then
            log "构建命令成功但没有找到产物，转入 fallback。"
            BUILD_STATUS=1
        else
            log "路径：xcodebuild 构建成功。"
        fi
    else
        log "路径：xcodebuild 失败（退出码 ${BUILD_STATUS}），检查是否有可用的最近成功 app。"
    fi
fi

# Xcode provisions before compiling. Search after xcodebuild so a failed build can
# still use a profile refreshed during its provisioning phase.
if ! prepare_profile; then
    log "失败：没有找到仍有效、属于 ${DEVELOPMENT_TEAM}/${BUNDLE_ID} 且包含该设备的最新 provisioning profile。"
    printf '%s\n' "profile search failed" >>"$RUN_LOG"
    exit 1
fi
IDENTITY="$(choose_identity 2>/dev/null || true)"
if [[ -z "$IDENTITY" ]]; then
    log "失败：security find-identity 没有可用的 Apple Development 身份。"
    exit 1
fi
log "使用 provisioning profile: ${PROFILE_PATH}（到期 $(format_expiry "$PROFILE_EXPIRY_EPOCH")）。"
log "使用签名身份: ${IDENTITY}。"

# Reinstalling with a profile that expires no later than the installed one renews nothing.
# (Expired Xcode login, TCC-blocked build, or Xcode still handing out the old profile.)
if (( FORCE == 0 && INSTALL_RECORDED == 1 )) && [[ -n "$LAST_EXPIRY" ]] && (( PROFILE_EXPIRY_EPOCH <= LAST_EXPIRY )); then
    REASON="$(account_problem_hint)"
    if [[ -z "$REASON" ]]; then
        if (( PROJECT_UNREADABLE == 1 )); then
            REASON="后台任务无权读取「下载」文件夹，请双击 tools/resign 里的「立即续签.command」。"
        else
            REASON="Xcode 还没有签发新的 profile，稍后自动重试。"
        fi
    fi
    log "未续签：找到的 profile 并不比已安装的新（$(format_expiry "$PROFILE_EXPIRY_EPOCH")）。${REASON}"
    maybe_warn_cannot_renew "$LAST_EXPIRY" "$REASON"
    exit 1
fi

if (( BUILD_STATUS != 0 )); then
    FALLBACK_APP="$LAST_APP"
    [[ -d "$FALLBACK_APP" ]] || FALLBACK_APP="$(find_last_local_app 2>/dev/null || true)"
    if [[ -z "$FALLBACK_APP" || ! -d "$FALLBACK_APP" ]]; then
        log "失败：构建失败且没有可重新签名的最近成功 .app。"
        exit 1
    fi
    FALLBACK_TMP="$(mktemp -d "${TMPDIR:-/tmp}/shuttl-fallback-app.XXXXXX")"
    BUILT_APP="$FALLBACK_TMP/Shuttl.app"
    if ! ditto "$FALLBACK_APP" "$BUILT_APP"; then
        log "失败：无法复制 fallback .app。"
        exit 1
    fi
    ENTITLEMENTS="$(mktemp "${TMPDIR:-/tmp}/shuttl-entitlements.XXXXXX")"
    entitlements_for_app "$BUILT_APP" "$ENTITLEMENTS" || {
        log "失败：无法取得 entitlements。"
        rm -f "$ENTITLEMENTS"
        exit 1
    }
    if ! resign_app "$BUILT_APP" "$ENTITLEMENTS"; then
        log "失败：fallback .app 重新签名失败。"
        rm -f "$ENTITLEMENTS"
        exit 1
    fi
    rm -f "$ENTITLEMENTS"
    log "路径：使用最新 profile 对最近成功的 .app 完成 fallback 重新签名。"
elif [[ "$(app_embedded_profile_uuid "$BUILT_APP")" == "$(plutil -extract UUID raw -o - "$PROFILE_PLIST" 2>/dev/null)" ]]; then
    # Xcode already embedded the newest profile and signed correctly: keep its signature.
    log "路径：xcodebuild 成功，已嵌入最新 profile，保留 Xcode 的签名。"
else
    # Xcode embedded an older profile than the newest one on disk: re-embed and re-sign.
    ENTITLEMENTS="$(mktemp "${TMPDIR:-/tmp}/shuttl-entitlements.XXXXXX")"
    entitlements_for_app "$BUILT_APP" "$ENTITLEMENTS" || {
        log "失败：无法取得 entitlements。"
        rm -f "$ENTITLEMENTS"
        exit 1
    }
    if ! resign_app "$BUILT_APP" "$ENTITLEMENTS"; then
        log "失败：构建产物重新签名/验证失败。"
        rm -f "$ENTITLEMENTS"
        exit 1
    fi
    rm -f "$ENTITLEMENTS"
    log "路径：xcodebuild 成功后，以最新有效 profile 重新嵌入并签名。"
fi

if ! install_and_verify "$BUILT_APP"; then
    [[ -n "$LAST_EXPIRY" ]] && maybe_warn_cannot_renew "$LAST_EXPIRY" "安装到手机失败，请解锁手机并保持连接。"
    exit 1
fi
if ! copy_snapshot "$BUILT_APP" >/dev/null; then
    exit 1
fi
SNAPSHOT="$(<"$STATE_DIR/last-installed-app")"
log "安装成功且已验证：${BUNDLE_ID}。"
log "已保存成功安装快照：${SNAPSHOT}。"
prune_snapshots
# Only launch on manual runs: an unattended renewal should not pop the app to the
# foreground while the user is doing something else on the phone.
if (( FORCE == 1 )); then
    if launch_app; then
        log "已启动 ${BUNDLE_ID}。"
    else
        log "警告：安装成功，但启动命令失败（手机可能锁屏）；安装快照已保留。"
    fi
fi
notify_user "Shuttl" "Shuttl 已自动续期到 $(format_expiry "$PROFILE_EXPIRY_EPOCH")"
log "本次续签完成。"
exit 0
