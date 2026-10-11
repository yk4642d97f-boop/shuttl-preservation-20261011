"""Freeze a deterministic match041 validation panel before candidate inference."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import sys

from adapters import HERE, ROOT, sha
sys.path.insert(0, str(HERE.parent))
import stroke_chain as R


def write_new(path, obj):
    with Path(path).open('x', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def select(events, per_class):
    """Selection uses only stable identifiers and labels; never model outcomes."""
    result = []
    for cls in range(1, 25):
        group = [e for e in events if e['class'] == cls]
        group.sort(key=lambda e: hashlib.sha256(('pose-panel-v1|' + e['id']).encode()).hexdigest())
        result.extend(group if per_class == 0 else group[:per_class])
    return sorted(result, key=lambda e: e['id'])


def freeze():
    frames = R.MatchFrames('041')
    # Directory names supply official classes; no train/test feature files read.
    official = {p.name[:-11]: d.name for d in sorted((Path(R.CV.OFFICIAL_RAW) / 'val').iterdir())
                for p in sorted(d.glob('41_*_joints.npy'))}
    events = []
    for rally in R.E.C.load_match('041')['rallies']:
        for i, label in enumerate(frames.labels(rally, official)):
            events.append(dict(label, id=f"041/{rally['set']}/{rally['rally']}/{label['frame']}/{i}"))
    inputs = [ROOT / 'research/extract/out/041.npz', ROOT / 'research/rtmpose/pose/041.npz',
              ROOT / 'research/shuttleset/videos/041.mp4', *sorted(frames.label_dir.glob('*.csv'))]
    sources = {str(p.relative_to(ROOT)): sha(p) for p in inputs}
    bst = {str(Path(p).relative_to(ROOT)): sha(p) for p in R.B.WEIGHTS}
    if len(bst) != 10:
        raise ValueError('Requires the frozen ten-model BST ensemble')
    (HERE / 'panels').mkdir(exist_ok=True)
    write_new(HERE / 'panels/official_val_labels.json', official)
    for name, n in [('small', 2), ('full', 0)]:
        selected = select(events, n)
        data = dict(version=1, created_at=datetime.now(timezone.utc).isoformat(), match='041',
                    split='existing validation, not blind test', classes=R.B.CLASSES, fps=frames.fps,
                    selection='SHA256(pose-panel-v1|id), at most two per known class' if n else 'all known validation labels',
                    per_class=n, events=selected, source_known=sum(e['class'] > 0 for e in events),
                    source_unknown=sum(e['class'] == 0 for e in events),
                    support=dict(Counter(e['class'] for e in selected)), sources=sources, bst_weights=bst,
                    official_labels_sha256=sha(HERE / 'panels/official_val_labels.json'),
                    protocol=dict(window='hit +/- round(fps)//2, available original extraction frames, no shift',
                                  normalization='original unpadded player_box, far-first',
                                  other_features='fixed reference pos/shuttle; only joints/pose availability change',
                                  abstention='missing window/pose/no resolved players or class 0; retained in denominator',
                                  inference='native preprocessing, no flip, frozen ten-model mean logits',
                                  primary='macro recall over supported known 25-class labels, abstentions count as wrong',
                                  scope='classification at labeled hits; not hit detection, end-to-end F1, pose AP, or doubles'))
        write_new(HERE / 'panels' / f'{name}.json', data)
        print(name, len(selected), 'clips', data['support'], flush=True)


if __name__ == '__main__':
    freeze()
