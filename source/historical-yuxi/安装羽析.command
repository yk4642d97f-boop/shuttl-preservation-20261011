#!/bin/bash
# ============================================================
#  羽析 · 一键安装 (只需要运行一次)
#  用法: 在"访达"里双击这个文件
# ============================================================
cd "$(dirname "$0")"
MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"

echo ""
echo "  🏸 羽析 · 安装程序"
echo "  ------------------------------------------"

# 1) 找 Python 3 (优先 Homebrew / 官网版, 其次系统自带)
PY=""
for c in "$HOME/.local/bin/python3.12" /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /usr/bin/python3; do
  if [ -x "$c" ] && "$c" -c "import sys; exit(0 if sys.version_info >= (3,9) else 1)" 2>/dev/null; then
    PY="$c"; break
  fi
done

if [ -z "$PY" ]; then
  echo ""
  echo "  ❗ 没有找到 Python 3。"
  echo "  如果屏幕上弹出了“安装命令行开发者工具”的窗口, 请点【安装】, 装完后再双击本文件。"
  echo "  如果没有弹窗, 请从国内镜像下载 Python 安装包 (选 macOS 的 .pkg):"
  echo "      https://registry.npmmirror.com/binary.html?path=python/3.12.8/"
  echo "  装好后再双击本文件。"
  /usr/bin/python3 --version >/dev/null 2>&1
  echo ""
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 1
fi
echo "  ✅ 使用 Python: $PY ($("$PY" --version 2>&1))"

# 2) 建立独立环境 (不影响电脑上的其他软件)
if [ ! -x ".venv/bin/python" ]; then
  echo "  ⏳ 创建运行环境..."
  "$PY" -m venv .venv || { echo "  ❌ 创建环境失败"; read -n 1 -s -r -p "  按任意键关闭..."; exit 1; }
fi

# 3) 安装依赖 (清华镜像, 约 300MB, 视网速需要几分钟)
echo "  ⏳ 安装依赖 (约 300MB, 请耐心等待几分钟)..."
.venv/bin/python -m pip install -q --upgrade pip -i "$MIRROR"
.venv/bin/python -m pip install -r backend/requirements.txt -i "$MIRROR" --progress-bar on
if [ $? -ne 0 ]; then
  echo ""
  echo "  ❌ 依赖安装失败。请把这个窗口的截图发给 Claude。"
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 1
fi

# 4) 自检: 模型能否加载、Apple 芯片加速是否可用
echo "  ⏳ 自检中..."
cd backend
../.venv/bin/python - <<'EOF'
import sys
try:
    import torch, cv2
    from engine.tracker import ShuttleTracker
    from engine.players import PlayerDetector, WEIGHTS
    t = ShuttleTracker()
    cv2.dnn.readNetFromONNX(WEIGHTS)
    dev = str(t.device)
    print(f"  ✅ 模型加载成功 | PyTorch {torch.__version__} | OpenCV {cv2.__version__} | 计算设备: {dev}")
    if dev == "mps":
        print("  🚀 已启用 Apple 芯片 GPU 加速")
except Exception as e:
    print("  ❌ 自检失败:", e)
    sys.exit(1)
EOF
OK=$?
cd ..
echo ""
if [ $OK -eq 0 ]; then
  echo "  🎉 安装完成! 以后每次使用, 双击【启动羽析.command】即可。"
else
  echo "  ❌ 自检没通过。请把这个窗口的截图发给 Claude。"
fi
echo ""
read -n 1 -s -r -p "  按任意键关闭..."
