#!/bin/bash
# 双击运行：移除自动续签任务（不删除手机上的 Shuttl 和比赛记录）。
cd "$(dirname "$0")" && /bin/bash ./uninstall.sh
echo; read -n 1 -s -r -p "按任意键关闭此窗口"
