#!/usr/bin/env python3
"""Download, authenticate, decrypt and restore a Shuttl preservation release."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

DEFAULT_REPOSITORY = "yk4642d97f-boop/shuttl-preservation-20261011"
DEFAULT_TAG = "backup-20261011"
META_FILES = {"manifest.sqlite3", "create-report.json", "verify-report.json", "SEALED.json"}
HEX = re.compile(r"[0-9a-f]{64}\Z")
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def emit(**value):
    print(json.dumps(value, ensure_ascii=True), flush=True)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def durable_json(path, data):
    temporary = path.with_name(path.name + ".partial-" + uuid.uuid4().hex)
    with temporary.open("x", encoding="utf-8") as out:
        json.dump(data, out, ensure_ascii=True, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)
    fsync_directory(path.parent)


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def ensure_directory(path):
    if os.path.lexists(path):
        if path.is_symlink() or not path.is_dir():
            raise ValueError("cache path must be a real directory: " + str(path))
    else:
        path.mkdir(mode=0o700)


def checked_file(path, expected_hash, expected_size=None):
    if not os.path.lexists(path):
        return False
    if path.is_symlink() or not path.is_file():
        raise ValueError("cache asset must be a regular non-symlink file: " + str(path))
    if expected_size is not None and path.stat().st_size != expected_size:
        return False
    return digest(path) == expected_hash


def quarantine_invalid(path):
    if os.path.lexists(path):
        if path.is_symlink() or not path.is_file():
            raise ValueError("refusing to replace unsafe cache entry: " + str(path))
        invalid = path.with_name(path.name + ".invalid-" + uuid.uuid4().hex)
        path.rename(invalid)
        emit(event="invalid_cache_preserved", path=str(invalid))


def read_index(path):
    index = json.loads(path.read_text(encoding="utf-8"))
    if index.get("format") != "shuttl-delivery-v1" or index.get("archive_format") != "shuttl-preservation-v1":
        raise ValueError("unsupported payload index format")
    if index.get("complete") is not True or index.get("private_key_included") is not False:
        raise ValueError("payload index must describe a complete delivery without a private key")
    if index.get("transport") not in (None, "ciphertext-parts-v1"):
        raise ValueError("unsupported payload transport")
    assets, names, paths = [], set(), set()
    ignored = []
    for item in index.get("assets", []):
        if not isinstance(item, dict):
            raise ValueError("payload asset must be an object")
        name = item.get("name")
        if not isinstance(name, str) or not SAFE_NAME.fullmatch(name):
            raise ValueError("unsafe payload asset name")
        if name in names:
            raise ValueError("duplicate payload or part name in trusted index")
        names.add(name)
        if item.get("standalone_video"):
            if "parts" in item:
                raise ValueError("standalone videos cannot declare encrypted archive parts")
            ignored.append(item.get("name", "unnamed-video"))
            continue
        name, relative = item.get("name"), item.get("restore_path")
        if not isinstance(name, str) or not isinstance(relative, str):
            raise ValueError("encrypted asset lacks name or restore_path")
        if (relative not in META_FILES and not re.fullmatch(r"volumes/volume-[0-9]{6}\.bin", relative)):
            raise ValueError("unexpected or unsafe archive restore_path: " + relative)
        if name != PurePosixPath(relative).name + ".age":
            raise ValueError("encrypted asset name does not match its restore_path")
        if relative in paths:
            raise ValueError("duplicate encrypted asset in trusted index")
        if not HEX.fullmatch(str(item.get("sha256", ""))) or not HEX.fullmatch(str(item.get("plaintext_sha256", ""))):
            raise ValueError("asset hashes must be lowercase SHA256 hex")
        if type(item.get("bytes")) is not int or item["bytes"] <= 0:
            raise ValueError("encrypted asset has invalid byte length")
        if "parts" in item:
            parts = item["parts"]
            if index.get("transport") != "ciphertext-parts-v1":
                raise ValueError("parts require ciphertext-parts-v1 transport")
            if not isinstance(parts, list) or not 1 <= len(parts) <= 999999:
                raise ValueError("encrypted asset parts must be a nonempty bounded list")
            total = 0
            for ordinal, part in enumerate(parts, 1):
                expected_name = name[:-4] + ".part-%06d.age" % ordinal
                if not isinstance(part, dict) or part.get("name") != expected_name:
                    raise ValueError("unsafe or nonconsecutive encrypted part name")
                if part["name"] in names:
                    raise ValueError("duplicate payload or part name in trusted index")
                if not HEX.fullmatch(str(part.get("sha256", ""))):
                    raise ValueError("part hash must be lowercase SHA256 hex")
                if type(part.get("bytes")) is not int or part["bytes"] <= 0:
                    raise ValueError("part has invalid byte length")
                names.add(part["name"])
                total += part["bytes"]
            if total != item["bytes"]:
                raise ValueError("part byte lengths do not sum to parent ciphertext length")
        paths.add(relative)
        assets.append(item)
    if not META_FILES.issubset(paths):
        raise ValueError("trusted index is missing required archive metadata assets")
    return sorted(assets, key=lambda a: a["restore_path"]), ignored


def init_workdir(path, repository, tag, index_path):
    path = path.expanduser().absolute()
    if path.is_symlink():
        raise ValueError("workdir must not be a symlink")
    existed = path.exists()
    if existed and not path.is_dir():
        raise ValueError("workdir must be a directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    path = path.parent.resolve() / path.name
    marker = path / ".shuttl-recovery-workdir.json"
    identity = {"format": "shuttl-recovery-cache-v1", "repository": repository,
                "tag": tag, "trusted_index_sha256": digest(index_path)}
    if existed:
        if marker.is_symlink():
            raise ValueError("unsafe workdir marker symlink")
        if marker.exists():
            if json.loads(marker.read_text()) != identity:
                raise ValueError("workdir belongs to another repository/tag/index; select a new workdir")
        elif any(path.iterdir()):
            raise ValueError("existing nonempty workdir has no recovery marker; original directories are never overwritten")
    else:
        path.mkdir(mode=0o700)
    if not marker.exists():
        durable_json(marker, identity)
    for sub in ("cipher", "staging", "archive", "logs"):
        ensure_directory(path / sub)
    ensure_directory(path / "archive" / "volumes")
    return path


class Runner:
    def __init__(self, workdir):
        self.workdir = workdir
        history = workdir / "commands.json"
        self.commands = json.loads(history.read_text()) if history.exists() else []

    def run(self, command, purpose, keep_output=False):
        record = {"purpose": purpose, "argv": [str(a) for a in command], "started_unix": time.time()}
        self.commands.append(record)
        emit(event="command_started", purpose=purpose, argv=record["argv"])
        durable_json(self.workdir / "commands.json", self.commands)
        # gh/age diagnostics are deliberately not copied into logs: commands
        # contain no token or key content, and private credentials stay external.
        if keep_output:
            log = self.workdir / "logs" / (purpose + "-" + uuid.uuid4().hex + ".stdout.txt")
            with log.open("x", encoding="utf-8") as output, tempfile.TemporaryFile() as errors:
                process = subprocess.Popen(record["argv"], stdout=subprocess.PIPE, stderr=errors, text=True)
                for line in process.stdout:
                    output.write(line)
                    output.flush()
                    print(line, end="", flush=True)
                process.wait()
            record["stdout_log"] = str(log)
        else:
            process = subprocess.run(record["argv"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        record["exit_code"] = process.returncode
        record["finished_unix"] = time.time()
        durable_json(self.workdir / "commands.json", self.commands)
        if process.returncode:
            suggestion = " Check gh auth status and repository access." if command[0] == "gh" else ""
            raise RuntimeError("Command failed (exit %s) during %s.%s See commands.json for exact arguments." %
                               (process.returncode, purpose, suggestion))


def download_asset(asset, args, workdir, runner):
    target = workdir / "cipher" / asset["name"]
    if checked_file(target, asset["sha256"], asset["bytes"]):
        emit(event="cipher_reused", asset=asset["name"])
        return target
    quarantine_invalid(target)
    with tempfile.TemporaryDirectory(prefix="download-", dir=workdir / "staging") as folder:
        command = ["gh", "release", "download", args.tag, "--repo", args.repository,
                   "--pattern", asset["name"], "--dir", folder]
        runner.run(command, "download-" + asset["name"])
        downloaded = Path(folder) / asset["name"]
        if not checked_file(downloaded, asset["sha256"], asset["bytes"]):
            raise ValueError("Downloaded ciphertext SHA256/size mismatch: " + asset["name"])
        with downloaded.open("rb") as f:
            os.fsync(f.fileno())
        downloaded.rename(target)
        fsync_directory(target.parent)
    emit(event="cipher_downloaded_verified", asset=asset["name"], bytes=asset["bytes"])
    return target


def decrypt_asset(asset, cipher, args, workdir, runner):
    target = workdir / "archive" / asset["restore_path"]
    if checked_file(target, asset["plaintext_sha256"]):
        emit(event="plaintext_reused", asset=asset["name"])
        return
    quarantine_invalid(target)
    partial = target.with_name(target.name + ".partial-" + uuid.uuid4().hex)
    try:
        runner.run(["age", "--decrypt", "--identity", str(args.identity), "--output", str(partial), str(cipher)],
                   "decrypt-" + asset["name"])
        if not checked_file(partial, asset["plaintext_sha256"]):
            raise ValueError("Decrypted plaintext SHA256 mismatch: " + asset["name"])
        with partial.open("rb") as f:
            os.fsync(f.fileno())
        partial.rename(target)
        fsync_directory(target.parent)
    finally:
        if partial.exists():
            partial.unlink()
    emit(event="plaintext_decrypted_verified", asset=asset["name"])


def verify_parts(asset, paths, output=None):
    """Authenticate concatenated ciphertext without retaining another full copy."""
    parent_hash, total = hashlib.sha256(), 0
    for part, path in zip(asset["parts"], paths):
        part_hash, part_bytes = hashlib.sha256(), 0
        with path.open("rb") as source:
            for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
                part_hash.update(block)
                parent_hash.update(block)
                part_bytes += len(block)
                total += len(block)
                if output is not None:
                    output.write(block)
        if part_bytes != part["bytes"] or part_hash.hexdigest() != part["sha256"]:
            raise ValueError("Cached ciphertext part SHA256/size mismatch: " + part["name"])
    if total != asset["bytes"] or parent_hash.hexdigest() != asset["sha256"]:
        raise ValueError("Combined ciphertext SHA256/size mismatch: " + asset["name"])
    emit(event="cipher_parts_verified", asset=asset["name"], parts=len(paths), bytes=total)


def recover_asset(asset, args, workdir, runner):
    if "parts" not in asset:
        cipher = download_asset(asset, args, workdir, runner)
        if not args.download_only:
            decrypt_asset(asset, cipher, args, workdir, runner)
        return
    paths = [download_asset(part, args, workdir, runner) for part in asset["parts"]]
    target = workdir / "archive" / asset["restore_path"]
    plaintext_ready = not args.download_only and checked_file(target, asset["plaintext_sha256"])
    if args.download_only or plaintext_ready:
        # Download-only and resumed plaintext need a streaming hash, no merged file.
        verify_parts(asset, paths)
        if plaintext_ready:
            emit(event="plaintext_reused", asset=asset["name"])
        return
    # Only one parent ciphertext exists transiently. Parts remain the durable
    # resume cache; TemporaryDirectory also removes the merged file on failure.
    with tempfile.TemporaryDirectory(prefix="assemble-", dir=workdir / "staging") as folder:
        cipher = Path(folder) / asset["name"]
        with cipher.open("xb") as output:
            verify_parts(asset, paths, output)
            output.flush()
            os.fsync(output.fileno())
        decrypt_asset(asset, cipher, args, workdir, runner)


def validate_archive_metadata(workdir, assets):
    archive = workdir / "archive"
    created = json.loads((archive / "create-report.json").read_text())
    verified = json.loads((archive / "verify-report.json").read_text())
    seal = json.loads((archive / "SEALED.json").read_text())
    if created.get("complete") is not True or verified.get("verified") is not True or seal.get("verified") is not True:
        raise ValueError("decrypted archive reports do not confirm complete and verified preservation")
    expected = {a["restore_path"]: a for a in assets if a["restore_path"] == "manifest.sqlite3" or a["restore_path"].startswith("volumes/")}
    sealed_assets = {a["path"]: a for a in seal.get("assets", [])}
    if set(expected) != set(sealed_assets):
        raise ValueError("sealed archive asset list differs from trusted delivery index")
    for path, item in sealed_assets.items():
        if item.get("sha256") != expected[path]["plaintext_sha256"]:
            raise ValueError("sealed asset hash disagrees with trusted index: " + path)
        if (archive / path).stat().st_size != item.get("bytes"):
            raise ValueError("sealed plaintext size mismatch: " + path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--tag", default=DEFAULT_TAG)
    parser.add_argument("--identity", type=Path, help="external age private key; required unless --download-only")
    parser.add_argument("--workdir", type=Path, required=True, help="new or matching managed recovery cache")
    parser.add_argument("--destination", type=Path, help="nonexistent restore destination")
    parser.add_argument("--include-prefix", action="append", default=[], help="repeatable absolute source prefix for selective restore")
    parser.add_argument("--source-prefix", default="/Users/yangcong")
    parser.add_argument("--download-only", action="store_true", help="download and verify ciphertext; no key/decryption/restore")
    parser.add_argument("--index", type=Path, default=Path(__file__).resolve().parent.parent / "recovery" / "payload-index.json",
                        help="trusted local index (defaults to ../recovery/payload-index.json in clone)")
    args = parser.parse_args()
    workdir = None
    lock = None
    report = {"repository": args.repository, "tag": args.tag, "download_only": args.download_only,
              "include_prefixes": args.include_prefix, "complete": False}
    try:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
            raise ValueError("invalid owner/repository")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", args.tag):
            raise ValueError("unsupported release tag")
        args.index = args.index.expanduser().resolve(strict=True)
        assets, ignored = read_index(args.index)
        if not shutil.which("gh"):
            raise ValueError("GitHub CLI gh is required; install it and authenticate with gh auth login")
        if not args.download_only:
            if args.identity is None or args.destination is None:
                raise ValueError("--identity and --destination are required for restore")
            args.identity = args.identity.expanduser().resolve(strict=True)
            if not args.identity.is_file():
                raise ValueError("identity must be an external readable file")
            if not shutil.which("age"):
                raise ValueError("age is required for decryption")
            args.destination = args.destination.expanduser().absolute()
            if os.path.lexists(args.destination):
                raise ValueError("destination already exists; original directories are never overwritten")
        workdir = init_workdir(args.workdir, args.repository, args.tag, args.index)
        lock = (workdir / ".recovery.lock").open("a+b")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("another recovery process is using this workdir")
        runner = Runner(workdir)
        report.update(trusted_index_sha256=digest(args.index), archive_assets=len(assets),
                      transport_assets=sum(len(a.get("parts", [a])) for a in assets),
                      ignored_standalone_videos=ignored, workdir=str(workdir))
        durable_json(workdir / "recovery-report.json", report)
        for asset in assets:
            recover_asset(asset, args, workdir, runner)
        report["ciphertexts_verified"] = True
        if args.download_only:
            report.update(complete=True, restored=False, full_archive_restored=False)
        else:
            validate_archive_metadata(workdir, assets)
            tool = Path(__file__).resolve().with_name("shuttl_backup.py")
            if not tool.is_file():
                raise ValueError("shuttl_backup.py must be adjacent to this recovery helper")
            verification = workdir / "recovered-archive-verification.json"
            runner.run([sys.executable, str(tool), "verify", "--archive", str(workdir / "archive"),
                        "--output", str(verification)], "verify-recovered-archive", keep_output=True)
            if json.loads(verification.read_text()).get("verified") is not True:
                raise ValueError("recovered archive verification did not report success")
            restoration = workdir / "restore-report.json"
            command = [sys.executable, str(tool), "restore", "--archive", str(workdir / "archive"),
                       "--source-prefix", args.source_prefix, "--destination", str(args.destination),
                       "--output", str(restoration)]
            for prefix in args.include_prefix:
                command += ["--include-prefix", prefix]
            runner.run(command, "restore-selected-scope" if args.include_prefix else "restore-full-archive", keep_output=True)
            restored = json.loads(restoration.read_text())
            if restored.get("restored") is not True:
                raise ValueError("restore did not report success; inspect restore-report.json")
            report.update(complete=True, restored=True, destination=restored["destination"],
                          full_archive_restored=restored["full_archive_restored"], scope=restored["scope"],
                          plaintexts_verified=True, verification_report=str(verification), restore_report=str(restoration))
        durable_json(workdir / "recovery-report.json", report)
        emit(**report)
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, json.JSONDecodeError) as exc:
        report["error"] = str(exc)
        if workdir:
            durable_json(workdir / "recovery-report.json", report)
        emit(**report)
        return 2
    finally:
        if lock:
            lock.close()


if __name__ == "__main__":
    sys.exit(main())
