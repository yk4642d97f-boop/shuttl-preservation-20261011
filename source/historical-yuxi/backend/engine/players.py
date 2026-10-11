"""
羽析 · 球员检测

使用 YOLOX-S 行人检测 (Apache-2.0, Megvii; ONNX 权重来自 OpenCV Model Zoo),
通过 OpenCV DNN 推理, 无需额外依赖。
只保留"脚底"位于球场附近的人 (排除裁判、司线员、观众)。

用途:
  1. 击球验证: 真正的击球发生在球员身边; 高球顶点远离所有球员 => 排除误检
  2. 击球方判定: 球员"脚底"在地面上, 经单应性变换可准确判断在近端还是远端
  3. 跑动统计: 跑动热图、跑动距离
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

import cv2
import numpy as np

from .court import Court, COURT_W, COURT_L, NET_Y

WEIGHTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "weights", "yolox_s.onnx")
S = 640  # 模型输入边长


def _grids():
    gs, es = [], []
    for s in (8, 16, 32):
        n = S // s
        xv, yv = np.meshgrid(np.arange(n), np.arange(n))
        g = np.stack((xv, yv), 2).reshape(-1, 2)
        gs.append(g)
        es.append(np.full((g.shape[0], 1), s))
    return np.concatenate(gs).astype(np.float32), np.concatenate(es).astype(np.float32)


class PlayerDetector:
    def __init__(self, court: Court, weights: str = WEIGHTS, conf: float = 0.35):
        self.court = court
        self.net = cv2.dnn.readNetFromONNX(weights)
        self.grids, self.strides = _grids()
        self.conf = conf

    def _raw_people(self, img) -> List[tuple]:
        r = min(S / img.shape[0], S / img.shape[1])
        pad = np.full((S, S, 3), 114, np.uint8)
        rs = cv2.resize(img, (int(img.shape[1] * r), int(img.shape[0] * r)))
        pad[:rs.shape[0], :rs.shape[1]] = rs
        pad = cv2.cvtColor(pad, cv2.COLOR_BGR2RGB)
        self.net.setInput(pad.transpose(2, 0, 1)[None].astype(np.float32))
        out = self.net.forward()[0]
        out[:, :2] = (out[:, :2] + self.grids) * self.strides
        out[:, 2:4] = np.exp(out[:, 2:4]) * self.strides
        sc = out[:, 4] * out[:, 5]          # 类别 0 = person
        k = sc > self.conf
        b, sc = out[k, :4], sc[k]
        if len(sc) == 0:
            return []
        xywh = np.stack([b[:, 0] - b[:, 2] / 2, b[:, 1] - b[:, 3] / 2, b[:, 2], b[:, 3]], 1) / r
        idx = np.array(cv2.dnn.NMSBoxes(xywh.tolist(), sc.tolist(), self.conf, 0.45)).flatten()
        return [(xywh[i], float(sc[i])) for i in idx]

    def detect(self, frame_bgr) -> List[Dict]:
        """返回该帧中场上的球员: [{box:[x,y,w,h], foot_px, foot_m, side, score}]"""
        out = []
        for (x, y, w, h), s in self._raw_people(frame_bgr):
            foot_px = [float(x + w / 2), float(y + h)]
            fm = self.court.px_to_m([foot_px])[0]
            # 球场范围: 两侧外扩 1.2m, 底线后外扩 2.5m
            if not (-1.2 <= fm[0] <= COURT_W + 1.2 and -2.5 <= fm[1] <= COURT_L + 2.5):
                continue
            out.append({
                "box": [float(x), float(y), float(w), float(h)],
                "foot_px": foot_px,
                "foot_m": [round(float(fm[0]), 2), round(float(fm[1]), 2)],
                "side": "far" if fm[1] < NET_Y else "near",
                "score": round(s, 2),
            })
        return out

    def detect_frames(self, video_path: str, frames: List[int], progress=None) -> Dict[int, List[Dict]]:
        """按帧号批量检测 (顺序读取, 比随机跳帧快)。"""
        cap = cv2.VideoCapture(video_path)
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        want = sorted(set(int(f) for f in frames if 0 <= f < n))
        res: Dict[int, List[Dict]] = {}
        if not want:
            return res
        cap.set(cv2.CAP_PROP_POS_FRAMES, want[0])
        i, wi = want[0], 0
        while wi < len(want):
            if want[wi] - i > 60:                 # 跨度大时直接跳帧
                cap.set(cv2.CAP_PROP_POS_FRAMES, want[wi])
                i = want[wi]
            ok = cap.grab()
            if not ok:
                break
            if i == want[wi]:
                ok, f = cap.retrieve()
                if ok:
                    res[i] = self.detect(f)
                wi += 1
                if progress and wi % 10 == 0:
                    progress(wi / len(want))
            i += 1
        cap.release()
        return res


def ball_near_player(ball_px, players: List[Dict]) -> Optional[Dict]:
    """球是否在某个球员的"可击球范围"内 (人框向上、左右扩展出手臂+球拍), 返回最近的球员。"""
    bx, by = ball_px
    best, best_d = None, 1e9
    for p in players:
        x, y, w, h = p["box"]
        ext_x = h * 0.6
        ext_top = h * 0.9
        if (x - ext_x) <= bx <= (x + w + ext_x) and (y - ext_top) <= by <= (y + h * 1.05):
            cx, cy = x + w / 2, y + h * 0.3
            d = ((bx - cx) ** 2 + (by - cy) ** 2) ** 0.5 / max(h, 1)
            if d < best_d:
                best, best_d = p, d
    return best
