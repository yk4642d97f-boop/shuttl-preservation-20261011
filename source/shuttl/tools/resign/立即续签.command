#!/bin/bash
# 双击运行：在「终端」里立即检查并续签（终端能读取「下载」文件夹，后台任务不能）。
cd "$(dirname "$0")" && /bin/bash ./resign.sh
echo; read -n 1 -s -r -p "按任意键关闭此窗口"
