"""Verify frozen bundles, then record an explicit float32 CUDA source variant."""
import hashlib
import json
from pathlib import Path

base = Path('/root/autodl-tmp/shuttl-5090-20261008')
relative = 'backend/app/services/tracking/rtmpose_core.py'
source = base / 'incoming/rtmpose_core.py'

def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()

for folder, manifest_name in [('shuttl-runtime', 'RUNTIME_MANIFEST.json'),
                              ('pose-eval', 'pose-eval-manifest.json')]:
    root = base / folder
    manifest_path = root / manifest_name
    original = root / (manifest_name + '.original')
    if original.exists():
        raise FileExistsError('Overlay already applied: ' + folder)
    doc = json.loads(manifest_path.read_text())
    rows = doc['files']
    mapping = {r['path']: r for r in rows} if isinstance(rows, list) else rows
    for name, row in mapping.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or sha(path) != row['sha256']:
            raise ValueError('Original bundle hash mismatch: ' + name)
    old_sha = mapping[relative]['sha256']
    original.write_bytes(manifest_path.read_bytes())
    (root / relative).write_bytes(source.read_bytes())
    mapping[relative].update(bytes=source.stat().st_size, sha256=sha(source))
    doc['runtime_variant'] = dict(name='RTX5090 CUDA float32 pose',
                                 original_manifest_sha256=sha(original),
                                 changed_file=relative, original_source_sha256=old_sha,
                                 source_sha256=sha(source),
                                 reason='Explicit CUDA use_tf32=0; verified against frozen CPU reference')
    manifest_path.write_text(json.dumps(doc, indent=2) + '\n')
    print(folder, doc['runtime_variant'], flush=True)
