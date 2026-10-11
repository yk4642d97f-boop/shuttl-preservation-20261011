#!/bin/bash
# Resume detect from a clean 43200-frame checkpoint, SIGKILL 1 s after the next detect_partial save,
# then report whether background segment 15 changed. 3 trials.
cd "/Users/yangcong/Downloads/华北五省"
U=44444444-0000-0000-0000-000000000045
for t in 1 2 3; do
  d=/tmp/luna11/repro-bg/t$t; rm -rf $d; mkdir -p $d/checkpoints/$U
  cp /tmp/luna11/repro-bg/detect_partial.bin $d/checkpoints/$U/
  ENDURANCE_KILL="save_begin:detect_partial:1" /tmp/luna11/driver/release/EnduranceDriver analyze /tmp/luna11/clips/singles_45m.mp4 $d $U singles > $d/log.txt 2>&1
  echo "trial $t exit $?"; grep -E "load_end detect_partial|save_end detect_partial|SIGKILL" $d/log.txt | head -3
  /Users/yangcong/Downloads/华北五省/backend/.venv/bin/python /tmp/luna11/repro-bg/check.py /tmp/luna11/repro-bg/detect_partial.bin $d/checkpoints/$U/detect_partial.bin
done
echo REPRO-BG DONE
