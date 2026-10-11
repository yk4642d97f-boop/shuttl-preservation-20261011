#!/usr/bin/env bash
# Usage: spotcheck.sh VIDEO FPS FRAME CX CY OUT.png [HALF]
# Crops a box around the hitter (CX,CY = labelled player_location in 1280x720 pixels, roughly the feet)
# and tiles frames FRAME-6 .. FRAME+7 (14 frames) into a 7x2 contact sheet; each tile is stamped
# with its absolute frame number, and the labelled frame is outlined in red.
set -euo pipefail
V=$1; FPS=$2; F=$3; CX=$4; CY=$5; OUT=$6; HALF=${7:-170}
S=$((F-6))
SS=$(python3 -c "print(f'{$S/$FPS:.6f}')")
X=$(python3 -c "print(max(0,min(1280-2*$HALF,int($CX)-$HALF)))")
Y=$(python3 -c "print(max(0,min(720-2*$HALF-60,int($CY)-int(1.5*$HALF))))")
W=$((2*HALF)); H=$((2*HALF+60))
ffmpeg -v error -y -ss "$SS" -i "$V" -vf \
"trim=end_frame=14,crop=$W:$H:$X:$Y,drawtext=text='%{eif\:n+$S\:d}':x=6:y=6:fontsize=26:fontcolor=yellow:box=1:boxcolor=black@0.6,\
drawbox=enable='eq(n,6)':x=0:y=0:w=iw:h=ih:color=red:t=6,tile=7x2:padding=4" -frames:v 1 -update 1 "$OUT"
