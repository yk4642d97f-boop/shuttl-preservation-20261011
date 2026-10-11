"""Build an allowlisted local evaluation archive; no accounts, venv, or held-out data."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tarfile
import io

from adapters import HERE, ROOT, BASELINE, X_PATH, VIT_PATH, sha
import run  # enumerate the actual imported local Python modules
from panel import write_new


def main():
    target = ROOT / 'research/cloud_upgrade/dist/shuttl-pose-eval-v1.tar.gz'
    if target.exists():
        raise FileExistsError('Archive is immutable; choose a new version')
    panel = json.loads((HERE / 'panels/full.json').read_text())
    run.verify_manifest(panel)
    paths = {Path(m.__file__).resolve() for m in list(sys.modules.values())
             if getattr(m, '__file__', None) and Path(m.__file__).resolve().is_relative_to(ROOT)
             and 'site-packages' not in str(m.__file__) and str(m.__file__).endswith('.py')}
    paths.update(ROOT / name for name in {**panel['sources'], **panel['bst_weights']})
    # MatchFrames constructs the side map even though run uses already frozen event labels.
    paths.add(ROOT / 'research/shuttleset/labels/ShuttleSet/set/match.csv')
    paths.update(HERE.glob('*.py'))
    paths.update(HERE.glob('*.sh'))
    paths.update(HERE.glob('requirements*.txt'))
    paths.update(HERE.glob('*.md'))
    paths.update((HERE / 'panels').glob('*.json'))
    paths.update((HERE / 'sources').glob('*.txt'))
    paths.update((HERE / 'sources').glob('*.json'))
    paths.add(HERE / 'sapiens2_coco17_mapping.json')
    paths.add(HERE / 'checks/reference.npz')
    paths.add(HERE / 'checks/reference.json')
    paths.add(ROOT / 'research/bst/repo/LICENSE')
    paths.add(HERE / 'models/downloads.json')
    paths.update(VIT_PATH.glob('*'))
    paths.update(X_PATH.parent.glob('*.json'))
    paths.add(X_PATH)
    files = {str(p.relative_to(ROOT)): p for p in paths}
    files[str((HERE / 'models/rtmpose_m.onnx').relative_to(ROOT))] = BASELINE
    for name, path in files.items():
        if path.is_symlink() or not path.is_file() or '..' in Path(name).parts:
            raise ValueError('Not a regular allowlisted file: ' + name)
    manifest = dict(version=1, created_at=datetime.now(timezone.utc).isoformat(),
                    scope='Private local transfer archive for match041 pose comparison; not API/mobile deployment',
                    files={n: dict(bytes=p.stat().st_size, sha256=sha(p)) for n, p in sorted(files.items())})
    tmp = target.with_suffix('.tar.gz.part')
    target.parent.mkdir(exist_ok=True)
    with tmp.open('xb') as handle, tarfile.open(fileobj=handle, mode='w:gz', compresslevel=1) as tar:
        for name, path in sorted(files.items()):
            tar.add(path, arcname=name, recursive=False)
        raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
        info = tarfile.TarInfo('pose-eval-manifest.json')
        info.size, info.mode = len(raw), 0o600
        tar.addfile(info, io.BytesIO(raw))
    # Detect source edits during packaging before publishing the archive.
    for name, path in files.items():
        if sha(path) != manifest['files'][name]['sha256']:
            raise ValueError('Source changed while packaging: ' + name)
    tmp.rename(target)
    receipt = dict(file=target.name, bytes=target.stat().st_size, sha256=sha(target), files=len(files))
    write_new(target.with_suffix('.json'), receipt)
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
