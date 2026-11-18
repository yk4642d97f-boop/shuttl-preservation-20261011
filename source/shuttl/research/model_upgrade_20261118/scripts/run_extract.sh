#!/bin/bash
# Launch N extraction workers detached; record pids. Usage: run_extract.sh SCRIPT QUEUE ROOT WORKERS
SCRIPT=$1; QUEUE=$2; ROOT=$3; N=${4:-8}
mkdir -p $ROOT/logs
cd /root/shuttl-claude-20261118
: > $ROOT/pids
for r in $(seq 0 $((N-1))); do
  setsid nohup /root/autodl-tmp/shuttl-5090-20261008/env/bin/python -u $SCRIPT --root $ROOT --queue $QUEUE \
    --zip /dev/shm/claude/VideoBadminton_Dataset.zip --rank $r --world $N > $ROOT/logs/w$r.log 2>&1 < /dev/null &
  echo $! >> $ROOT/pids
done
echo launched $N
