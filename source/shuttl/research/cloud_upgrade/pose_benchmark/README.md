# 姿态候选的下游球种对照

此目录是研究评测，不修改手机/后端默认模型。只使用已有验证比赛 041，不访问 039/040/042–044 的测试样本。
新候选是否有益以冻结 BST 球种分类结果判断。没有人工姿态标注，因此不报告姿态 AP；
使用标注击球时刻，因此这里也不是完整 HitNet→BST 联合 F1、完整录像误报率或双打精度。

## 冻结协议

- `panels/small.json`：按 SHA256(`pose-panel-v1|id`) 在每个已知类别取最多 2 个片段。
  共 44 片段、22 个有样本类别，每类 2 个；两种远近端长发球类别无支持。选择早于模型推理。
- `panels/full.json`：全 041 的 1,154 个已知标签事件。未知/同帧冲突标签不用于分类分母，数量保存在清单。
  此处不会像训练准备那样先剔除缺姿态样本；缺框/缺姿态、模型未知都计为未正确分类。
- 固定击球帧 ± round(fps)//2，沿用原始提取中可用帧与 seq30 截断/补零；不根据预测移动窗口。
- 相同原始图像、球员框、框外 10% 裁剪余量、far-first 槽位。归一化始终使用原始未扩张框。
  `pos`、`shuttle` 使用原有冻结参考特征（含原来的有效性掩码）；只改变人体关键点和相应可用性。
- BST 使用原有十模型的 **mean logits**。不平均权重，不重新训练、不调分类阈值。
- 主要指标：有支持类别的 macro recall，弃权算错；同时报告 exact/type/side accuracy、逐类支持与弃权原因。
  小样本是类别均衡的接入实验，不代表自然球种频率；1154 全验证仍不能作为新的盲测。
- 视频、提取、原有姿态、原 CSV、标签映射、BST 权重均 SHA256 冻结。
  每个模型还记录实际解码像素摘要、代码、环境、模型 SHA256 和全部片段预测；比较前验证一致。

## 候选与输入约定

| 模型 | 输入/坐标约定 | 选择理由 |
|---|---|---|
| 现有 RTMPose-m body7 | 256×192，沿用项目已验证的 BGR；COCO17 | 产品现有基线 |
| RTMPose-X body7 | 384×288，RGB；COCO17、SimCC×2 | Apache2，较高容量/分辨率候选 |
| ViTPose++ base | 256×192，RGB；原生 HF 处理器 XYWH，COCO expert 0 | Apache2，Transformer/MoE 候选 |

RTMPose-X 的 SDK `pipeline.json` 和 `detail.json` 中部分尺寸错误地写成 192×256；
实际 ONNX 输入是 `[batch,3,384,288]`，输出轴为 576/768，codec 也为 288×384。
训练配置 `bgr_to_rgb=True` 和 SDK `to_rgb=true` 一致，图的第一层直接卷积，没有内置换色。
因此 X 使用 RGB；基线保留 BGR。比较的是各候选预处理+权重整体替换，不是严格控制预处理后的纯架构消融。
与 rtmlib 的对照给 X 显式传 RGB，不假定 rtmlib 自行换色。

ViTPose++ 固定 Hugging Face revision `92be54d7a29e42fad47b6e2ca01dd9e685a61e0d`，
本地 safetensors、`local_files_only=True`，不执行模型仓库的远程代码。三个模型均不做翻转集成。
`test_contracts.py` 比较单框参考与批量结果、四框顺序、非法框、缺槽位和分母。
四框检查用同一双人画面的四个不同裁剪，只能证明接口没有折叠/串位，不能算双打验收。

## Sapiens2 调查（未纳入本次运行）

[官方仓库](https://github.com/facebookresearch/sapiens2) 2026-04-24 发布，0.4B/0.8B/1B/5B 姿态系列，308 点。
0.4B 模型卡给出 1024×768、1.260T backbone FLOPs；HF 元数据显示全模型 425,677,380 参数、未门控。
官方 `pyproject.toml` 要求 Python≥3.12、torch≥2.7，与现有 torch2.4.1 栈不同。
未实测显存/速度，不从参数量猜租卡配置。

它使用自定义 Sapiens2 License（有 biometric processing、surveillance 等限制），官方包分类为
`Other/Proprietary License`，不能与 Apache2 候选一并称为不受限开源。
本次仅保存文档、许可、模型元数据和关键点配置；未下载权重、安装其运行库或接入产品。

`sapiens2_coco17_mapping.json` 用 AST 读取配置，不执行下载的代码：COCO17 所需索引为
`[0,1,2,3,4,5,6,7,8,62,41,9,10,11,12,13,14]`，**不能直接取前17点**。
去除的36个牙齿点位于这些点之后，不改变这些索引。映射是模式核验，尚无实际推理证明。
来源、日期与响应 SHA256 在 `sources/retrieval*.json`。

## 本机复现

当前 `.venv` 是独立 research overlay，通过 `.pth` 只读复用 backend 依赖；已将错误自动安装的 NumPy2
改为 NumPy1.26.4。backend 环境未改。实际版本见 `environment.json`。
在工程根目录运行：

```sh
research/cloud_upgrade/pose_benchmark/.venv/bin/python -m pytest research/cloud_upgrade/pose_benchmark/test_contracts.py -q
research/cloud_upgrade/pose_benchmark/.venv/bin/python research/cloud_upgrade/pose_benchmark/download_models.py
research/cloud_upgrade/pose_benchmark/.venv/bin/python research/cloud_upgrade/pose_benchmark/run.py --model rtmpose_m --panel small --device cpu
research/cloud_upgrade/pose_benchmark/.venv/bin/python research/cloud_upgrade/pose_benchmark/run.py --model rtmpose_x --panel small --device cpu
research/cloud_upgrade/pose_benchmark/.venv/bin/python research/cloud_upgrade/pose_benchmark/run.py --model vitpose_plus_base --panel small --device cpu
research/cloud_upgrade/pose_benchmark/.venv/bin/python research/cloud_upgrade/pose_benchmark/compare.py --panel small --device cpu
```

已有面板、结果目录和比较报告拒绝覆盖。重跑须明确保留旧证据后另选版本/目录；不要删除旧输出只保留较好的一次。
首次接口检查因 ViTPose 配置的 `L_Wrist` 与统一命名 `left_wrist` 比较失败，修复显式命名转换后 11 项全过；
初次 `checks.log/xml` 和最终 `checks_verified.log/xml` 都保留。不是模型效果调整。

## 拿到 GPU 后

`package.py` 生成独立 `dist/shuttl-pose-eval-v1.tar.gz`。包含验证041视频/输入、三个姿态模型、十个BST权重、
所需本地源码/许可和全文件 SHA256；仅用于当前工程的私有迁移评测，不发布数据或自动上传。
它与冻结的 runtime-v3 计算包分开，也不是后端 API/数据库/手机部署包。

在**已解压评测包根目录**执行以下命令；无需原电脑的 home 模型缓存：

```sh
bash research/cloud_upgrade/pose_benchmark/setup_cloud.sh cuda
.venv-pose/bin/python research/cloud_upgrade/pose_benchmark/cloud_eval.py run --model rtmpose_m --panel full --device cuda
.venv-pose/bin/python research/cloud_upgrade/pose_benchmark/cloud_eval.py run --model rtmpose_x --panel full --device cuda
.venv-pose/bin/python research/cloud_upgrade/pose_benchmark/cloud_eval.py run --model vitpose_plus_base --panel full --device cuda
.venv-pose/bin/python research/cloud_upgrade/pose_benchmark/cloud_eval.py compare --panel full --device cuda
```

先 preflight 再小面板 CPU/CUDA 一致性、显存/吞吐，最后全验证。CUDA preflight 不可用则报错，不能当成CPU成功。
安装脚本固定 torch2.4.1/cu124、ORT-GPU1.20.1；新Linux环境安装及真实CUDA尚未验收。
CPU耗时只能报告为当前Mac上的CPU耗时，不能换算云显卡速度或最终费用。
结果如有提升，下一阶段才是用对应姿态准备训练特征、训练BST并做按源比赛隔离的验收。
真实双打仍需四人ID/击球人配对标注和独立测试。
