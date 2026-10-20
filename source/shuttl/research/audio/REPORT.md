# 声音辅助击球检测（实验功能，默认关闭）

2026-10-20。代码在后端 `app/services/tracking/audio_hits.py`、`hit_fusion.py`，由 `HitNet.detect(audio_curve=...)`
和流水线开关 `SHUTTL_AUDIO_FUSION=1` 接入。全部在云端 worker 上运行，手机端不做任何声音处理。

## 结论

1. 声音不能单独当检测器。用真实标注拟合音画偏差（上限情形），z≥8 时 P 0.334 / R 0.612 / F1 0.432。
   但它适合在视觉模型已有候选时"加减分 + 对时"。
2. 在声音清楚的场馆（clementi，122 次击球），用 HitNet 级精度的锚点自动估计音画偏差，误差中位数 5 ms。
   开关打开后，代理视觉模型 F1@±2 帧从 0.471 升到 0.585，F1@±1 帧从 0.318 升到 0.472；召回从 0.557 升到 0.721，精度也从 0.407 升到 0.492。
3. 声音不可用时开关自动关闭，结果和不用声音完全一样：
   - 嘈杂场馆（china）"高出随机"幅度只有 0.046–0.057，30 次抽样里 0 次开启。
   - 转播视频的击球声和其他时刻没有区分度（Cohen d −1.08–0.12）。
   - 视觉锚点太粗时（代理模型自身锚点），三个场馆全部关闭，没有一处变差。
4. 局限，上线前必须补：
   - 视觉模型是代理（kwyoke 的 GRU），不是 HitNet v2。
   - 真正开启的场馆只有 1 个（yewtee 只有 22 次击球，被"至少 30 个锚点"挡住）。
   - 融合参数是固定默认值，没有在开启的场馆上调参；18 组参数敏感性检验的 F1@±2 在 0.524–0.589，全部高于 0.471。
   - 结论要等你在云端用 HitNet v2 和自己的手机录像跑完 `eval_hitnet_fusion.py` 才能定。

## 方法

| 环节 | 做法 |
|---|---|
| 音轨 | ffmpeg 解码成 32 kHz 单声道，30 s 分块流式处理，整场比赛不会占满内存；无音轨或无 ffmpeg 时返回 None |
| 起音特征 | STFT 512 点 / 步长 64（2 ms），只取 6–16 kHz 对数谱通量（人声、脚步、球鞋摩擦大多在低频） |
| 归一化 | 0.1 s 分块的中位数/MAD，在 1.5 s 滑动范围内求稳健 z 分数，适应不同场馆的底噪 |
| 音画偏差 | 手机录像的音轨和画面有固定偏差（三个场馆按标注拟合为 +65 / +99 / +132 ms）。用 HitNet 高置信击球（p≥0.9）当锚点，在 ±250 ms 内做核密度评分（σ 12 ms、1 ms 网格），起音按强度加权 min(z,20)/20 |
| 开关 | 每段录像单独判断：锚点 ≥ 30，且偏差峰值比随机水平高 ≥ 0.10，否则这段录像完全不用声音 |
| 融合 | 在 logit 上加减：e = clip((A−3)/6, 0, 1)，logit p' = logit p + 2.0·e − 0.5·(1−e)，A 为该帧 ±1 帧内的最大起音 z；解码沿用 HitNet 的阈值 0.4 和 NMS 间隔 |
| 对时 | 解码后在 ±2 帧内吸附到 z ≥ 6 的起音，每个起音只用一次，按置信度优先 |

强度加权的原因：最初的计数法在锚点抖动约 1 帧时会失效（HitNet 的偏移分布：0 帧 2032、+1 帧 1390、−1 帧 430、±2 帧 409，见 `research/hitnet/REPORT.md`）。
不加权的核密度在 yewtee（22 次击球）上选错了峰（207 ms，该偏差下击球处证据中位数只有 3.8）。
更危险的是，它在 30 次模拟里 100% 打开开关，偏差误差中位数却有 71 ms，等于带着错误的偏差去融合。
本场馆自己的击球声明显更响（clementi 匹配起音 z 中位数 11.6，未匹配 5.2；yewtee 8.7 对 4.4），加权后选回 132 ms，
同时嘈杂场馆的幅度从 0.087 降到 0.049，好坏场馆的间隔拉开。

## 数据

| 来源 | 内容 | 用途 | 许可 |
|---|---|---|---|
| [kwyoke/Badminton-hit-detection](https://github.com/kwyoke/Badminton-hit-detection) | 业余回合 18 段（有声），214 次击球，3 个场馆，30 fps，共 247 s；附作者 GRU 的逐帧概率 | 主评测；GRU 概率作代理视觉模型 | 仓库没有许可文件，只做内部评测，不随产品分发、不用于发布模型的训练 |
| [FineBadminton-20K](https://huggingface.co/datasets/iLearn-Lab/Finebadminton-20K) | 8 场有声转播单打，1,614 次标注击球（start_frame 即接触帧） | 对照：转播音轨是否可用 | Apache-2.0 |

场馆：china（含 china2）8 段 70 次（单打+双打）；clementi 7 段 122 次（双打）；yewtee 3 段 22 次（单打）。

## 结果

### 1. 频谱分离（`explore2.py` → `results_spectral.txt`）

击球时刻 ±200 ms 内的最大 6–16 kHz 通量与其他时刻的 Cohen d：业余 china 1.10、clementi 0.88、yewtee 0.91；
转播 8 场在 −1.08 到 0.12 之间。转播音轨经过混音、压缩和解说覆盖，不可用；手机现场录音可用。

### 2. 声音单独检测（`eval_audio_only.py` → `results_audio_only.txt`）

| 起音阈值 | P | R | F1@±2 帧 |
|---|---|---|---|
| z≥3 | 0.133 | 0.860 | 0.231 |
| z≥8 | 0.334 | 0.612 | 0.432 |

声音清楚的 clementi 在 z≥3 时召回 0.959，几乎每次击球都有声音，但同时有大量隔壁场地、脚步等起音。

### 3. 击球帧的声音证据（`diag_evidence.py` → `results_evidence.txt`，偏差取标注拟合值）

| 场馆 | 偏差 | 证据中位数：击球帧 / 其他帧 | A≥12：击球帧 / 其他帧（似然比） |
|---|---|---|---|
| clementi | 99 ms | 14.4 / 2.7 | 59% / 4.9%（12.1） |
| yewtee | 132 ms | 8.8 / 2.1 | 41% / 4.6%（8.8） |
| china | 65 ms | 2.9 / 2.1 | 9% / 1.1%（7.9，但只有 9% 的击球达到） |

### 4. 偏差估计的稳健性（`eval_lag_robustness.py` → `results_lag_robustness.json`）

锚点模拟 HitNet：漏掉 10% 击球，加 10% 误检，偏移按 HitNet 实测分布抽样，每个场馆 30 次。

| 场馆 | 偏差误差中位数 / P90 | 幅度中位数（P10–最大） | 开关开启比例 |
|---|---|---|---|
| clementi | 5.0 / 20.5 ms | 0.179（0.159–0.230） | 100% |
| yewtee | 11.5 / 38.0 ms | 0.154（0.116–0.238） | 93%（但锚点不足 30，生产中关闭） |
| china | 38.5 / 84.7 ms | 0.046（0.036–0.076） | 0% |

锚点抖动更大时（高斯 σ=2 帧），clementi 只有 23% 开启。开关只在锚点足够准时才打开。

### 5. 融合效果（`eval_fusion_proxy.py` → `results_fusion_proxy_min30.json`）

协议：融合参数固定为默认值；视觉阈值和时间偏移按留一场馆选取；开关用生产规则。

| 场馆 | 开关（原因、偏差） | 仅视觉 P / R / F1@±2 / F1@±1 | 融合后 P / R / F1@±2 / F1@±1 |
|---|---|---|---|
| clementi | 开（96 ms） | 0.407 / 0.557 / 0.471 / 0.318 | 0.492 / 0.721 / 0.585 / 0.472 |
| china | 关（声音没有信息量） | 0.296 / 0.343 / 0.318 / 0.172 | 不变 |
| yewtee | 关（锚点只有 22 个） | 0.367 / 0.500 / 0.423 / 0.269 | 不变 |
| 合计 | | 0.371 / 0.481 / 0.419 / 0.268 | 0.424 / 0.575 / 0.488 / 0.361 |

- 拆分：clementi 只加减分是 0.565，只吸附是 0.484，两者合用是 0.585。
- 把锚点下限放到 20（`results_fusion_proxy_min20.json`），yewtee 开启：F1@±2 0.423 → 0.519，合计 0.498。
- 用代理模型自己的粗锚点：clementi 幅度 0.079、yewtee 0.072，全部关闭，合计 0.419 不变。

## 上线前在云端验证

1. 开机 AutoDL，恢复 HitNet v2 权重（需要恢复密钥）。
2. 录像：3–5 个场馆，单打和双打都要。
   - 手机固定机位，录整场而不是剪片段（锚点会有几百个）。
   - 关闭降噪、美声等音频处理。
3. 标注：每段视频一个 CSV，列 `frame`（从 0 开始的解码帧号）。
   - 可选列 `type`，发球写 `发球`，可以单独统计发球召回。
   - 清单 CSV 列为 `video,labels,venue,mode`。
4. 在 `source/shuttl/backend` 下运行：
   - `PYTHONPATH=. python ../research/audio/eval_hitnet_fusion.py collect --manifest 清单.csv --device cuda --cache 缓存目录`（需要 GPU，每段视频只跑一次）。
   - `PYTHONPATH=. python ../research/audio/eval_hitnet_fusion.py evaluate --cache 缓存目录`（CPU，几秒）。
5. 判定：只有当每个开关打开的留出场馆都比仅视觉更好，且场馆数 ≥ 3 时，脚本才给推荐参数。
   这时再在 worker 上设 `SHUTTL_AUDIO_FUSION=1`。否则保持关闭。

## 复现本报告

```bash
pip install gdown numpy scipy            # 另需 ffmpeg / ffprobe
export AUDIO_STUDY_DATA=~/shuttl-audio-data
python prepare_data.py                   # 下载公开数据，提取 32 kHz WAV 和逐帧 PTS
python explore2.py; python eval_audio_only.py; python diag_evidence.py
python eval_lag_robustness.py; python eval_fusion_proxy.py; MIN_ANCHORS=20 python eval_fusion_proxy.py
```

`explore.py` 是最初的频带探索，保留作记录；`common.py` / `data.py` 是共用的加载和匹配代码（一对一贪心匹配，与 `research/hits/score.py` 相同）。
线上 numpy 1.26 与研究时 numpy 2.5 算出的曲线最大差 0.00016，起音数量完全相同。
