#!/usr/bin/env python3
"""Upload this specific private backup and verify every delivery asset by download."""
import argparse
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import threading
import time

OWNER = 'yk4642d97f-boop'
REPO = OWNER + '/shuttl-preservation-20261011'
TAG = 'backup-20261011'
GH_ENV = dict(os.environ, GH_HOST='github.com')


def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, env=GH_ENV, **kwargs)


def output(args, **kwargs):
    return subprocess.check_output(args, text=True, env=GH_ENV, **kwargs)


def api(path):
    return json.loads(output(['gh', 'api', path]))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def durable_json(path, data):
    partial = path.with_suffix(path.suffix + '.partial')
    if os.path.lexists(partial):
        partial.unlink()
    with partial.open('x') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    partial.replace(path)
    fd = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def local_asset(path, expected=None):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise RuntimeError('Asset must be a regular file, not a symlink: ' + path.name)
    actual = {'name': path.name, 'sha256': sha(path), 'bytes': path.stat().st_size}
    if expected and (actual['sha256'] != expected['sha256'] or actual['bytes'] != expected['bytes']):
        raise RuntimeError('Local asset mismatch: ' + path.name)
    return actual


class RemoteDownloadError(RuntimeError):
    """A transfer failed before its content could be checked."""


def remote_sha_once(asset_id):
    h, size = hashlib.sha256(), 0
    try:
        with subprocess.Popen(['gh', 'api', f'repos/{REPO}/releases/assets/{asset_id}',
                               '-H', 'Accept: application/octet-stream'],
                              stdout=subprocess.PIPE, env=GH_ENV) as process:
            for block in iter(lambda: process.stdout.read(8 * 1024 * 1024), b''):
                h.update(block)
                size += len(block)
            if process.wait() != 0:
                raise RemoteDownloadError('Remote download failed for asset ' + str(asset_id))
    except OSError as exc:
        raise RemoteDownloadError('Remote download failed for asset ' + str(asset_id)) from exc
    return h.hexdigest(), size


def remote_sha(asset_id):
    # Retry a broken download without replacing a correctly uploaded large file.
    for attempt in range(3):
        try:
            return remote_sha_once(asset_id)
        except RemoteDownloadError:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))
    raise AssertionError('unreachable')


def private_destination():
    details = api(f'repos/{REPO}')
    if (not details.get('private') or details.get('owner', {}).get('login') != OWNER
            or details.get('full_name') != REPO):
        raise RuntimeError('Destination must be this exact private repository owned by the requested user.')
    return details


def checked_query(arguments):
    result = subprocess.run(arguments, capture_output=True, text=True, env=GH_ENV)
    if result.returncode and '404' not in result.stderr:
        raise RuntimeError('GitHub lookup failed; refusing to treat it as a missing resource: ' + result.stderr)
    return result


def publish(base, workers=4):
    if not isinstance(workers, int) or not 1 <= workers <= 8:
        raise ValueError('Upload workers must be an integer between 1 and 8.')
    delivery, repo = base / 'delivery', base / 'repository'
    if delivery.is_symlink() or repo.is_symlink():
        raise RuntimeError('Delivery and repository directories must not be symlinks.')
    if api('user').get('login') != OWNER:
        raise RuntimeError('Wrong authenticated GitHub account')
    index_path = delivery / 'payload-index.json'
    local_asset(index_path)
    index = json.loads(index_path.read_text())
    if (index.get('format') != 'shuttl-delivery-v1' or not index.get('complete')
            or index.get('private_key_included') is not False):
        raise RuntimeError('A complete encrypted delivery index without the recovery private key is required.')
    expected = {}
    for asset in index['assets']:
        name = asset['name']
        if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', name) or name in expected
                or name in ['payload-index.json', 'SHA256SUMS', 'github-verification.json']):
            raise RuntimeError('Unsafe, duplicate or reserved asset name: ' + name)
        if not name.endswith('.age') and not (asset.get('standalone_video') and name.endswith('.mp4')):
            raise RuntimeError('Unencrypted non-video payload is forbidden: ' + name)
        if not re.fullmatch(r'[0-9a-f]{64}', asset['sha256']):
            raise RuntimeError('Invalid asset SHA256: ' + name)
        expected[name] = asset
        local_asset(delivery / name, asset)
    if not expected:
        raise RuntimeError('Delivery must contain assets.')
    for name in ['payload-index.json', 'SHA256SUMS']:
        expected[name] = local_asset(delivery / name)
    # Check the checksum file against the index, not merely against itself.
    checksum_lines = (delivery / 'SHA256SUMS').read_text().splitlines()
    checksum_expected = {name: meta['sha256'] for name, meta in expected.items() if name != 'SHA256SUMS'}
    parsed = {}
    for line in checksum_lines:
        fields = line.split('  ', 1)
        if len(fields) != 2 or fields[1] in parsed:
            raise RuntimeError('Malformed or duplicate SHA256SUMS entry.')
        parsed[fields[1]] = fields[0]
    if parsed != checksum_expected:
        raise RuntimeError('SHA256SUMS does not describe the complete current delivery.')

    report_path = base / 'github-verification.json'
    previous = json.loads(report_path.read_text()) if report_path.exists() else {}
    index_hash = expected['payload-index.json']['sha256']
    report = {'repository': REPO, 'tag': TAG, 'delivery_index_sha256': index_hash,
              'complete': False, 'assets': {}}
    if (previous.get('repository') == REPO and previous.get('tag') == TAG
            and previous.get('delivery_index_sha256') == index_hash):
        report['assets'] = {k: v for k, v in previous.get('assets', {}).items() if k in expected}
        report['repository_id'] = previous.get('repository_id')
    durable_json(report_path, report)
    receipt_path = base / 'github-upload-receipt.json'
    durable_json(receipt_path, {'complete': False, 'repository': REPO, 'tag': TAG})
    # Scanner errors and findings both block publication. Reports remain outside Git.
    run(['gitleaks', 'dir', str(repo), '--redact', '--report-format', 'json',
         '--report-path', str(base / 'publication-secret-scan.json')])
    query = checked_query(['gh', 'api', f'repos/{REPO}'])
    if query.returncode:
        run(['gh', 'repo', 'create', REPO, '--private', '--description',
             'Shuttl 完整开发恢复备份，含源码、模型、数据、宣传工程与校验清单'])
    details = private_destination()
    if report.get('repository_id') != details['id']:
        report['assets'] = {}
    report['repository_id'] = details['id']
    durable_json(report_path, report)
    if (repo / '.git').is_symlink():
        raise RuntimeError('Publication Git directory must not be a symlink.')
    if not (repo / '.git').exists():
        run(['git', 'init', '--initial-branch=main'], cwd=repo)
        run(['git', 'config', 'user.name', 'Shuttl Preservation'], cwd=repo)
        run(['git', 'config', 'user.email', OWNER + '@users.noreply.github.com'], cwd=repo)
    if (Path(output(['git', 'rev-parse', '--show-toplevel'], cwd=repo).strip()).resolve() != repo.resolve()
            or output(['git', 'branch', '--show-current'], cwd=repo).strip() != 'main'):
        raise RuntimeError('Expected the dedicated publication repository on branch main.')
    run(['git', 'add', '.'], cwd=repo)
    staged = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=repo, env=GH_ENV)
    if staged.returncode == 1:
        run(['git', 'commit', '-m', 'Preserve Shuttl development source and complete recovery instructions'], cwd=repo)
    elif staged.returncode != 0:
        raise RuntimeError('Cannot inspect staged Git changes.')
    run(['gitleaks', 'git', str(repo), '--redact', '--report-format', 'json',
         '--report-path', str(base / 'publication-history-secret-scan.json')])
    remotes = output(['git', 'remote'], cwd=repo).split()
    remote_url = 'https://github.com/' + REPO + '.git'
    if 'origin' not in remotes:
        run(['git', 'remote', 'add', 'origin', remote_url], cwd=repo)
    elif output(['git', 'remote', 'get-url', 'origin'], cwd=repo).strip() != remote_url:
        raise RuntimeError('Unexpected Git remote; inspect manually')
    private_destination()
    run(['gh', 'auth', 'setup-git', '--hostname', 'github.com'])
    run(['git', 'push', '--set-upstream', 'origin', 'main'], cwd=repo)
    exists = checked_query(['gh', 'api', f'repos/{REPO}/releases/tags/{TAG}'])
    if exists.returncode:
        private_destination()
        run(['gh', 'release', 'create', TAG, '--repo', REPO, '--target', 'main',
             '--title', 'Shuttl 完整恢复备份 · 2026-10-11', '--notes-file', str(repo / 'RELEASE_NOTES.md')])
    release = api(f'repos/{REPO}/releases/tags/{TAG}')
    assets_lock = threading.Lock()
    report_lock = threading.Lock()
    assets = {}

    def get_assets():
        # Serialize refreshes so a slower old snapshot cannot replace a newer
        # shared snapshot. Uploads and download hashing remain independent.
        with assets_lock:
            pages = json.loads(output(['gh', 'api', f'repos/{REPO}/releases/{release["id"]}/assets?per_page=100',
                                       '--paginate', '--slurp']))
            items = [a for page in pages for a in page]
            if len({a['name'] for a in items}) != len(items):
                raise RuntimeError('Duplicate remote asset names.')
            assets.clear()
            assets.update({a['name']: a for a in items})
            return dict(assets)

    def upload_and_readback(path, meta, asset=None):
        # Existing same-sized content may still be wrong. A failed readback forces
        # replacement on the next attempt instead of trapping every resume.
        force_upload = False
        for attempt in range(3):
            private_destination()
            try:
                if (force_upload or not asset or asset['size'] != meta['bytes']
                        or (asset.get('digest') and asset['digest'] != 'sha256:' + meta['sha256'])):
                    local_asset(path, meta)
                    run(['gh', 'release', 'upload', TAG, str(path), '--repo', REPO, '--clobber'])
                    asset = get_assets().get(path.name)
                    if not asset:
                        raise RuntimeError('Uploaded asset not found: ' + path.name)
                downloaded, size = remote_sha(asset['id'])
                if downloaded != meta['sha256'] or size != meta['bytes']:
                    raise RuntimeError('Remote round-trip mismatch: ' + path.name)
                return {'asset_id': asset['id'], 'bytes': size, 'downloaded_sha256': downloaded,
                        'verified_at_unix': time.time()}
            except RemoteDownloadError:
                # remote_sha has already exhausted its three download attempts.
                # Leave the existing asset for a later resume to verify.
                raise
            except (subprocess.CalledProcessError, RuntimeError):
                if attempt == 2:
                    raise
                force_upload = True
                time.sleep(5 * (attempt + 1))
        raise AssertionError('unreachable')

    get_assets()

    def transfer_asset(name, meta):
        with assets_lock:
            asset = assets.get(name)
        with report_lock:
            saved = report['assets'].get(name)
        if (asset and saved and saved.get('downloaded_sha256') == meta['sha256']
                and saved.get('asset_id') == asset['id'] and saved.get('bytes') == meta['bytes']
                and asset['size'] == meta['bytes']
                and (not asset.get('digest') or asset['digest'] == 'sha256:' + meta['sha256'])):
            return
        proof = upload_and_readback(delivery / name, meta, asset)
        # Persist the entire report under one lock: a successful worker must
        # never overwrite another worker's completed download proof.
        with report_lock:
            report['assets'][name] = proof
            durable_json(report_path, report)
            print(json.dumps({'uploaded_and_download_verified': name, 'bytes': meta['bytes']}), flush=True)

    failures = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='shuttl-upload') as executor:
        futures = {executor.submit(transfer_asset, name, meta): name for name, meta in expected.items()}
        try:
            for future in as_completed(futures):
                try:
                    future.result()
                except CancelledError:
                    continue
                except Exception as exc:
                    failures.append((futures[future], exc))
                    for pending in futures:
                        pending.cancel()
        except BaseException:
            for pending in futures:
                pending.cancel()
            raise
    # Active transfers finish and save their proofs even when a sibling fails;
    # queued transfers are cancelled, and a later run resumes the remainder.
    if failures:
        report['failed_assets'] = [name for name, _ in failures]
        durable_json(report_path, report)
        raise RuntimeError('Delivery transfer failed: ' + ', '.join(report['failed_assets'])) from failures[0][1]
    local_head = output(['git', 'rev-parse', 'HEAD'], cwd=repo).strip()
    remote_head = api(f'repos/{REPO}/git/ref/heads/main')['object']['sha']
    if local_head != remote_head:
        raise RuntimeError('Remote Git commit mismatch')
    private_destination()
    final_assets = get_assets()
    for name, meta in expected.items():
        asset = final_assets.get(name)
        if not asset or asset['id'] != report['assets'][name]['asset_id'] or asset['size'] != meta['bytes']:
            raise RuntimeError('Remote asset changed after verification: ' + name)
    report.update(complete=True, git_commit=local_head, asset_count=len(expected),
                  verified_at_unix=time.time(), repository_url='https://github.com/' + REPO)
    durable_json(report_path, report)
    try:
        proof = upload_and_readback(report_path, local_asset(report_path), final_assets.get(report_path.name))
        private_destination()
    except BaseException:
        report['complete'] = False
        report['verification_report_readback_failed'] = True
        durable_json(report_path, report)
        raise
    durable_json(receipt_path, {'complete': True, 'repository': REPO, 'tag': TAG,
                               'delivery_index_sha256': index_hash, 'git_commit': local_head,
                               'delivery_assets_verified': len(expected), 'verification_report': proof})
    print(json.dumps({'complete': True, 'repository_url': report['repository_url'],
                      'assets': len(expected), 'verification_report_readback_verified': True}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--workers', type=int, choices=range(1, 9), default=4,
                        help='Concurrent asset upload/download workers (default: 4).')
    args = parser.parse_args()
    base = args.base.resolve()
    with (base / '.upload.lock').open('a+b') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Another uploader holds this backup lock.')
        publish(base, workers=args.workers)


if __name__ == '__main__':
    main()
