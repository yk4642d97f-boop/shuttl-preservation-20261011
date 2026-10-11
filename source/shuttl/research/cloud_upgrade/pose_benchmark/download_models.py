"""Fetch/verify the two research candidates against the recorded SHA256 manifest.

Existing files must match; never overwrite weights. No Sapiens2 weights included.
"""
from pathlib import Path
import shutil
import urllib.request
import zipfile
import json
from adapters import HERE, sha


def main():
    root = HERE / 'models'
    manifest = json.loads((root / 'downloads.json').read_text())
    for row in manifest['files']:
        path = root / row['file']
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            tmp = path.with_suffix(path.suffix + '.part')
            with urllib.request.urlopen(row['source'], timeout=60) as source, tmp.open('xb') as dest:
                shutil.copyfileobj(source, dest)
            if tmp.stat().st_size != row['bytes'] or sha(tmp) != row['sha256']:
                raise ValueError(f'Download mismatch; partial file retained: {tmp}')
            tmp.rename(path)
        if path.stat().st_size != row['bytes'] or sha(path) != row['sha256']:
            raise ValueError(f'Existing weight/config mismatch: {path}')
        print('verified', row['file'], flush=True)
    with zipfile.ZipFile(root / 'rtmpose_x.zip') as z:
        for item in z.infolist():
            if item.is_dir():
                continue
            rel = Path(item.filename)
            if rel.is_absolute() or '..' in rel.parts or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Unsafe SDK entry')
            target = root / 'rtmpose_x' / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                with z.open(item) as source, target.open('xb') as dest:
                    shutil.copyfileobj(source, dest)
            # Compare decompressed content against the verified ZIP, including existing files.
            import hashlib
            h = hashlib.sha256()
            with z.open(item) as f:
                for b in iter(lambda: f.read(1 << 20), b''):
                    h.update(b)
            if target.stat().st_size != item.file_size or sha(target) != h.hexdigest():
                raise ValueError(f'Extracted SDK mismatch: {target}')
    print('verified extracted RTMPose-X SDK', flush=True)


if __name__ == '__main__':
    main()
