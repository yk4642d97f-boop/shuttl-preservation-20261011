"""Exploratory plots: per-clip time series used to design a label-free contact-frame estimator."""
import json, sys, numpy as np
from pathlib import Path
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
root = Path('/dev/shm/claude/vb'); q = json.loads(Path('/root/shuttl-claude-20261118/vb_queue.json').read_text())
classes = sys.argv[1].split(',') if len(sys.argv) > 1 else ['05_Drop Shot', '08_Cut', '14_Smash', '12_Clear', '02_Lift', '00_Short Serve']
per = int(sys.argv[2]) if len(sys.argv) > 2 else 4
fig, axes = plt.subplots(len(classes), per, figsize=(5 * per, 3.2 * len(classes)), squeeze=False)
for ci, cl in enumerate(classes):
    rows = [r for r in q if r['raw_class'] == cl and (root / 'feat' / (r['id'] + '.npz')).exists()]
    rows = rows[:: max(1, len(rows) // per)][:per]
    for k, r in enumerate(rows):
        z = np.load(root / 'feat' / (r['id'] + '.npz')); ax = axes[ci][k]
        n = int(z['meta'][3]); H = z['meta'][2]; W = z['meta'][1]; t = np.arange(n)
        xy = z['xy'].astype(float); vis = z['visible']
        y = np.where(vis, xy[:, 1] / H, np.nan); x = np.where(vis, xy[:, 0] / W, np.nan)
        ax.plot(t, y, 'k.-', label='shuttle y'); ax.plot(t, x, 'c.-', alpha=.5, label='shuttle x')
        kp = z['kp'].astype(float); box = z['box'].astype(float)
        for p, col in ((0, 'tab:blue'), (1, 'tab:red')):
            wr = kp[:, p, 9:11, :2]; hgt = box[:, p, 3] - box[:, p, 1]
            sp = np.linalg.norm(np.diff(wr, axis=0), axis=-1).max(1) / np.maximum(hgt[1:], 1)
            ax.plot(t[1:], sp, color=col, label=('far' if p == 0 else 'near') + ' wrist speed/h')
            cy = (box[:, p, 1] + box[:, p, 3]) / 2 / H
            ax.plot(t, cy, color=col, ls=':', alpha=.6)
        ax.set_title(f"{cl} {r['id'][:6]} n={n} pl={r['player']} {r['date'][5:]}", fontsize=9); ax.set_ylim(-.05, 1.05)
        if ci == 0 and k == 0: ax.legend(fontsize=6)
plt.tight_layout(); out = '/root/shuttl-claude-20261118/contact_explore.png'; plt.savefig(out, dpi=70); print(out)
