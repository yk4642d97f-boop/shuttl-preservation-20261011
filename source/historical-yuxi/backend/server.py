"""
羽析 · 后端服务

启动:  uvicorn server:app --host 0.0.0.0 --port 8000
浏览器打开 http://localhost:8000 ; 同一 Wi-Fi 下的手机打开 http://<电脑IP>:8000

接口一览
  GET    /api/health                      服务状态 (计算设备等)
  POST   /api/videos                      上传视频 (multipart: file)
  GET    /api/videos                      历史记录
  GET    /api/videos/{id}                 视频信息 + 分析状态
  GET    /api/videos/{id}/file            视频文件 (支持拖动播放 Range)
  GET    /api/videos/{id}/frame?t=秒       取一帧 JPEG (用于标定场地)
  POST   /api/videos/{id}/analyze         开始分析 {corners, match_type, mode, names}
  GET    /api/videos/{id}/result          分析结果 JSON
  PATCH  /api/videos/{id}/rallies/{n}     人工改判某回合 {winner}
  DELETE /api/videos/{id}                 删除
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import threading
import time
import traceback
import uuid
from typing import List, Optional

import cv2
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("YUXI_DATA") or os.path.join(ROOT, "data")
FRONT = os.path.join(os.path.dirname(ROOT), "frontend")
os.makedirs(DATA, exist_ok=True)

app = FastAPI(title="羽析 API", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ------------------------------------------------------------------ 存储
def vdir(vid: str) -> str:
    d = os.path.join(DATA, vid)
    if not os.path.isdir(d) or "/" in vid or ".." in vid:
        raise HTTPException(404, "视频不存在")
    return d


def load_meta(vid: str) -> dict:
    with open(os.path.join(vdir(vid), "meta.json"), encoding="utf-8") as f:
        return json.load(f)


def save_meta(vid: str, meta: dict):
    p = os.path.join(vdir(vid), "meta.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    os.replace(tmp, p)


def video_path(vid: str) -> str:
    return os.path.join(vdir(vid), load_meta(vid)["file"])


# ------------------------------------------------------------------ 分析任务队列 (单线程, 模型只加载一次)
JOBS: "queue.Queue[str]" = queue.Queue()
STATUS: dict = {}          # vid -> {stage, progress, state}
LOCK = threading.Lock()


def set_status(vid, **kw):
    with LOCK:
        STATUS.setdefault(vid, {}).update(kw)


def worker():
    from engine.pipeline import analyze_video
    while True:
        vid = JOBS.get()
        try:
            meta = load_meta(vid)
            req = meta["request"]
            set_status(vid, state="running", stage="加载模型", progress=0.0, started=time.time())
            cache = None
            cache_p = os.path.join(vdir(vid), "track.json")
            # 只改了标定/单双打时, 复用上次的追踪结果 (秒出)
            if os.path.exists(cache_p) and meta.get("track_mode") == req["mode"]:
                with open(cache_p) as f:
                    cache = json.load(f)
            res = analyze_video(video_path(vid), req["corners"], req["match_type"], req["mode"],
                                progress=lambda s, r: set_status(vid, stage=s, progress=round(r, 3)),
                                track_cache=cache)
            with open(cache_p, "w") as f:
                json.dump(res.pop("track_raw"), f)
            res["names"] = req.get("names") or {"near": "近端", "far": "远端"}
            with open(os.path.join(vdir(vid), "result.json"), "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False)
            meta = load_meta(vid)
            meta.update(state="done", track_mode=req["mode"], analyzed_at=time.time(),
                        summary=res["summary"], elapsed=res["meta"]["time_total_s"])
            meta.pop("error", None)
            save_meta(vid, meta)
            set_status(vid, state="done", stage="完成", progress=1.0)
        except Exception as e:  # noqa
            traceback.print_exc()
            try:
                meta = load_meta(vid)
                meta.update(state="error", error=str(e))
                save_meta(vid, meta)
            except Exception:
                pass
            set_status(vid, state="error", stage=f"出错: {e}", progress=0.0)
        finally:
            JOBS.task_done()


threading.Thread(target=worker, daemon=True).start()


# ------------------------------------------------------------------ 接口
@app.get("/api/health")
def health():
    import torch
    dev = "cuda" if torch.cuda.is_available() else (
        "mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu")
    return {"ok": True, "device": dev, "queue": JOBS.qsize()}


@app.post("/api/videos")
async def upload(file: UploadFile = File(...)):
    vid = time.strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    d = os.path.join(DATA, vid)
    os.makedirs(d)
    ext = os.path.splitext(file.filename or "")[1].lower() or ".mp4"
    if ext not in (".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"):
        shutil.rmtree(d)
        raise HTTPException(400, "请上传视频文件 (mp4 / mov)")
    fname = "video" + ext
    with open(os.path.join(d, fname), "wb") as f:
        while chunk := await file.read(4 << 20):
            f.write(chunk)
    cap = cv2.VideoCapture(os.path.join(d, fname))
    if not cap.isOpened():
        shutil.rmtree(d)
        raise HTTPException(400, "无法读取该视频, 请换成 mp4 格式再试")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    meta = {"id": vid, "name": file.filename, "file": fname, "created": time.time(),
            "fps": fps, "frames": n, "width": w, "height": h,
            "duration": round(n / fps, 2) if fps else 0, "state": "uploaded"}
    with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    return meta


@app.get("/api/videos")
def list_videos():
    out = []
    for vid in sorted(os.listdir(DATA), reverse=True):
        p = os.path.join(DATA, vid, "meta.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                m = json.load(f)
            m.update(STATUS.get(vid, {}))
            out.append(m)
    return out


@app.get("/api/videos/{vid}")
def get_video(vid: str):
    m = load_meta(vid)
    m["status"] = STATUS.get(vid, {"state": m.get("state")})
    return m


@app.delete("/api/videos/{vid}")
def delete_video(vid: str):
    shutil.rmtree(vdir(vid))
    STATUS.pop(vid, None)
    return {"ok": True}


@app.get("/api/videos/{vid}/frame")
def get_frame(vid: str, t: float = 1.0, w: int = 1280):
    cap = cv2.VideoCapture(video_path(vid))
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000)
    ok, f = cap.read()
    cap.release()
    if not ok:
        raise HTTPException(400, "取帧失败")
    if f.shape[1] > w:
        f = cv2.resize(f, (w, int(f.shape[0] * w / f.shape[1])), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return Response(buf.tobytes(), media_type="image/jpeg")


@app.get("/api/videos/{vid}/file")
def get_file(vid: str, request: Request):
    """带 Range 支持的视频流 (Safari / iPhone 播放必须)。"""
    path = video_path(vid)
    size = os.path.getsize(path)
    ext = os.path.splitext(path)[1].lower()
    mime = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime",
            ".webm": "video/webm"}.get(ext, "video/mp4")
    rng = request.headers.get("range")
    if not rng:
        return FileResponse(path, media_type=mime, headers={"Accept-Ranges": "bytes"})
    start_s, _, end_s = rng.replace("bytes=", "").partition("-")
    start = int(start_s) if start_s else 0
    end = min(int(end_s) if end_s else size - 1, size - 1)
    length = end - start + 1

    def it():
        with open(path, "rb") as f:
            f.seek(start)
            left = length
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                left -= len(chunk)
                yield chunk

    return StreamingResponse(it(), status_code=206, media_type=mime, headers={
        "Content-Range": f"bytes {start}-{end}/{size}", "Accept-Ranges": "bytes",
        "Content-Length": str(length)})


class AnalyzeReq(BaseModel):
    corners: List[List[float]]
    match_type: str = "singles"
    mode: str = "accurate"
    names: Optional[dict] = None


@app.post("/api/videos/{vid}/analyze")
def analyze(vid: str, req: AnalyzeReq):
    if len(req.corners) != 4:
        raise HTTPException(400, "需要 4 个角点")
    meta = load_meta(vid)
    meta["request"] = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    meta["state"] = "queued"
    save_meta(vid, meta)
    set_status(vid, state="queued", stage="排队中", progress=0.0)
    JOBS.put(vid)
    return {"ok": True, "queue": JOBS.qsize()}


@app.get("/api/videos/{vid}/result")
def result(vid: str):
    p = os.path.join(vdir(vid), "result.json")
    if not os.path.exists(p):
        raise HTTPException(404, "尚未分析")
    return FileResponse(p, media_type="application/json")


class Override(BaseModel):
    winner: Optional[str] = None      # near / far / None(撤销改判)


@app.patch("/api/videos/{vid}/rallies/{idx}")
def override(vid: str, idx: int, body: Override):
    """人工复核: 对存疑回合改判得分方, 并重算比分。"""
    p = os.path.join(vdir(vid), "result.json")
    with open(p, encoding="utf-8") as f:
        res = json.load(f)
    for r in res["rallies"]:
        if r["index"] == idx:
            if body.winner in ("near", "far"):
                r.setdefault("auto_winner", r.get("winner"))
                r["winner"] = body.winner
                r["overridden"] = True
            elif "auto_winner" in r:
                r["winner"] = r.pop("auto_winner")
                r["overridden"] = False
    pts = {"near": 0, "far": 0}
    for r in res["rallies"]:
        if r.get("winner") in pts:
            pts[r["winner"]] += 1
    res["summary"]["points"] = pts
    with open(p, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)
    return {"ok": True, "points": pts}


# ------------------------------------------------------------------ 前端静态文件
if os.path.isdir(FRONT):
    app.mount("/", StaticFiles(directory=FRONT, html=True), name="front")
