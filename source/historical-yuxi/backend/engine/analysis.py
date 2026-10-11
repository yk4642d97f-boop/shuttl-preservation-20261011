"""
羽析 · 回合与击球分析

输入: 追踪结果 (每帧球坐标) + 场地标定
输出: 回合列表、每拍击球 (时间/击球方/类型)、落点 (米) 与界内外判定、得分方、汇总统计

核心思路
1. 清洗轨迹: 剔除离群点, 插值补全短暂丢失
2. 球静止 (落地) 或长时间消失 => 回合边界
3. 击球 = 轨迹方向"急转" (抛物线顶点是平滑转弯, 不会误判)
4. 击球方: 2 状态隐马尔可夫模型 (近端/远端),
   观测 = 球相对球网的画面位置 + 击球后飞行方向, 转移 = 双方交替击球,
   用 Viterbi 求最可能序列 —— 比简单交替更能容忍误检
5. 落点: 回合末球静止处经单应性映射到球场坐标 => 界内/出界/下网 => 得分方
"""
from __future__ import annotations

import math
from typing import List, Optional

import numpy as np

from .court import Court, judge_in_out, NET_Y, COURT_L
from .players import ball_near_player

SIDE_CN = {"near": "近端", "far": "远端"}


# ============================================================ 工具
def _interp_gaps(x, y, vis, max_gap):
    """对连续丢失 <= max_gap 帧的空洞做线性插值。"""
    x, y, vis = x.copy(), y.copy(), vis.copy()
    n = len(vis)
    i = 0
    while i < n:
        if vis[i] == 0:
            j = i
            while j < n and vis[j] == 0:
                j += 1
            if i > 0 and j < n and (j - i) <= max_gap:
                for k in range(i, j):
                    t = (k - i + 1) / (j - i + 1)
                    x[k] = x[i - 1] + t * (x[j] - x[i - 1])
                    y[k] = y[i - 1] + t * (y[j] - y[i - 1])
                    vis[k] = 1
            i = j
        else:
            i += 1
    return x, y, vis


def _remove_outliers(x, y, vis, thr):
    """与前后邻居都相距很远、而前后邻居彼此很近的孤立点 => 误检。"""
    vis = vis.copy()
    idx = np.where(vis == 1)[0]
    for a in range(1, len(idx) - 1):
        i, p, q = idx[a], idx[a - 1], idx[a + 1]
        if i - p > 3 or q - i > 3:
            continue
        dp = math.hypot(x[i] - x[p], y[i] - y[p])
        dq = math.hypot(x[i] - x[q], y[i] - y[q])
        dpq = math.hypot(x[p] - x[q], y[p] - y[q])
        if dp > thr and dq > thr and dpq < thr * 0.8:
            vis[i] = 0
    return vis


def _runs(mask):
    """返回布尔数组中所有 True 连续段 [(start, end_exclusive), ...]"""
    out, n, i = [], len(mask), 0
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


# ============================================================ 主分析
class RallyAnalyzer:
    def __init__(self, track: dict, court: Court, match_type: str = "singles"):
        self.fps = float(track.get("fps") or 30.0)
        self.W = int(track["width"])
        self.H = int(track["height"])
        self.court = court
        self.match_type = match_type
        self.raw_x = np.array(track["x"], dtype=np.float64)
        self.raw_y = np.array(track["y"], dtype=np.float64)
        self.raw_vis = np.array(track["vis"], dtype=np.int32)
        self.n = len(self.raw_vis)
        # 以 1280 宽、30fps 为基准的尺度系数, 让阈值对不同分辨率/帧率通用
        self.px = self.W / 1280.0
        self.fr = self.fps / 30.0

    # ---------------------------------------------------------- 步骤 1 清洗
    def _clean(self):
        vis = _remove_outliers(self.raw_x, self.raw_y, self.raw_vis, thr=80 * self.px)
        x, y, vis = _interp_gaps(self.raw_x, self.raw_y, vis, max_gap=int(round(6 * self.fr)))
        self.x, self.y, self.vis = x, y, vis

    # ---------------------------------------------------------- 步骤 2 静止/边界
    def _rest_mask(self):
        """球几乎不动 (躺在地上/被捡起前) 的帧。"""
        win = max(5, int(round(8 * self.fr)))
        tol = 5 * self.px
        rest = np.zeros(self.n, dtype=bool)
        for i in range(0, self.n - win + 1):
            seg = slice(i, i + win)
            if self.vis[seg].min() == 0:
                continue
            if (np.ptp(self.x[seg]) < tol) and (np.ptp(self.y[seg]) < tol):
                rest[seg] = True
        return rest

    # ---------------------------------------------------------- 步骤 3 击球检测
    def _detect_hits(self, s, e):
        """在活动区间 [s, e) 内检测方向急转点。"""
        k = max(2, int(round(3 * self.fr)))
        min_move = 3.5 * self.px          # 击球后至少 3.5 px/帧 (720p, 30fps 基准)
        cand = []
        for i in range(s + k, e - k):
            if not (self.vis[i - k] and self.vis[i] and self.vis[i + k]):
                continue
            ax, ay = self.x[i] - self.x[i - k], self.y[i] - self.y[i - k]
            bx, by = self.x[i + k] - self.x[i], self.y[i + k] - self.y[i]
            na, nb = math.hypot(ax, ay), math.hypot(bx, by)
            if nb < min_move * k:
                continue
            if na < min_move * 0.5:
                # 从几乎静止到运动 => 发球
                cand.append((i, 2.0))
                continue
            cosang = (ax * bx + ay * by) / (na * nb)
            ang = math.degrees(math.acos(max(-1.0, min(1.0, cosang))))
            ratio = nb / na
            score = 0.0
            # 羽毛球阻力极大: 高球到顶点后会急剧减速、近乎垂直下落, 顶点在画面上也是"急转"。
            # 区别在于: 击球后球会加速 (ratio > 1), 顶点处则是减速 (ratio < 1)。
            if ang > 120:
                score = ang / 90.0                     # 近乎反向: 必是击球 (含挡网等减速回球)
            elif ang > 45 and ratio > 1.25:
                score = ang / 90.0 * min(ratio, 3) / 1.5
            elif ang > 20 and ratio > 2.2:
                score = 0.6 + 0.1 * min(ratio, 5)     # 同向大幅加速 (如扑杀/抽球)
            if score > 0:
                cand.append((i, score))
        # 非极大值抑制: 0.3 秒内只保留一个
        gap = int(round(9 * self.fr))
        cand.sort(key=lambda c: -c[1])
        taken: List[tuple] = []
        for i, sc in cand:
            if all(abs(i - t[0]) > gap for t in taken):
                taken.append((i, sc))
        return sorted(taken)

    def _validate_hits(self, cands, players_at):
        """用球员位置验证候选击球: 球必须在某名球员的击球范围内。
        返回 [{f, sc, hint, strength, foot_m}]:
          hint     = 倾向的击球方 (只有一侧球员够得着 => 强证据; 两侧都够得着 => 弱证据)
          foot_m   = 击球者脚底的球场坐标 (用于"下网"合理性检查)"""
        out = []
        for f, sc in cands:
            item = {"f": f, "sc": sc, "hint": None, "strength": 0.0, "foot_m": None, "by_side": {}}
            ps = None if players_at is None else players_at.get(f)
            if ps is None:
                out.append(item)
                continue
            reach = {}
            for side in ("near", "far"):
                p = ball_near_player((self.x[f], self.y[f]), [q for q in ps if q["side"] == side])
                if p is not None:
                    reach[side] = p
            item["by_side"] = {k: v["foot_m"] for k, v in reach.items()}
            if len(reach) == 1:
                side, p = next(iter(reach.items()))
                item.update(hint=side, strength=8.0, foot_m=p["foot_m"])
            elif len(reach) == 2:
                # 画面上两人都够得着 (前后重叠): 只给弱倾向, 交给轨迹证据 + HMM 决定
                best = ball_near_player((self.x[f], self.y[f]), list(reach.values()))
                item.update(hint=best["side"], strength=1.0)
            elif not ps and sc >= 1.3:
                pass                              # 这一帧没检测到人 (遮挡/出画), 信号又很强: 保留
            else:
                continue                          # 球不在任何球员身边 => 不是击球 (如高球顶点)
            out.append(item)
        return out

    def _resolve(self, items, landing):
        """HMM 判定击球方, 再用两条物理约束迭代剔除误检:
        1) 单打同一方不可能连续击球 (球必须先过网) => 同侧相邻的两拍删掉证据较弱者
        2) 若判为"下网", 落点必须在击球者与球网之间; 落在击球者身后 => 最后一拍其实没击到"""
        items = list(items)
        for _ in range(20):
            if not items:
                return [], []
            hits = [it["f"] for it in items]
            sides = self._assign_sides(hits, items)
            drop = None
            for i in range(len(items) - 1):
                if sides[i] == sides[i + 1]:
                    a, b = items[i], items[i + 1]
                    ka = (a["strength"] >= 8) * 10 + a["sc"]
                    kb = (b["strength"] >= 8) * 10 + b["sc"]
                    drop = i if ka < kb else i + 1
                    break
            if drop is None and landing and sides[-1] == landing["side"]:
                foot = items[-1]["by_side"].get(sides[-1]) or items[-1]["foot_m"]
                if foot is not None:
                    d_hit = abs(foot[1] - NET_Y)
                    d_land = abs(landing["m"][1] - NET_Y)
                    if d_land > d_hit + 0.3:
                        drop = len(items) - 1
            if drop is None:
                for it, sd in zip(items, sides):
                    it["foot_m"] = it["by_side"].get(sd, it["foot_m"])
                return items, sides
            items.pop(drop)
        return items, self._assign_sides([it["f"] for it in items], items)

    # ---------------------------------------------------------- 步骤 4 击球方 (HMM)
    def _side_evidence(self, f, next_f):
        """返回 log P(obs|near) - log P(obs|far) 的近似分数 (>0 倾向近端)。"""
        score = 0.0
        net_y = self.court.net_y_px_at(self.x[f])
        # 球在画面中低于地面网线 => 必在近端上空 (强证据)
        if self.y[f] > net_y + 10 * self.px:
            score += 2.5
        else:
            score -= 0.8
        # 击球后 ~0.2s 内的画面纵向运动: 近端击出的球总是"向上/远离"
        k = min(int(round(6 * self.fr)), max(1, (next_f - f) - 1) if next_f else int(round(6 * self.fr)))
        j = min(self.n - 1, f + k)
        dy = self.y[j] - self.y[f]
        if dy > 6 * self.px:
            score -= 2.0            # 球朝镜头方向来 => 远端击出
        elif dy < -6 * self.px:
            score += 0.6            # 向上: 近端击出 (但远端挑高球也会向上, 所以证据弱)
        return score

    def _assign_sides(self, hits, items=None):
        if not hits:
            return []
        ev = []
        for i, h in enumerate(hits):
            traj = self._side_evidence(h, hits[i + 1] if i + 1 < len(hits) else None)
            it = items[i] if items else None
            if it and it["hint"] is not None and it["strength"] >= 8:
                ev.append(8.0 if it["hint"] == "near" else -8.0)   # 只有一侧球员够得着: 强证据
            elif it and it["hint"] is not None:
                ev.append(traj + (it["strength"] if it["hint"] == "near" else -it["strength"]))
            else:
                ev.append(traj)
        # 状态 0=near 1=far, 发射对数似然 = ±ev/2, 转移: 交替 log(0.85), 同侧 log(0.15)
        t_alt, t_same = math.log(0.85), math.log(0.15)
        emit = lambda s, e: (e / 2) if s == 0 else (-e / 2)
        dp = [[emit(0, ev[0]), emit(1, ev[0])]]
        bp = [[0, 0]]
        for i in range(1, len(hits)):
            row, brow = [], []
            for s in (0, 1):
                c0 = dp[-1][0] + (t_same if s == 0 else t_alt)
                c1 = dp[-1][1] + (t_alt if s == 0 else t_same)
                if c0 >= c1:
                    row.append(c0 + emit(s, ev[i])); brow.append(0)
                else:
                    row.append(c1 + emit(s, ev[i])); brow.append(1)
            dp.append(row); bp.append(brow)
        s = 0 if dp[-1][0] >= dp[-1][1] else 1
        path = [s]
        for i in range(len(hits) - 1, 0, -1):
            s = bp[i][s]
            path.append(s)
        path.reverse()
        return ["near" if p == 0 else "far" for p in path]

    # ---------------------------------------------------------- 步骤 5 击球类型 (实验性)
    def _px_per_m(self, f):
        """该点附近地面上 1 米对应多少像素 (粗略的局部尺度)。"""
        c = self.court
        pm = c.px_to_m([[self.x[f], self.y[f]]])[0]
        pm[0] = min(max(pm[0], 0.0), 6.1)
        pm[1] = min(max(pm[1], 0.0), COURT_L)
        a = c.m_to_px([pm, pm + np.array([0.0, 1.0])])
        b = c.m_to_px([pm, pm + np.array([1.0, 0.0])])
        return max(1e-3, (np.linalg.norm(a[1] - a[0]) + np.linalg.norm(b[1] - b[0])) / 2)

    def _classify(self, f, side, next_f, is_serve, foot_m=None):
        """击球类型 (规则法, 实验性)。
        依据: 击球者站位 (离网距离) + 飞行时间 (到下一拍/落地) + 出球方向与速度。"""
        if is_serve:
            return "发球"
        dur = ((next_f - f) / self.fps) if next_f else None
        k = max(2, int(round(3 * self.fr)))
        j = min(self.n - 1, f + k)
        v_px = math.hypot(self.x[j] - self.x[f], self.y[j] - self.y[f]) / k * self.fps
        dy = self.y[j] - self.y[f]
        if foot_m is not None:
            dn = abs(foot_m[1] - NET_Y)                        # 击球者离网距离 (米)
            v_mps = v_px / self._px_per_m_at_m(foot_m)
        else:
            net_y = self.court.net_y_px_at(self.x[f])
            dn = 1.0 if abs(self.y[f] - net_y) < 60 * self.px else 4.0
            v_mps = v_px / self._px_per_m(f)
        # 远端击球时, 球朝镜头方向来是"向下压"; 近端击球的杀/吊/高远在画面上都向上, 靠飞行时间区分
        up_far = (side == "far" and dy < -3 * self.px)
        if dn < 2.3:
            if (dur is not None and dur > 1.0) or up_far:
                return "挑球"
            return "网前球"
        if dur is not None and dur > 1.3:
            return "高远球"
        if up_far and (dur is None or dur > 1.0):
            return "高远球"
        if (dur is None or dur < 0.8) and v_mps > 12:
            return "杀球"
        if dur is not None and dur < 0.8:
            return "平抽"
        return "吊球"

    def _px_per_m_at_m(self, pm):
        """球场上某点 (米) 附近 1 米对应的像素数。"""
        c = self.court
        pm = np.array([min(max(pm[0], 0.0), 6.1), min(max(pm[1], 0.0), COURT_L)])
        a = c.m_to_px([pm, pm + np.array([0.0, 1.0])])
        b = c.m_to_px([pm, pm + np.array([1.0, 0.0])])
        return max(1e-3, (np.linalg.norm(a[1] - a[0]) + np.linalg.norm(b[1] - b[0])) / 2)

    # ---------------------------------------------------------- 主入口
    def run(self, player_fn=None) -> dict:
        """player_fn(frames: List[int]) -> {frame: [player,...]}; 为 None 时退化为纯轨迹分析。"""
        self._clean()
        rest = self._rest_mask()
        moving = (self.vis == 1) & (~rest)
        # 活动段合并: 中间没有"球静止"时, 短暂丢失 (<1.2s) 或球飞出画面顶部 (<3s) 都视为同一回合
        segs = _runs(moving)
        merged = []
        short_gap = int(round(1.2 * self.fps))
        top_gap = int(round(3.0 * self.fps))
        top_edge = 0.10 * self.H
        for s, e in segs:
            if merged:
                ps, pe = merged[-1]
                gap = s - pe
                no_rest = not rest[pe:s].any()
                via_top = self.y[pe - 1] < top_edge or self.y[s] < top_edge
                if no_rest and (gap <= short_gap or (via_top and gap <= top_gap)):
                    merged[-1] = (ps, e)
                    continue
            merged.append((s, e))
        min_len = int(round(0.8 * self.fps))
        merged = [(s, e) for s, e in merged if e - s >= min_len]

        # ---- 阶段 A: 每个回合的候选击球 + 落地点
        plans = []
        for s, e in merged:
            cands = self._detect_hits(s, e)
            # 若起点前是静止 (球在手中/地上), 视为发球
            serve_at_start = s > 0 and rest[max(0, s - 3):s].any()
            if serve_at_start and (not cands or cands[0][0] - s > int(round(6 * self.fr))):
                cands = [(s, 2.0)] + cands
            landing = self._landing(e, rest)
            if landing:
                # 触地后的弹跳也会产生"急转", 去掉落地前后的伪击球
                cut = landing["frame"] - int(round(4 * self.fr))
                cands = [c for c in cands if c[0] < cut]
            plans.append((s, e, cands, serve_at_start, landing))

        # ---- 阶段 B: 一次性检测球员 (候选击球帧 + 每 0.33s 采样的跑动帧)
        players_at = None
        move_frames: List[int] = []
        if player_fn is not None:
            step = max(1, int(round(self.fps / 3)))
            for s, e, cands, _, landing in plans:
                end = landing["frame"] if landing else e
                move_frames.extend(range(s, end + 1, step))
            want = sorted(set([c[0] for p in plans for c in p[2]] + move_frames))
            players_at = player_fn(want) if want else {}

        # ---- 阶段 C: 验证击球、判定击球方、组装回合
        rallies = []
        for s, e, cands, serve_at_start, landing in plans:
            valid, sides = self._resolve(self._validate_hits(cands, players_at), landing)
            if serve_at_start and valid and valid[0]["f"] != s:
                serve_at_start = False
            if not valid:
                continue
            hits = [v["f"] for v in valid]
            shots = []
            for i, (h, sd) in enumerate(zip(hits, sides)):
                nxt = hits[i + 1] if i + 1 < len(hits) else (landing["frame"] if landing else None)
                shots.append({
                    "frame": int(h),
                    "t": round(h / self.fps, 2),
                    "side": sd,
                    "side_cn": SIDE_CN[sd],
                    "type": self._classify(h, sd, nxt, is_serve=(i == 0 and serve_at_start), foot_m=valid[i]["foot_m"]),
                    "px": [round(float(self.x[h]), 1), round(float(self.y[h]), 1)],
                    "player_m": valid[i]["foot_m"],
                    "verified": valid[i]["hint"] is not None,
                })
            rally = {
                "index": len(rallies) + 1,
                "start_frame": int(hits[0]),
                "end_frame": int(landing["frame"] if landing else e),
                "shots": shots,
                "num_shots": len(shots),
                "landing": landing,
            }
            rally["start_t"] = round(rally["start_frame"] / self.fps, 2)
            rally["end_t"] = round(rally["end_frame"] / self.fps, 2)
            rally["duration"] = round(rally["end_t"] - rally["start_t"], 2)
            rally.update(self._point_result(shots, landing))
            rallies.append(rally)

        movement = self._movement(players_at, move_frames) if players_at is not None else None
        return {
            "fps": self.fps,
            "num_frames": self.n,
            "match_type": self.match_type,
            "rallies": rallies,
            "summary": self._summary(rallies),
            "movement": movement,
            "trajectory": {
                "x": [round(float(v), 1) for v in self.x],
                "y": [round(float(v), 1) for v in self.y],
                "vis": [int(v) for v in self.vis],
            },
        }

    def _movement(self, players_at, frames):
        """跑动统计: 每侧球员的站位点 (热图用) 与跑动距离。"""
        out = {}
        for side in ("near", "far"):
            pts, dist, prev = [], 0.0, None
            for f in sorted(set(frames)):
                ps = [p for p in players_at.get(f, []) if p["side"] == side]
                if not ps:
                    prev = None
                    continue
                if prev is not None:
                    p = min(ps, key=lambda q: math.dist(q["foot_m"], prev))
                else:
                    p = max(ps, key=lambda q: q["score"])
                fm = p["foot_m"]
                pts.append([fm[0], fm[1]])
                if prev is not None:
                    d = math.dist(fm, prev)
                    if d < 3.0:            # 0.33s 内移动超过 3m 视为检测跳变, 不计入
                        dist += d
                prev = fm
            out[side] = {"positions_m": pts, "distance_m": round(dist, 1)}
        return out

    def _landing(self, e, rest):
        """回合结束的落地点。
        若之后球静止: 在静止前 0.8s 内的下落段里找"画面最低点"= 第一次触地 (羽毛球触地后会小幅弹跳)。
        否则取最后可见点, 标记为低置信度。"""
        look = int(round(12 * self.fr))
        f = None
        conf = "high"
        for i in range(e, min(self.n, e + look)):
            if rest[i]:
                f = i
                break
        if f is not None:
            back = int(round(0.8 * self.fps))
            lo = max(0, f - back)
            win = [i for i in range(lo, f + 1) if self.vis[i]]
            if win:
                contact = max(win, key=lambda i: self.y[i])
                if self.y[contact] > self.y[f] + 2 * self.px:
                    f = contact
        else:
            f = e - 1
            conf = "low"
        if f < 0 or not self.vis[f]:
            return None
        xm, ym = self.court.px_to_m([[self.x[f], self.y[f]]])[0]
        # 映射后远离球场 3 米以上, 多半是球飞出画面/被人拿着, 不作判定
        if not (-3 < xm < 9.1 and -3 < ym < COURT_L + 3):
            return None
        j = judge_in_out(float(xm), float(ym), self.match_type)
        return {
            "frame": int(f),
            "t": round(f / self.fps, 2),
            "px": [round(float(self.x[f]), 1), round(float(self.y[f]), 1)],
            "m": [round(float(xm), 2), round(float(ym), 2)],
            "confidence": conf,
            **j,
        }

    def _point_result(self, shots, landing):
        if not landing or not shots:
            return {"winner": None, "reason": "未检测到落地", "uncertain": True,
                    "last_hitter": shots[-1]["side"] if shots else None}
        last = shots[-1]["side"]
        other = {"near": "far", "far": "near"}
        unc = bool(landing.get("uncertain")) or landing.get("confidence") == "low"
        if landing["side"] == last:
            return {"winner": other[last], "reason": "下网", "last_hitter": last, "uncertain": unc}
        if landing["in"]:
            return {"winner": last, "reason": "界内得分", "last_hitter": last, "uncertain": unc}
        return {"winner": other[last], "reason": "出界", "last_hitter": last, "uncertain": unc}

    def _summary(self, rallies):
        types = {}
        for r in rallies:
            for s in r["shots"]:
                types[s["type"]] = types.get(s["type"], 0) + 1
        pts = {"near": 0, "far": 0}
        for r in rallies:
            if r.get("winner"):
                pts[r["winner"]] += 1
        durs = [r["duration"] for r in rallies]
        shots = [r["num_shots"] for r in rallies]
        landings = [r["landing"] for r in rallies if r.get("landing")]
        return {
            "num_rallies": len(rallies),
            "total_shots": int(sum(shots)),
            "avg_shots_per_rally": round(float(np.mean(shots)), 1) if shots else 0,
            "longest_rally_shots": int(max(shots)) if shots else 0,
            "avg_rally_duration": round(float(np.mean(durs)), 1) if durs else 0,
            "points": pts,
            "shot_types": types,
            "in_count": sum(1 for l in landings if l["in"]),
            "out_count": sum(1 for l in landings if not l["in"]),
            "landings_m": [l["m"] + [1 if l["in"] else 0] for l in landings],
        }
