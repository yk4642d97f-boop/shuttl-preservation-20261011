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
PART_LIMIT = 128 * 1024 * 1024
RESERVED_ASSETS = {'payload-index.json', 'SHA256SUMS', 'github-verification.json'}


def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, env=GH_ENV, **kwargs)


def output(args, **kwargs):
    return subprocess.check_output(args, text=True, env=GH_ENV, **kwargs)


class ReadOnlyAPIError(RuntimeError):
    """A metadata query failed; it must never force a successful upload to repeat."""


def readonly_query(arguments, allow_not_found=False):
    """Retry only transient failures of these read-only gh API queries."""
    for attempt in range(3):
        try:
            result = subprocess.run(arguments, capture_output=True, text=True,
                                    env=GH_ENV, timeout=60)
        except subprocess.TimeoutExpired as error:
            if attempt == 2:
                raise ReadOnlyAPIError('GitHub metadata query timed out after three attempts.') from error
        except OSError as error:
            raise ReadOnlyAPIError('Cannot run GitHub metadata query.') from error
        else:
            if result.returncode == 0:
                return result
            status = re.search(r'\bHTTP(?:/[0-9.]+)?\s+([1-5][0-9]{2})\b', result.stderr, re.IGNORECASE)
            code = int(status.group(1)) if status else None
            if allow_not_found and code == 404:
                return result
            # Explicit authorization/not-found errors are not transient. Never
            # treat a network failure as evidence that a repo/release is absent.
            transient = (code in (500, 502, 503, 504) if code is not None else bool(re.search(
                r'\bEOF\b|connection reset|connection aborted|broken pipe|'
                r'(?:handshake|i/o|request) timeout|context deadline exceeded|'
                r'temporary failure|network is unreachable|no such host',
                result.stderr, re.IGNORECASE)))
            if not transient or attempt == 2:
                raise ReadOnlyAPIError('GitHub metadata query failed; refusing to continue: ' + result.stderr.strip())
        time.sleep(5 * (attempt + 1))
    raise AssertionError('unreachable')


def json_query(arguments):
    result = readonly_query(arguments)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ReadOnlyAPIError('GitHub metadata query returned invalid JSON.') from error


def api(path):
    return json_query(['gh', 'api', path])


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


def asset_metadata(asset):
    if not isinstance(asset, dict):
        raise RuntimeError('Asset metadata must be an object.')
    name = asset.get('name')
    if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', name)
            or name in RESERVED_ASSETS):
        raise RuntimeError('Unsafe or reserved asset name: ' + str(name))
    if not isinstance(asset.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', asset['sha256']):
        raise RuntimeError('Invalid asset SHA256: ' + name)
    if type(asset.get('bytes')) is not int or asset['bytes'] <= 0:
        raise RuntimeError('Invalid asset byte length: ' + name)
    return name


def delivery_assets(index, delivery):
    """Validate logical assets and return the actual files to transfer."""
    if (not isinstance(index, dict) or index.get('format') != 'shuttl-delivery-v1'
            or index.get('complete') is not True or index.get('private_key_included') is not False):
        raise RuntimeError('A complete encrypted delivery index without the recovery private key is required.')
    if 'transport' in index and index['transport'] != 'ciphertext-parts-v1':
        raise RuntimeError('Unsupported delivery transport.')
    assets = index.get('assets')
    if not isinstance(assets, list) or not assets:
        raise RuntimeError('Delivery must contain an asset list.')
    logical_names = set()
    for asset in assets:
        name = asset_metadata(asset)
        if name in logical_names:
            raise RuntimeError('Duplicate logical asset name: ' + name)
        logical_names.add(name)
        if 'standalone_video' in asset and type(asset['standalone_video']) is not bool:
            raise RuntimeError('standalone_video must be a boolean: ' + name)
        if asset.get('standalone_video'):
            if not name.endswith('.mp4') or 'parts' in asset:
                raise RuntimeError('Standalone video must be an unsplit MP4: ' + name)
        elif not name.endswith('.age'):
            raise RuntimeError('Unencrypted non-video payload is forbidden: ' + name)

    expected = {}
    for asset in assets:
        name = asset['name']
        if 'parts' not in asset:
            expected[name] = asset
            local_asset(delivery / name, asset)
            continue
        if index.get('transport') != 'ciphertext-parts-v1':
            raise RuntimeError('Split assets require ciphertext-parts-v1 transport.')
        parts = asset['parts']
        if not isinstance(parts, list) or not parts or len(parts) > 999999:
            raise RuntimeError('Split asset must contain a nonempty ordered part list: ' + name)
        combined, combined_size = hashlib.sha256(), 0
        for number, part in enumerate(parts, 1):
            part_name = asset_metadata(part)
            if set(part) != {'name', 'bytes', 'sha256'}:
                raise RuntimeError('Unexpected fields in ciphertext part: ' + part_name)
            if part_name != name[:-4] + '.part-' + f'{number:06d}' + '.age':
                raise RuntimeError('Part name or sequence differs from parent: ' + part_name)
            if part_name in logical_names or part_name in expected:
                raise RuntimeError('Duplicate or colliding transfer asset name: ' + part_name)
            if part['bytes'] > PART_LIMIT:
                raise RuntimeError('Ciphertext part exceeds 128 MiB: ' + part_name)
            path = delivery / part_name
            before = path.lstat()
            if not stat.S_ISREG(before.st_mode):
                raise RuntimeError('Part must be a regular file, not a symlink: ' + part_name)
            part_hash, part_size = hashlib.sha256(), 0
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                    combined.update(block)
                    part_hash.update(block)
                    part_size += len(block)
            after = path.lstat()
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise RuntimeError('Part changed while validating: ' + part_name)
            if part_hash.hexdigest() != part['sha256'] or part_size != part['bytes']:
                raise RuntimeError('Local ciphertext part mismatch: ' + part_name)
            combined_size += part_size
            expected[part_name] = part
        if combined_size != asset['bytes'] or combined.hexdigest() != asset['sha256']:
            raise RuntimeError('Reassembled ciphertext hash or size mismatch: ' + name)
    return expected


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
    return readonly_query(arguments, allow_not_found=True)


def remote_asset_uploaded(asset):
    # An interrupted GitHub upload can retain the intended full size while its
    # state is "starter" and its download returns 404. Older metadata fixtures
    # omit state; when GitHub supplies it, require successful completion.
    return 'state' not in asset or asset['state'] == 'uploaded'


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
    expected = delivery_assets(index, delivery)
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
            pages = json_query(['gh', 'api', f'repos/{REPO}/releases/{release["id"]}/assets?per_page=100',
                                '--paginate', '--slurp'])
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
                if (force_upload or not asset or not remote_asset_uploaded(asset)
                        or asset['size'] != meta['bytes']
                        or (asset.get('digest') and asset['digest'] != 'sha256:' + meta['sha256'])):
                    local_asset(path, meta)
                    run(['gh', 'release', 'upload', TAG, str(path), '--repo', REPO, '--clobber'])
                    asset = get_assets().get(path.name)
                    if not asset:
                        raise RuntimeError('Uploaded asset not found: ' + path.name)
                    if not remote_asset_uploaded(asset):
                        raise RuntimeError('Remote upload is incomplete: ' + path.name)
                downloaded, size = remote_sha(asset['id'])
                if downloaded != meta['sha256'] or size != meta['bytes']:
                    raise RuntimeError('Remote round-trip mismatch: ' + path.name)
                return {'asset_id': asset['id'], 'bytes': size, 'downloaded_sha256': downloaded,
                        'verified_at_unix': time.time()}
            except (RemoteDownloadError, ReadOnlyAPIError):
                # Readback or metadata retries are exhausted. Leave a completed
                # upload intact so a later resume can verify it without reupload.
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
        if (asset and remote_asset_uploaded(asset) and saved and saved.get('downloaded_sha256') == meta['sha256']
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
        if (not asset or not remote_asset_uploaded(asset)
                or asset['id'] != report['assets'][name]['asset_id'] or asset['size'] != meta['bytes']):
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
