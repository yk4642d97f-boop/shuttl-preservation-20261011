#!/usr/bin/env python3
"""Offline end-to-end recovery test: simulated gh downloads, real age crypto."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(argv, env=None, expected=0):
    result = subprocess.run([str(a) for a in argv], env=env, capture_output=True, text=True)
    if result.returncode != expected:
        details = []
        if "--workdir" in argv:
            workdir = Path(argv[argv.index("--workdir") + 1])
            for log in (workdir / "logs").glob("*.txt"):
                details.append(log.read_text())
        raise AssertionError((argv, result.returncode, result.stdout, result.stderr, details))
    return result


def main():
    if not shutil.which("age") or not shutil.which("age-keygen"):
        raise SystemExit("Tests require real age and age-keygen; no network needed.")
    checks = []
    with tempfile.TemporaryDirectory(prefix="shuttl-github-recovery-test-") as name:
        base = Path(name)
        source, archive, remote, clone = base / "source", base / "archive", base / "remote", base / "clone"
        source.mkdir()
        (source / "nested").mkdir()
        (source / "nested" / "keep.bin").write_bytes(bytes(range(256)) * 4096)
        (source / "omit.txt").write_text("not selected in partial recovery")
        config = base / "config.json"
        config.write_text(json.dumps({"roots": [{"path": str(source), "category": "test"}]}))
        run([sys.executable, HERE / "shuttl_backup.py", "create", "--config", config, "--archive", archive])
        run([sys.executable, HERE / "shuttl_backup.py", "verify", "--archive", archive, "--seal", "--output", archive / "verify-report.json"])
        key = base / "external-recovery-key.txt"
        run(["age-keygen", "--output", key])
        recipient = run(["age-keygen", "-y", key]).stdout.strip()
        remote.mkdir()
        (clone / "tools").mkdir(parents=True)
        (clone / "recovery").mkdir()
        for filename in ["shuttl_backup.py", "recover_from_github.py"]:
            shutil.copyfile(HERE / filename, clone / "tools" / filename)
        assets = []
        sources = [archive / p for p in ["manifest.sqlite3", "create-report.json", "verify-report.json", "SEALED.json"]]
        sources += list((archive / "volumes").glob("*.bin"))
        for path in sources:
            ciphertext = remote / (path.name + ".age")
            run(["age", "-r", recipient, "-o", ciphertext, path])
            assets.append({"name": ciphertext.name, "bytes": ciphertext.stat().st_size, "sha256": sha(ciphertext),
                           "plaintext_sha256": sha(path), "restore_path": str(path.relative_to(archive))})
        assets.append({"name": "not-downloaded-video.mp4", "bytes": 123, "sha256": "0" * 64, "standalone_video": True})
        index = {"format": "shuttl-delivery-v1", "archive_format": "shuttl-preservation-v1", "complete": True,
                 "private_key_included": False, "recipient": recipient, "assets": assets}
        (clone / "recovery" / "payload-index.json").write_text(json.dumps(index))
        fakebin = base / "fakebin"
        fakebin.mkdir()
        fakegh = fakebin / "gh"
        fakegh.write_text("#!" + sys.executable + "\n" + '''import os,sys,shutil
from pathlib import Path
a=sys.argv[1:]
assert a[:2]==['release','download']
assert a[2]=='backup-20261011'
assert a[a.index('--repo')+1]=='yk4642d97f-boop/shuttl-preservation-20261011'
name=a[a.index('--pattern')+1]
assert '*' not in name and '?' not in name and '/' not in name
out=Path(a[a.index('--dir')+1])/name
with Path(os.environ['TEST_GH_CALLS']).open('a') as f:f.write(name+'\\n')
if os.environ.get('TEST_GH_CORRUPT')=='1' or os.environ.get('TEST_GH_CORRUPT_NAME')==name:out.write_bytes(b'corrupted download')
else:shutil.copyfile(Path(os.environ['TEST_GH_REMOTE'])/name,out)
''')
        fakegh.chmod(0o700)
        env = dict(os.environ)
        env.update(PATH=str(fakebin) + os.pathsep + env.get("PATH", ""), TEST_GH_REMOTE=str(remote), TEST_GH_CALLS=str(base / "gh-calls.txt"))
        helper = clone / "tools" / "recover_from_github.py"
        cache = base / "cache"
        # No explicit --index: exercise discovery relative to clone/tools.
        command = [sys.executable, helper, "--workdir", cache]
        result = run(command + ["--download-only"], env)
        report = json.loads(result.stdout.splitlines()[-1])
        assert report["complete"] and not report["restored"]
        assert not list((cache / "archive").glob("*.sqlite3"))
        calls = (base / "gh-calls.txt").read_text().splitlines()
        assert len(calls) == len(assets) - 1 and "not-downloaded-video.mp4" not in calls
        checks.append("trusted index found relative to cloned helper; exact gh asset requests; standalone videos skipped; download-only needs no key")
        run(command + ["--download-only"], env)
        assert (base / "gh-calls.txt").read_text().splitlines() == calls
        checks.append("SHA256-matching ciphertext cache reused without additional gh requests")
        partial = base / "selective-destination"
        result = run(command + ["--identity", key, "--source-prefix", source, "--destination", partial,
                                "--include-prefix", source / "nested"], env)
        report = json.loads(result.stdout.splitlines()[-1])
        assert report["complete"] and report["restored"] and not report["full_archive_restored"]
        assert sha(partial / "nested" / "keep.bin") == sha(source / "nested" / "keep.bin")
        assert not (partial / "omit.txt").exists()
        assert not any(p.name == key.name for p in clone.rglob("*"))
        assert not any(p.name == key.name for p in cache.rglob("*"))
        checks.append("real age decryption and plaintext hashes; full archive verify then selective restoration; key never copied")
        full = base / "full-destination"
        run(command + ["--identity", key, "--source-prefix", source, "--destination", full], env)
        assert (full / "omit.txt").read_text() == (source / "omit.txt").read_text()
        assert (base / "gh-calls.txt").read_text().splitlines() == calls
        checks.append("verified plaintext reused for subsequent full restoration")
        run(command + ["--identity", key, "--destination", full], env, expected=2)
        unsafe = base / "original-nonempty-directory"
        unsafe.mkdir()
        (unsafe / "keep-original").write_text("untouched")
        run([sys.executable, helper, "--workdir", unsafe, "--download-only"], env, expected=2)
        assert (unsafe / "keep-original").read_text() == "untouched"
        checks.append("existing destination and unmanaged nonempty workdir rejected without touching originals")
        corrupted_cache = base / "corrupted-download-cache"
        corrupt_env = dict(env, TEST_GH_CORRUPT="1")
        result = run([sys.executable, helper, "--workdir", corrupted_cache, "--download-only"], corrupt_env, expected=2)
        assert "SHA256/size mismatch" in result.stdout
        assert not list((corrupted_cache / "cipher").glob("*.age"))
        checks.append("corrupt remote download rejected before ciphertext promotion")
        wrong_key = base / "wrong-external-key.txt"
        run(["age-keygen", "--output", wrong_key])
        result = run([sys.executable, helper, "--workdir", base / "wrong-key-cache", "--identity", wrong_key,
                      "--destination", base / "wrong-key-destination"], env, expected=2)
        assert "Command failed" in result.stdout and not (base / "wrong-key-destination").exists()
        checks.append("wrong age key fails explicitly before restore; exact command log retained")
        # A valid encrypted blob with a wrong trusted plaintext digest must fail.
        bad_index = base / "bad-plaintext-index.json"
        corrupted_index = json.loads(json.dumps(index))
        corrupted_index["assets"][0]["plaintext_sha256"] = "f" * 64
        bad_index.write_text(json.dumps(corrupted_index))
        result = run([sys.executable, helper, "--index", bad_index, "--workdir", base / "bad-plaintext-cache",
                      "--identity", key, "--destination", base / "bad-plaintext-destination"], env, expected=2)
        assert "plaintext SHA256 mismatch" in result.stdout
        checks.append("valid age ciphertext cannot bypass trusted plaintext SHA256 verification")

        # The real age ciphertext remains unchanged; only its transport is split.
        split_remote = base / "remote-parts"
        shutil.copytree(remote, split_remote)
        split_index = json.loads(json.dumps(index))
        split_index["transport"] = "ciphertext-parts-v1"
        split_parents = []
        for item in split_index["assets"]:
            if item.get("restore_path") != "manifest.sqlite3" and not item.get("restore_path", "").startswith("volumes/"):
                continue
            payload = (remote / item["name"]).read_bytes()
            width = max(1, len(payload) // 3)
            item["parts"] = []
            for ordinal, offset in enumerate(range(0, len(payload), width), 1):
                part_name = item["name"][:-4] + ".part-%06d.age" % ordinal
                part = split_remote / part_name
                part.write_bytes(payload[offset:offset + width])
                item["parts"].append({"name": part_name, "bytes": part.stat().st_size, "sha256": sha(part)})
            assert len(item["parts"]) >= 3
            split_parents.append(item)
            (split_remote / item["name"]).unlink()
        split_index_path = base / "split-index.json"
        split_index_path.write_text(json.dumps(split_index))
        split_calls_path = base / "split-gh-calls.txt"
        split_env = dict(env, TEST_GH_REMOTE=str(split_remote), TEST_GH_CALLS=str(split_calls_path))
        split_cache = base / "split-cache"
        split_command = [sys.executable, helper, "--index", split_index_path, "--workdir", split_cache]
        result = run(split_command + ["--download-only"], split_env)
        split_report = json.loads(result.stdout.splitlines()[-1])
        assert split_report["complete"] and split_report["ciphertexts_verified"]
        expected_names = sorted(part["name"] for a in split_index["assets"] if not a.get("standalone_video")
                                for part in a.get("parts", [a]))
        split_calls = split_calls_path.read_text().splitlines()
        assert sorted(split_calls) == expected_names
        assert not list((split_cache / "staging").iterdir())
        assert all(not (split_cache / "cipher" / a["name"]).exists() for a in split_parents)
        checks.append("multipart download-only verifies each part and concatenated parent without writing merged ciphertext or requesting parents")
        split_destination = base / "split-restored"
        run(split_command + ["--identity", key, "--source-prefix", source, "--destination", split_destination], split_env)
        assert sha(split_destination / "nested" / "keep.bin") == sha(source / "nested" / "keep.bin")
        assert (split_destination / "omit.txt").read_text() == (source / "omit.txt").read_text()
        split_commands_before = json.loads((split_cache / "commands.json").read_text())
        run(split_command + ["--identity", key, "--source-prefix", source, "--destination", base / "split-restored-again"], split_env)
        split_commands_after = json.loads((split_cache / "commands.json").read_text())
        assert split_calls_path.read_text().splitlines() == split_calls
        assert sum(c["purpose"].startswith("decrypt-") for c in split_commands_before) == sum(c["purpose"].startswith("decrypt-") for c in split_commands_after)
        assert not list((split_cache / "staging").iterdir())
        assert all(not (split_cache / "cipher" / a["name"]).exists() for a in split_parents)
        key_bytes = key.read_bytes()
        assert all(p.read_bytes() != key_bytes for p in split_cache.rglob("*") if p.is_file())
        checks.append("real age multipart full restore and rerun preserve original bytes, reuse verified parts/plaintext, discard merged parents, and never copy key")

        # Corrupt local data is retained under .invalid-* and redownloaded alone.
        damaged = split_parents[0]["parts"][0]
        (split_cache / "cipher" / damaged["name"]).write_bytes(b"preserve this corrupt cache")
        run(split_command + ["--download-only"], split_env)
        assert split_calls_path.read_text().splitlines()[len(split_calls):] == [damaged["name"]]
        invalid = list((split_cache / "cipher").glob(damaged["name"] + ".invalid-*"))
        assert len(invalid) == 1 and invalid[0].read_bytes() == b"preserve this corrupt cache"
        checks.append("damaged cached part is preserved, only that exact part redownloads, and parent ciphertext is reverified")

        corrupt_part_env = dict(split_env, TEST_GH_CORRUPT_NAME=damaged["name"])
        corrupt_part_cache = base / "corrupt-part-cache"
        result = run([sys.executable, helper, "--index", split_index_path, "--workdir", corrupt_part_cache,
                      "--download-only"], corrupt_part_env, expected=2)
        assert "SHA256/size mismatch" in result.stdout
        assert not (corrupt_part_cache / "cipher" / damaged["name"]).exists()
        checks.append("corrupt remote part fails its own hash/size check before cache promotion")

        missing = split_parents[0]["parts"][1]
        missing_path = split_remote / missing["name"]
        missing_bytes = missing_path.read_bytes()
        missing_path.unlink()
        missing_cache = base / "missing-part-cache"
        missing_command = [sys.executable, helper, "--index", split_index_path, "--workdir", missing_cache, "--download-only"]
        result = run(missing_command, split_env, expected=2)
        assert "Command failed" in result.stdout
        assert (missing_cache / "cipher" / damaged["name"]).is_file()
        assert not (missing_cache / "cipher" / missing["name"]).exists()
        missing_path.write_bytes(missing_bytes)
        calls_before_resume = split_calls_path.read_text().splitlines()
        run(missing_command, split_env)
        assert damaged["name"] not in split_calls_path.read_text().splitlines()[len(calls_before_resume):]
        checks.append("missing remote part fails explicitly and recovery resumes from verified earlier parts when it becomes available")

        wrong_parent = json.loads(json.dumps(split_index))
        next(a for a in wrong_parent["assets"] if "parts" in a)["sha256"] = "f" * 64
        wrong_parent_path = base / "wrong-parent-index.json"
        wrong_parent_path.write_text(json.dumps(wrong_parent))
        wrong_parent_cache = base / "wrong-parent-cache"
        result = run([sys.executable, helper, "--index", wrong_parent_path, "--workdir", wrong_parent_cache,
                      "--download-only"], split_env, expected=2)
        assert "Combined ciphertext SHA256/size mismatch" in result.stdout
        assert not list((wrong_parent_cache / "staging").iterdir())
        result = run([sys.executable, helper, "--index", wrong_parent_path, "--workdir", wrong_parent_cache,
                      "--identity", key, "--destination", base / "wrong-parent-restored"], split_env, expected=2)
        assert "Combined ciphertext SHA256/size mismatch" in result.stdout
        assert not list((wrong_parent_cache / "staging").iterdir())
        assert not (base / "wrong-parent-restored").exists()
        checks.append("correct individual parts cannot bypass the original parent ciphertext SHA256")

        # Reject malformed or conflicting trusted manifests before any download.
        invalid_variants = []
        def invalid_variant(label, mutate):
            value = json.loads(json.dumps(split_index))
            parent = next(a for a in value["assets"] if "parts" in a)
            mutate(value, parent)
            invalid_variants.append((label, value))
        invalid_variant("missing-part", lambda value, parent: parent["parts"].pop())
        invalid_variant("unsafe-name", lambda value, parent: parent["parts"][0].update(name="../escape.age"))
        invalid_variant("duplicate-part", lambda value, parent: parent["parts"].append(dict(parent["parts"][0])))
        invalid_variant("bad-hash", lambda value, parent: parent["parts"][0].update(sha256="X" * 64))
        invalid_variant("boolean-size", lambda value, parent: parent["parts"][0].update(bytes=True))
        invalid_variant("zero-size", lambda value, parent: parent["parts"][0].update(bytes=0))
        invalid_variant("sequence-gap", lambda value, parent: parent["parts"][0].update(name=parent["name"][:-4] + ".part-000002.age"))
        invalid_variant("reordered-parts", lambda value, parent: parent["parts"].reverse())
        invalid_variant("missing-transport", lambda value, parent: value.pop("transport"))
        invalid_variant("ordinary-name-conflict", lambda value, parent: value["assets"].append({"name": parent["parts"][0]["name"], "standalone_video": True}))
        invalid_variant("early-ordinary-conflict", lambda value, parent: value["assets"].insert(0, {"name": parent["parts"][0]["name"], "standalone_video": True}))
        calls_before_invalid = split_calls_path.read_text()
        for label, value in invalid_variants:
            invalid_index = base / (label + "-index.json")
            invalid_index.write_text(json.dumps(value))
            invalid_cache = base / ("invalid-schema-" + label + "-cache")
            run([sys.executable, helper, "--index", invalid_index, "--workdir", invalid_cache, "--download-only"], split_env, expected=2)
            assert not invalid_cache.exists()
        assert split_calls_path.read_text() == calls_before_invalid
        checks.append("multipart schema rejects omitted parts, unsafe/duplicate/conflicting names, invalid SHA256/sizes, sequence gaps/reordering, and missing transport before downloading")
    report = {"passed": True, "checks": checks, "python": sys.version.split()[0], "network_used": False,
              "gh": "isolated fake CLI with exact argument assertions", "age": "real installed age and temporary external keys"}
    (HERE / "recovery-test-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
