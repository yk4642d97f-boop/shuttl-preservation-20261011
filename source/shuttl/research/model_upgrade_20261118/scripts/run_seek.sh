#!/bin/bash
# Usage: run_seek.sh NAME QUEUE ROOT VIDEOS WORKERS
NAME=$1; QUEUE=$2; ROOT=$3; VIDEOS=$4; N=${5:-8}
for r in $(seq 0 $((N-1))); do
  bash /root/shuttl-claude-20261118/bg.sh ${NAME}_w$r 15_extract_seek.py --root $ROOT --queue $QUEUE --videos $VIDEOS --rank $r --world $N --mem-fraction 0.07
done
