#!/usr/bin/env python3
"""Resumable ShuttleSet video fetcher (run on the Mac).

Two independent stages, both resumable:
  download (server): yt-dlp through the Cloudflare WARP SOCKS proxy (wireproxy, 127.0.0.1:40000 on the
      server), choosing a video stream whose fps equals the fps implied by the labels (25 or 30),
      720p H.264 preferred, + m4a audio, merged to mp4, then ffprobe'd (exact packet = frame count).
      Downloads run ahead of transfers while the server buffer stays below SERVER_BUDGET bytes.
  transfer (server -> Mac): the file is pulled in CHUNK-byte ranges over `ssh dd` with STREAMS parallel
      connections; finished chunks are kept under videos/.chunks/<id>/ so an interrupted transfer resumes
      chunk-wise. After size check the chunks are joined to videos/<id>.mp4 and the server copy is deleted.

The server->Mac path is the bottleneck (server egress is capped at roughly 0.5 MB/s in total).

Usage:  python3 fetch_all.py [--only 3,5] [--retry-failed] [--max N] [--streams 2] [--no-download]
Safe to Ctrl-C and rerun. State lives in research/shuttleset/manifest.csv.
"""
import argparse, csv, fcntl, hashlib, json, os, shlex, signal, subprocess, threading, time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS = os.path.join(ROOT, "labels/ShuttleSet/set")
VIDEOS = os.path.join(ROOT, "videos")
MANIFEST = os.path.join(ROOT, "manifest.csv")
SUMMARY = os.path.join(ROOT, "labels_summary.json")
KEY = os.path.expanduser("~/.ssh/shuttl_deploy")
HOST = "root@43.108.9.91"
SSH = ["ssh", "-i", KEY, "-o", "ServerAliveInterval=30", "-o", "ConnectTimeout=20", HOST]
RW = "/root/work/shuttleset"
PROXY = "socks5h://127.0.0.1:40000"
SERVER_BUDGET = 12e9       # bytes of finished videos allowed to wait on the server (task limit is 15 GB)
EST_NEXT = 1.5e9           # head-room reserved for the download in progress
CHUNK = 32 * 1024 * 1024
# Official test/validation matches: must be on the Mac first for the accuracy measurement.
# Everything else keeps ascending id order after these.
PRIORITY = ["39", "40", "41", "42", "43", "44"]
LOCKFILE = os.path.join(ROOT, "fetch_all.lock")
FIELDS = ["id", "video", "url", "label_fps", "label_strokes", "label_max_frame", "status", "format_id",
          "vcodec", "width", "height", "fps", "frame_count", "duration_s", "frames_cover_labels",
          "size_bytes", "dl_seconds", "dl_MBps", "xfer_seconds", "xfer_MBps", "attempts", "error", "updated"]
lock = threading.Lock()
stop = threading.Event()


def prio(mid):
    """Sort key: the six priority matches first (in order), then ascending id."""
    return (PRIORITY.index(str(mid)), int(mid)) if str(mid) in PRIORITY else (len(PRIORITY), int(mid))


def log(*a):
    print(time.strftime("%m-%d %H:%M:%S"), *a, flush=True)


def acquire_lock():
    """Single-instance guard: a second fetch_all.py must not race on the same
    dl/<id>.mp4 (delete+re-fetch) and the same videos/.chunks/<id>/ trees."""
    fd = os.open(LOCKFILE, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise SystemExit(f"another fetch_all.py already holds {LOCKFILE}; refusing to start a second copy")
    os.ftruncate(fd, 0)
    os.write(fd, str(os.getpid()).encode())
    return fd  # keep fd open for the process lifetime; flock releases on exit


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def ssh(cmd, timeout=None):
    return subprocess.run(SSH + [cmd], capture_output=True, text=True, timeout=timeout)


def load_manifest():
    rows = {}
    if os.path.exists(MANIFEST):
        for r in csv.DictReader(open(MANIFEST, encoding="utf-8")):
            rows[r["id"]] = {k: r.get(k, "") for k in FIELDS}
    summ = json.load(open(SUMMARY, encoding="utf-8"))["ShuttleSet"]["per_match"]
    for m in csv.DictReader(open(os.path.join(LABELS, "match.csv"), encoding="utf-8")):
        s = next(p for p in summ if p["id"] == m["id"])
        r = rows.setdefault(m["id"], {k: "" for k in FIELDS})
        r.update(id=m["id"], video=m["video"], url=m["url"].strip(),
                 label_fps=str(round(s["fps_fit_mean"], 3)), label_strokes=str(s["strokes"]),
                 label_max_frame=str(int(max(x["last_frame"] for x in s["sets"]))))
        if not r["status"]:
            r["status"] = "pending" if r["url"] else "no_url"
    return rows


def save(rows):
    with lock:
        tmp = MANIFEST + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, FIELDS)
            w.writeheader()
            for k in sorted(rows, key=int):
                w.writerow(rows[k])
        os.replace(tmp, MANIFEST)


def fmt_selector(fps, height):
    f = f"[fps>={fps - 1.5}][fps<={fps + 1.5}]"
    return "/".join([
        f"bv*[height={height}]{f}[vcodec^=avc1]+ba[ext=m4a]",
        f"bv*[height={height}]{f}+ba[ext=m4a]",
        f"bv*[height<=1080][height>=480]{f}+ba[ext=m4a]",
        f"bv*[height<=1080]{f}+ba",
    ])  # deliberately no fps-agnostic fallback: a wrong-fps file would silently break label alignment


def server_download(r, height):
    mid = int(r["id"]); out = f"{RW}/dl/{mid:03d}"
    sel = fmt_selector(round(float(r["label_fps"])), height)
    cmd = f"""set -o pipefail; cd {RW} && mkdir -p dl && export PATH={RW}/venv/bin:$PATH
pgrep -f 'wireproxy -c {RW}/warp/wireproxy.conf' >/dev/null || (cd warp && (nohup ./wireproxy -c {RW}/warp/wireproxy.conf > wireproxy.log 2>&1 &) ; sleep 6)
rm -f {out}.*
yt-dlp --proxy {PROXY} --no-progress --no-playlist --sleep-requests 1 --retries 10 --fragment-retries 20 \
  -f {shlex.quote(sel)} --merge-output-format mp4 --write-info-json -o '{out}.%(ext)s' {shlex.quote(r['url'])} 2>&1 | tail -n 6
test -s {out}.mp4 || exit 3
python3 -c "import json;d=json.load(open('{out}.info.json'));print('INFO',json.dumps(dict(format_id=d.get('format_id'),vcodec=d.get('vcodec'))))"
rm -f {out}.info.json
echo PROBE $(ffprobe -v error -select_streams v:0 -count_packets -show_entries stream=width,height,r_frame_rate,nb_read_packets,duration -of json {out}.mp4 | tr -d '\\n ') SIZE $(stat -c %s {out}.mp4)
"""
    t0 = time.time()
    p = ssh(cmd, timeout=7200)
    dt = time.time() - t0
    txt = p.stdout + p.stderr
    if p.returncode != 0 or "PROBE " not in txt:
        lines = txt.strip().splitlines()
        err = [l for l in lines if "ERROR" in l] + lines[-3:]
        raise RuntimeError(" | ".join(err)[-500:])
    info = json.loads(txt.split("INFO ", 1)[1].splitlines()[0])
    pj, size = txt.split("PROBE ", 1)[1].splitlines()[0].rsplit(" SIZE ", 1)
    st = json.loads(pj)["streams"][0]
    num, den = st["r_frame_rate"].split("/")
    size = int(size)
    return dict(format_id=info["format_id"], vcodec=info["vcodec"], width=st["width"], height=st["height"],
                fps=round(int(num) / int(den), 3), frame_count=int(st["nb_read_packets"]),
                duration_s=st.get("duration", ""), size_bytes=size, dl_seconds=round(dt),
                dl_MBps=round(size / 1e6 / max(dt, 1), 2))


def buffered_bytes(rows):
    return sum(int(r["size_bytes"] or 0) for r in rows.values() if r["status"] in ("on_server", "transferring"))


def downloader(rows, todo, height):
    todo = list(todo); retried = set()
    for mid in todo:
        while not stop.is_set() and buffered_bytes(rows) + EST_NEXT > SERVER_BUDGET:
            time.sleep(30)
        if stop.is_set():
            return
        r = rows[mid]
        r["attempts"] = str(int(r["attempts"] or 0) + 1)
        r["status"] = "downloading"; r["error"] = ""; save(rows)
        log(f"[dl] {mid} start {r['url']}")
        try:
            res = server_download(r, height)
        except Exception as e:
            r["status"] = "failed_download"; r["error"] = str(e)[:500]; r["updated"] = now(); save(rows)
            log(f"[dl] {mid} FAILED: {r['error']}")
            if mid not in retried:  # one automatic retry at the end of the queue
                retried.add(mid); todo.append(mid)
            time.sleep(30)
            continue
        for k, v in res.items():
            r[k] = str(v)
        r["frames_cover_labels"] = str(int(r["frame_count"]) > int(r["label_max_frame"]))
        if abs(float(r["fps"]) - float(r["label_fps"])) > 0.5:
            r["error"] = f"fps mismatch video {r['fps']} vs labels {r['label_fps']}"
        r["status"] = "on_server"; r["updated"] = now(); save(rows)
        log(f"[dl] {mid} ok {res['size_bytes']/1e6:.0f} MB in {res['dl_seconds']} s, "
            f"{res['width']}x{res['height']}@{res['fps']} frames={res['frame_count']}")


def fetch_chunk(name, idx, size, cdir):
    off = idx * CHUNK
    n = min(CHUNK, size - off)
    dst = os.path.join(cdir, f"{idx:05d}")
    if os.path.exists(dst) and os.path.getsize(dst) == n:
        return 0
    for attempt in range(8):
        if stop.is_set():
            return -1
        cmd = f"dd if={RW}/dl/{name} bs=1M iflag=skip_bytes,count_bytes skip={off} count={n} status=none"
        with open(dst + ".tmp", "wb") as f:
            p = subprocess.run(SSH + [cmd], stdout=f, stderr=subprocess.PIPE, timeout=3600)
        if p.returncode == 0 and os.path.getsize(dst + ".tmp") == n:
            os.replace(dst + ".tmp", dst)
            return n
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"chunk {idx} failed: {p.stderr.decode()[-200:]}")


def transfer_one(r, streams):
    mid = r["id"]; name = f"{int(mid):03d}.mp4"; size = int(r["size_bytes"])
    cdir = os.path.join(VIDEOS, ".chunks", f"{int(mid):03d}")
    os.makedirs(cdir, exist_ok=True)
    # Clean leftovers from an interrupted run before retrying: a partial .tmp is never
    # resumed, and a wrong-size cached chunk would poison the join.
    nchunks = (size + CHUNK - 1) // CHUNK
    for fn in os.listdir(cdir):
        p = os.path.join(cdir, fn)
        if fn.endswith(".tmp") or not fn.isdigit() or int(fn) >= nchunks or os.path.getsize(p) != min(CHUNK, size - int(fn) * CHUNK):
            os.remove(p)
    r["status"] = "transferring"; save(rows_ref[0])
    t0 = time.time()
    with ThreadPoolExecutor(streams) as ex:
        got = list(ex.map(lambda i: fetch_chunk(name, i, size, cdir), range(nchunks)))
    if stop.is_set() or any(g < 0 for g in got):
        return False
    dt = time.time() - t0
    dst = os.path.join(VIDEOS, name)
    with open(dst + ".part", "wb") as out:
        for i in range(nchunks):
            with open(os.path.join(cdir, f"{i:05d}"), "rb") as f:
                out.write(f.read())
    if os.path.getsize(dst + ".part") != size:
        raise RuntimeError("joined size mismatch")
    h = hashlib.md5()
    with open(dst + ".part", "rb") as f:
        for blk in iter(lambda: f.read(1 << 22), b""):
            h.update(blk)
    remote = ssh(f"md5sum {RW}/dl/{name}").stdout.split()[:1]
    if remote != [h.hexdigest()]:
        os.remove(dst + ".part")
        for i in range(nchunks):
            os.remove(os.path.join(cdir, f"{i:05d}"))
        raise RuntimeError(f"md5 mismatch local {h.hexdigest()} remote {remote} (chunks discarded, server copy kept)")
    os.replace(dst + ".part", dst)
    for i in range(nchunks):
        os.remove(os.path.join(cdir, f"{i:05d}"))
    os.rmdir(cdir)
    # Only now, with the Mac copy in place and md5-verified against the server, may the
    # server copy go: this is the sole delete path for a dl/*.mp4.
    if not (os.path.exists(dst) and os.path.getsize(dst) == size):
        raise RuntimeError("local file vanished before server cleanup; server copy kept")
    ssh(f"rm -f {RW}/dl/{name}")
    newly = sum(g for g in got if g > 0)
    r["xfer_seconds"] = str(round(dt))
    r["xfer_MBps"] = str(round(newly / 1e6 / max(dt, 1), 3))
    r["status"] = "done"; r["updated"] = now()
    log(f"[xfer] {mid} done {size/1e6:.0f} MB ({newly/1e6:.0f} MB this run) in {dt:.0f} s")
    return True


rows_ref = [None]


def transferrer(rows, streams, dl_thread, retry_failed):
    ready_states = ("on_server", "transferring") + (("failed_transfer",) if retry_failed else ())
    while not stop.is_set():
        ready = [k for k in sorted(rows, key=prio) if rows[k]["status"] in ready_states]
        if not ready:
            if dl_thread is None or not dl_thread.is_alive():
                return
            time.sleep(15)
            continue
        r = rows[ready[0]]
        try:
            transfer_one(r, streams)
        except Exception as e:
            r["status"] = "failed_transfer"; r["error"] = str(e)[:300]; r["updated"] = now()
            log(f"[xfer] {r['id']} FAILED {e}")
        save(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--streams", type=int, default=2)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--no-download", action="store_true", help="only drain files already on the server")
    a = ap.parse_args()
    lock_fd = acquire_lock()  # refuse a second instance; held for the whole run
    rows = load_manifest(); rows_ref[0] = rows
    # reconcile with reality: what is on the server / on the Mac
    p = ssh(f"ls -l {RW}/dl/ 2>/dev/null | awk '{{print $5, $9}}'")
    on_server = {l.split()[1]: int(l.split()[0]) for l in p.stdout.splitlines() if l.strip().endswith(".mp4")}
    for r in rows.values():
        name = f"{int(r['id']):03d}.mp4"
        local = os.path.join(VIDEOS, name)
        # A file already correctly on the Mac is done regardless of how the last run ended
        # (recovers rows left failed_transfer/transferring by an interrupted duplicate run).
        if r["status"] in ("done", "on_server", "transferring", "failed_transfer", "downloading"):
            if os.path.exists(local) and os.path.getsize(local) == int(r["size_bytes"] or -1) > 0:
                r["status"] = "done"; continue
        if r["status"] == "done" and not os.path.exists(local):
            r["status"] = "pending"
        if r["status"] in ("downloading", "on_server", "transferring", "failed_transfer"):
            if r["status"] != "downloading" and on_server.get(name) == int(r["size_bytes"] or -1):
                r["status"] = "on_server"
            elif r["status"] != "failed_transfer":
                r["status"] = "pending"
    save(rows)
    # a "transferring" row with a good server copy is already on_server above; anything else
    # that still has a server copy is left for the transferrer, which sorts by priority.
    ok_states = {"pending"} | ({"failed_download", "failed_transfer"} if a.retry_failed else set())
    todo = [k for k in sorted(rows, key=prio) if rows[k]["status"] in ok_states]
    if a.only:
        todo = [k for k in todo if k in a.only.split(",")]
    if a.max:
        todo = todo[: a.max]
    if a.no_download:
        todo = []
    log(f"to download: {','.join(todo) or '-'}; already on server: "
        f"{','.join(k for k in rows if rows[k]['status'] == 'on_server') or '-'}")
    def on_signal(sig, frame):
        stop.set()
        log(f"signal {sig}: finishing in-flight chunks/download then exiting; rerun to resume")
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    dl = threading.Thread(target=downloader, args=(rows, todo, a.height), daemon=True)
    dl.start()
    transferrer(rows, a.streams, dl, a.retry_failed)
    dl.join()
    c = {}
    for r in rows.values():
        c[r["status"]] = c.get(r["status"], 0) + 1
    save(rows)
    log("status counts:", c)


if __name__ == "__main__":
    main()
