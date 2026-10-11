"""
羽析 · 追踪准确率评估 (TrackNet 论文标准)

用法 (在 yuxi 目录下):
    .venv/bin/python tools/eval_tracking.py                 # 默认评估 dev_data/nycu/Test, fast 模式
    .venv/bin/python tools/eval_tracking.py --set Amateur --mode accurate

判定标准: 预测点与人工标注点距离 <= 4px (模型输入 512x288 下), 即 1280x720 下 10px, 算"正确"。
    TP  = 标注有球, 预测有球且距离在阈值内
    FP1 = 标注有球, 预测有球但距离超出阈值
    FP2 = 标注无球, 预测却有球
    FN  = 标注有球, 预测无球
    TN  = 标注无球, 预测无球
同时分别统计 "仅 TrackNet 检测" 与 "检测 + InpaintNet 补全" 两种口径
(补全会在被遮挡帧上填出坐标, 而人工标注把遮挡帧记为无球, 所以补全会增加 FP2)。

说明: dev_data/nycu/Test 与 TrackNetV3 官方测试集完全一致 (训练时未使用), 结果可与论文对比;
      dev_data/nycu/Amateur 为业余比赛, 可能被用于训练, 结果会偏乐观。
"""
import argparse
import csv
import glob
import json
import math
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))


def score(pred_x, pred_y, pred_vis, labels, tol):
    s = dict(TP=0, FP1=0, FP2=0, FN=0, TN=0)
    for f, (v, x, y) in labels.items():
        if f >= len(pred_vis):
            continue
        pv = pred_vis[f]
        if pv and v:
            s["TP" if math.hypot(pred_x[f] - x, pred_y[f] - y) <= tol else "FP1"] += 1
        elif pv and not v:
            s["FP2"] += 1
        elif v and not pv:
            s["FN"] += 1
        else:
            s["TN"] += 1
    return s


def summarize(s):
    n = sum(s.values()) or 1
    acc = (s["TP"] + s["TN"]) / n
    prec = s["TP"] / max(1, s["TP"] + s["FP1"] + s["FP2"])
    rec = s["TP"] / max(1, s["TP"] + s["FN"])
    f1 = 2 * prec * rec / max(1e-9, prec + rec)
    return acc, prec, rec, f1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="Test", choices=["Test", "Amateur"])
    ap.add_argument("--mode", default="fast", choices=["fast", "accurate"])
    ap.add_argument("--cache", default=os.path.join(ROOT, "dev_data", "eval_cache"))
    a = ap.parse_args()
    os.makedirs(a.cache, exist_ok=True)

    from engine.tracker import ShuttleTracker
    tracker = None
    vids = sorted(glob.glob(os.path.join(ROOT, "dev_data", "nycu", a.set, "match*", "video", "*.mp4")))
    tot = {"detect": dict(TP=0, FP1=0, FP2=0, FN=0, TN=0), "inpaint": dict(TP=0, FP1=0, FP2=0, FN=0, TN=0)}
    for v in vids:
        match = v.split(os.sep)[-3]
        rid = os.path.basename(v)[:-4]
        lab = os.path.join(os.path.dirname(os.path.dirname(v)), "csv", f"{rid}_ball.csv")
        if not os.path.exists(lab):
            print(f"跳过 {match}/{rid}: 缺少标注文件")
            continue
        cache = os.path.join(a.cache, f"{a.set}_{a.mode}_{match}_{rid}.json")
        if os.path.exists(cache):
            pr = json.load(open(cache))
        else:
            tracker = tracker or ShuttleTracker()
            t0 = time.time()
            pr = tracker.track(v, mode=a.mode).to_dict()
            pr["elapsed_s"] = round(time.time() - t0, 1)
            json.dump(pr, open(cache, "w"))
        tol = 4 * pr["width"] / 512
        labels = {int(r["Frame"]): (int(r["Visibility"]), float(r["X"]), float(r["Y"])) for r in csv.DictReader(open(lab))}
        vis_full = pr["vis"]
        inp = pr.get("inpainted") or [0] * len(vis_full)
        vis_det = [1 if (vv and not ii) else 0 for vv, ii in zip(vis_full, inp)]
        s_det = score(pr["x"], pr["y"], vis_det, labels, tol)
        s_inp = score(pr["x"], pr["y"], vis_full, labels, tol)
        for k in s_det:
            tot["detect"][k] += s_det[k]
            tot["inpaint"][k] += s_inp[k]
        acc, prec, rec, f1 = summarize(s_det)
        acc2, _, rec2, _ = summarize(s_inp)
        print(f"{match}/{rid}  帧={sum(s_det.values()):4d}  仅检测: acc={acc:.3f} prec={prec:.3f} rec={rec:.3f}"
              f" | 含补全: acc={acc2:.3f} rec={rec2:.3f}  用时={pr.get('elapsed_s', '?')}s")
    print()
    for k, name in (("detect", "仅 TrackNet 检测"), ("inpaint", "检测 + InpaintNet 补全")):
        acc, prec, rec, f1 = summarize(tot[k])
        print(f"[{a.set} / {a.mode}] {name}: 帧数={sum(tot[k].values())}  准确率={acc:.3f}  精确率={prec:.3f}"
              f"  召回率={rec:.3f}  F1={f1:.3f}  {tot[k]}")


if __name__ == "__main__":
    main()
