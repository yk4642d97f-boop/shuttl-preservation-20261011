#!/bin/bash
# Usage: run_bfmd.sh WORKERS
N=${1:-10}; ROOT=/dev/shm/claude/bfmd
mkdir -p $ROOT/logs; cd /root/shuttl-claude-20261118; : > $ROOT/pids
for r in $(seq 0 $((N-1))); do
  setsid nohup /root/autodl-tmp/shuttl-5090-20261008/env/bin/python -u 13_extract_bfmd.py --root $ROOT --queue bfmd_segments.json \
    --videos $ROOT/videos --rank $r --world $N --mem-fraction 0.07 > $ROOT/logs/w$r.log 2>&1 < /dev/null &
  echo $! >> $ROOT/pids
done
echo launched $N
