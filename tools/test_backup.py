#!/usr/bin/env python3
"""End-to-end fixture tests for the preservation format (no project sources)."""
import hashlib
import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

TOOL = Path(__file__).with_name("shuttl_backup.py")


def run(*args, expected=0):
    p = subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True)
    if p.returncode != expected:
        raise AssertionError((args, p.returncode, p.stdout, p.stderr))
    return json.loads(p.stdout.splitlines()[-1])


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def main():
    checks = []
    spec = importlib.util.spec_from_file_location("backup", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with tempfile.TemporaryDirectory(prefix="shuttl-backup-test-") as temporary:
        base = Path(temporary)
        source, other, archive = base / "source", base / "other", base / "archive"
        (source / "nested" / "中文 space").mkdir(parents=True)
        other.mkdir()
        (source / "empty").touch()
        (source / "nested" / "binary.dat").write_bytes(bytes(range(256)) * 4096)
        (source / "nested" / "中文 space" / "text.txt").write_text("Shuttl\n中文\x00binary\n")
        (other / "outside.txt").write_text("outside source prefix")
        block = bytes(range(256)) * 4096
        big = source / "larger-than-chunk.bin"
        with big.open("wb") as f:
            for _ in range(65):
                f.write(block)
            f.write(b"last chunk\x00\xff")
        shutil.copyfile(big, source / "duplicate.bin")
        os.link(source / "nested" / "binary.dat", source / "hardlink.dat")
        os.symlink("nested/binary.dat", source / "relative-link")
        os.symlink(str(source / "nested" / "binary.dat"), source / "absolute-link")
        os.symlink("/deliberately/missing", source / "dangling-external-link")
        excluded = source / "excluded"
        excluded.mkdir()
        (excluded / "not-backed-up").write_text("excluded")
        os.chmod(source / "nested" / "binary.dat", 0o640)
        os.utime(source / "nested" / "binary.dat", ns=(1600000000000000000, 1600000000123456789))
        xattr = None
        if hasattr(os, "setxattr") or mod.DARWIN_XATTR is not None:
            xattr = "com.example.shuttl.test" if sys.platform == "darwin" else "user.shuttl.test"
            mod.xattr_set(source / "nested" / "binary.dat", xattr, b"attribute\x00\xff")
        config = base / "config.json"
        config.write_text(json.dumps({"roots": [{"path": str(source), "category": "test"},
                                                {"path": str(other), "category": "external"}],
                                      "excludes": [str(excluded)]}))
        inventory = run("inventory", "--config", config)
        assert inventory["counts"]["symlink"] == 3
        checks.append("read-only inventory, exact-prefix exclusion, no symlink traversal")
        created = run("create", "--config", config, "--archive", archive)
        assert created["complete"]
        assert created["stored_chunk_bytes"] < 2 * 1024 * 1024
        checks.append("64 MiB boundary, binary data, empty file, nested Unicode paths, compression and dedup")
        volume_sizes = {p.name: p.stat().st_size for p in (archive / "volumes").glob("*.bin")}
        resumed = run("create", "--config", config, "--archive", archive)
        assert resumed["reused_entries"] == resumed["source_entries"]
        assert volume_sizes == {p.name: p.stat().st_size for p in (archive / "volumes").glob("*.bin")}
        checks.append("completed-run resume reuses all file records and objects")
        verified = run("verify", "--archive", archive)
        assert verified["verified"]
        restored = base / "restored"
        result = run("restore", "--archive", archive, "--source-prefix", source, "--destination", restored)
        assert result["restored"]
        restored = Path(result["destination"])
        for p in source.rglob("*"):
            if p.is_file() and not p.is_symlink() and excluded not in p.parents:
                assert sha(p) == sha(restored / p.relative_to(source))
        assert not (restored / "excluded").exists()
        assert (restored / "rootfs" / str(other / "outside.txt").lstrip("/")).read_text() == "outside source prefix"
        assert os.readlink(restored / "relative-link") == "nested/binary.dat"
        assert os.readlink(restored / "absolute-link") == str(restored / "nested" / "binary.dat")
        assert os.readlink(restored / "dangling-external-link") == "/deliberately/missing"
        a, b = (restored / "hardlink.dat").stat(), (restored / "nested" / "binary.dat").stat()
        assert a.st_ino == b.st_ino and a.st_dev == b.st_dev
        assert a.st_mode & 0o777 == 0o640
        assert a.st_mtime_ns == (source / "hardlink.dat").stat().st_mtime_ns
        if xattr:
            assert mod.xattr_get(restored / "hardlink.dat", xattr) == b"attribute\x00\xff"
        checks.append("complete SHA256 restoration, rootfs mapping, soft/hard links, mode, mtime, xattr")
        db = sqlite3.connect(archive / "manifest.sqlite3")
        hard_member, hard_original = db.execute("SELECT path,hardlink_to FROM files WHERE hardlink_to IS NOT NULL LIMIT 1").fetchone()
        db.close()
        selective = base / "selected-restore"
        selection = run("restore", "--archive", archive, "--source-prefix", source,
                        "--destination", selective, "--include-prefix", hard_member,
                        "--include-prefix", other / "outside.txt")
        selective = Path(selection["destination"])
        assert selection["restored"] and not selection["full_archive_restored"]
        assert selection["scope"]["mode"] == "selected-prefixes"
        assert selection["hardlinks_restored_as_independent_files"] == [hard_member]
        assert sha(selective / Path(hard_member).relative_to(source)) == sha(Path(hard_member))
        assert not (selective / Path(hard_original).relative_to(source)).exists()
        assert not (selective / "larger-than-chunk.bin").exists()
        assert (selective / "rootfs" / str(other / "outside.txt").lstrip("/")).is_file()
        run("restore", "--archive", archive, "--destination", base / "no-match",
            "--include-prefix", source / "definitely-absent", expected=2)
        assert not (base / "no-match").exists()
        checks.append("repeatable prefix selection includes ancestors, excludes unrelated files, and restores hardlink bytes when original is outside scope")
        run("restore", "--archive", archive, "--destination", restored, expected=2)
        checks.append("existing destination rejected without overwrite")
        volume = next((archive / "volumes").glob("*.bin"))
        with volume.open("ab") as f:
            f.write(b"CHN")
        recovered = run("create", "--config", config, "--archive", archive)
        assert recovered["recovered_uncommitted_tails"][0]["truncated_uncommitted_tail"] == 3
        checks.append("interrupted frame-header tail safely recovered")
        db = sqlite3.connect(archive / "manifest.sqlite3")
        digest = db.execute("SELECT hash FROM chunks LIMIT 1").fetchone()[0]
        db.execute("DELETE FROM chunks WHERE hash=?", (digest,))
        db.commit()
        db.close()
        run("create", "--config", config, "--archive", archive)
        assert run("verify", "--archive", archive)["verified"]
        checks.append("fsynced object with missing DB commit re-indexed and hash-validated")
        data = bytearray(volume.read_bytes())
        data[-1] ^= 0x01
        volume.write_bytes(data)
        assert not run("verify", "--archive", archive, expected=2)["verified"]
        checks.append("compressed-object corruption detected")
        data[-1] ^= 0x01
        volume.write_bytes(data)
        (source / "empty").unlink()
        report = run("create", "--config", config, "--archive", archive, expected=2)
        assert not report["complete"]
        run("restore", "--archive", archive, "--destination", base / "incomplete-restore", expected=2)
        checks.append("disappeared source reported; incomplete restore refused by default")
        changing = base / "changing"
        changing.mkdir()
        changing_file = changing / "live.bin"
        changing_file.write_bytes(b"original" * 1024)
        changing_config = base / "changing-config.json"
        changing_config.write_text(json.dumps({"roots": [{"path": str(changing)}]}))
        original_add = mod.VolumeWriter.add
        mutated = []

        def mutate_after_read(self, data):
            result = original_add(self, data)
            if not mutated:
                with changing_file.open("ab") as f:
                    f.write(b"changed during backup")
                mutated.append(True)
            return result

        mod.VolumeWriter.add = mutate_after_read
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                code = mod.create(argparse.Namespace(archive=str(base / "changing-archive"), config=str(changing_config)))
            assert code == 2
        finally:
            mod.VolumeWriter.add = original_add
        checks.append("real source mutation during content capture explicitly fails the run")
        run("create", "--config", changing_config, "--archive", base / "changing-archive")
        wal_keeper = sqlite3.connect(base / "changing-archive" / "manifest.sqlite3")
        wal_keeper.execute("PRAGMA journal_mode=WAL")
        wal_keeper.execute("INSERT INTO metadata VALUES('committed_wal_probe', '\"must survive without WAL\"')")
        wal_keeper.commit()
        assert (base / "changing-archive" / "manifest.sqlite3-wal").stat().st_size > 0
        seal_report = run("verify", "--archive", base / "changing-archive", "--seal")
        assert seal_report["sealed"]
        wal_keeper.close()
        seal = json.loads((base / "changing-archive" / "SEALED.json").read_text())
        for asset in seal["assets"]:
            assert sha(base / "changing-archive" / asset["path"]) == asset["sha256"]
        run("create", "--config", changing_config, "--archive", base / "changing-archive", expected=2)
        assert run("verify", "--archive", base / "changing-archive")["verified"]
        assert run("restore", "--archive", base / "changing-archive", "--source-prefix", changing,
                   "--destination", base / "sealed-restored")["restored"]
        checks.append("sealed asset hashes match; further creation blocked; sealed verify/restore still work")
        sealed_copy = base / "sealed-copy-without-wal"
        (sealed_copy / "volumes").mkdir(parents=True)
        for asset in seal["assets"]:
            shutil.copyfile(base / "changing-archive" / asset["path"], sealed_copy / asset["path"])
        shutil.copyfile(base / "changing-archive" / "SEALED.json", sealed_copy / "SEALED.json")
        # Verify before any read/write SQLite connection can initialize sidecars.
        assert run("verify", "--archive", sealed_copy)["verified"]
        copied_db = sqlite3.connect(sealed_copy / "manifest.sqlite3")
        assert copied_db.execute("SELECT value FROM metadata WHERE key='committed_wal_probe'").fetchone()[0] == '"must survive without WAL"'
        copied_db.close()
        assert run("verify", "--archive", sealed_copy)["verified"]
        (sealed_copy / "manifest.sqlite3-wal").write_bytes(b"nonempty journal must never be ignored")
        run("verify", "--archive", sealed_copy, expected=2)
        checks.append("committed WAL checkpointed before sealing; fresh copied sealed assets verify without sidecar initialization; nonempty sealed WAL is rejected")
        dangerous = base / "unsafe-archive"
        run("create", "--config", changing_config, "--archive", dangerous)
        db = sqlite3.connect(dangerous / "manifest.sqlite3")
        db.execute("UPDATE files SET path='/Users/yangcong/../escape' WHERE kind='file'")
        db.commit()
        db.close()
        run("restore", "--archive", dangerous, "--destination", base / "unsafe-restore", expected=2)
        assert not (base / "escape").exists()
        checks.append("untrusted archive path traversal rejected")
        # Exercise rollover with reduced constants, using the identical format.
        spec = importlib.util.spec_from_file_location("backup", TOOL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        rollover = base / "rollover"
        rollover.mkdir()
        db = mod.db_open(rollover)
        mod.VOLUME_SIZE = 2 * 1024 * 1024
        writer = mod.VolumeWriter(rollover, db)
        for _ in range(3):
            writer.add(os.urandom(1200 * 1024))
        writer.close()
        paths = list((rollover / "volumes").glob("*.bin"))
        assert len(paths) == 3 and all(p.stat().st_size <= mod.VOLUME_SIZE for p in paths)
        for row in db.execute("SELECT * FROM chunks"):
            mod.read_chunk(rollover, row)
        db.close()
        checks.append("volume rollover honors configured cap; all rolled objects readable")
        mod.VOLUME_SIZE = 512 * 1024 * 1024
        adaptive = base / "adaptive-compression"
        adaptive.mkdir()
        db = mod.db_open(adaptive)
        writer = mod.VolumeWriter(adaptive, db)
        noise = os.urandom(2 * 1024 * 1024)
        repeated = b"Shuttl\x00\xff" * (2 * 1024 * 1024 // 8)
        assert mod.compression_level(noise) == 0
        assert mod.compression_level(repeated) == 1
        assert mod.compression_level(noise[:1024 * 1024 - 1]) == 1
        for data in [noise, repeated]:
            expected = hashlib.sha256(data).hexdigest()
            assert writer.add(data) == expected
            writer.checkpoint()
            row = db.execute("SELECT * FROM chunks WHERE hash=?", (expected,)).fetchone()
            recovered = mod.read_chunk(adaptive, row)
            assert recovered == data and hashlib.sha256(recovered).hexdigest() == expected
            assert row["stored_size"] == len(mod.zlib.compress(data, mod.compression_level(data)))
        size_before = writer.handle.tell()
        assert writer.add(noise) == hashlib.sha256(noise).hexdigest()
        assert writer.handle.tell() == size_before
        writer.close()
        db.close()
        checks.append("adaptive random chunk uses zlib level 0; compressible chunk uses level 1; raw SHA256, dedup and bounded volume reader remain unchanged")
    report = {"passed": True, "checks": checks, "python": sys.version.split()[0]}
    Path(__file__).with_name("test-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
