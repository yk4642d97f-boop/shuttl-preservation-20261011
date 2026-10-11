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
if os.environ.get('TEST_GH_CORRUPT')=='1':out.write_bytes(b'corrupted download')
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
    report = {"passed": True, "checks": checks, "python": sys.version.split()[0], "network_used": False,
              "gh": "isolated fake CLI with exact argument assertions", "age": "real installed age and temporary external keys"}
    (HERE / "recovery-test-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
