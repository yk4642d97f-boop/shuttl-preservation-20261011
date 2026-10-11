#!/usr/bin/env python3
"""Encrypt a verified preservation archive; never copy its private key."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

FORMAT = 'shuttl-preservation-v1'
VIDEO_SOURCES = [
    ('Shuttl-promo-v1.mp4', Path('/Users/yangcong/Downloads/华北五省/promo/out/Shuttl-宣传片.mp4')),
    ('Shuttl-promo-v2.mp4', Path('/Users/yangcong/Downloads/华北五省/promo2/out/Shuttl-宣传片-2.mp4')),
    ('Shuttl-demo-competition.mp4', Path('/Users/yangcong/Downloads/claude/output/huabei2026/05_演示视频/Shuttl_创意与程序演示.mp4')),
]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def durable_text(path, text):
    temporary = path.with_suffix(path.suffix + '.partial')
    # Never follow an unexpected link in our generated output directory.
    if os.path.lexists(temporary):
        temporary.unlink()
    with temporary.open('x') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    temporary.replace(path)
    sync_directory(path.parent)


def durable_json(path, data):
    durable_text(path, json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def regular_file(path):
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode):
        raise RuntimeError('Expected a regular file, not a symlink: ' + str(path))
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def decrypt_digest(path, identity):
    h = hashlib.sha256()
    process = subprocess.Popen(['age', '-d', '-i', str(identity), str(path)], stdout=subprocess.PIPE)
    try:
        for block in iter(lambda: process.stdout.read(8 * 1024 * 1024), b''):
            h.update(block)
    finally:
        process.stdout.close()
    if process.wait() != 0:
        raise RuntimeError('Decryption failed: ' + path.name)
    return h.hexdigest()


def prepare(base, identity, reclaim=False):
    archive = base / 'archive'
    if archive.is_symlink() or not archive.is_dir():
        raise RuntimeError('Expected a generated archive directory, not a symlink.')
    if (archive / 'volumes').is_symlink():
        raise RuntimeError('Generated volumes directory must not be a symlink.')
    if identity.resolve().is_relative_to(base):
        raise RuntimeError('Keep recovery private key outside preservation output directory.')
    for name in ['create-report.json', 'verify-report.json', 'SEALED.json', 'manifest.sqlite3']:
        regular_file(archive / name)
    report = json.loads((archive / 'create-report.json').read_text())
    verification = json.loads((archive / 'verify-report.json').read_text())
    sealed = json.loads((archive / 'SEALED.json').read_text())
    if report.get('format') != FORMAT or not report.get('complete'):
        raise RuntimeError('Archive creation is incomplete or has an unexpected format.')
    if not verification.get('verified'):
        raise RuntimeError('A successful verify-report.json is required.')
    if sealed.get('format') != FORMAT or not sealed.get('verified'):
        raise RuntimeError('Archive must have a successful seal before encryption.')
    sealed_assets = {}
    for entry in sealed['assets']:
        relative = entry['path']
        if relative != 'manifest.sqlite3' and not re.fullmatch(r'volumes/volume-[0-9]{6}\.bin', relative):
            raise RuntimeError('Unexpected sealed archive path: ' + relative)
        if relative in sealed_assets or not re.fullmatch(r'[0-9a-f]{64}', entry['sha256']):
            raise RuntimeError('Duplicate sealed path or invalid SHA256: ' + relative)
        if not isinstance(entry['bytes'], int) or entry['bytes'] < 0:
            raise RuntimeError('Invalid sealed asset size: ' + relative)
        sealed_assets[relative] = entry
    if 'manifest.sqlite3' not in sealed_assets:
        raise RuntimeError('Sealed archive does not contain its manifest.')

    delivery = base / 'delivery'
    if delivery.is_symlink():
        raise RuntimeError('Delivery directory must not be a symlink.')
    delivery.mkdir(exist_ok=True)
    sync_directory(base)
    recipient = subprocess.check_output(['age-keygen', '-y', str(identity)], text=True).strip()
    seal_hash = digest(archive / 'SEALED.json')
    sources = [archive / n for n in ['manifest.sqlite3', 'create-report.json', 'verify-report.json', 'SEALED.json']]
    sources += [archive / p for p in sorted(sealed_assets) if p.startswith('volumes/')]
    expected_names = {p.name + '.age' for p in sources} | {name for name, _ in VIDEO_SOURCES}
    index_path = delivery / 'payload-index.json'
    if index_path.is_symlink():
        raise RuntimeError('Delivery index must not be a symlink.')
    previous = json.loads(index_path.read_text()) if index_path.exists() else {}
    if previous and (previous.get('format') != 'shuttl-delivery-v1' or previous.get('recipient') != recipient):
        raise RuntimeError('Existing delivery belongs to a different format or recovery key.')
    if previous.get('archive_seal_sha256', seal_hash) != seal_hash:
        raise RuntimeError('Existing delivery belongs to a different sealed archive.')
    entries = {}
    for entry in previous.get('assets', []):
        if entry['name'] in entries or entry['name'] not in expected_names:
            raise RuntimeError('Duplicate or unexpected previous delivery asset.')
        entries[entry['name']] = entry
    index = {'format': 'shuttl-delivery-v1', 'recipient': recipient, 'private_key_included': False,
             'archive_format': FORMAT, 'archive_seal_sha256': seal_hash, 'complete': False, 'assets': []}

    def save_index():
        # Retain later completed assets when a resumed run stops in an earlier asset.
        index['assets'] = list(entries.values())
        durable_json(index_path, index)

    save_index()
    for source in sources:
        relative = str(source.relative_to(archive))
        target = delivery / (source.name + '.age')
        source_signature = regular_file(source) if os.path.lexists(source) else None
        sealed_entry = sealed_assets.get(relative)
        if source_signature:
            plain_hash = digest(source)
            if regular_file(source) != source_signature:
                raise RuntimeError('Archive asset changed while hashing: ' + relative)
            if sealed_entry and (plain_hash != sealed_entry['sha256'] or source_signature[2] != sealed_entry['bytes']):
                raise RuntimeError('Sealed archive source changed: ' + relative)
        elif sealed_entry and relative.startswith('volumes/'):
            plain_hash = sealed_entry['sha256']
        else:
            raise RuntimeError('Missing archive source: ' + relative)
        encrypted_ok = False
        if os.path.lexists(target):
            regular_file(target)
            try:
                # This also reconstructs an index lost after a previously reclaimed volume.
                encrypted_ok = decrypt_digest(target, identity) == plain_hash
            except RuntimeError:
                if not source_signature:
                    raise
        if not encrypted_ok:
            if not source_signature:
                raise RuntimeError('Reclaimed volume lacks a valid encrypted copy: ' + relative)
            partial = target.with_suffix(target.suffix + '.partial')
            if os.path.lexists(partial):
                partial.unlink()
            subprocess.run(['age', '-r', recipient, '-o', str(partial), str(source)], check=True)
            if decrypt_digest(partial, identity) != plain_hash:
                raise RuntimeError('Encryption round-trip check failed: ' + source.name)
            with partial.open('rb') as f:
                os.fsync(f.fileno())
            partial.replace(target)
            sync_directory(delivery)
        if source_signature and regular_file(source) != source_signature:
            raise RuntimeError('Archive asset changed during encryption: ' + relative)
        entry = {'name': target.name, 'bytes': target.stat().st_size, 'sha256': digest(target),
                 'plaintext_sha256': plain_hash, 'restore_path': relative}
        entries[target.name] = entry
        save_index()
        if reclaim and relative.startswith('volumes/') and source_signature:
            # Only fixed generated volume paths reach this branch. Their ciphertext
            # and the complete index entry are durable and have passed real decryption.
            if regular_file(source) != source_signature:
                raise RuntimeError('Volume changed before reclamation: ' + relative)
            source.unlink()
            sync_directory(archive / 'volumes')
        print(json.dumps({'encrypted_and_roundtrip_verified': target.name, 'bytes': entry['bytes']}), flush=True)

    for name, source in VIDEO_SOURCES:
        target = delivery / name
        signature = regular_file(source)
        source_hash = digest(source)
        if os.path.lexists(target):
            regular_file(target)
        if not target.exists() or digest(target) != source_hash:
            partial = target.with_suffix(target.suffix + '.partial')
            if os.path.lexists(partial):
                partial.unlink()
            shutil.copyfile(source, partial)
            if digest(partial) != source_hash:
                raise RuntimeError('Standalone video copy verification failed: ' + name)
            with partial.open('rb') as f:
                os.fsync(f.fileno())
            partial.replace(target)
            sync_directory(delivery)
        if regular_file(source) != signature:
            raise RuntimeError('Standalone video source changed during copying: ' + name)
        entries[name] = {'name': name, 'bytes': target.stat().st_size,
                         'sha256': source_hash, 'standalone_video': True}
        save_index()
    index['complete'] = True
    index['assets'] = list(entries.values())
    final_index = json.dumps(index, ensure_ascii=False, indent=2) + '\n'
    # Publish complete=true last. A crash must not expose a complete index with
    # a missing or stale checksum file.
    durable_text(delivery / 'SHA256SUMS', ''.join(a['sha256'] + '  ' + a['name'] + '\n' for a in index['assets'])
                 + hashlib.sha256(final_index.encode()).hexdigest() + '  payload-index.json\n')
    durable_text(index_path, final_index)
    print(json.dumps({'complete': True, 'assets': len(entries),
                      'bytes': sum(a['bytes'] for a in entries.values())}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--identity', type=Path, required=True)
    parser.add_argument('--reclaim-plaintext-volumes', action='store_true',
                        help='Remove only generated sealed volumes after durable encrypted round-trip verification.')
    args = parser.parse_args()
    base = args.base.resolve()
    with (base / '.prepare.lock').open('a+b') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Another delivery preparation process holds this lock.')
        prepare(base, args.identity, args.reclaim_plaintext_volumes)


if __name__ == '__main__':
    main()
