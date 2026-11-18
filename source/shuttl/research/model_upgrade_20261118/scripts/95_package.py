"""Package the frozen candidates as drop-in artifacts and verify them with the runtime's own loaders.
Usage: 95_package.py BST_RUN HITNET_PT"""
import hashlib, json, shutil, sys
from pathlib import Path
import numpy as np, torch
sys.path.insert(0, '/root/autodl-tmp/shuttl-5090-20261008/shuttl-runtime/backend')
import bstlib as bo
run, hit = Path('/dev/shm/claude/runs') / sys.argv[1], Path(sys.argv[2])
dst = Path('/root/shuttl-claude-20261118/models'); bdir = dst / 'bst_seq30_20261118'; hdir = dst / 'hitnet_20261118'
for d in (bdir, hdir): d.mkdir(parents=True, exist_ok=True)
src = json.loads((bo.ART / 'manifest.json').read_text()); weights = []
for i in range(10):
    name = f'bst_CG_AP_seq30_20261118_m{i}.pt'; shutil.copyfile(run / f'member-{i}.pt', bdir / name)
    weights.append(dict(file=name, sha256=hashlib.sha256((bdir / name).read_bytes()).hexdigest(), initialised_from=src['weights'][i]['file'],
                        selected_epoch=json.loads((run / f'member-{i}.json').read_text())['best_epoch']))
manifest = dict(architecture=src['architecture'], classes=src['classes'], ensemble=src['ensemble'], weights=weights,
                scope='singles only; candidate trained 2026-11-18, not deployed', training=json.loads((run / 'config.json').read_text()))
(bdir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
shutil.copyfile(bo.ART / 'LICENSE', bdir / 'LICENSE')
shutil.copyfile(hit, hdir / 'hitnet_single_v3_20261118.pt')
(hdir / 'hitnet_single_v3_20261118.json').write_text(json.dumps(dict(file='hitnet_single_v3_20261118.pt', sha256=hashlib.sha256((hdir / 'hitnet_single_v3_20261118.pt').read_bytes()).hexdigest(),
    decoder=dict(thr=.4, gap_s=.3, lam=0.0), arch='tcn', n_in=51, initialised_from='hitnet_single_v2.pt', scope='singles hit detection candidate; not deployed'), indent=2))
# verification with the runtime loaders (same contracts production enforces)
from app.services.tracking import bst as rt_bst, hitnet as rt_hit
model = rt_bst.BST(bdir / 'manifest.json', device='cuda')
vj, vs, vp, vl, vy = bo.load_split('val')
mine = bo.logits_of(model.nets, (vj, vs, vp, vl)); print('runtime BST loader ok; members', len(model.nets), 'val acc12', round(bo.pro_metrics(mine, vy)['acc12'], 4))
h = rt_hit.HitNet(hdir / 'hitnet_single_v3_20261118.pt', device='cuda'); print('runtime HitNet loader ok; decoder', h.decoder)
print(json.dumps(dict(bst=str(bdir), hitnet=str(hdir))))
