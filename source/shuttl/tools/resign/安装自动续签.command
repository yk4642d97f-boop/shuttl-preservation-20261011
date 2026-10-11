#!/bin/bash
# 双击运行：在「终端」里安装自动续签任务。
cd "$(dirname "$0")" && /bin/bash ./install.sh
echo; read -n 1 -s -r -p "按任意键关闭此窗口"
