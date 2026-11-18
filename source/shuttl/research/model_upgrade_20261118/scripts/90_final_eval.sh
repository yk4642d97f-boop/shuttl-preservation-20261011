#!/bin/bash
# Frozen evaluation of the candidates on development AND holdout data. Run once per frozen candidate set.
# Usage: 90_final_eval.sh BST_RUN HITNET_PT TAG
BST=$1; HIT=$2; TAG=$3
cd /root/shuttl-claude-20261118; PY=/root/autodl-tmp/shuttl-5090-20261008/env/bin/python; R=reports/$TAG; mkdir -p $R
$PY 40_eval.py --final --ref control17 --out $R/bst.json released control17 aux17 new=$BST > $R/bst.txt 2>&1
$PY 45_rally_decode.py --final --out=$R/rally_decode.json control17 new=$BST > $R/rally_decode.txt 2>&1
$PY 56_hit_eval.py --final --rules --out=$R/hit.json released new=$HIT > $R/hit.txt 2>&1
$PY 60_chain_eval.py --final --out=$R/chain.json rules+released=rules:released hitnet_v2+released=released:released rules+control17=rules:control17 new=$HIT:$BST > $R/chain.txt 2>&1
echo FINAL_EVAL_DONE > $R/done
