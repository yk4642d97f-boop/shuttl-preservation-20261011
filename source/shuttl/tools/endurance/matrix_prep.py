"""Checkpoint-directory manipulations for matrix cases (applied before / between attempts).

ops (paths are relative to the match checkpoint dir):
  {"op": "rm", "path": "track.json"}                      delete one checkpoint file
  {"op": "truncate", "path": "players.bin", "frac": 0.5}  keep the first frac of the bytes
  {"op": "garbage", "path": "camera.json"}                overwrite with non-JSON bytes
  {"op": "diskfull", "image_mb": 400, "leave_mb": 5}      put checkpoints on a small APFS
        disk image under /tmp/luna11/mnt (hdiutil) and fill it until leave_mb are free
  {"op": "free_disk"}                                     delete the filler (space returns)
cleanup() detaches and deletes the image and restores a normal checkpoint dir.
"""
import os, shutil, subprocess

IMG = "/tmp/luna11/diskfull.dmg"
MNT = "/tmp/luna11/mnt"


def _free_mb(path):
    s = os.statvfs(path)
    return s.f_bavail * s.f_frsize / 2**20


def apply(op, ctx):
    ck = ctx["ck"]
    kind = op["op"]
    if kind == "rm":
        p = os.path.join(ck, op["path"])
        ctx["notes"].append(f"rm {op['path']} existed={os.path.exists(p)}")
        if os.path.exists(p):
            os.remove(p)
    elif kind == "truncate":
        p = os.path.join(ck, op["path"])
        n = os.path.getsize(p)
        keep = int(n * op["frac"])
        with open(p, "r+b") as f:
            f.truncate(keep)
        ctx["notes"].append(f"truncate {op['path']} {n} -> {keep} bytes")
    elif kind == "garbage":
        p = os.path.join(ck, op["path"])
        with open(p, "wb") as f:
            f.write(b"\x00garbage{{{" * 100)
        ctx["notes"].append(f"garbage {op['path']}")
    elif kind == "diskfull":
        subprocess.run(["hdiutil", "detach", MNT, "-force"], capture_output=True)
        if os.path.exists(IMG):
            os.remove(IMG)
        os.makedirs(MNT, exist_ok=True)
        subprocess.run(["hdiutil", "create", "-size", f"{op['image_mb']}m", "-fs", "APFS", "-volname", "luna11full",
                        IMG], check=True, capture_output=True)
        subprocess.run(["hdiutil", "attach", IMG, "-mountpoint", MNT, "-nobrowse"], check=True, capture_output=True)
        target = os.path.join(MNT, "ck")
        if os.path.isdir(ck):
            shutil.copytree(ck, target)
            shutil.rmtree(ck)
        else:
            os.makedirs(target)
        os.makedirs(os.path.dirname(ck), exist_ok=True)
        os.symlink(target, ck)
        ctx["image"] = True
        filler = os.path.join(MNT, "filler.bin")
        want = max(0, _free_mb(MNT) - op["leave_mb"])
        with open(filler, "wb") as f:
            chunk = b"\0" * (1 << 20)
            for _ in range(int(want)):
                try:
                    f.write(chunk)
                except OSError:
                    break
        ctx["notes"].append(f"diskfull image {op['image_mb']} MB, free after fill {_free_mb(MNT):.1f} MB")
    elif kind == "free_disk":
        filler = os.path.join(MNT, "filler.bin")
        if os.path.exists(filler):
            os.remove(filler)
        ctx["notes"].append(f"free_disk: free now {_free_mb(MNT):.1f} MB")
    else:
        raise ValueError(kind)


def cleanup(ctx):
    if not ctx.get("image"):
        return
    ck = ctx["ck"]
    if os.path.islink(ck):
        target = os.readlink(ck)
        os.remove(ck)
        if os.path.isdir(target):
            shutil.copytree(target, ck, ignore=shutil.ignore_patterns("filler.bin"))
    subprocess.run(["hdiutil", "detach", MNT, "-force"], capture_output=True)
    if os.path.exists(IMG):
        os.remove(IMG)
    ctx["notes"].append("disk image detached and deleted")
