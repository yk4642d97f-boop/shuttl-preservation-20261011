#!/usr/bin/env python3
"""Durably split verified age ciphertext into resumable 128 MiB transport files.

This operates only on generated delivery ciphertext. It never opens the source
archive, engineering files, or recovery key. Logical asset metadata is preserved.
"""
import argparse
from contextlib import ExitStack, contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat

PART_SIZE = 128 * 1024 * 1024
TRANSPORT = 'ciphertext-parts-v1'
CHUNK_SIZE = 8 * 1024 * 1024


def signature(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def regular_file(path):
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode):
        raise RuntimeError('Expected a regular file, not a symlink: ' + str(path))
    return signature(st)


def directory(path):
    if not stat.S_ISDIR(path.lstat().st_mode):
        raise RuntimeError('Expected a real directory, not a symlink: ' + str(path))


@contextmanager
def open_regular(path):
    before = regular_file(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        if signature(os.fstat(fd)) != before:
            raise RuntimeError('File changed while opening: ' + path.name)
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            yield stream, before
        if signature(os.fstat(fd)) != before or regular_file(path) != before:
            raise RuntimeError('File changed while reading: ' + path.name)
    finally:
        os.close(fd)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def temporary_path(path):
    return path.with_name('.' + path.name + '.fragment.partial')


def clean_partial(path):
    # Only our exact, generated temporary basename is removed. Never follow links.
    if os.path.lexists(path):
        regular_file(path)
        path.unlink()
        sync_directory(path.parent)


def durable_bytes(path, data, replace=True):
    directory(path.parent)
    if os.path.lexists(path):
        regular_file(path)
        if not replace:
            raise RuntimeError('Refusing to replace an existing part: ' + path.name)
    temporary = temporary_path(path)
    clean_partial(temporary)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    if replace:
        if os.path.lexists(path):
            regular_file(path)
        os.replace(temporary, path)
    else:
        # link(2) fails if final already exists; it cannot clobber a raced-in file.
        os.link(temporary, path, follow_symlinks=False)
        temporary.unlink()
    sync_directory(path.parent)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def save_index(path, index):
    durable_bytes(path, json_bytes(index))


@contextmanager
def backup_locks(base):
    # Same locks as preparation/upload, always in this order. A failed second
    # acquisition releases the first, and no index mutation has occurred yet.
    with ExitStack() as stack:
        for name in ('.prepare.lock', '.upload.lock'):
            path = base / name
            if os.path.lexists(path):
                regular_file(path)
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            stream = stack.enter_context(os.fdopen(fd, 'a+b'))
            if not stat.S_ISREG(os.fstat(fd).st_mode) or regular_file(path) != signature(os.fstat(fd)):
                raise RuntimeError('Invalid backup lock: ' + name)
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Another backup process holds ' + name)
        yield


def metadata(entry):
    if not isinstance(entry, dict):
        raise RuntimeError('Asset metadata must be an object.')
    name = entry.get('name')
    if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', name)
            or name in ('payload-index.json', 'SHA256SUMS')):
        raise RuntimeError('Unsafe or reserved asset name.')
    if type(entry.get('bytes')) is not int or entry['bytes'] < 0:
        raise RuntimeError('Invalid asset byte count: ' + name)
    if not isinstance(entry.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', entry['sha256']):
        raise RuntimeError('Invalid asset SHA256: ' + name)
    return name


def part_plan(asset, part_size):
    count = (asset['bytes'] + part_size - 1) // part_size
    if count > 999999:
        raise RuntimeError('Too many ciphertext parts: ' + asset['name'])
    return [{'name': asset['name'][:-4] + '.part-' + f'{number:06d}' + '.age',
             'bytes': min(part_size, asset['bytes'] - (number - 1) * part_size)}
            for number in range(1, count + 1)]


def validate_index(index, part_size):
    if (not isinstance(index, dict) or index.get('format') != 'shuttl-delivery-v1'
            or index.get('private_key_included') is not False
            or type(index.get('complete')) is not bool):
        raise RuntimeError('Expected a verified delivery index without a private key.')
    if 'transport' in index and index['transport'] != TRANSPORT:
        raise RuntimeError('Unsupported delivery transport.')
    if 'transport' not in index and index['complete'] is not True:
        raise RuntimeError('Initial delivery preparation must be complete before fragmentation.')
    assets = index.get('assets')
    if not isinstance(assets, list) or not assets:
        raise RuntimeError('Delivery contains no logical assets.')
    logical_names = set()
    for asset in assets:
        name = metadata(asset)
        if name in logical_names:
            raise RuntimeError('Duplicate logical asset name: ' + name)
        logical_names.add(name)
    planned = set()
    for asset in assets:
        name = asset['name']
        if 'standalone_video' in asset and type(asset['standalone_video']) is not bool:
            raise RuntimeError('standalone_video must be a boolean: ' + name)
        if asset.get('standalone_video'):
            if not name.endswith('.mp4') or 'parts' in asset:
                raise RuntimeError('Standalone videos must remain unsplit MP4 files: ' + name)
            continue
        if not name.endswith('.age'):
            raise RuntimeError('Non-video assets must be age ciphertext: ' + name)
        if asset['bytes'] <= part_size:
            if 'parts' in asset:
                raise RuntimeError('Small ciphertext must remain unsplit: ' + name)
            continue
        plan = part_plan(asset, part_size)
        for part in plan:
            if part['name'] in logical_names or part['name'] in planned:
                raise RuntimeError('Transport filename collision: ' + part['name'])
            planned.add(part['name'])
        if 'parts' in asset:
            parts = asset['parts']
            if (index.get('transport') != TRANSPORT or not isinstance(parts, list)
                    or len(parts) > len(plan)):
                raise RuntimeError('Invalid or incompatible previous parts: ' + name)
            for number, part in enumerate(parts):
                metadata(part)
                if (set(part) != {'name', 'bytes', 'sha256'}
                        or any(part[key] != plan[number][key] for key in ('name', 'bytes'))):
                    raise RuntimeError('Previous part metadata does not match its fixed position: ' + name)


def verify_file(path, expected, combined=None):
    hasher, length = hashlib.sha256(), 0
    with open_regular(path) as (stream, before):
        for data in iter(lambda: stream.read(CHUNK_SIZE), b''):
            hasher.update(data)
            if combined is not None:
                combined.update(data)
            length += len(data)
    if length != expected['bytes'] or hasher.hexdigest() != expected['sha256']:
        raise RuntimeError('Ciphertext hash or byte count mismatch: ' + path.name)
    return before


def verify_parts(delivery, asset, plan):
    parts = asset.get('parts', [])
    if len(parts) != len(plan):
        raise RuntimeError('Missing parent ciphertext with incomplete parts: ' + asset['name'])
    combined = hashlib.sha256()
    total = 0
    for part in parts:
        verify_file(delivery / part['name'], part, combined)
        total += part['bytes']
    if total != asset['bytes'] or combined.hexdigest() != asset['sha256']:
        raise RuntimeError('Concatenated ciphertext hash or size mismatch: ' + asset['name'])


def fragment_asset(delivery, index_path, index, asset, reclaim, part_size):
    parent = delivery / asset['name']
    plan = part_plan(asset, part_size)
    parent_signature = None
    if os.path.lexists(parent):
        complete_hash = hashlib.sha256()
        total = 0
        with open_regular(parent) as (stream, parent_signature):
            if parent_signature[2] != asset['bytes']:
                raise RuntimeError('Parent ciphertext size mismatch: ' + parent.name)
            parts = asset.setdefault('parts', [])
            for number, planned in enumerate(plan):
                data = stream.read(planned['bytes'])
                if len(data) != planned['bytes']:
                    raise RuntimeError('Truncated parent ciphertext: ' + parent.name)
                complete_hash.update(data)
                total += len(data)
                part = dict(planned, sha256=hashlib.sha256(data).hexdigest())
                target = delivery / part['name']
                if number < len(parts):
                    if parts[number] != part:
                        raise RuntimeError('Committed part differs from parent ciphertext: ' + target.name)
                    # Missing/corrupt committed files are never silently repaired.
                    verify_file(target, part)
                else:
                    if os.path.lexists(target):
                        # Crash after part fsync but before index save: adopt only
                        # after proving exact equality with the original slice.
                        verify_file(target, part)
                        clean_partial(temporary_path(target))
                        with open_regular(target) as (stored, unused):
                            os.fsync(stored.fileno())
                        sync_directory(delivery)
                    else:
                        durable_bytes(target, data, replace=False)
                        verify_file(target, part)
                    parts.append(part)
                    save_index(index_path, index)
                del data
            if stream.read(1) or total != asset['bytes'] or complete_hash.hexdigest() != asset['sha256']:
                raise RuntimeError('Original ciphertext hash or size mismatch: ' + parent.name)
    # This independent complete stream proves stored part data, including the
    # resume case where a previous successful run already reclaimed the parent.
    verify_parts(delivery, asset, plan)
    save_index(index_path, index)
    if reclaim and parent_signature is not None:
        if regular_file(parent) != parent_signature:
            raise RuntimeError('Parent changed before reclamation: ' + parent.name)
        # Complete metadata and all parts are durable, and the stored byte stream
        # matches the unchanged logical parent hash. Only this generated file is removed.
        parent.unlink()
        sync_directory(delivery)


def fragment_delivery(base, reclaim=False, part_size=PART_SIZE):
    """Convert generated delivery assets. part_size is injectable for small tests."""
    if type(part_size) is not int or not 1 <= part_size <= PART_SIZE:
        raise RuntimeError('Invalid part size.')
    base = Path(base).expanduser().absolute()
    directory(base)
    delivery = base / 'delivery'
    directory(delivery)
    index_path = delivery / 'payload-index.json'
    with backup_locks(base):
        with open_regular(index_path) as (stream, unused):
            index = json.load(stream)
        validate_index(index, part_size)
        checksum_path = delivery / 'SHA256SUMS'
        if os.path.lexists(checksum_path):
            regular_file(checksum_path)
        index['transport'] = TRANSPORT
        index['complete'] = False
        save_index(index_path, index)
        transport_assets = []
        fragmented, reclaimed = 0, 0
        for asset in index['assets']:
            if asset['name'].endswith('.age') and asset['bytes'] > part_size:
                existed = os.path.lexists(delivery / asset['name'])
                fragment_asset(delivery, index_path, index, asset, reclaim, part_size)
                transport_assets.extend(asset['parts'])
                fragmented += 1
                reclaimed += int(existed and reclaim)
            else:
                verify_file(delivery / asset['name'], asset)
                transport_assets.append(asset)
            print(json.dumps({'fragment_verified': asset['name'],
                              'transport_files': len(asset.get('parts', [asset]))}), flush=True)
        # SHA256SUMS names real transport files and the exact final index bytes.
        # Persist it while complete=false, then publish complete=true LAST.
        index['complete'] = True
        final_index = json_bytes(index)
        checksum_data = ''.join(a['sha256'] + '  ' + a['name'] + '\n' for a in transport_assets)
        checksum_data += hashlib.sha256(final_index).hexdigest() + '  payload-index.json\n'
        durable_bytes(checksum_path, checksum_data.encode('ascii'))
        durable_bytes(index_path, final_index)
        return {'complete': True, 'transport': TRANSPORT, 'logical_assets': len(index['assets']),
                'transport_assets': len(transport_assets), 'fragmented_assets': fragmented,
                'reclaimed_parent_ciphertexts': reclaimed,
                'transport_bytes': sum(a['bytes'] for a in transport_assets)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, type=Path)
    parser.add_argument('--reclaim-parent-ciphertexts', action='store_true',
                        help='Remove only generated large delivery parents after verified durable parts/index.')
    args = parser.parse_args()
    try:
        result = fragment_delivery(args.base, reclaim=args.reclaim_parent_ciphertexts)
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit('Fragmentation failed; delivery is not ready: ' + str(error))
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
