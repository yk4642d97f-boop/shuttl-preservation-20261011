"""Fetch pinned compatible wheels with curl and verify PyPI SHA256 metadata."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import urlsplit
from urllib.request import urlopen

from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import parse_wheel_filename

BASE = Path('/root/autodl-tmp/shuttl-20261007')
DEST = BASE / 'wheels'
DEST.mkdir(exist_ok=True)
TAGS = {tag: rank for rank, tag in enumerate(sys_tags())}


def fetch(pin):
    name, version = pin.split('==')
    source = f'https://pypi.org/pypi/{name}/{version}/json'
    with urlopen(source, timeout=30) as response:
        metadata = json.load(response)
    options = []
    for item in metadata['urls']:
        if not item['filename'].endswith('.whl'):
            continue
        tags = parse_wheel_filename(item['filename'])[3]
        ranks = [TAGS[tag] for tag in tags if tag in TAGS]
        if ranks and not item.get('yanked'):
            options.append((min(ranks), item))
    if not options:
        options = [(0, item) for item in metadata['urls'] if item['packagetype'] == 'sdist' and not item.get('yanked')]
    if not options:
        raise ValueError('No compatible distribution: ' + pin)
    item = min(options, key=lambda entry: entry[0])[1]
    target = DEST / item['filename']
    expected = item['digests']['sha256']
    def valid(path):
        if not path.exists() or path.stat().st_size != item['size']:
            return False
        with path.open('rb') as handle:
            return hashlib.file_digest(handle, 'sha256').hexdigest() == expected
    if target.exists() and not valid(target):
        raise ValueError('Existing wheel hash mismatch: ' + target.name)
    url = 'https://mirrors.aliyun.com/pypi' + urlsplit(item['url']).path
    if not target.exists():
        partial = target.with_name(target.name + '.part')
        result = subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                                 '--connect-timeout', '15', '--max-time', '240', '--retry', '2',
                                 '--output', str(partial), url])
        if result.returncode:
            raise RuntimeError('Wheel download failed: ' + pin)
        if not valid(partial):
            raise ValueError('Downloaded wheel hash mismatch: ' + pin)
        partial.rename(target)
    print('verified', pin, item['size'], flush=True)
    return dict(pin=pin, file=target.name, bytes=item['size'], sha256=expected, url=url, metadata=source)


if __name__ == '__main__':
    pins = [line.strip() for line in (BASE / 'incoming/requirements-overlay.txt').read_text().splitlines()
            if line.strip() and not line.startswith('#')]
    pins += ['rtmlib==0.0.16', 'ultralytics==8.2.103', 'llvmlite==0.43.0']
    with ThreadPoolExecutor(max_workers=4) as executor:
        rows = list(executor.map(fetch, pins))
    (DEST / 'verified.json').write_text(json.dumps(rows, indent=2) + '\n')
