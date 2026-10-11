#!/bin/bash
set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PLIST_SOURCE="$SCRIPT_DIR/com.shuttl.resign.plist"
LABEL="com.shuttl.resign"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
PLIST_DEST="$LAUNCH_AGENTS/$LABEL.plist"
STATE_DIR="$HOME/Library/Application Support/ShuttlResign"
RUNTIME_SCRIPT="$STATE_DIR/resign.sh"
LOG_FILE="$HOME/Library/Logs/shuttl-resign.log"
BACKUP_ROOT="$SCRIPT_DIR/../../.ui-backup/handoff-20260927"
BACKUP_PATH="$BACKUP_ROOT/tools/resign/com.shuttl.resign.plist"

mkdir -p "$LAUNCH_AGENTS" "$HOME/Library/Logs"

if [[ -e "$PLIST_DEST" && ! -L "$PLIST_DEST" ]]; then
    mkdir -p "$(dirname "$BACKUP_PATH")"
    if [[ ! -e "$BACKUP_PATH" ]]; then
        cp -p "$PLIST_DEST" "$BACKUP_PATH"
    fi
    if ! /usr/libexec/PlistBuddy -c "Print :Label" "$PLIST_DEST" 2>/dev/null | grep -Fxq "$LABEL"; then
        printf '%s\n' "安装停止：已有同名 LaunchAgent，不是 Shuttl 工具创建的文件；未覆盖。" >&2
        exit 1
    fi
fi
mkdir -p "$STATE_DIR"
if ! ditto "$SCRIPT_DIR/resign.sh" "$RUNTIME_SCRIPT"; then
    printf '%s\n' "安装失败：无法复制续签脚本到 ${STATE_DIR}。" >&2
    exit 1
fi
chmod 755 "$RUNTIME_SCRIPT"
if ! cp -f "$PLIST_SOURCE" "$PLIST_DEST"; then
    printf '%s\n' "安装失败：无法安装 LaunchAgent plist。" >&2
    exit 1
fi
plutil -lint "$PLIST_DEST" >/dev/null

launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
# bootout is asynchronous; an immediate bootstrap can fail with "Input/output error".
bootstrapped=0
for attempt in 1 2 3 4 5; do
    if launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST" 2>/dev/null; then
        bootstrapped=1
        break
    fi
    sleep 1
done
if (( bootstrapped == 0 )); then
    printf '%s\n' "安装失败：LaunchAgent 无法 bootstrap。" >&2
    exit 1
fi
launchctl enable "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true

printf '%s\n' "Shuttl 自动续签已安装。登录时、每 6 小时、以及每天每 3 小时（睡眠错过的在唤醒后补上）检查一次。"
if [[ "$SCRIPT_DIR" == "$HOME/Downloads"* || "$SCRIPT_DIR" == "$HOME/Desktop"* || "$SCRIPT_DIR" == "$HOME/Documents"* ]]; then
    printf '%s\n' "注意：工程在「下载/桌面/文稿」里，后台任务无权读取，无法自动重新构建；快过期时会提醒你双击「立即续签.command」。"
fi
printf '%s\n' "日志：$LOG_FILE"
printf '%s\n' "服务：launchctl print gui/$(id -u)/$LABEL"
