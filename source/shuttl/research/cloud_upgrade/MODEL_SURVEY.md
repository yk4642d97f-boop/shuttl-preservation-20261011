# Shuttl 开源模型与数据调查

检索日期：2026-10-07。范围包括 GitHub 主题搜索、arXiv 羽毛球/羽毛球跟踪论文、
Hugging Face 数据和模型索引、Zenodo 及作者仓库。实际响应与论文文本保存在 `sources/`。
这是可追溯的候选筛选，不是对整个互联网绝无遗漏的保证；论文自报数字不等于本项目实测。

## 模型选择

| 任务 / 候选 | 已核实的公开情况 | 本项目决策 |
|---|---|---|
| [TrackNetV3](https://github.com/qaz812345/TrackNetV3) | 本地已有权重、训练实现和真实数据；当前手机主模型 | 保留基线，先做低成本有对照微调 |
| [WASB](https://github.com/nttcom/WASB-SBDT) | 已有 HRNet 权重和训练实现；原项目一次微调只有 1 轮且验证稍降 | 与 TrackNetV3 分别训练评测，不因为“训过”就替换 |
| [TrackNetV4](https://github.com/TrackNetV4/TrackNetV4) | 官方 TensorFlow 仓库、MIT；当前 `docs/RESULT.md` 权重链接仍为 `#` | 公开代码可研究，尚不能当作可直接加载的升级权重 |
| [gino6178/TrackNetV5](https://github.com/gino6178/TrackNetV5) | 第三方复现代码及 Lite/full 权重；未发现许可证 | 暂不打包产品；独立评测与授权明确后再考虑 |
| [thaonan/TrackNetV5-SDK](https://github.com/thaonan/TrackNetV5-SDK) | README 明确权重、数据私有 | 不列为可自由训练部署的开源替换方案 |
| [TrajectoryNetPP](https://github.com/Yinshuisiyuan23670/TrajectoryNetPP) | README 仍大量沿用 TrackNetV3 命令/权重名称，未验证到独立可用新权重和许可证 | 先核验成熟度，暂不占第一轮租卡预算 |
| 本项目 HitNet TCN | 自有可训练代码和旧权重；已完成扩充比赛与首拍采样训练 | 新候选测试 F1 94.55%，详见模型卡；还需完整录像验收 |
| [SwingNet 击球检测](https://github.com/wish44165/A-New-Perspective-for-Shuttlecock-Hitting-Event-Detection) | 光流 + MobileNetV2/BiLSTM；README 有 Zenodo 权重链接 | RGB/光流补充路线；旧比赛名次不是领先当前 HitNet 的证据 |
| [BST](https://github.com/Va6lue/BST-Badminton-Stroke-type-Transformer) | MIT，正式模型权重已在本地 | 保留 seq30 固定窗和 logits 集成；先提升姿态特征与领域适配 |
| [TemPose-TF-ASF](https://arxiv.org/abs/2605.02558) | 2026 相邻球种语义融合论文；未找到作者独立发布的对应训练代码/权重 | 借鉴回合上下文，不能宣传成已接入的开源模型 |
| [DSTA](https://arxiv.org/abs/2605.23355) | 2026 参数高效时序定位；论文与部分数据可访问；未核实对应模型权重 | 后续候选，不在首轮从零复现大模型 |
| [RTMPose](https://github.com/open-mmlab/mmpose/tree/main/projects/rtmpose)、[ViTPose/ViTPose++](https://github.com/ViTAE-Transformer/ViTPose) | 已加载RTMPose-m、RTMPose-X、ViTPose++ base并完成同输入对照 | 44个验证片段分别39/44、38/44、39/44；暂保留m。全验证1,154事件已冻结，待GPU运行；不是双打/整场指标 |
| [Sapiens2](https://github.com/facebookresearch/sapiens2) | 官方308点模型与自定义许可已核实；Python≥3.12、torch≥2.7，输入1024×768 | 尚未下载权重或执行；COCO17映射已核验，不能取前17点。先完成已有三路验证，再按收益和成本决定是否实验 |

TrackNetV5 有同名不同项目。gino6178 仓库的公开训练命令将 `test` 作为 `eval_split`，
训练代码又按该 split 的 F1 保存最佳权重，README 还报告在该测试集扫描阈值的结果。
即使测试样本没有参与反向传播，仍存在测试集选模/调阈值影响。不能把其 98% 数字与
本项目 HitNet 的 94% 比较：前者是球位置检测，后者是击球时刻检测，任务不同。

本地 `research/bst/ACCURACY.md` 已说明在相同 3,209 个可分类片段上，RTMPose 特征
准确率约 83.63%，Vision 特征约 51.59%。优先保证姿态与下游训练分布匹配。
不要将独立训练的 10 份 BST 权重直接平均当作 logits 集成；现有 `finetune.py` 有这类初始化，
新实验应从一份明确权重开始或进行真正输出集成，并与原模型对照。

本次姿态对照的像素、框、位置和球特征保持相同，BST十模型固定为mean-logits集成；
较大姿态模型在小面板上未增加正确数，不能仅凭参数更多就替换。证据和限制见`pose_benchmark/REPORT.md`。
旧OpenCV5与当前4.11裁剪插值存在差异，44片段分类虽相同，也不能外推全数据等价。
Sapiens2的自定义许可含生物识别/监控等用途限制，不等同于无限制的Apache开源授权；
本地保存来源与308→COCO17映射，尚无显存、速度或羽毛球精度实测。

## 单打、双打数据的实际可用性

| 数据 | 实际核实结果 | 用法与限制 |
|---|---|---|
| 本地 ShuttleSet 提取 | 41 场可读，32 场训练；具备击球/轨迹/球员输入 | 单打训练与既有测试。缺完整录像负样本 |
| [Finebadminton-20K](https://huggingface.co/datasets/Moujuruo/Finebadminton-20K) | 70 份 JSON 全部下载并校验；2,066 回合、20,757 击球；2,048 回合列两名选手、18 回合名单缺失；未见四人标注 | 可补单打球种和语义，不能算双打训练数据。70 个视频约 43.4 GB 尚未下载。20 个视频与 FineBadmintonBenchmark 重叠，必须按源比赛去重 |
| [BFMD 完整数据](https://huggingface.co/datasets/OpenSportsLab/BFMD) | 论文含单/双打；HF `gated: manual`，匿名无法读取完整数据 | 候选双打来源，需要账号申请访问；本轮未自动申请或联系作者 |
| [bfmd-captions](https://huggingface.co/datasets/OpenSportsLab/bfmd-captions) | 下载并解析两个 parquet；11,301 片段，实际为 12 场两人比赛 | 可做单打动作/描述研究；不含可验证的双打四人标注。文件头注明 `non-commercial, no redistribution`，不能当作可自由商用数据 |
| [DSTA Fine-Badminton](https://zenodo.org/records/20292976) | 实际公开 10 场单打、约 10.72 小时、9,817 动作；ZIP 6.46 GB | 名字相似但与上面的 20K 不是同一数据。元数据 CC-BY4、视频说明非商业学术用途，需分别核实 |
| [Drone_BD_ControlArea](https://github.com/Ning-D/Drone_BD_ControlArea) | 双打四人框；俯视角有标注，背视角未标；球位置仅击球/落点事件，非逐帧轨迹 | 可研究双打 ID/跑位，和手机底线机位差异明显；许可尚未明确，不直接打包训练 |
| [DoublesEval](https://github.com/Chengjt1999/DoublesEval) | Apache2 README，但代码标注为将来发布；约 60 回合、9.6K 推理实例 | 战术问答基准，不是现成的四人追踪/击球定位训练集 |

下载和解析证据：`data/finebadminton_downloads.json`、`data/finebadminton_inventory.json`、
`data/bfmd_inventory.json`；可运行 `audit_public_data.py` 重建统计。

## 双打必须补的工作

[2025 单打迁移双打研究](https://arxiv.org/abs/2508.13507) 使用 ViTPose、STGCN 特征、
Transformer 和身份重分配，在两场人工标注双打中报告总体 F1 0.7104。
未验证到可直接复用的公开代码/权重；这说明双打有独立难点，不能宣称“把单打模型放大即可解决”。

1. 固定四位选手 ID、队伍和换边关系；遮挡/前后交叉时不能只按左右位置换 ID。
2. 每次击球同时判断时刻、半场和具体选手；快速平抽挡单独评测，不能直接沿用单打 0.30 秒去重。
3. 先申请完整 BFMD 或获取有使用权的双打手机录像，逐场确认连续视频、FPS、击球帧、四人 ID、球种。
4. 按场馆/源比赛划分训练、验证、盲测，避免同一回合剪出的片段跨集合；人工标注未知项保留 unknown。
5. 分别报告击球 F1、具体击球人准确率、ID 切换数、球种 macro-F1、整场误报/分钟、每视频分钟计算成本。

第一轮双打验收应包含至少两个未训练的机位/场馆和男双、女双或混双中的目标类型。
具体需要多少标注由学习曲线决定；不能保证两次小额租卡就达到所有场景的领先水平。
