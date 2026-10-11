"""
羽析 · 场地标定与几何

坐标系(单位: 米), 以画面中"远端左角"为原点:
    x: 从左到右  0 ~ 6.10   (双打宽度)
    y: 从远到近  0 ~ 13.40  (全长), 球网在 y = 6.70

用户在画面上依次点击双打外边线的 4 个角:
    远左 -> 远右 -> 近右 -> 近左
由此求出"画面像素 -> 球场米"的单应性矩阵 (Homography)。

注意: 单应性只对"地面上的点"成立。球在空中时的投影会有偏差,
因此只用它计算"落地点", 不用于空中击球点。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

import cv2
import numpy as np

COURT_W = 6.10          # 双打宽
COURT_L = 13.40         # 全长
NET_Y = COURT_L / 2     # 球网位置
SINGLES_MARGIN = 0.46   # 单打边线距双打边线
SHORT_SERVICE = 1.98    # 前发球线距网
DOUBLES_LONG_SERVICE = 0.76  # 双打后发球线距底线
LINE_TOL = 0.04         # 线宽 4cm, 压线算界内

# 画面四角对应的球场坐标 (远左, 远右, 近右, 近左)
CORNERS_M = np.array([[0, 0], [COURT_W, 0], [COURT_W, COURT_L], [0, COURT_L]], dtype=np.float32)


@dataclass
class Court:
    corners_px: np.ndarray      # (4,2) 画面像素
    H: np.ndarray               # 像素 -> 米
    H_inv: np.ndarray           # 米 -> 像素

    @classmethod
    def from_corners(cls, corners_px: Sequence[Sequence[float]]) -> "Court":
        pts = np.array(corners_px, dtype=np.float32).reshape(4, 2)
        pts = order_corners(pts)
        H = cv2.getPerspectiveTransform(pts, CORNERS_M)
        return cls(corners_px=pts, H=H, H_inv=np.linalg.inv(H))

    def px_to_m(self, xy) -> np.ndarray:
        a = np.asarray(xy, dtype=np.float64).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(a, self.H).reshape(-1, 2)

    def m_to_px(self, xy) -> np.ndarray:
        a = np.asarray(xy, dtype=np.float64).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(a, self.H_inv).reshape(-1, 2)

    def net_line_px(self) -> Tuple[np.ndarray, np.ndarray]:
        """球网在地面上的投影线 (左端点, 右端点), 像素坐标。"""
        p = self.m_to_px([[0, NET_Y], [COURT_W, NET_Y]])
        return p[0], p[1]

    def net_y_px_at(self, x_px: float) -> float:
        """画面中某一列 x 处, 地面球网线的 y 像素值 (用于判断球在网的哪一侧)。"""
        a, b = self.net_line_px()
        if abs(b[0] - a[0]) < 1e-6:
            return float((a[1] + b[1]) / 2)
        t = (x_px - a[0]) / (b[0] - a[0])
        return float(a[1] + t * (b[1] - a[1]))

    def court_lines_px(self) -> List[List[List[float]]]:
        """所有场线的像素坐标, 供前端叠加绘制 / 让用户核对标定是否准确。"""
        segs_m = court_line_segments()
        out = []
        for (x1, y1), (x2, y2) in segs_m:
            p = self.m_to_px([[x1, y1], [x2, y2]])
            out.append(p.round(1).tolist())
        return out


def order_corners(pts: np.ndarray) -> np.ndarray:
    """把任意顺序点击的 4 个点整理成 远左、远右、近右、近左。
    画面中远端在上 (y 小), 近端在下 (y 大)。"""
    idx = np.argsort(pts[:, 1])
    top, bottom = pts[idx[:2]], pts[idx[2:]]
    top = top[np.argsort(top[:, 0])]
    bottom = bottom[np.argsort(bottom[:, 0])]
    return np.array([top[0], top[1], bottom[1], bottom[0]], dtype=np.float32)


def court_line_segments():
    """羽毛球场全部标线 (米)。"""
    W, L = COURT_W, COURT_L
    s = SINGLES_MARGIN
    ny = NET_Y
    segs = [
        ((0, 0), (W, 0)), ((0, L), (W, L)),                  # 底线
        ((0, 0), (0, L)), ((W, 0), (W, L)),                  # 双打边线
        ((s, 0), (s, L)), ((W - s, 0), (W - s, L)),          # 单打边线
        ((0, ny - SHORT_SERVICE), (W, ny - SHORT_SERVICE)),  # 前发球线
        ((0, ny + SHORT_SERVICE), (W, ny + SHORT_SERVICE)),
        ((0, DOUBLES_LONG_SERVICE), (W, DOUBLES_LONG_SERVICE)),          # 双打后发球线
        ((0, L - DOUBLES_LONG_SERVICE), (W, L - DOUBLES_LONG_SERVICE)),
        ((W / 2, 0), (W / 2, ny - SHORT_SERVICE)),            # 中线
        ((W / 2, ny + SHORT_SERVICE), (W / 2, L)),
        ((0, ny), (W, ny)),                                   # 球网 (地面投影)
    ]
    return segs


def judge_in_out(x_m: float, y_m: float, match_type: str = "singles") -> dict:
    """
    判定落点界内/出界。
    返回: {in: bool, side: 'far'|'near', margin_m: 距最近边界的距离(界内为正, 出界为负), line: 最近的边界名}
    """
    if match_type == "singles":
        x_lo, x_hi = SINGLES_MARGIN, COURT_W - SINGLES_MARGIN
    else:
        x_lo, x_hi = 0.0, COURT_W
    side = "far" if y_m < NET_Y else "near"
    # 到各条边界的有符号距离 (在界内为正)
    d = {
        "左边线": x_m - x_lo,
        "右边线": x_hi - x_m,
        "底线": y_m if side == "far" else COURT_L - y_m,
    }
    line, margin = min(d.items(), key=lambda kv: kv[1])
    is_in = margin >= -LINE_TOL / 2
    # 存疑: 离边线不足 8cm, 或离球网不足 0.4m (标定与追踪误差量级内, 建议人工复核)
    net_dist = abs(y_m - NET_Y)
    uncertain = abs(margin) < 0.08 or net_dist < 0.4
    return {"in": bool(is_in), "side": side, "margin_m": round(float(margin), 3), "line": line,
            "net_dist_m": round(float(net_dist), 2), "uncertain": bool(uncertain)}
