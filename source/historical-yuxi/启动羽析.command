#!/bin/bash
# ============================================================
#  羽析 · 启动
#  用法: 双击这个文件; 用完后关掉这个终端窗口即可停止
# ============================================================
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/python" ]; then
  echo "  ❗ 还没有安装, 请先双击【安装羽析.command】"
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 1
fi

PORT=8000
IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)
export PYTORCH_ENABLE_MPS_FALLBACK=1   # 个别算子 Apple GPU 不支持时自动回退 CPU

echo ""
echo "  🏸 羽析 正在启动..."
echo "  ------------------------------------------"
echo "  电脑浏览器打开:  http://localhost:$PORT"
if [ -n "$IP" ]; then
  echo "  手机 (连同一个 Wi-Fi) 打开:  http://$IP:$PORT"
fi
echo "  关闭这个窗口 = 停止服务"
echo "  ------------------------------------------"
echo ""

( sleep 3; open "http://localhost:$PORT" ) &
cd backend
../.venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port $PORT
