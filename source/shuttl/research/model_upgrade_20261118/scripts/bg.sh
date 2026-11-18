#!/bin/bash
# Usage: bg.sh LOGNAME script.py args...   (runs detached in the experiment folder, logs to /dev/shm/claude/logs)
LOG=$1; shift
mkdir -p /dev/shm/claude/logs /dev/shm/claude/pids
cd /root/shuttl-claude-20261118
setsid nohup /root/autodl-tmp/shuttl-5090-20261008/env/bin/python -u "$@" > /dev/shm/claude/logs/$LOG.log 2>&1 < /dev/null &
echo $! > /dev/shm/claude/pids/$LOG.pid
echo started $LOG $!
