# 云推理与 BST 训练准备（2026-10-07）

> **2026-10-08 最新：**已换至5090 32GB并完成环境、真实模型CUDA、GPU断点恢复验收。
> BST首轮2000步完成，候选86.59%低于原十模型87.30%，保留原模型；全姿态验证与视觉模型训练正在执行。
> 5090使用PyTorch2.8/CUDA12.8/ORT-GPU1.23.2及显式float32姿态配置，不运行下文旧cu124安装配方。
> 用户负责续费并明确不关机。本次事实与证据以`cloud_runs/autodl_5090_20261008/README.md`为准；下文旧实例/等待GPU文字为历史记录。


当前完成的是可搬到云主机的计算代码、模型和本地检查。用户尚未租卡；CUDA、网络服务、手机上传联调待实例到位。
已验证的单打结果见 MODEL_CARD.md 和 STROKE_CHAIN_REPORT.md；本页的迁移检查不产生新的准确率结论。

## 后端模型链路

`pipeline_v2` 新增 hitnet_weights、bst_manifest、rtmpose_weights 三项显式配置。
原后端环境需另装 `backend/requirements-cloud-models.txt`（CPU）或 `backend/requirements-cloud-models-cuda.txt`（CUDA）的可选依赖；按文件注释安装。
Celery 对应环境变量为 SHUTTL_HITNET_WEIGHTS、SHUTTL_BST_MANIFEST、SHUTTL_RTMPOSE_WEIGHTS。
实验开关（2026-10-20，默认关闭，验证前不要在演示服务上打开）：
- SHUTTL_AUDIO_FUSION=1：手机录像的击球声辅助 HitNet，每段录像单独判断是否启用，见 research/audio/REPORT.md。镜像已加入 ffmpeg。
- SHUTTL_HITNET_DOUBLES=1：双打时用单打 HitNet 跑 4 种搭档配对；可选 SHUTTL_DOUBLES_GAP_S，默认 0.25 s。见 research/doubles/REPORT.md。
未设置时保持原后端规则路径。设置后按以下路径运行：

TrackNetV3/WASB → 链接轨迹 → 球场/球员 → 新 HitNet → 3D/回合 → RTMPose-m → BST 十模型平均 logits。

- HitNet far-first，缺失框和脚点独立处理，时间戳缺口切断上下文；事件使用真实 PTS。
- BST 使用已冻结的无帧偏移窗口和原始追踪框归一化。RTMPose 的扩大框只用于裁剪，不能代替归一化框。
- 两人模型遇到四人输入拒绝；pipeline 在 diagnostics 中记录规则回退，不伪装成双打学习模型。
- 缺少校准、RTMPose、可靠姿态或模型输出时，保留原规则结果并记录原因。
- HitNet 需要球场标定：没有相机（自动标定失败且没有手点角点）时直接用规则检测击球，
  `hit_model.fallback_reason = "calibration_required"`。HitNet 的 51 维输入里有球员脚点的场地坐标，
  只能由标定得到；验证场 041 去掉脚点后 F1@±2 从 0.967 降到 0.309（2026-10-20，云端 RTX 6000D 实测），
  kwyoke 业余低机位片段（标定全部失败）上 HitNet 0.05–0.21，规则 0.66–0.74。
- 整段视频实测仍有差距：FineBadminton 0044–0047 转播单打（标定全部成功，标注按 +7 帧修正）上，
  生产流水线的 HitNet F1@±2 0.405（P 0.612，R 0.302），规则 0.535。原因未拆分，详见 `research/audio/REPORT.md` 第 6 节。
  上线默认用哪个检测器，应当先用标准机位的手机录像对比。
- BST 的击球侧与已有几何结果不一致时，在诊断中保留该预测，避免事后改侧让已经拟合的轨迹自相矛盾。
- short_serve/long_serve/cross_net 保留细分类；旧接口分别映射为 serve/serve/net。

## 已执行的本地验证

- HitNet：033/041 两场、184 回合、87,800 帧；原始特征、51 维特征、logits、击球事件均一致，logit 最大误差 0。
- BST：041 的 56,416 帧特征一致；17 个有效片段的十模型 logits 和类别一致，最大误差 0。
- RTMPose：041 真实视频 4 帧、8 个姿态；原始逐人推理与生产批推理一致，最大误差 0。
- 后端 HitNet/BST/流水线/持久化/序列化测试 42 项通过；本地上传与任务权限测试 24 项通过。
- 完整模型加载、参考张量和两种轨迹模型前向、YOLO 人体检测/NMS 的 CPU preflight 已通过。
- 已跑 041 的两个完整回合，使用给定场地角点。第 69 回合 5 个击球全部在 ±2 帧内匹配，BST 接受 3 个分类，另 2 个因姿态覆盖不足保留规则。
- 第 10 回合失败：标注击球在相对第 60 帧，云端预测第 18 帧，训练参考输入预测第 52 帧；BST 返回未知。不能把这个错误简单归因于迁移接口，也不能用成功回合掩盖它。原始结果、输入分组替换分析分别见 `cloud/runtime_integration*.json` 和 `cloud_feature_shift.json`。
- 这只是两个样例的集成检查，非整场性能评测。运行成功与预测正确分别记录；BST 全部弃权时新诊断明确标记实际采用 rules。

## 两份可搬迁包

1. `dist/shuttl-cloud-training-v1.tar.gz`：已有的视觉模型训练包，带轨迹公开数据，约 1.87 GB。它是之前的冻结快照。
2. `dist/shuttl-cloud-runtime-v3.tar.gz`：本次计算运行包，带最新推理适配、模型、参考张量、BST 训练/验证特征及脚本。
   这是命令行计算包，**不是已部署 API 服务或已完成手机云端切换**。不包含 .env、账号密钥、私人视频和虚拟环境。

每包有 SHA256 和逐文件清单；不覆盖旧包。旧包不含本轮新代码，不能用旧包的检查结果替代新包检查。

实例到位后的命令（当前不执行）：

```bash
tar -xzf shuttl-cloud-runtime-v3.tar.gz
cd shuttl-runtime
bash research/cloud_upgrade/cloud/setup_inference.sh cuda
.venv-inference/bin/python research/cloud_upgrade/cloud/run_inference.py preflight --device cuda --report cuda-preflight.json
.venv-inference/bin/python research/cloud_upgrade/cloud/run_inference.py analyze --video /data/example.mp4 --output /data/result.json --device cuda
```

推理使用独立 `.venv-inference`（torch 2.4.1 / CUDA 12.4），视觉训练的 `.venv-cloud` 使用 torch 2.6；避免旧 YOLO
加载逻辑与 torch 2.6 的 weights_only 默认值发生兼容问题。CPU 核对用本机已有环境，Linux 新环境安装和 CUDA 算子尚待验证。
RTMPose 明确要求 CUDA provider 可用，不能因 CUDA 安装失败静默变成 CPU 推理。

## BST 实验入口

已准备固定窗口数据：001–006 共 6,522 个训练片段，041 共 1,126 个验证片段；帧缺失、未知/冲突标签有排除计数。
007 的提取记录存在重复全局帧号，先隔离并在 manifest 记录原因。没有读取测试样本来选新参数。
这些预训练权重的历史训练来源与本轮新划分分开记录；不宣称新盲测。

```bash
.venv-inference/bin/python research/cloud_upgrade/cloud/run_bst.py train \
  --data research/cloud_upgrade/data/bst_fixed30/manifest.json \
  --init research/cloud_upgrade/artifacts/bst_seq30/bst_CG_AP_JnB_bone_merged.pt \
  --out /data/bst-first --device cuda --steps 2000 --batch 32 --hours 2
```

恢复时相同参数加 `--resume`。训练从**一个**已发布权重初始化，不平均参数；十模型基线平均的是 logits。
只用验证集 macro-F1 选 checkpoint，保留训练前基线；原子保存模型/优化器/RNG/累计用时，进程锁防止同一输出并发训练。
`freeze --out /data/bst-first` 固定最佳权重哈希后禁止继续训练。6 步中断恢复 smoke 的参数与验证记录逐项一致。
正式训练和新 BST 效果比较尚未执行。新候选需要再跑定位+球种联合评测，不能用片段分类准确率代替。
训练预算只停止进程，不会关闭租赁计费；严重 kill/crash 后可能损失最近 25 步及相应未记录耗时，需核对账单和日志再恢复。

## 演示服务接入前仍需处理

- 持久任务、幂等提交、会话锁、尝试 token、数据库轮询和后端取消已完成；真实 PostgreSQL/Redis 及 worker 强制中断恢复已测，见 DURABLE_JOBS.md。
  当前源代码比 runtime-v3 计算包新，不能用该包直接部署完整 API。
- 单卡 worker 使用 concurrency=1；数据库/Redis 不直接暴露公网，API 通过有效 TLS。
- 手机已改为固定后台 URLSession 的 uploadTask(fromFile:)，补齐持久回执、系统任务重接、签名刷新和退出登录取消。
  46项检查及独立模拟器SIGKILL后重开传输验证通过，见 BACKGROUND_UPLOAD.md；服务端分块续传和真机测试仍待完成。
- 本地录像已禁止覆盖；OSS 固定版本并使用条件下载，但真实 bucket 联调尚未做。手机端远端取消、账号删除、录像与结果的保留策略仍需联调。
- 云端关闭时可查看已有结果；新分析需开机。训练后的权重、配置、验证记录和演示部署版本要离开租赁盘备份。

以上是明确的剩余工作，不是已完成部署的承诺。真实双打数据规范见 DOUBLE_DATA_PROTOCOL.md。
