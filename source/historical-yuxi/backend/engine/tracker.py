"""
羽析 · 羽毛球轨迹追踪引擎

基于 TrackNetV3 (MIT License, https://github.com/qaz812345/TrackNetV3) 的预训练模型,
重写了推理流程:
  - 流式读取视频,长视频不会占满内存
  - 支持进度回调,便于前端显示进度条
  - 两种模式: fast(不重叠滑窗,约 8 倍速) / accurate(重叠滑窗 + 时序加权集成)
  - 自动选择计算设备: NVIDIA CUDA > Apple MPS > CPU

输出: 每一帧羽毛球在原视频中的像素坐标 (x, y) 与是否可见。
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import cv2
import numpy as np
import torch

from .tracknet.model import TrackNet, InpaintNet

# TrackNetV3 固定的输入分辨率
IN_W, IN_H = 512, 288
TRACK_SEQ = 8      # TrackNet 一次看 8 帧
INPAINT_SEQ = 16   # InpaintNet 一次看 16 帧
COOR_TH = (1 / math.sqrt(IN_H ** 2 + IN_W ** 2)) * 50  # 归一化坐标过小视为"无球"

WEIGHTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "weights")

ProgressFn = Optional[Callable[[str, float], None]]


def pick_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


@dataclass
class TrackResult:
    fps: float
    width: int
    height: int
    num_frames: int
    x: List[float] = field(default_factory=list)   # 原视频像素坐标, 不可见时为 0
    y: List[float] = field(default_factory=list)
    vis: List[int] = field(default_factory=list)   # 1 可见 / 0 不可见
    inpainted: List[int] = field(default_factory=list)  # 1 = 该帧由 InpaintNet 补全 (原始检测没看到球)

    def to_dict(self):
        return {
            "fps": self.fps, "width": self.width, "height": self.height,
            "num_frames": self.num_frames,
            "x": [round(v, 1) for v in self.x],
            "y": [round(v, 1) for v in self.y],
            "vis": self.vis,
            "inpainted": self.inpainted,
        }


class ShuttleTracker:
    """加载一次模型, 可重复分析多个视频。"""

    def __init__(self, weights_dir: str = WEIGHTS_DIR, device: Optional[torch.device] = None):
        self.device = device or pick_device()
        tk = torch.load(os.path.join(weights_dir, "TrackNet_best.pt"), map_location="cpu", weights_only=False)
        assert tk["param_dict"]["bg_mode"] == "concat" and tk["param_dict"]["seq_len"] == TRACK_SEQ
        self.tracknet = TrackNet(in_dim=(TRACK_SEQ + 1) * 3, out_dim=TRACK_SEQ)
        self.tracknet.load_state_dict(tk["model"])
        self.tracknet.to(self.device).eval()

        ip = torch.load(os.path.join(weights_dir, "InpaintNet_best.pt"), map_location="cpu", weights_only=False)
        self.inpaintnet = InpaintNet()
        self.inpaintnet.load_state_dict(ip["model"])
        self.inpaintnet.to(self.device).eval()

    # ------------------------------------------------------------------ 预处理
    @staticmethod
    def _prep(frame_bgr: np.ndarray) -> np.ndarray:
        """BGR 原图 -> (3, 288, 512) RGB uint8"""
        small = cv2.resize(frame_bgr, (IN_W, IN_H), interpolation=cv2.INTER_AREA)
        return np.ascontiguousarray(small[..., ::-1].transpose(2, 0, 1))

    def _median_background(self, path: str, n_frames: int, max_samples: int = 300) -> np.ndarray:
        """在视频中均匀采样, 取中位数得到"无球无人"的背景图 (3, 288, 512)。"""
        cap = cv2.VideoCapture(path)
        step = max(1, n_frames // max_samples)
        imgs = []
        for i in range(0, n_frames, step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, fr = cap.read()
            if not ok:
                break
            imgs.append(self._prep(fr))
        cap.release()
        if not imgs:
            raise RuntimeError("无法读取视频帧, 请确认视频格式 (建议 mp4 / H.264)")
        return np.median(np.stack(imgs), axis=0).astype(np.uint8)

    # ------------------------------------------------------------------ 主流程
    @torch.no_grad()
    def track(self, path: str, mode: str = "accurate", batch_size: int = 8,
              progress: ProgressFn = None, start_frame: int = 0,
              end_frame: Optional[int] = None) -> TrackResult:
        """start_frame/end_frame: 只分析视频中的一段 (结果帧号从 0 开始, 相对 start_frame)。"""
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise RuntimeError(f"打不开视频: {path}")
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if n_total <= 0:                       # 少数格式读不到总帧数: 数一遍
            n_total = 0
            while cap.grab():
                n_total += 1
        cap.release()
        end_frame = n_total if end_frame is None else min(end_frame, n_total)
        n_est = max(0, end_frame - start_frame)

        if progress:
            progress("生成背景模型", 0.0)
        median = self._median_background(path, n_total).astype(np.float32) / 255.0

        step = 1 if mode == "accurate" else TRACK_SEQ
        heat_xy = self._run_tracknet(path, median, step, batch_size, n_est, progress, start_frame)
        n = len(heat_xy)

        xs = np.array([p[0] for p in heat_xy], dtype=np.float32)
        ys = np.array([p[1] for p in heat_xy], dtype=np.float32)
        vis = ((xs > 0) | (ys > 0)).astype(np.int32)

        if progress:
            progress("轨迹补全", 0.92)
        raw_vis = vis.copy()
        xs, ys, vis = self._run_inpaint(xs, ys, vis, W, H)

        res = TrackResult(fps=float(fps), width=W, height=H, num_frames=n)
        # 模型坐标 (512x288) -> 原视频坐标
        sx, sy = W / IN_W, H / IN_H
        res.x = (xs * sx * vis).tolist()
        res.y = (ys * sy * vis).tolist()
        res.vis = vis.tolist()
        res.inpainted = ((vis == 1) & (raw_vis == 0)).astype(int).tolist()
        if progress:
            progress("追踪完成", 1.0)
        return res

    def _run_tracknet(self, path, median, step, batch_size, n_est, progress, start_frame=0):
        """滑窗推理。step=1 时对每帧做 8 次预测并按位置加权平均 (TrackNetV3 的 temporal ensemble)。"""
        L = TRACK_SEQ
        # 时序集成权重: 窗口中间的预测更可信 [1,2,3,4,4,3,2,1]
        w = np.ones(L, dtype=np.float32)
        for i in range(math.ceil(L / 2)):
            w[i] = i + 1
            w[L - i - 1] = i + 1

        acc: dict[int, np.ndarray] = {}   # 帧号 -> 加权热力图累加
        wsum: dict[int, float] = {}
        results: List[tuple] = []
        next_out = 0

        cap = cv2.VideoCapture(path)
        if start_frame:
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        buf: List[np.ndarray] = []   # 当前滑窗内的帧 (float32, 3xHxW)
        start = 0                    # buf[0] 的帧号
        total_read = 0
        eof = False
        pending_starts: List[int] = []
        pending_x: List[np.ndarray] = []

        def flush_batch():
            nonlocal next_out
            if not pending_x:
                return
            x = torch.from_numpy(np.stack(pending_x)).to(self.device)
            y = self.tracknet(x).float().cpu().numpy()  # (B, 8, 288, 512)
            for b, s in enumerate(pending_starts):
                for k in range(L):
                    f = s + k
                    if step == 1:
                        wk = w[k]
                    else:
                        wk = 1.0
                    if f in acc:
                        acc[f] += y[b, k] * wk
                        wsum[f] += wk
                    else:
                        acc[f] = y[b, k] * wk
                        wsum[f] = wk
            pending_x.clear()
            pending_starts.clear()

        def emit_ready(upto: int):
            """把帧号 < upto 的帧 (已不会再被新窗口覆盖) 转成坐标。"""
            nonlocal next_out
            while next_out < upto and next_out in acc:
                hm = acc.pop(next_out) / wsum.pop(next_out)
                results.append(_heatmap_to_xy(hm))
                next_out += 1

        while True:
            while len(buf) < L and not eof:
                ok, fr = cap.read() if total_read < n_est else (False, None)
                if not ok:
                    eof = True
                    break
                buf.append(self._prep(fr).astype(np.float32) / 255.0)
                total_read += 1
            if not buf:
                break
            real = len(buf)
            frames = buf + [buf[-1]] * (L - real)            # 末尾不足 8 帧时补齐
            x = np.concatenate([median] + frames, axis=0)   # (27, 288, 512)
            pending_x.append(x)
            pending_starts.append(start)
            if len(pending_x) >= batch_size:
                flush_batch()
                emit_ready(start + 1 if step == 1 else start + L)
                if progress and n_est:
                    progress("追踪羽毛球", min(0.9, 0.05 + 0.85 * total_read / n_est))
            if eof:
                break          # 已读完, 当前窗口覆盖了剩余所有帧
            buf = buf[step:]
            start += step
        flush_batch()
        cap.release()
        emit_ready(total_read)
        return results[:total_read]

    def _run_inpaint(self, xs, ys, vis, W, H):
        """InpaintNet: 对被人/网遮挡而短暂"消失"的球, 用前后轨迹补全坐标。"""
        n = len(xs)
        if n == 0:
            return xs, ys, vis
        mask = _inpaint_mask(ys * (H / IN_H), vis, th_h=H * 0.05)
        if mask.sum() == 0:
            return xs, ys, vis

        cx = xs / IN_W
        cy = ys / IN_H
        L = INPAINT_SEQ
        out_x = np.zeros(n, dtype=np.float32)
        out_y = np.zeros(n, dtype=np.float32)
        cnt = np.zeros(n, dtype=np.float32)
        starts = list(range(0, max(1, n - L + 1)))
        for b0 in range(0, len(starts), 64):
            chunk = starts[b0:b0 + 64]
            idx = np.array([[min(s + k, n - 1) for k in range(L)] for s in chunk])
            coor = np.stack([cx[idx], cy[idx]], axis=-1).astype(np.float32)        # (B, L, 2)
            m = mask[idx][..., None].astype(np.float32)                            # (B, L, 1)
            ct = torch.from_numpy(coor).to(self.device)
            mt = torch.from_numpy(m).to(self.device)
            pred = self.inpaintnet(ct, mt).float().cpu().numpy()
            pred = pred * m + coor * (1 - m)
            for bi in range(len(chunk)):
                for k in range(L):
                    f = idx[bi, k]
                    out_x[f] += pred[bi, k, 0]
                    out_y[f] += pred[bi, k, 1]
                    cnt[f] += 1
        cnt[cnt == 0] = 1
        nx, ny = out_x / cnt, out_y / cnt
        # 只替换被标记需要补全的帧
        fx = np.where(mask == 1, nx, cx)
        fy = np.where(mask == 1, ny, cy)
        small = (fx < COOR_TH) & (fy < COOR_TH)
        fx[small] = 0
        fy[small] = 0
        new_vis = ((fx > 0) | (fy > 0)).astype(np.int32)
        return fx * IN_W, fy * IN_H, new_vis


def _heatmap_to_xy(hm: np.ndarray) -> tuple:
    """二值化热力图, 取面积最大的连通区域中心作为球的位置 (512x288 坐标)。"""
    binm = (hm > 0.5).astype(np.uint8)
    if binm.max() == 0:
        return (0.0, 0.0)
    cnts, _ = cv2.findContours(binm, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = max((cv2.boundingRect(c) for c in cnts), key=lambda r: r[2] * r[3])
    x, y, w, h = best
    return (float(x + w / 2), float(y + h / 2))


def _inpaint_mask(y_px: np.ndarray, vis: np.ndarray, th_h: float) -> np.ndarray:
    """与 TrackNetV3 generate_inpaint_mask 等价: 标记"球在场内却短暂丢失"的帧段。"""
    n = len(vis)
    mask = np.zeros(n, dtype=np.int32)
    i = j = 0
    while j < n:
        while i < n - 1 and vis[i] == 1:
            i += 1
        j = i
        while j < n - 1 and vis[j] == 0:
            j += 1
        if j == i:
            break
        elif i == 0 and y_px[j] > th_h:
            mask[:j] = 1
        elif (i > 1 and y_px[i - 1] > th_h) and (j < n and y_px[j] > th_h):
            mask[i:j] = 1
        i = j
    return mask
