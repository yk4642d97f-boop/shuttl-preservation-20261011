#!/usr/bin/env python3
"""Portable, resumable, content-addressed local backup. Python 3.9+ stdlib only."""
import argparse
import base64
import ctypes
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import struct
import sys
import time
import uuid
import zlib

FORMAT = "shuttl-preservation-v1"
MAGIC = b"SHUTBKP1"
FRAME = struct.Struct(">4s32sQQ")
CHUNK_SIZE = 64 * 1024 * 1024
VOLUME_SIZE = 512 * 1024 * 1024
EMPTY_HASH = hashlib.sha256(b"").hexdigest()


def compression_level(data):
    """Avoid recompressing high-entropy blocks; both choices remain zlib streams."""
    if len(data) < 1024 * 1024:
        return 1
    # Four separated 64 KiB windows (256 KiB total) reduce the influence of
    # compressible container headers. Sampling changes only storage encoding;
    # content-addressed hashes are always computed from the complete raw block.
    width = 64 * 1024
    span = len(data) - width
    sample = b"".join(data[(span * index) // 3:(span * index) // 3 + width]
                      for index in range(4))
    return 0 if len(zlib.compress(sample, level=1)) / len(sample) >= 0.99 else 1


def darwin_xattr_lib():
    lib = ctypes.CDLL(None, use_errno=True)
    lib.listxattr.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    lib.listxattr.restype = ctypes.c_ssize_t
    lib.getxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p,
                            ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    lib.getxattr.restype = ctypes.c_ssize_t
    lib.setxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p,
                            ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    lib.setxattr.restype = ctypes.c_int
    return lib


DARWIN_XATTR = darwin_xattr_lib() if sys.platform == "darwin" and not hasattr(os, "listxattr") else None


def xattr_list(path):
    if hasattr(os, "listxattr"):
        return os.listxattr(path, follow_symlinks=False)
    if DARWIN_XATTR is None:
        raise OSError(errno.ENOSYS, "xattr API unavailable")
    encoded = os.fsencode(path)
    for _ in range(3):
        size = DARWIN_XATTR.listxattr(encoded, None, 0, 1)
        if size < 0:
            raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()), str(path))
        buffer = ctypes.create_string_buffer(max(1, size))
        length = DARWIN_XATTR.listxattr(encoded, buffer, size, 1)
        if length >= 0:
            return [os.fsdecode(p) for p in buffer.raw[:length].split(b"\0") if p]
        if ctypes.get_errno() != errno.ERANGE:
            break
    raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()), str(path))


def xattr_get(path, name):
    if hasattr(os, "getxattr"):
        return os.getxattr(path, name, follow_symlinks=False)
    if DARWIN_XATTR is None:
        raise OSError(errno.ENOSYS, "xattr API unavailable")
    encoded, key = os.fsencode(path), os.fsencode(name)
    for _ in range(3):
        size = DARWIN_XATTR.getxattr(encoded, key, None, 0, 0, 1)
        if size < 0:
            raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()), str(path))
        buffer = ctypes.create_string_buffer(max(1, size))
        length = DARWIN_XATTR.getxattr(encoded, key, buffer, size, 0, 1)
        if length >= 0:
            return buffer.raw[:length]
        if ctypes.get_errno() != errno.ERANGE:
            break
    raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()), str(path))


def xattr_set(path, name, value):
    if hasattr(os, "setxattr"):
        return os.setxattr(path, name, value, follow_symlinks=False)
    if DARWIN_XATTR is None:
        raise OSError(errno.ENOSYS, "xattr API unavailable")
    buffer = ctypes.create_string_buffer(value)
    if DARWIN_XATTR.setxattr(os.fsencode(path), os.fsencode(name), buffer, len(value), 0, 1) < 0:
        raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()), str(path))


def emit(**data):
    print(json.dumps(data, ensure_ascii=True), flush=True)


def under(path, prefix):
    return path == prefix or path.startswith(prefix.rstrip(os.sep) + os.sep)


def absolute(path):
    return os.path.abspath(os.path.expanduser(path))


def config_read(path, archive=None):
    data = json.loads(Path(path).read_text())
    roots = []
    for item in data["roots"]:
        p = absolute(item["path"])
        roots.append({"path": p, "category": item.get("category", "uncategorized")})
    if not roots:
        raise ValueError("config must contain at least one root")
    excludes = sorted(set(absolute(p) for p in data.get("excludes", [])))
    if archive:
        ap = absolute(archive)
        if any(under(r["path"], ap) for r in roots):
            raise ValueError("an archive cannot contain a configured source root")
        if any(under(ap, r["path"]) for r in roots):
            excludes.append(ap)
    return {"roots": roots, "excludes": sorted(set(excludes))}


def excluded(path, config):
    return any(under(path, prefix) for prefix in config["excludes"])


def walk(config):
    """Yield path, root, lstat, error; never descend into a symlink."""
    # Overlapping roots are handled without retaining a million-path Python set.
    ordered = sorted(config["roots"], key=lambda r: (len(r["path"]), r["path"]))
    previous = []
    for root in ordered:
        if any(under(root["path"], p) for p in previous):
            continue
        previous.append(root["path"])
        stack = [root["path"]]
        while stack:
            path = stack.pop()
            if excluded(path, config):
                continue
            try:
                st = os.lstat(path)
            except OSError as exc:
                yield path, root, None, str(exc)
                continue
            yield path, root, st, None
            if stat.S_ISDIR(st.st_mode):
                try:
                    with os.scandir(path) as entries:
                        children = [entry.path for entry in entries]
                    stack.extend(sorted(children, reverse=True))
                except OSError as exc:
                    yield path, root, None, "directory listing failed: " + str(exc)


def kind_of(st):
    if stat.S_ISREG(st.st_mode):
        return "file"
    if stat.S_ISDIR(st.st_mode):
        return "directory"
    if stat.S_ISLNK(st.st_mode):
        return "symlink"
    return "special"


def signature(st):
    return json.dumps([st.st_dev, st.st_ino, st.st_mode, st.st_size,
                       st.st_mtime_ns, st.st_ctime_ns], separators=(",", ":"))


def xattrs_read(path):
    result, errors = {}, []
    try:
        names = xattr_list(path)
    except OSError as exc:
        if exc.errno in (errno.ENOTSUP, getattr(errno, "EOPNOTSUPP", errno.ENOTSUP)):
            return {}, []
        return {}, ["listxattr: " + str(exc)]
    for name in names:
        try:
            value = xattr_get(path, name)
            result[name] = base64.b64encode(value).decode("ascii")
        except OSError as exc:
            errors.append("getxattr " + repr(name) + ": " + str(exc))
    return result, errors


def db_open(archive, readonly=False):
    path = Path(archive) / "manifest.sqlite3"
    if readonly:
        uri = path.resolve().as_uri() + "?mode=ro"
        if (Path(archive) / "SEALED.json").exists():
            wal = Path(archive) / "manifest.sqlite3-wal"
            if wal.exists() and wal.stat().st_size:
                raise ValueError("sealed archive has a nonempty WAL; refusing to ignore committed journal data")
            # Freshly decrypted WAL-mode SQLite files may not have sidecars.
            # macOS SQLite cannot always initialize those via mode=ro. A sealed,
            # checkpointed manifest is static; immutable reads need no sidecars.
            uri += "&immutable=1"
        db = sqlite3.connect(uri, uri=True)
    else:
        db = sqlite3.connect(path)
        db.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS chunks(
          hash TEXT PRIMARY KEY,volume TEXT NOT NULL,offset INTEGER NOT NULL,
          raw_size INTEGER NOT NULL,stored_size INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS files(
          path TEXT PRIMARY KEY,root_path TEXT,category TEXT,kind TEXT,size INTEGER,
          mode INTEGER,mtime_ns INTEGER,atime_ns INTEGER,uid INTEGER,gid INTEGER,
          dev INTEGER,ino INTEGER,nlink INTEGER,signature TEXT,sha256 TEXT,
          link_target TEXT,hardlink_to TEXT,xattrs_json TEXT,status TEXT,error TEXT,
          seen_run TEXT);
        CREATE TABLE IF NOT EXISTS file_chunks(
          path TEXT NOT NULL,seq INTEGER NOT NULL,hash TEXT NOT NULL,
          PRIMARY KEY(path,seq));
        CREATE INDEX IF NOT EXISTS files_inode ON files(dev,ino,status);
        CREATE TABLE IF NOT EXISTS issues(
          id INTEGER PRIMARY KEY,run TEXT,path TEXT,severity TEXT,message TEXT);
        """)
    db.row_factory = sqlite3.Row
    return db


def meta_set(db, key, value):
    db.execute("INSERT OR REPLACE INTO metadata VALUES(?,?)",
               (key, json.dumps(value, ensure_ascii=True)))


def meta_get(db, key, default=None):
    row = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class VolumeWriter:
    """Objects are fsynced before their SQLite references are committed."""
    def __init__(self, archive, db):
        self.archive, self.db = Path(archive), db
        self.folder = self.archive / "volumes"
        was_present = self.folder.exists()
        self.folder.mkdir(exist_ok=True)
        if not was_present:
            fsync_directory(self.archive)
        self.handle = None
        self.name = None
        self.needs_directory_sync = False
        self.recovered = []
        self.last_checkpoint = time.monotonic()
        self.reconcile()

    def reconcile(self):
        paths = sorted(self.folder.glob("volume-*.bin"))
        for index, path in enumerate(paths):
            is_last = index == len(paths) - 1
            with path.open("r+b") as f:
                header_magic = f.read(len(MAGIC))
                if len(header_magic) < len(MAGIC) and is_last and not self.db.execute(
                        "SELECT 1 FROM chunks WHERE volume=?", (path.name,)).fetchone():
                    f.seek(0)
                    f.write(MAGIC)
                    f.truncate(len(MAGIC))
                    f.flush()
                    os.fsync(f.fileno())
                    self.recovered.append({"volume": path.name, "recovered_uncommitted_volume_header": True})
                    header_magic = MAGIC
                if header_magic != MAGIC:
                    raise ValueError("bad volume magic: " + str(path))
                size = os.fstat(f.fileno()).st_size
                if size > VOLUME_SIZE:
                    raise ValueError("oversize volume: " + str(path))
                offset = len(MAGIC)
                while offset < size:
                    f.seek(offset)
                    header = f.read(FRAME.size)
                    if len(header) < FRAME.size:
                        if not is_last or self.db.execute(
                                "SELECT 1 FROM chunks WHERE volume=? AND offset>=?",
                                (path.name, offset)).fetchone():
                            raise ValueError("truncated committed frame header: " + str(path))
                        f.truncate(offset)
                        f.flush()
                        os.fsync(f.fileno())
                        self.recovered.append({"volume": path.name, "truncated_uncommitted_tail": size-offset})
                        size = offset
                        break
                    valid = len(header) == FRAME.size
                    if valid:
                        marker, digest, raw, stored = FRAME.unpack(header)
                        valid = (marker == b"CHNK" and 0 < raw <= CHUNK_SIZE
                                 and 0 < stored <= CHUNK_SIZE + 1024 * 1024)
                    if not valid:
                        raise ValueError("invalid frame header (refusing truncation): " + str(path))
                    end = offset + FRAME.size + stored
                    if end > size:
                        if not is_last:
                            raise ValueError("truncated nonfinal volume: " + str(path))
                        ref = self.db.execute("SELECT 1 FROM chunks WHERE volume=? AND offset>=?",
                                              (path.name, offset)).fetchone()
                        if ref:
                            raise ValueError("a committed object is truncated: " + str(path))
                        f.truncate(offset)
                        f.flush()
                        os.fsync(f.fileno())
                        self.recovered.append({"volume": path.name, "truncated_uncommitted_tail": size-offset})
                        size = offset
                        break
                    digest = digest.hex()
                    old = self.db.execute("SELECT * FROM chunks WHERE hash=?", (digest,)).fetchone()
                    if not old:
                        # Crash after data fsync, before DB commit. Validate before adoption.
                        f.seek(offset + FRAME.size)
                        compressed = f.read(stored)
                        block = decompress_block(compressed, raw)
                        if hashlib.sha256(block).hexdigest() != digest:
                            raise ValueError("orphan frame has invalid hash: " + str(path))
                        self.db.execute("INSERT INTO chunks VALUES(?,?,?,?,?)",
                                        (digest, path.name, offset, raw, stored))
                    offset = end
                f.flush()
                os.fsync(f.fileno())
                self.db.commit()
        if paths:
            self.name = paths[-1].name
            self.handle = paths[-1].open("ab")

    def add(self, data):
        digest = hashlib.sha256(data).hexdigest()
        row = self.db.execute("SELECT raw_size FROM chunks WHERE hash=?", (digest,)).fetchone()
        if row:
            if row[0] != len(data):
                raise ValueError("chunk hash/length conflict")
            return digest
        compressed = zlib.compress(data, level=compression_level(data))
        needed = FRAME.size + len(compressed)
        if self.handle is None or self.handle.tell() + needed > VOLUME_SIZE:
            self.close()
            number = int(self.name[7:13]) + 1 if self.name else 1
            self.name = "volume-%06d.bin" % number
            self.handle = (self.folder / self.name).open("xb")
            self.needs_directory_sync = True
            self.handle.write(MAGIC)
        offset = self.handle.tell()
        self.handle.write(FRAME.pack(b"CHNK", bytes.fromhex(digest), len(data), len(compressed)))
        self.handle.write(compressed)
        self.db.execute("INSERT INTO chunks VALUES(?,?,?,?,?)",
                        (digest, self.name, offset, len(data), len(compressed)))
        if time.monotonic() - self.last_checkpoint >= 1:
            self.checkpoint()
        return digest

    def checkpoint(self):
        if self.handle:
            self.handle.flush()
            os.fsync(self.handle.fileno())
        if self.needs_directory_sync:
            fsync_directory(self.folder)
            self.needs_directory_sync = False
        self.db.commit()
        self.last_checkpoint = time.monotonic()

    def close(self):
        if self.handle:
            self.handle.flush()
            os.fsync(self.handle.fileno())
            self.handle.close()
            self.handle = None
        if self.needs_directory_sync:
            fsync_directory(self.folder)
            self.needs_directory_sync = False


def decompress_block(compressed, expected):
    if not 0 < expected <= CHUNK_SIZE:
        raise ValueError("invalid raw chunk length")
    decoder = zlib.decompressobj()
    data = decoder.decompress(compressed, expected + 1)
    if (len(data) != expected or not decoder.eof or decoder.unused_data
            or decoder.unconsumed_tail):
        raise ValueError("invalid compressed chunk length or stream")
    return data


def read_chunk(archive, row):
    name = row["volume"]
    if not name.startswith("volume-") or not name.endswith(".bin") or Path(name).name != name:
        raise ValueError("unsafe volume name")
    path = Path(archive) / "volumes" / name
    if path.is_symlink():
        raise ValueError("volume must not be a symbolic link")
    with path.open("rb") as f:
        if f.read(len(MAGIC)) != MAGIC:
            raise ValueError("bad volume magic")
        f.seek(row["offset"])
        header = f.read(FRAME.size)
        if len(header) != FRAME.size:
            raise ValueError("truncated frame header")
        marker, digest, raw, stored = FRAME.unpack(header)
        if (marker != b"CHNK" or digest.hex() != row["hash"]
                or raw != row["raw_size"] or stored != row["stored_size"]):
            raise ValueError("frame and manifest disagree")
        if not 0 < raw <= CHUNK_SIZE or not 0 < stored <= CHUNK_SIZE + 1024 * 1024:
            raise ValueError("invalid chunk length")
        compressed = f.read(stored)
        if len(compressed) != stored:
            raise ValueError("truncated frame")
    block = decompress_block(compressed, raw)
    if hashlib.sha256(block).hexdigest() != row["hash"]:
        raise ValueError("chunk SHA256 mismatch")
    return block


def inventory(args):
    config = config_read(args.config, args.archive)
    result = {"format": FORMAT, "config": config, "counts": {}, "logical_bytes": 0,
              "unique_inode_bytes": 0, "excluded_prefixes": config["excludes"], "issues": []}
    inodes = set()
    for path, root, st, error in walk(config):
        if error:
            result["issues"].append({"path": path, "error": error})
            continue
        kind = kind_of(st)
        result["counts"][kind] = result["counts"].get(kind, 0) + 1
        if kind == "file":
            result["logical_bytes"] += st.st_size
            key = (st.st_dev, st.st_ino)
            if st.st_nlink == 1 or key not in inodes:
                result["unique_inode_bytes"] += st.st_size
            if st.st_nlink > 1:
                inodes.add(key)
        elif kind == "special":
            result["issues"].append({"path": path, "error": "unsupported special file"})
    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n")
    emit(**result)
    return 2 if result["issues"] else 0


def create(args):
    archive = Path(args.archive).absolute()
    if (archive / "SEALED.json").exists():
        raise ValueError("archive is sealed for upload; create a new archive instead of modifying it")
    archive.mkdir(parents=True, exist_ok=True)
    config = config_read(args.config, archive)
    db = db_open(archive)
    previous_config = meta_get(db, "config")
    if previous_config is not None and previous_config != config:
        if not getattr(args, "extend_scope", False):
            db.close()
            raise ValueError("config differs from existing archive; use --extend-scope only to append roots, or a new archive directory")
        if config["excludes"] != previous_config["excludes"]:
            db.close()
            raise ValueError("--extend-scope requires exactly the same excludes; exclusions cannot be added, removed, or changed")
        current_roots = {}
        for root in config["roots"]:
            if root["path"] in current_roots:
                db.close()
                raise ValueError("--extend-scope requires unique root paths; duplicate roots are not allowed")
            current_roots[root["path"]] = root["category"]
        for old_root in previous_config["roots"]:
            if old_root["path"] not in current_roots or current_roots[old_root["path"]] != old_root["category"]:
                db.close()
                raise ValueError("--extend-scope must preserve every old root path and category exactly: " + old_root["path"])
        added = [root for root in config["roots"] if root not in previous_config["roots"]]
        emit(event="scope_extension_validated", added_roots=added,
             preserved_root_count=len(previous_config["roots"]))
    if meta_get(db, "format", FORMAT) != FORMAT:
        raise ValueError("unsupported archive format")
    run = uuid.uuid4().hex
    meta_set(db, "format", FORMAT)
    meta_set(db, "config", config)
    meta_set(db, "chunk_size", CHUNK_SIZE)
    meta_set(db, "volume_limit", VOLUME_SIZE)
    meta_set(db, "latest_run", run)
    meta_set(db, "complete", False)
    db.commit()
    writer = VolumeWriter(archive, db)
    count, reused, logical, last_progress = 0, 0, 0, time.monotonic()

    def issue(path, message, severity="error"):
        db.execute("INSERT INTO issues(run,path,severity,message) VALUES(?,?,?,?)",
                   (run, path, severity, message))
        emit(event="source_issue", path=path, severity=severity, message=message)

    try:
        for path, root, st, scan_error in walk(config):
            if scan_error:
                issue(path, scan_error)
                db.execute("UPDATE files SET status='error',error=?,seen_run=? WHERE path=?",
                           (scan_error, run, path))
                writer.checkpoint()
                continue
            count += 1
            kind = kind_of(st)
            sig = signature(st)
            old = db.execute("SELECT * FROM files WHERE path=?", (path,)).fetchone()
            if old and old["status"] == "ok" and old["signature"] == sig:
                db.execute("UPDATE files SET seen_run=? WHERE path=?", (run, path))
                reused += 1
                logical += st.st_size if kind == "file" else 0
                if count % 250 == 0 or time.monotonic() - writer.last_checkpoint >= 1:
                    writer.checkpoint()
                if time.monotonic() - last_progress >= 10:
                    emit(event="progress", scanned=count, reused=reused, logical_bytes=logical)
                    last_progress = time.monotonic()
                continue
            attrs, attr_errors = xattrs_read(path)
            for error in attr_errors:
                issue(path, error)
            row = dict(path=path, root_path=root["path"], category=root["category"], kind=kind,
                       size=st.st_size, mode=st.st_mode, mtime_ns=st.st_mtime_ns,
                       atime_ns=st.st_atime_ns, uid=st.st_uid, gid=st.st_gid, dev=st.st_dev,
                       ino=st.st_ino, nlink=st.st_nlink, signature=sig, sha256=None,
                       link_target=None, hardlink_to=None,
                       xattrs_json=json.dumps(attrs, sort_keys=True), status="ok", error=None,
                       seen_run=run)
            hashes = []
            try:
                if kind == "file":
                    hard = None
                    if st.st_nlink > 1:
                        hard = db.execute("SELECT * FROM files WHERE dev=? AND ino=? AND status='ok' "
                                          "AND seen_run=? AND path<>? AND hardlink_to IS NULL LIMIT 1",
                                          (st.st_dev, st.st_ino, run, path)).fetchone()
                    if hard and hard["signature"] == sig:
                        row["hardlink_to"] = hard["path"]
                        row["sha256"] = hard["sha256"]
                        hashes = [r[0] for r in db.execute("SELECT hash FROM file_chunks WHERE path=? ORDER BY seq", (hard["path"],))]
                    else:
                        digest = hashlib.sha256()
                        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                        fd = os.open(path, flags)
                        with os.fdopen(fd, "rb") as source:
                            if signature(os.fstat(source.fileno())) != sig:
                                raise RuntimeError("source changed before reading")
                            while True:
                                block = source.read(CHUNK_SIZE)
                                if not block:
                                    break
                                digest.update(block)
                                hashes.append(writer.add(block))
                            if signature(os.fstat(source.fileno())) != sig:
                                raise RuntimeError("source changed while reading")
                        row["sha256"] = digest.hexdigest()
                    if signature(os.lstat(path)) != sig:
                        raise RuntimeError("source changed or replaced while backing up")
                    logical += st.st_size
                elif kind == "symlink":
                    row["link_target"] = os.readlink(path)
                    if signature(os.lstat(path)) != sig:
                        raise RuntimeError("symlink changed while backing up")
                elif kind == "special":
                    raise RuntimeError("unsupported special file; explicit exclusion or separate preservation required")
                if attr_errors:
                    raise RuntimeError("extended attributes could not all be captured")
            except (OSError, RuntimeError) as exc:
                row["status"], row["error"] = "error", str(exc)
                issue(path, str(exc))
            keys = list(row)
            db.execute("INSERT OR REPLACE INTO files (" + ",".join(keys) + ") VALUES (" + ",".join("?" for _ in keys) + ")",
                       [row[k] for k in keys])
            db.execute("DELETE FROM file_chunks WHERE path=?", (path,))
            db.executemany("INSERT INTO file_chunks VALUES(?,?,?)", [(path, i, h) for i, h in enumerate(hashes)])
            if count % 250 == 0 or time.monotonic() - writer.last_checkpoint >= 1:
                writer.checkpoint()
            if time.monotonic() - last_progress >= 10:
                emit(event="progress", scanned=count, reused=reused, logical_bytes=logical)
                last_progress = time.monotonic()
        missing = db.execute("SELECT path FROM files WHERE seen_run<>? OR seen_run IS NULL", (run,)).fetchall()
        for row in missing:
            issue(row[0], "previously archived path was not observed in this run")
            db.execute("UPDATE files SET status='missing',error=? WHERE path=?",
                       ("not observed in latest source traversal", row[0]))
        emit(event="source_consistency_check", entries=count)
        final_count = 0
        for path, root, st, scan_error in walk(config):
            final_count += 1
            if scan_error:
                issue(path, "final source traversal: " + scan_error)
                db.execute("UPDATE files SET status='error',error=? WHERE path=?",
                           ("final source traversal failed", path))
                continue
            saved = db.execute("SELECT signature,status,seen_run FROM files WHERE path=?", (path,)).fetchone()
            if saved is None or saved["seen_run"] != run:
                issue(path, "path appeared after initial traversal; rerun create to capture it")
            elif saved["status"] == "ok" and saved["signature"] != signature(st):
                message = "source metadata/content changed during the complete backup run; rerun create"
                issue(path, message)
                db.execute("UPDATE files SET status='error',error=? WHERE path=?", (message, path))
            if time.monotonic() - last_progress >= 10:
                emit(event="source_consistency_progress", checked=final_count)
                last_progress = time.monotonic()
        # Entries removed after their first visit are not yielded by the second
        # traversal. lstat them explicitly so their loss cannot be hidden.
        for saved in db.execute("SELECT path FROM files WHERE seen_run=? AND status='ok'", (run,)).fetchall():
            try:
                os.lstat(saved["path"])
            except OSError as exc:
                issue(saved["path"], "final existence check: " + str(exc))
                db.execute("UPDATE files SET status='error',error=? WHERE path=?",
                           ("path disappeared during backup", saved["path"]))
        errors = db.execute("SELECT count(*) FROM issues WHERE run=? AND severity='error'", (run,)).fetchone()[0]
        meta_set(db, "complete", errors == 0)
        meta_set(db, "created_unix", time.time())
        report = {"format": FORMAT, "run": run, "complete": errors == 0, "source_entries": count,
                  "reused_entries": reused, "logical_file_bytes": logical, "errors": errors,
                  "recovered_uncommitted_tails": writer.recovered,
                  "chunks": db.execute("SELECT count(*) FROM chunks").fetchone()[0],
                  "stored_chunk_bytes": db.execute("SELECT coalesce(sum(stored_size),0) FROM chunks").fetchone()[0]}
        meta_set(db, "last_create_report", report)
        writer.checkpoint()
        writer.close()
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.close()
        (archive / "create-report.json").write_text(json.dumps(report, indent=2) + "\n")
        emit(**report)
        return 2 if errors else 0
    finally:
        writer.close()
        try:
            db.close()
        except sqlite3.Error:
            pass


def chunks_for(db, path):
    return db.execute("SELECT c.* FROM file_chunks f LEFT JOIN chunks c ON c.hash=f.hash "
                      "WHERE f.path=? ORDER BY f.seq", (path,)).fetchall()


def verify(args):
    if args.seal:
        # A crash can leave the latest committed manifest only in its WAL.
        # Never distribute a main DB that omits those committed records.
        if not (Path(args.archive) / "manifest.sqlite3").is_file():
            raise ValueError("manifest does not exist")
        checkpoint_db = db_open(args.archive)
        checkpoint = checkpoint_db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        checkpoint_db.close()
        wal = Path(args.archive) / "manifest.sqlite3-wal"
        if checkpoint[0] != 0 or (wal.exists() and wal.stat().st_size != 0):
            raise ValueError("manifest WAL could not be fully checkpointed; stop other archive readers/writers and retry sealing")
    db = db_open(args.archive, readonly=True)
    errors, checked_chunks, checked_files, cache = [], set(), 0, set()
    if meta_get(db, "format") != FORMAT:
        raise ValueError("unsupported archive format")
    integrity = db.execute("PRAGMA integrity_check").fetchall()
    if [r[0] for r in integrity] != ["ok"]:
        errors.append({"manifest": [r[0] for r in integrity]})
    incomplete = db.execute("SELECT path,status,error FROM files WHERE status<>'ok'").fetchall()
    errors.extend(dict(r) for r in incomplete)
    if not meta_get(db, "complete", False):
        errors.append({"archive": "latest create run did not finish without source errors"})
    last_progress = time.monotonic()
    for row in db.execute("SELECT * FROM files WHERE kind='file' AND status='ok' ORDER BY path"):
        try:
            chunks = chunks_for(db, row["path"])
            if any(c["hash"] is None for c in chunks):
                raise ValueError("missing chunk object reference")
            identity = (row["sha256"], row["size"], tuple(c["hash"] for c in chunks))
            if identity not in cache:
                digest, size = hashlib.sha256(), 0
                for c in chunks:
                    block = read_chunk(args.archive, c)
                    digest.update(block)
                    size += len(block)
                    checked_chunks.add(c["hash"])
                if size != row["size"] or digest.hexdigest() != row["sha256"]:
                    raise ValueError("file size or SHA256 mismatch")
                cache.add(identity)
            checked_files += 1
        except (OSError, ValueError, zlib.error) as exc:
            errors.append({"path": row["path"], "error": str(exc)})
        if time.monotonic() - last_progress >= 10:
            emit(event="verify_progress", files=checked_files, chunks=len(checked_chunks))
            last_progress = time.monotonic()
    for c in db.execute("SELECT * FROM chunks"):
        if c["hash"] not in checked_chunks:
            try:
                read_chunk(args.archive, c)
                checked_chunks.add(c["hash"])
            except (OSError, ValueError, zlib.error) as exc:
                errors.append({"chunk": c["hash"], "error": str(exc)})
    for path in (Path(args.archive) / "volumes").glob("volume-*.bin"):
        if path.stat().st_size > VOLUME_SIZE:
            errors.append({"volume": path.name, "error": "volume exceeds 512 MiB"})
        try:
            with path.open("rb") as volume:
                if volume.read(len(MAGIC)) != MAGIC:
                    raise ValueError("bad volume magic")
                size, offset = path.stat().st_size, len(MAGIC)
                while offset < size:
                    volume.seek(offset)
                    header = volume.read(FRAME.size)
                    if len(header) != FRAME.size:
                        raise ValueError("trailing incomplete frame header; rerun create before verification")
                    marker, digest, raw, stored = FRAME.unpack(header)
                    if (marker != b"CHNK" or not 0 < raw <= CHUNK_SIZE
                            or not 0 < stored <= CHUNK_SIZE + 1024 * 1024
                            or offset + FRAME.size + stored > size):
                        raise ValueError("invalid or truncated frame in volume")
                    if not db.execute("SELECT 1 FROM chunks WHERE hash=?", (digest.hex(),)).fetchone():
                        raise ValueError("unindexed object; rerun create before verification")
                    offset += FRAME.size + stored
        except (OSError, ValueError) as exc:
            errors.append({"volume": path.name, "error": str(exc)})
    report = {"verified": not errors, "files": checked_files, "chunks": len(checked_chunks), "errors": errors}
    if not errors and args.seal:
        db.close()
        wal = Path(args.archive) / "manifest.sqlite3-wal"
        if wal.exists() and wal.stat().st_size != 0:
            raise ValueError("manifest WAL changed during verification; refusing to seal")
        sealed = Path(args.archive) / "SEALED.json"
        if sealed.exists():
            raise ValueError("archive is already sealed")
        assets = []
        for path in [Path(args.archive) / "manifest.sqlite3"] + sorted((Path(args.archive) / "volumes").glob("volume-*.bin")):
            digest = hashlib.sha256()
            with path.open("rb") as f:
                for block in iter(lambda: f.read(CHUNK_SIZE), b""):
                    digest.update(block)
            assets.append({"path": str(path.relative_to(args.archive)), "bytes": path.stat().st_size,
                           "sha256": digest.hexdigest()})
        with sealed.open("x") as f:
            json.dump({"format": FORMAT, "verified": True, "sealed_unix": time.time(), "assets": assets}, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        for entry in assets:
            os.chmod(Path(args.archive) / entry["path"], 0o400)
        os.chmod(sealed, 0o400)
        fsync_directory(Path(args.archive))
        report["sealed"] = True
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n")
    emit(**report)
    db.close()
    return 2 if errors else 0


def mapped_path(source, prefix, destination):
    # Treat the archive's pathname as untrusted. Reject lexical traversals.
    path = Path(source)
    if not path.is_absolute() or ".." in path.parts or "\x00" in source:
        raise ValueError("unsafe archived source path: " + repr(source))
    if under(source, prefix):
        relative = os.path.relpath(source, prefix)
    else:
        relative = os.path.join("rootfs", source.lstrip(os.sep))
    target = destination / relative
    if not under(os.path.abspath(target), str(destination)):
        raise ValueError("path escapes restore destination")
    return target


def safe_parents(path, destination):
    relative = path.relative_to(destination)
    cursor = destination
    for part in relative.parts[:-1]:
        cursor = cursor / part
        try:
            st = os.lstat(cursor)
        except FileNotFoundError:
            cursor.mkdir(mode=0o700)
            continue
        if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
            raise ValueError("unsafe non-directory/symlink parent: " + str(cursor))


def metadata_restore(path, row, errors):
    try:
        if row["kind"] != "symlink":
            # macOS requires owner-write permission for some xattrs. A hardlink
            # may share an inode whose final read-only mode was already applied
            # through an earlier restored path, so defer that restriction again.
            current_mode = stat.S_IMODE(os.lstat(path).st_mode)
            if not current_mode & stat.S_IWUSR:
                os.chmod(path, current_mode | stat.S_IWUSR, follow_symlinks=False)
    except (OSError, NotImplementedError) as exc:
        errors.append({"path": row["path"], "metadata_error": str(exc)})
    for name, encoded in json.loads(row["xattrs_json"] or "{}").items():
        try:
            xattr_set(path, name, base64.b64decode(encoded, validate=True))
        except (OSError, ValueError, AttributeError, NotImplementedError) as exc:
            errors.append({"path": row["path"], "xattr": name, "error": str(exc)})
    try:
        if row["kind"] != "symlink":
            os.chmod(path, stat.S_IMODE(row["mode"]), follow_symlinks=False)
        os.utime(path, ns=(row["atime_ns"], row["mtime_ns"]), follow_symlinks=False)
    except (OSError, NotImplementedError) as exc:
        errors.append({"path": row["path"], "metadata_error": str(exc)})


def restore_scope(prefixes, ancestors=True):
    if not prefixes:
        return "1", []
    parts, parameters = [], []
    for prefix in prefixes:
        child_prefix = prefix.rstrip(os.sep) + os.sep
        clause = "(path=? OR substr(path,1,?)=?"
        parameters.extend([prefix, len(child_prefix), child_prefix])
        if ancestors:
            clause += " OR (kind='directory' AND (path='/' OR substr(?,1,length(path)+1)=path||'/'))"
            parameters.append(prefix)
        parts.append(clause + ")")
    return "(" + " OR ".join(parts) + ")", parameters


def restore(args):
    db = db_open(args.archive, readonly=True)
    if meta_get(db, "format") != FORMAT:
        raise ValueError("unsupported archive format")
    if not meta_get(db, "complete", False) and not args.allow_incomplete:
        raise ValueError("archive incomplete; inspect issues; --allow-incomplete explicitly restores only successful entries")
    includes = sorted(set(absolute(p) for p in (args.include_prefix or [])))
    scope, scope_parameters = restore_scope(includes)
    for include in includes:
        one_scope, one_parameters = restore_scope([include], ancestors=False)
        if not db.execute("SELECT 1 FROM files WHERE status='ok' AND " + one_scope + " LIMIT 1", one_parameters).fetchone():
            raise ValueError("include prefix matches no successful archived entries: " + include)
    destination = Path(args.destination).absolute()
    if os.path.lexists(destination):
        raise ValueError("destination already exists; choose a new directory (never overwritten)")
    # Resolve the parent first, so a symlink in the chosen destination's parents
    # does not undermine subsequent lexical containment checks.
    destination = destination.parent.resolve() / destination.name
    destination.mkdir(parents=True, mode=0o700)
    prefix = absolute(args.source_prefix)
    errors, warnings, count = [], [], 0
    hardlink_fallbacks = []
    collisions = sqlite3.connect(":memory:")
    collisions.execute("CREATE TABLE targets(target TEXT PRIMARY KEY, source TEXT)")
    for row in db.execute("SELECT path FROM files WHERE status='ok' AND " + scope, scope_parameters):
        target = mapped_path(row["path"], prefix, destination)
        try:
            collisions.execute("INSERT INTO targets VALUES(?,?)", (str(target), row["path"]))
        except sqlite3.IntegrityError:
            raise ValueError("multiple source paths map to the same restore destination: " + str(target))
    # Symlinks are created last; no archive-controlled symlink is ever followed
    # while restoring file data. Directory metadata is applied after children.
    query = "SELECT * FROM files WHERE status='ok' AND " + scope + """
      ORDER BY CASE kind WHEN 'directory' THEN 0 WHEN 'file' THEN 1 WHEN 'symlink' THEN 2 ELSE 3 END,
        CASE WHEN hardlink_to IS NULL THEN 0 ELSE 1 END, length(path),path"""
    directories = []
    for row in db.execute(query, scope_parameters):
        target = mapped_path(row["path"], prefix, destination)
        try:
            safe_parents(target, destination)
            if row["kind"] == "directory":
                if target != destination:
                    if os.path.lexists(target):
                        if target.is_symlink() or not target.is_dir():
                            raise ValueError("directory conflicts with restored path")
                    else:
                        target.mkdir(mode=0o700)
                directories.append(row)
            elif row["kind"] == "file":
                original_selected = bool(row["hardlink_to"] and collisions.execute(
                    "SELECT 1 FROM targets WHERE target=?", (str(mapped_path(row["hardlink_to"], prefix, destination)),)).fetchone())
                if original_selected:
                    original = mapped_path(row["hardlink_to"], prefix, destination)
                    safe_parents(original, destination)
                    if not stat.S_ISREG(os.lstat(original).st_mode):
                        raise ValueError("hardlink target is not a regular file")
                    os.link(original, target, follow_symlinks=False)
                else:
                    if row["hardlink_to"]:
                        hardlink_fallbacks.append(row["path"])
                    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                    with os.fdopen(os.open(target, flags, 0o600), "wb") as out:
                        digest, size = hashlib.sha256(), 0
                        for c in chunks_for(db, row["path"]):
                            if c["hash"] is None:
                                raise ValueError("missing chunk reference")
                            block = read_chunk(args.archive, c)
                            out.write(block)
                            digest.update(block)
                            size += len(block)
                        out.flush()
                        os.fsync(out.fileno())
                    if size != row["size"] or digest.hexdigest() != row["sha256"]:
                        raise ValueError("restored file SHA256/size mismatch")
                metadata_restore(target, row, errors)
            elif row["kind"] == "symlink":
                link = row["link_target"]
                if os.path.isabs(link) and under(os.path.normpath(link), prefix):
                    link = str(mapped_path(os.path.normpath(link), prefix, destination))
                elif os.path.isabs(link):
                    warnings.append({"path": row["path"], "external_absolute_symlink": link})
                elif not under(os.path.abspath(target.parent / link), str(destination)):
                    warnings.append({"path": row["path"], "external_relative_symlink": link})
                os.symlink(link, target)
                metadata_restore(target, row, errors)
            else:
                raise ValueError("unsupported archived entry kind")
            count += 1
        except (OSError, ValueError, zlib.error) as exc:
            errors.append({"path": row["path"], "error": str(exc)})
    for row in reversed(directories):
        metadata_restore(mapped_path(row["path"], prefix, destination), row, errors)
    report = {"restored": not errors, "destination": str(destination), "entries": count,
              "errors": errors, "warnings": warnings,
              "scope": {"mode": "selected-prefixes" if includes else "all-successful-entries",
                        "include_prefixes": includes, "includes_archived_ancestor_directories": True,
                        "archive_complete": meta_get(db, "complete", False)},
              "full_archive_restored": not includes and not errors and meta_get(db, "complete", False),
              "hardlinks_restored_as_independent_files": hardlink_fallbacks,
              "ownership": "uid/gid retained in manifest; restored files belong to current user"}
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n")
    emit(**report)
    collisions.close()
    db.close()
    return 2 if errors else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("inventory", help="read-only source inventory; no content archived")
    p.add_argument("--config", required=True)
    p.add_argument("--archive", help="prospective archive path, automatically excluded")
    p.add_argument("--output", help="optional JSON report")
    p.set_defaults(func=inventory)
    p = sub.add_parser("create", help="create/resume archive; explicit --extend-scope permits only appended roots")
    p.add_argument("--config", required=True)
    p.add_argument("--archive", required=True)
    p.add_argument("--extend-scope", action="store_true", help="allow only additional roots while retaining all old path/category pairs and exactly the same excludes")
    p.set_defaults(func=create)
    p = sub.add_parser("verify", help="validate every object and every complete file SHA256")
    p.add_argument("--archive", required=True)
    p.add_argument("--output")
    p.add_argument("--seal", action="store_true", help="after successful verification, hash all assets and forbid further create runs")
    p.set_defaults(func=verify)
    p = sub.add_parser("restore", help="restore into a new destination without overwriting")
    p.add_argument("--archive", required=True)
    p.add_argument("--source-prefix", default="/Users/yangcong")
    p.add_argument("--destination", required=True)
    p.add_argument("--include-prefix", action="append", help="restore only this absolute source prefix plus ancestor directories; repeatable")
    p.add_argument("--allow-incomplete", action="store_true")
    p.add_argument("--output")
    p.set_defaults(func=restore)
    args = parser.parse_args()
    lock = None
    try:
        if args.command == "create" or (args.command == "verify" and args.seal):
            if args.command == "create":
                Path(args.archive).mkdir(parents=True, exist_ok=True)
            lock = (Path(args.archive) / ".create.lock").open("a+b")
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("another create process holds this archive lock")
        return args.func(args)
    except (OSError, ValueError, sqlite3.Error, zlib.error) as exc:
        emit(fatal=True, error=str(exc))
        return 2
    finally:
        if lock:
            lock.close()


if __name__ == "__main__":
    sys.exit(main())
