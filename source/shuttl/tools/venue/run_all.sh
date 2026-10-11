#!/bin/bash
# run_all.sh — 一条命令跑完：拉取手机 → Mac 复算 → 叠加视频 → 标定检查图 → 中文报告并打开
#
# 用法：
#   ./run_all.sh                 # 拉取最新录像，每个视频只分析前 180 秒（快，够定位问题）
#   ./run_all.sh --full          # 完整分析（慢：1080p60 大约每 60 秒视频要 4 分钟）
#   ./run_all.sh 300             # 每个视频只分析前 300 秒
#   ./run_all.sh --dir <已拉取目录>   # 跳过拉取，直接用已有目录
#   ./run_all.sh --skip-pull     # 跳过拉取，用 data/ 里最新的目录
#
# 需要：手机用数据线连着 Mac 并且已解锁（否则 pull 会报错，但不会改动手机）。
set -uo pipefail
cd "$(dirname "$0")"

PY="$(pwd)/../../backend/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "错误：找不到 Python 环境 $PY" >&2
  exit 1
fi

MAX_SECONDS="180"
FULL=0
DIR=""
SKIP_PULL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --full) FULL=1 ;;
    --skip-pull) SKIP_PULL=1 ;;
    --dir) shift; DIR="${1:-}" ;;
    -h|--help)
      sed -n '2,14p' "$0"; exit 0 ;;
    ''|*[!0-9]*) echo "未知参数: $1（用 -h 看用法）" >&2; exit 2 ;;
    *) MAX_SECONDS="$1" ;;
  esac
  shift
done

if [ -n "$DIR" ]; then
  PULLED="$(cd "$DIR" && pwd)"
  echo "== 使用已有目录 $PULLED"
elif [ "$SKIP_PULL" = "1" ]; then
  PULLED="$(ls -td data/*/ 2>/dev/null | grep -v '/_' | head -1)"
  if [ -z "$PULLED" ]; then echo "错误：data/ 下没有已拉取的目录，请先运行 ./run_all.sh" >&2; exit 1; fi
  PULLED="$(cd "$PULLED" && pwd)"
  echo "== 跳过拉取，使用最新目录 $PULLED"
else
  echo "== 第 1 步 / 5：从手机拉取录像（只读，不会删除手机上的文件）"
  "$PY" pull.py || { echo "错误：拉取失败（手机是否已连接并解锁？）" >&2; exit 1; }
  PULLED="$(ls -td data/*/ 2>/dev/null | grep -v '/_' | head -1)"
  PULLED="$(cd "$PULLED" && pwd)"
fi

shopt -s nullglob
if ! ls "$PULLED"/Documents/Matches/*.mov "$PULLED"/Documents/Matches/*.mp4 >/dev/null 2>&1; then
  echo
  echo "没有找到任何录像（$PULLED/Documents/Matches 是空的）。"
  echo "如果手机上还没有录像，今晚就不用分析了；拍完之后再运行一次 ./run_all.sh。"
  exit 0
fi

echo
echo "== 第 2 步 / 5：在 Mac 上复算（$([ "$FULL" = "1" ] && echo 完整 || echo "每个视频前 ${MAX_SECONDS} 秒")）"
if [ "$FULL" = "1" ]; then
  "$PY" analyze.py "$PULLED"
else
  "$PY" analyze.py "$PULLED" --max-seconds "$MAX_SECONDS"
fi
ANALYZE_RC=$?
[ $ANALYZE_RC -ne 0 ] && echo "警告：analyze 有失败项，继续生成报告" >&2

echo
echo "== 第 3 步 / 5：生成诊断叠加视频"
VIDEOS=()
for v in "$PULLED"/Documents/Matches/*.mov "$PULLED"/Documents/Matches/*.mp4; do
  [ -f "$v" ] || continue
  case "$(basename "$v")" in
    *_overlay.*) continue ;;                # 我们自己生成的叠加视频
    .*) continue ;;
  esac
  VIDEOS+=("$v")
done
if [ ${#VIDEOS[@]} -eq 0 ]; then
  echo "警告：没有找到录像文件，跳过叠加视频" >&2
fi
for v in "${VIDEOS[@]}"; do
  a="${v%.*}.mac_analysis.json"
  if [ ! -f "$a" ]; then
    echo "  跳过 $(basename "$v")（没有 Mac 分析结果）"
    continue
  fi
  echo "  → $(basename "$v")"
  "$PY" overlay.py "$v" "$a" || echo "  警告：$(basename "$v") 叠加视频失败" >&2
done

echo
echo "== 第 4 步 / 5：生成标定检查图"
for v in "${VIDEOS[@]}"; do
  a="${v%.*}.mac_analysis.json"
  [ -f "$a" ] || continue
  echo "  → $(basename "$v")"
  "$PY" calib_sheet.py "$v" "$a" || echo "  警告：$(basename "$v") 标定图失败" >&2
done

echo
echo "== 第 5 步 / 5：生成中文报告"
"$PY" report.py "$PULLED" --open || { echo "错误：报告生成失败" >&2; exit 1; }

echo
echo "全部完成。报告：$PULLED/report.html"
