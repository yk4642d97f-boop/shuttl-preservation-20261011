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
   - 转播视频：按 +7 帧修正标注后，4 场大样本（168–538 次击球）的击球声和其他时刻几乎没有区分度（Cohen d −0.12–0.13）；
     4 场小样本（29–72 次）为 0.44–1.15。
   - 视觉锚点太粗时（代理模型自身锚点），三个场馆全部关闭，没有一处变差。
   - 云端用真实 HitNet v2 跑的两批数据（kwyoke、FineBadminton）开关也全部关闭，没有一处变差（第 6 节）。
4. 云端 HitNet v2 实测（2026-10-20，第 6 节）：
   - 模型本身没有问题：验证场 041 上 F1@±2 0.967，与模型卡一致。
   - 它离不开球场标定：去掉球员脚点的场地坐标后 F1 降到 0.309。kwyoke 18 段机位不标准，自动标定全部失败，
     HitNet 只有 0.05–0.21，规则 0.66–0.74。已修复：没有标定时流水线直接用规则（`calibration_required`）。
   - 锚点门槛从 0.9 改为 0.8：041 上正确检出的峰值中位数只有 0.844，≥0.9 的只占 16%；≥0.8 时占 76%，锚点约 99.7% 是真击球。
   - 标定成功也不保证比规则好：FineBadminton 4 场转播单打（标定全部成功）上，HitNet 0.405（召回 0.302）低于规则 0.535。
     原因还没有拆分。线上默认用 HitNet 还是规则，应当用你自己的标准机位录像对比后再定（`eval_hitnet_fusion.py` 会同时给出规则基线）。
   - HitNet + 声音的真实增益还没有测到：kwyoke 标定失败；FineBadminton 虽然标定成功，但每场只有 4–14 个锚点，而且转播声音大多没用。
5. 局限，上线前必须补：
   - 需要标准机位、标定成功、有现场声音的手机录像（你自己录），在云端跑 `eval_hitnet_fusion.py`。
   - 代理实验里真正开启的场馆只有 1 个（yewtee 只有 22 次击球，被"至少 30 个锚点"挡住）。
   - 融合参数是固定默认值，没有在开启的场馆上调参；18 组参数敏感性检验的 F1@±2 在 0.524–0.589，全部高于 0.471。

## 方法

| 环节 | 做法 |
|---|---|
| 音轨 | ffmpeg 解码成 32 kHz 单声道，30 s 分块流式处理，整场比赛不会占满内存；无音轨或无 ffmpeg 时返回 None |
| 起音特征 | STFT 512 点 / 步长 64（2 ms），只取 6–16 kHz 对数谱通量（人声、脚步、球鞋摩擦大多在低频） |
| 归一化 | 0.1 s 分块的中位数/MAD，在 1.5 s 滑动范围内求稳健 z 分数，适应不同场馆的底噪 |
| 音画偏差 | 手机录像的音轨和画面有固定偏差（三个场馆按标注拟合为 +65 / +99 / +132 ms）。用 HitNet 高置信击球（p≥0.8，依据见第 6 节）当锚点，在 ±250 ms 内做核密度评分（σ 12 ms、1 ms 网格），起音按强度加权 min(z,20)/20 |
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
| [FineBadminton-20K](https://huggingface.co/datasets/iLearn-Lab/Finebadminton-20K) | 8 场有声转播单打，1,614 次标注击球。`start_frame` 是挥拍开始，接触约晚 7 帧（第 6 节实测），加载时已修正 | 对照：转播音轨是否可用；HitNet 在标定成功的视频上的表现 | Apache-2.0 |
| 验证场 041（ShuttleSet，研究提取结果） | 112 个回合、1,200 次击球，含逐帧球、球员框和脚点场地坐标 | HitNet 训练域内对照 | 研究数据，只在云端服务器上评测，不入仓库 |

场馆：china（含 china2）8 段 70 次（单打+双打）；clementi 7 段 122 次（双打）；yewtee 3 段 22 次（单打）。

## 结果

### 1. 频谱分离（`explore2.py` → `results_spectral.txt`）

击球时刻 ±200 ms 内的最大 6–16 kHz 通量与其他时刻的 Cohen d：业余 china 1.10、clementi 0.88、yewtee 0.91。
转播 8 场按 +7 帧修正标注后：大样本 0013 / 0018 / 0025 / 0045（168–538 次）为 −0.05 / 0.13 / 0.12 / −0.12，
小样本 0015 / 0044 / 0046 / 0047（29–72 次）为 1.15 / 0.45 / 0.50 / 0.44。
修正前的旧结论"转播 −1.08–0.12"用错了标注时刻，已作废。转播音轨经过混音、压缩和解说覆盖，大多数场次不可用，
少数场次有中等区分度；是否使用由每段录像的开关自己判断。手机现场录音可用。

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
- 用代理模型自己的粗锚点（门槛 0.8）：clementi 幅度 0.072、yewtee 0.065，全部关闭，合计 0.419 不变。

### 6. 云端 HitNet v2 实测（2026-10-20，AutoDL RTX 6000D）

权重 `hitnet_single_v2.pt`，SHA256 `c515a40b…`，与导出记录和模型卡一致；torch 2.8.0+cu128。
服务器上部署的 main（`hitnet.py`、`pipeline_v2.py` 与 main 相同）和本分支在相同输入上给出完全相同的 HitNet 击球，排除了重构引入问题的可能。

**训练域内**（`eval_hitnet_041.py` → `results_hitnet_v2_041.txt`）：验证场 041，研究提取的输入，按回合推理。

| 输入 | P | R | F1@±2 |
|---|---:|---:|---:|
| 完整 | 0.971 | 0.963 | 0.967 |
| 去掉球员脚点的场地坐标 | 0.302 | 0.315 | 0.309 |

正确检出处的峰值概率：P10 0.76、中位数 0.844、P90 0.912、最大 0.966。
达到 0.8 的占正确检出的 76.3%、误检的 8.6%；达到 0.9 的只占正确检出的 16.0%。因此锚点门槛改为 0.8。

**业余片段，标定失败**（`eval_hitnet_fusion.py evaluate --concat-by-venue` → `results_hitnet_v2_kwyoke_venue.json`，逐段见 `results_hitnet_v2_kwyoke_clips.json`）

| 场馆 | 模式 | 击球数 | 规则 | HitNet v2 | HitNet v2 + 声音 |
|---|---|---:|---:|---:|---|
| china | 双打 | 37 | 0.676 | 0.088 | 不变（2 个锚点，关闭） |
| clementi | 双打 | 122 | 0.675 | 0.209 | 不变（3 个锚点，关闭） |
| china | 单打 | 33 | 0.657 | 0.097 | 不变（0 个锚点，关闭） |
| yewtee | 单打 | 22 | 0.744 | 0.049 | 不变（0 个锚点，关闭） |

- 机位：china 低机位侧面近景；clementi 地面机位，近端球员占大半画面；china2 低机位侧面；yewtee 大部分画面是天花板。
  18 段的自动标定全部失败，HitNet 没有脚点输入，表现和 041 去掉脚点的消融一致。
- 服务器上部署的 main 原版在这 7 段单打上同样是 F1 0.078（P 0.083，R 0.073），所以这是线上已有的问题，不是本分支引入的。
- 每种模式只有 2 个场馆，留一场馆的推荐参数不成立，脚本不给推荐。

**转播单打，标定成功**（`eval_hitnet_broadcast.py` → `results_hitnet_v2_fineb.json`；偏移和重算：`eval_hitnet_broadcast_offsets.py` → `results_hitnet_v2_fineb_offsets.txt`）

FineBadminton 0044–0047，25 fps，1280×720，334 次击球。自动标定全部成功（置信度 0.69–0.93），脚点覆盖率 100%。

- 标注偏移：规则检测和 HitNet 相对 `start_frame` 的偏移中位数都是 +7 帧（IQR 5–9，n = 313 / 165）。
  所以 `start_frame` 是挥拍开始，不是接触帧，`data.py` 已按 +7 帧修正。
- 按 +7 帧重算，4 场合计（±2 帧）：

| 方法 | P | R | F1@±2 |
|---|---:|---:|---:|
| 规则 | 0.528 | 0.542 | 0.535 |
| HitNet v2 | 0.612 | 0.302 | 0.405 |
| HitNet v2，去掉脚点 | 0.314 | 0.222 | 0.260 |
| HitNet v2 + 声音 | 0.612 | 0.302 | 0.405 |

声音开关在 4 场都关闭：门槛 0.8 下每场只有 4–14 个锚点（要求至少 30 个），没有改动任何一次击球。

- HitNet 在这里精度高、召回低，峰值概率最大只有 0.831–0.86（041 上最大 0.966）。
  特征计算是逐帧的局部运算（没有按整段统计的归一化，速度按 fps 统一到 1/30 s），整段推理和按回合推理的输入基本一致，
  所以差距更可能来自上游追踪输入或数据域（赛事、25 fps、转播机位），还没有拆分。
  下一步可以在 041 原视频的几个回合上跑生产流程，逐列对比原始特征。
- 有标定时 HitNet 在这 4 场上仍低于规则，所以 `CLOUD_INFERENCE.md` 里"连续整段视频待验证"的说明保持不变。

## 下一步：用你自己的录像验证

1. 权重已经在云端服务器上，SHA256 已核对，不需要恢复密钥：
   `/root/autodl-tmp/shuttl-5090-20261008/shuttl-runtime/research/cloud_upgrade/artifacts/hitnet_single_v2.pt`。
2. 录像：3–5 个场馆，单打和双打都要。
   - 机位按使用说明：手机横屏，架在底线后方 1–3 米、高 1.5–2 米，固定不动。这是 HitNet 能用的前提。
   - 录整场，不要剪片段，这样锚点会有几百个。
   - 关闭降噪、美声等音频处理。
3. 先跑一遍流水线，确认结果里有 `diagnostics.calibration`（标定成功）。
   没有的话，在 App 里手点四个角点（请求里的 `calibration.corners`），否则这段录像只会用规则检测。
4. 标注：每段视频一个 CSV，列 `frame`（从 0 开始的解码帧号）。
   - 可选列 `type`，发球写 `发球`，可以单独统计发球召回。
   - 清单 CSV 列为 `video,labels,venue,mode`。
5. 在 `source/shuttl/backend` 下运行：
   - `PYTHONPATH=. python ../research/audio/eval_hitnet_fusion.py collect --manifest 清单.csv --device cuda --cache 缓存目录`（需要 GPU，每段视频只跑一次）。
   - `PYTHONPATH=. python ../research/audio/eval_hitnet_fusion.py evaluate --cache 缓存目录`（CPU，几秒）。
6. 判定：只有当每个开关打开的留出场馆都比仅视觉更好，且场馆数 ≥ 3 时，脚本才给推荐参数。
   这时再在 worker 上设 `SHUTTL_AUDIO_FUSION=1`。否则保持关闭。

## 复现本报告

```bash
pip install gdown numpy scipy            # 另需 ffmpeg / ffprobe
export AUDIO_STUDY_DATA=~/shuttl-audio-data
python prepare_data.py                   # 下载公开数据，提取 32 kHz WAV 和逐帧 PTS
python explore2.py; python eval_audio_only.py; python diag_evidence.py
python eval_lag_robustness.py; python eval_fusion_proxy.py; MIN_ANCHORS=20 python eval_fusion_proxy.py

# 第 6 节（云端 GPU，在 source/shuttl/backend 下，设置 SHUTTL_WEIGHTS_DIR / SHUTTL_HITNET_WEIGHTS）
PYTHONPATH=. python ../research/audio/eval_hitnet_041.py <研究提取的 041.npz>
FINEB_DIR=<放 0044–0047 的 mp4 和 json> PYTHONPATH=. python ../research/audio/eval_hitnet_broadcast.py 0044 0045 0046 0047
python ../research/audio/eval_hitnet_broadcast_offsets.py results_hitnet_v2_fineb.json
PYTHONPATH=. python ../research/audio/eval_hitnet_fusion.py evaluate --cache <缓存目录> --concat-by-venue
```

`explore.py` 是最初的频带探索，保留作记录；`common.py` / `data.py` 是共用的加载和匹配代码（一对一贪心匹配，与 `research/hits/score.py` 相同）。
线上 numpy 1.26 与研究时 numpy 2.5 算出的曲线最大差 0.00016，起音数量完全相同。
