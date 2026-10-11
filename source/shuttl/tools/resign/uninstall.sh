#!/bin/bash
set -u

LABEL="com.shuttl.resign"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
RUNTIME_SCRIPT="$HOME/Library/Application Support/ShuttlResign/resign.sh"

launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
if [[ -f "$PLIST_DEST" ]]; then
    if /usr/libexec/PlistBuddy -c "Print :Label" "$PLIST_DEST" 2>/dev/null | grep -Fxq "$LABEL"; then
        rm -f "$PLIST_DEST"
    else
        printf '%s\n' "已停止服务，但保留了不是本工具创建的同名 LaunchAgent 文件。" >&2
    fi
fi
if [[ -f "$RUNTIME_SCRIPT" ]]; then
    rm -f "$RUNTIME_SCRIPT"
fi
printf '%s\n' "Shuttl 自动续签已卸载。已保留应用和续签日志。"
