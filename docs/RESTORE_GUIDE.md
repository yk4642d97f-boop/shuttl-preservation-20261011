# Shuttl 完整恢复与继续开发指南

编写日期：2026-10-11，北京时间。

本指南依据本机源码、依赖清单和历史记录编写。下载、解密和归档验证使用仓库 README 中的 `tools/recover_from_github.py`；交付是否全部完成以 Release 的 `github-verification.json` 为准。后文标注“历史报告”的成功记录来自原文件，本次另做的验证见 `docs/VALIDATION.md`，二者不可混淆。

## 1. 接手时先读什么

主要开发工程原路径是 `/Users/yangcong/Downloads/华北五省`。名称与项目用途不同，但这就是 Shuttl 的完整开发目录；不要仅恢复参赛提交材料中的精简源码或某个旧的云端计算包。

| 内容 | 原路径或工程内路径 | 用途 |
|---|---|---|
| 当前 iOS 工程 | `iOS/` | App 源码、Swift packages、CoreML 模型、资源、单元/UI 测试 |
| 当前本机后端 | `backend/` | FastAPI、Celery、持久任务、数据库、存储、推理链路 |
| 训练及研究 | `research/`、`backend/ml/` | 数据、标签、划分、权重、检查点、实验、导出与评测 |
| 两版宣传片 | `promo/`、`promo2/` | 源码、素材、网页动画、音乐、渲染产物 |
| 参赛材料 | `Shuttl-参赛提交材料/`；`/Users/yangcong/Downloads/claude/output/huabei2026/` | 交付文档、演示片、源代码副本等；保留，但不默认作为最新版开发工程 |
| 原始设备与云端数据 | `~/Library/Application Support/Shuttl/` | 真机 Documents、SwiftData 数据、云端恢复快照 |
| AutoDL 完整恢复包 | `/Users/yangcong/Downloads/claude/autodl_backup/shuttl-20261008/` | 2026-10-08 的服务器代码、模型、训练数据、三层 Python 环境、CUDA、数据库与运维脚本 |
| 开发历史 | 本次审计的 `context-candidates.json` | Claude/Codex 会话、附件、历史文件版本、产品与设计记忆 |
| 路径与环境审计 | `source-classification.json`、`source-external-paths.json`、`environment-locks/` | 大文件、模型包、符号链接、外部路径、原环境版本 |

建议按以下顺序阅读：

1. 本指南及最终备份清单。
2. `iOS/project.yml`、`backend/pyproject.toml`、`backend/docker-compose.yml`。
3. `research/cloud_upgrade/mobile_cloud_20261008/STATUS.md`、`mobile_sample_20261008/REPORT.md`。
4. AutoDL 恢复包的 `README.md` 和 `关机前检查报告.md`。
5. `research/cloud_upgrade/MODEL_CARD.md`、`STROKE_CHAIN_REPORT.md`、相关训练结果及 `promo2/README.md`。

**文档存在时间层次。** `research/cloud_upgrade/README.md`、`CLOUD_PLAN.md`、`CLOUD_INFERENCE.md`、`RUNTIME_HANDOFF.md` 保留了“未租 GPU”“未部署 API”等较早状态。10 月 8 日真机部署记录已经更新了其中部分结论；同日晚的服务器备份/关机报告又比“实例持续运行”更新。不能取一段旧文档推断 10 月 11 日的远端现状。

## 2. 下载后先验证完整性

仓库 `source/` 提供可浏览源码，`recovery/payload-index.json` 列出 Release `backup-20261011` 的加密资产。归档由 SQLite 清单及最多 512 MiB 的内容数据卷组成，全部用 age 加密；本次不使用 Git LFS。Git 克隆成功不代表 Release 数据已下载。

在新机器开始开发前：

1. 下载最终清单列出的全部归档/分卷及校验文件，保留文件名和目录层级。
2. 对照逐文件 SHA-256、字节数和文件数核验；分卷应先核验再按最终恢复脚本重组。
3. 将归档恢复到一个全新目录，检查解压返回码、断裂符号链接、被跳过的文件及权限。
4. 若有加密包，先确认用户在重置电脑后仍能取得解密凭据；GitHub 登录权不能代替解密凭据。不要把加密包误认为已经解密可用的工程。
5. 保存一份不参与开发的原始备份；实际开发从另一份副本开始。

macOS 原生 SHA-256 检查形式如下；文件名应改成最终交付使用的名称：

```sh
cd '/新机器/备份下载目录'
shasum -a 256 -c SHA256SUMS
```

AutoDL 的 `SHA256SUMS`、`PAYLOAD_SHA256SUMS`、`RESTORE_KIT_SHA256.txt` 是其已有内部校验文件。它们与本次全量备份的最终外层清单是不同层次，应分别校验。

恢复到目标目录后，主工程位于 `目标目录/Downloads/华北五省`，审计位于 `目标目录/Downloads/shuttl-preservation-20261011-audit`，服务器备份位于 `目标目录/Downloads/claude/autodl_backup/shuttl-20261008`。后文用以下变量指代它们：

```sh
export SHUTTL_SOURCE='/新机器/Shuttl完整工程'
export SHUTTL_AUDIT='/新机器/备份中的审计目录'
export SHUTTL_SERVER_BACKUP='/新机器/autodl_backup/shuttl-20261008'
```

这些都是示例路径，需要使用实际解压位置。任何包含空格或中文的路径都保持双引号。

## 3. macOS、Xcode 与 iOS 工程

本次只读检查确证了原电脑的版本：

| 项目 | 原环境/工程记录 |
|---|---|
| 机器架构 | Apple Silicon，`arm64` |
| macOS | 15.7.9，构建号 `24G830` |
| Xcode | 16.2，构建号 `16C5032a` |
| Swift 编译器 | 6.0.3 |
| 工程 Swift language version | `5.10`，见 `iOS/project.yml` |
| XcodeGen | 2.46.0 |
| iOS 最低部署版本 | 17.0 |
| 已发现模拟器运行时 | iOS 18.3 |
| App bundle ID | `com.ycyangcong.shuttl` |
| 原签名团队 | `F878S66X7Q` |

优先在兼容的 Apple Silicon macOS 上安装 Xcode、Command Line Tools、相应模拟器运行时和 XcodeGen。版本升级后需要重新构建验证；本次未证明任意新版 Xcode 或 Intel Mac 都可无改动恢复。

`iOS/project.yml` 是 XcodeGen 工程定义，引用的是工程内的本地 Swift packages。若 `.xcodeproj` 缺失或路径失效，可以重新生成。以下命令根据现有工程定义给出，**本次未运行**：

```sh
cd "$SHUTTL_SOURCE/iOS"
xcodegen generate
xcodebuild -list -project Shuttl.xcodeproj
xcrun simctl list devices available
```

选取新机器确实存在的模拟器 UUID 后，再构建和测试；不要照搬旧电脑 UUID：

```sh
export SHUTTL_SIMULATOR_ID='填写新机器的模拟器UUID'
xcodebuild -project Shuttl.xcodeproj -scheme Shuttl \
  -configuration Debug \
  -destination "platform=iOS Simulator,id=$SHUTTL_SIMULATOR_ID" \
  -derivedDataPath "$SHUTTL_SOURCE/iOS/build/restored-debug" build

xcodebuild -project Shuttl.xcodeproj -scheme Shuttl \
  -configuration Debug \
  -destination "platform=iOS Simulator,id=$SHUTTL_SIMULATOR_ID" \
  -derivedDataPath "$SHUTTL_SOURCE/iOS/build/restored-debug" test
```

历史真机部署报告记载：未签名模拟器测试曾导致后台 URLSession 无法建立会话，正常 ad-hoc 签名后通过。因此不要为了“编译通过”普遍关闭签名，再把后台上传测试的失败当作可忽略问题。部分 Swift package 可独立 `swift test`，但依赖 UIKit/iOS framework 的测试应在 iOS destination 运行，不能假设全部可在 macOS 执行。

### 模型与资源不能只恢复空目录

至少核对以下可复用模型包及其完整内部文件：

- `iOS/Resources/Models/ShuttleTracker.mlpackage`
- `iOS/Packages/ShuttlDetector/Models/TrackNetV3.mlpackage`
- `iOS/Packages/ShuttlDetector/Models/WASB.mlpackage`
- `iOS/Packages/ShuttlPlayers/Models/RTMPoseM.mlpackage`
- `iOS/Packages/ShuttlHitModel/Sources/ShuttlHitModel/Models/HitNetDetector.mlpackage`
- `iOS/Packages/ShuttlStrokeModel/Sources/ShuttlStrokeModel/Models/BSTStroke.mlpackage`
- 图标、字体、`PrivacyInfo.xcprivacy`、`Resources/Legal` 与测试 fixtures。

部分 `project.yml` 模型路径标记为 `optional: true`；因此“构建成功”本身不能证明模型已全部进入应用。需要检查产物中的 CoreML 资源并执行相应模型/数值一致性测试。研究目录的 fp16 候选与已发布 fp32 模型不能任意互换；相关文档记录过明显的数值/分类偏差。

### 真机签名

已导出唯一一份 Apple Development 签名身份（团队 F878S66X7Q）为 `Shuttl-Apple-Development.p12`，并用 OpenSSL 验证 PKCS#12 完整性、私钥包存在及证书 SHA-1 指纹与原身份相同。文件和随机生成的内层密码仅放在加密归档中：恢复后的 `Downloads/shuttl-preservation-20261011-audit/signing-private/`。使用新电脑的“钥匙串访问”导入该 p12，并使用同目录的 `PKCS12-PASSWORD.txt` 完成导入；不要把这些文件上传为明文。Provisioning profile 本身仍不等于私钥。

新电脑需要登录有权使用该团队和 bundle ID 的 Apple 开发者账户，重新配置证书/私钥/描述文件，或导入本次保全的签名材料。另一个开发者若不属于原团队，可能需要自己的团队及新的 bundle ID；新的标识会影响原 App 数据与身份连续性，不能直接当作原 App 无损覆盖安装。

已发现的个人开发描述文件有效至 **2026-10-15 17:07（北京时间）**。到期后旧安装包未必能继续打开；归档旧 `.app` 或描述文件不会延长签名有效期。不要卸载有数据的原手机 App 来解决签名问题，先确保当前数据已备份。

## 4. Python 开发环境：三个用途分别恢复

本机后端/研究环境使用 Python **3.12.14**；宣传片旧虚拟环境使用 Python **3.9.6**；AutoDL 快照为 Linux x86_64 Python **3.12.3**。macOS、Linux、CPU、CUDA 环境不能直接互换。

`environment-locks/` 记录了本机六套环境的已安装版本和 `.pth` 关系。它们是现状清单，并非已经在空环境成功求解/安装过的跨平台锁文件。`backend/requirements.txt` 与实际 `backend_venv.txt` 有版本漂移：例如工程声明 FastAPI 0.115.0，而原环境已安装版本为 0.141.1。需要保留两份证据，选择恢复原环境还是验证工程声明环境，不要静默混装。

在新目录建立后端环境的候选命令如下；**此处没有执行安装，也没有证明所有历史包仍可从网络取得**：

```sh
cd "$SHUTTL_SOURCE"
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r "$SHUTTL_AUDIT/environment-locks/backend_venv.txt"
backend/.venv/bin/python -m pip check
```

若某包没有对应 wheel、版本冲突或原包源不可用，保存安装日志，对照 `backend/requirements.txt` 与历史环境逐项解决；不要把升级全部依赖作为默认恢复步骤。将新环境的版本和测试结果另存，原清单不覆盖。

另外分别恢复这些环境：

| 环境目录 | 清单 |
|---|---|
| `research/rtmpose/venv` | `research_rtmpose_venv.txt` |
| `research/coreml/venv` | `research_coreml_venv.txt` |
| `research/bst/venv` | `research_bst_venv.txt` |
| `research/cloud_upgrade/pose_benchmark/.venv` | `research_cloud_upgrade_pose_benchmark_venv.txt` |
| `promo/.venv` | `promo_venv.txt` |

姿态评测环境原先通过 `shuttl_backend.pth` 引用后端的 `site-packages`。在新电脑必须使用新根目录重建这个引用；不要把原 `/Users/yangcong/...` 路径直接复制进去。CoreML 导出与一致性验证应在 macOS；CUDA GPU 恢复按第 6 节，不使用 macOS venv。

## 5. 后端开发与 App 连接

现有后端包括 FastAPI API、Celery worker、持久任务 dispatcher、PostgreSQL 和 Redis。`backend/docker-compose.yml` 定义了这五项服务，本地开发的 PostgreSQL 使用 16-alpine、Redis 使用 7-alpine。历史 AutoDL 使用 PostgreSQL 14 和专用端口；这两种布局不能混为一谈。

本地开发示例：

1. 在新副本中基于 `.env.example` 建立私有 `.env`，填入新的开发配置；不要在文档、命令日志或公开 Git 中放入真实密钥。
2. 明确配置本地存储和持久媒体目录；如用 Compose，检查 `STORAGE_BACKEND`、`POSTGRES_PASSWORD`、`SECRET_KEY`，不要部署示例默认口令。
3. 开发后端所需的显式模型路径至少涉及 `SHUTTL_WEIGHTS_DIR`、`SHUTTL_HITNET_WEIGHTS`、`SHUTTL_BST_MANIFEST`、`SHUTTL_RTMPOSE_WEIGHTS`。模型只恢复在研究目录但配置仍指向旧绝对路径，会导致回退或失败。
4. 在确认使用全新开发数据库后运行：

```sh
cd "$SHUTTL_SOURCE/backend"
docker compose up -d --build
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
```

这些是现有 Compose 结构对应的启动命令，**本次未验证在空白系统上的实际成功率**。Dockerfile 默认 Python 3.12-slim 并安装普通 requirements；它不等同于 RTX 5090 的已验证 CUDA 环境。Compose volume 保存数据库和媒体，删除 volume 会删除开发数据。

不使用 Docker 时，源码入口分别是：

```sh
cd "$SHUTTL_SOURCE/backend"
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# 在另一个已配置相同环境变量的终端运行 worker：
.venv/bin/python -m celery -A app.worker.celery_app worker --loglevel=info --concurrency=1 --pool=solo
# 在第三个终端运行 dispatcher：
.venv/bin/python -m app.services.analysis_jobs dispatch
```

上面仍要求 PostgreSQL、Redis、配置和模型已准备好；不能只启动 API 就把后台分析视为可用。单 GPU worker 保持单并发，避免未经验证的 GPU 内存竞争。

### 手机/API 地址

当前 `iOS/Sources/Services/Network/CloudConfiguration.swift` 从 `iOS/Resources/Info.plist` 读取：

- `ShuttlAPIBaseURL`
- `ShuttlCloudAnalysisEnabled`

`SHUTTL_API_BASE_URL` 环境覆盖只在 **Debug** 编译生效。Release 连接新服务器应修改 Info.plist 中的实际 HTTPS 地址后重建；旧 AutoDL 公网域名/端口可能已变化或失效。云分析开关还要求 URL 是合法 HTTPS，不能把 `http://localhost:8000` 填进去就认为云模式已启用。

真机的 `127.0.0.1` 指向手机自身；后端“本机接口可访问”与手机网络可达是两项验证。新域名还会影响保存的远端账号/任务 scope，迁移时要检查已有记录、登录、任务重接和媒体 URL，不要批量改数据库字符串后直接启动。

## 6. AutoDL / RTX 5090 服务与训练环境恢复

本机已有独立服务器恢复包：

```text
/Users/yangcong/Downloads/claude/autodl_backup/shuttl-20261008/
  README.md
  关机前检查报告.md
  restore_and_start.sh
  SHA256SUMS
  PAYLOAD_SHA256SUMS
  restore-kit.tar.gz
  payload/
    gpu-project.tar.gz
    service-project.tar.gz
    python-base.tar.gz
    cuda-toolkit.tar.gz
    system-config.tar.gz
  database/
  inventory/
  private/
  scripts/
  verification/
```

五个大归档的历史报告总大小为 **28,430,030,241 字节**。恢复工具包并不代替五个 payload；只下载 `restore-kit.tar.gz` 不足以恢复全部模型、训练数据、Python 和 CUDA。

历史报告记录的环境：Ubuntu 22.04.5 x86_64，RTX 5090，Python 3.12.3，PyTorch 2.8.0+cu128，torchvision 0.23.0+cu128，Transformers 4.51.3，CUDA Toolkit 12.8，ONNX Runtime GPU 1.23.2。服务通过 `gpu-overlay.pth` 使用另一层 GPU 依赖；不能只复制服务 venv。**不要在此环境上重新运行旧的 torch 2.4.1 / CUDA 12.4 安装配方。**

历史部署根目录：

```text
/root/autodl-tmp/shuttl-5090-20261008
/root/autodl-tmp/shuttl-service
/root/miniconda3
/usr/local/cuda-12.8
```

已有脚本按这些布局恢复并处理 Python 路径、权限、服务配置。先保持原布局完成恢复，再考虑目录迁移。

新实例须提供兼容 NVIDIA 宿主驱动、Linux 系统及可安装 PostgreSQL/Redis/Nginx/FFmpeg/ACL 的软件源。NVIDIA 宿主驱动、GPU 硬件和完整 Ubuntu 根文件系统不在文件包内；这不是保证完全离线裸机恢复的系统镜像。历史建议数据盘至少 80 GB，上传归档后还应有至少 38 GiB 可用；以本次归档解压体积与新平台实际可用空间重新核算。

将完整备份目录传到新实例后，历史脚本的确证入口是：

```sh
cd /root/autodl-tmp/autodl_backup/shuttl-20261008
bash restore_and_start.sh verify
NEW_PUBLIC_BASE_URL='https://填写新实例的6006服务域名:8443' \
  bash restore_and_start.sh fresh
```

如果只取得 `payload/` 和恢复工具包，需要先按包内校验文件验证 `restore-kit.tar.gz`，再解压工具包，使其余目录回到同一级。`fresh` 适用于新实例/空目标，存在同名目录或端口碰撞时应停下检查；不要删除现有项目绕过保护。

同一保留实例再次开机后的历史入口是：

```sh
bash /root/autodl_backup/shuttl-20261008/restore_and_start.sh start
```

脚本还支持 `restart`、`check`。以脚本返回码、`SHUTTL_RESTORE_OR_START_OK`、Supervisor 状态、`/health`、`/ready` 和 GPU preflight 共同判断结果，不能只看到某个进程就判定恢复成功。

历史服务端口：Nginx 6006 对外；API 8000、PostgreSQL 5433、Redis 6381 仅监听回环地址。新域名须写入服务 `PUBLIC_BASE_URL` 和 iOS Release 配置。

### 历史验证与今天未知的状态

10 月 8 日报告记载：备份在本机通过哈希，源 GPU 上使用独立目录/端口恢复数据库并验证六类 GPU 模型，随后重启真实服务；未实际另租一台新实例跑完整 `fresh`。同日晚记录实例正常关机、未释放，平台镜像尚未生成。**本次未登录远端，无法确认今天实例是否仍存在、是否又开机写入、是否有更新的权重/数据或镜像。**

Google Drive 历史报告记载上传完成，但大归档没有全量下载回读，仅恢复工具包做过回读。这不能替代本次 GitHub 全量回读。Google Drive 链接和远端账户也不能由本地文件证明今天仍可访问。

## 7. 继续训练、评测与模型导出

恢复训练需要源码、训练/验证/测试清单、实际样本、标签、预处理、初始权重、best/last 检查点、优化器状态、RNG 状态、配置、日志和评测器。仅有 `.pt` 或 `.mlpackage` 无法重建完整实验。

保留 `research/` 全部关联数据，特别是 `extract`、`shuttleset`、`bst`、`hitnet`、`rtmpose`、`coreml`、`cloud_upgrade`；不要只下载 `research/cloud_upgrade/dist/` 的旧冻结包。现有 App/后端源码可能比这些包更新。`deliverables`、`.handoff`、`.remote-inbox`、`.ui-backup`、`.ml-backup` 等历史目录包含已替换版本和实验记录，用于溯源，不自动覆盖当前版本。

最低验证顺序：

1. 用 manifest/哈希核对模型与样本，检查所有路径和符号链接。
2. 用 `run_inference.py preflight` 验证当前设备实际模型加载、前向和参考结果。
3. 验证断点续跑，确认 optimizer/RNG/累计步数和输出目录配置一致。
4. 再做固定样例端到端评测，最后才开新训练或更换已发布权重。

现有 CLI 的入口经过源码核对，下面是模板，**本次没有执行**：

```sh
cd "$SHUTTL_SOURCE"
backend/.venv/bin/python research/cloud_upgrade/cloud/run_inference.py \
  preflight --device cpu --report '/新输出目录/cpu-preflight.json'
```

在恢复好的 AutoDL Linux 环境中，使用包内指定 Python 并把 `--device` 改为 `cuda`。CUDA 不可用时不接受静默 CPU 回退作为 GPU 恢复成功。

BST 原命令形式为：

```sh
python research/cloud_upgrade/cloud/run_bst.py train \
  --data research/cloud_upgrade/data/bst_fixed30/manifest.json \
  --init research/cloud_upgrade/artifacts/bst_seq30/bst_CG_AP_JnB_bone_merged.pt \
  --out '/选择一个新的实验目录' --device cuda \
  --steps 2000 --batch 32 --hours 0.25
```

这是一个训练命令示例，不是现在应自动启动的操作；参数需以要恢复实验的已保存配置为准。已有 run 续跑要求相同配置并加 `--resume`；不能为通过校验而修改旧配置。`freeze --out ...` 会冻结选定产物，执行前了解其不可继续训练的规则。

检测训练入口在 `research/cloud_upgrade/cloud/run_detector.py`，5090 的实际首轮流程记录在 `cloud_runs/autodl_5090_20261008/first_round.sh`；它会实际启动多项计算，不要未经检查整段重跑。

模型选择的历史事实：线上保留原 BST 十模型 mean-logits 集成、RTMPose-m 以及已验证原 detector；首轮训练候选不是一律替换线上版本。指标表、训练选择与最终 held-out 测试分开保存，不把一个回合的成功扩展成完整比赛/双打保证。

CoreML 导出参考 `research/hitnet/coreml/README.md`、`research/coreml/REPORT.md` 和 BST 导出报告。导出后比较 PyTorch/CoreML 数值、特征顺序和 Swift fixtures，再替换 App 包。HitNet 输入为 far-first，BGR/RGB、缺失值、原始框/扩张框、PTS 和帧率约定都属于模型的一部分。

## 8. 宣传片：成片、源码与可再生成能力

两版都应保留，不只保存最终 MP4：

- `promo/out/Shuttl-宣传片.mp4` 及 `promo/` 下的渲染、音乐、素材生成代码。
- `promo2/out/Shuttl-宣传片-2.mp4` 及 `promo2/` 下的 `web/`、`assets/`、`build/`、全部 Python 脚本。
- 其他审计清单列出的成片版本、抽帧、配乐、宣传图、参赛材料和原始参考数据。

V2 README 记录成片为 60 秒、1920×1080、60 fps；动画由 HTML/Canvas 确定性逐帧渲染，音乐由 NumPy 合成。14–30 秒的回合动画来自 `research/cloud_upgrade/mobile_sample_20261008/phone-archive.json`。该 JSON 也是重做宣传片的依赖，不能只保留 `promo2/`。

两版共同使用 `promo/.venv`；代码会在这个 venv 的 `imageio_ffmpeg/binaries` 下查找 FFmpeg，并用 Playwright Chromium。重建 venv 后还需要安装匹配的 Chromium。原依赖清单位于 `environment-locks/promo_venv.txt`，原 Python 为 3.9.6；换新 Python 后需要重新验证字体、渲染、音画时序。

候选环境重建流程（未在空机器执行）：

```sh
cd "$SHUTTL_SOURCE"
python3.9 -m venv promo/.venv
promo/.venv/bin/python -m pip install -r "$SHUTTL_AUDIT/environment-locks/promo_venv.txt"
promo/.venv/bin/python -m playwright install chromium
```

保留旧成片后再生成新输出，V2 README 确证的命令为：

```sh
cd "$SHUTTL_SOURCE/promo2"
../promo/.venv/bin/python prep.py
../promo/.venv/bin/python stills.py 3 20.5 45
../promo/.venv/bin/python render.py --audio-only
../promo/.venv/bin/python render.py --out out/Shuttl-宣传片-2-restored.mp4
```

可先在浏览器打开 `web/index.html?play`，或加 `&t=14` 定位。最终验证应打开成片，检查时长、分辨率、帧率、文字、字体、音乐、首尾帧；文件存在或 FFmpeg 返回成功不代表视觉内容一致。

## 9. 真机、模拟器与云端业务数据

### 真机历史备份

`~/Library/Application Support/Shuttl/` 本次发现约 14.40 GB，包含：

- `DeviceBackups/20261008-before-cloud/`
- `DeviceBackups/20261008-before-sample/`
- `CloudBackups/20261008/`

保留这些目录及全部 manifest、校验记录、数据库、原始视频、分析归档和 `after-install` 核对副本。`before-cloud` 历史报告记录 30 场比赛；后续测试后手机达到 31 场，并不意味着这个较早的完整备份自动包含后加的所有数据。新增报告/样例在工程与其他副本中另有保存；**当前手机最新数据是否全部落到本机，需要单独核对，不能用这份旧目录推断。**

数据库是 SwiftData/SQLite。复制时必须在一致的边界保存 `default.store`、相应 WAL/SHM 和引用的 Documents 文件；不要只取主数据库，也不要把来自不同时间的 WAL 拼到一起。恢复先在副本运行只读 `PRAGMA integrity_check`，再核对比赛/回合/击球数与媒体引用。

本次没有新做整部 iPhone 的 Finder/iCloud 备份。旧开发设备配对信息、用户钥匙串登录凭据和手机里尚未导出的数据不应由本机工程归档来保证。项目专用 SSH 文件计划由主备份流程加密保存，其保全状态以最终清单为准；SSH 身份与第 3 节单独导出的 Apple 签名身份是不同材料。

### 模拟器

本次找到五套 Shuttl 安装：`UI-Shots-16Pro`、`iPhone 16 Pro`、`Kiro-16Pro`、`iPhone 16`、`Release-16Pro`，均记录 iOS 18.3。应用 bundle 约 1.00 GB，数据容器约 3.07 GB，路径见 `simulator-candidates.json`。

新机器先创建兼容模拟器、安装新构建 App，再通过：

```sh
xcrun simctl get_app_container "$SHUTTL_SIMULATOR_ID" com.ycyangcong.shuttl data
```

取得新容器。停止 App/模拟器后，在副本中恢复对应的 Documents 和应用 Library 数据；不要把旧容器 UUID 当作新机器固定路径。旧安装 `.app` 与容器用于证据和兼容恢复，但依赖相应架构/运行时，不能替代重新编译。复制后的实际启动、数据库迁移和媒体回放仍需验证。

### 云端应用级快照与删除记录

`CloudBackups/20261008/` 包含约 307.6 MB 的应用快照，以及 `latest-snapshot.json`、`latest-deletions.json`、验证记录。它比整套 AutoDL 文件备份更早，覆盖范围也不同。

`research/cloud_upgrade/BACKUP_RESTORE.md` 和 `backend/app/maintenance/recovery.py` 的恢复协议要求：完整核验快照、全新目录、空 PostgreSQL 数据库，并同时保留匹配的 `latest-deletions.json`。旧快照必须重放删除记录，不能因为较早快照中还存在已删除的比赛就把它重新发布。

CLI 校验入口为：

```sh
cd "$SHUTTL_SOURCE/backend"
.venv/bin/python -m app.maintenance.recovery verify '/实际快照路径/快照.tar'
```

恢复的数据库 DSN 与 Redis URL 通过 `SHUTTL_RECOVERY_DSN`、`SHUTTL_RECOVERY_REDIS_URL` 等环境变量提供；不要把含口令 URL 写入公开脚本或终端历史。只有 `restore-report.json` 显示 complete 且没有 `RESTORE_IN_PROGRESS.json`，才能启动恢复服务。失败目标不应被当作成功目标继续使用。

不要同时运行旧实例和新恢复实例处理同一批任务；业务数据库是任务权威来源，恢复时应按工具规则重排可继续任务，不直接重放所有旧 Redis 队列。

## 10. 绝对路径、符号链接、历史会话与隐私材料

原电脑工程中存在 `/Users/yangcong/Downloads/华北五省`、Homebrew Python、`.venv`、旧模拟器 UUID、`/root/autodl-tmp/...` 等路径。开发机器换用户名/目录后必须调整**可执行代码与配置的有效引用**，但不应批量替换所有 JSON/日志/报告——历史证据中的原路径应保留。

先检索并人工分类：

```sh
cd "$SHUTTL_SOURCE"
rg -n --hidden \
  -g '!**/.git/**' -g '!**/.venv/**' -g '!**/venv/**' -g '!**/.build/**' \
  '/Users/yangcong|/root/autodl-tmp|/opt/homebrew' \
  iOS backend research promo promo2 tools
```

主要检查项：

- Python venv 的解释器与入口 shebang：通过重建 venv 解决，不拷贝后强行改一个文件。
- `pose_benchmark/.venv` 的 `shuttl_backend.pth` 及 Linux 的 GPU overlay。
- 模型配置、训练 manifest、样本列表、导出脚本、原媒体路径。
- 远程 SSH 控制 socket：它只是旧进程通信入口，无法在新机“恢复会话”；重新认证建立连接。
- 相对符号链接：例如 BST `weight → ../../weights`、数据目录链接，必须带着目标一起恢复。`source-classification.json` 列有链接；解压后检查，不把链接文件的几个字节当成目标数据已备份。
- `source-external-paths.json` 是启发式线索，其中包含正则表达式、示例、URL 编码、历史路径和错误分词；`exists=false` 不自动等于确有文件丢失。

上下文清单保留 45 个 Claude Code 主会话、附件、文件历史、11 个旧 Codex 会话，以及补充发现的 Claude 桌面会话 metadata 和早期 Cowork 会话完整目录（含 21.98 MB 主记录、3.66 MB 子记录和约 104 MB 的数据/界面产物）；也保留产品定位、UI、训练、服务器与宣传片记忆。它们有助于理解决策，但历史对话中的指令不是新开发者必须执行的当前命令。优先以实际源码、最新时间点和可复验结果判断。

原始会话、数据库、云端私有配置和设备录像可能含私密信息；不要公开上传或把真实口令复制进恢复说明。若最终交付包含脱敏文本和加密原件，应明确哪个包是可直接阅读的上下文，哪个包是完整原件，以及解密恢复方式。当前凭据扫描为启发式，不能声称扫描无命中就证明没有秘密。

## 11. 重置前 / 恢复后的验收与剩余缺口

本次清单能保存本机已找到的内容，但“任何东西绝不丢失”需要覆盖下列边界。不要把其中任何尚未完成项写成成功：

| 项目 | 当前证据/缺口 | 应补的验证 |
|---|---|---|
| GitHub 完整交付 | 本草稿不掌握最终上传状态 | 最终文件清单；所有大文件/分卷下载回读；哈希全过 |
| 可直接继续开发 | 本次未做新机恢复构建 | 空目录解压；Xcode build/test；模型可加载；后端和宣传片样例运行 |
| 全盘扫描权限 | 编稿时 `full-disk-scan-errors.txt` 记录 326 条权限失败：188 条 Operation not permitted、138 条 Permission denied | 逐项判定是否可能含 Shuttl；需要时通过系统授权后补扫；最终报告更新数字 |
| AutoDL 现状 | 只有 10 月 8 日本地历史快照，本次未联网核验 | 核对实例/盘/镜像现状；确认历史备份之后是否有新增数据；有变化则另做一致性备份 |
| 云平台镜像 | 历史记录是尚未生成 | 以平台实际状态核验，不推定已存在 |
| 当前手机数据 | 主要完整目录是 before-cloud，后续有部分增量 | 对照手机现有记录/媒体清单；保留最新一致性导出；不要先卸载 App |
| 签名与账户 | 描述文件即将到期；Apple 签名私钥已导出并加密保全，但尚未在新系统导入验证 | 确认 Apple/GitHub/云平台账户与二次验证在重置后可使用；新签名实际安装验证 |
| 未落盘内容 | 文件系统无法证明编辑器所有未保存缓冲区 | 检查 Xcode/编辑器未保存文档并保存到明确路径 |
| 数据集/第三方资源 | 归档只能保证实际找到并纳入的本地副本 | 权重和数据逐文件核对；许可/原始来源保留；缺失在线依赖单列 |
| 私有/加密内容 | 有些原件含凭据和用户录像 | 验证加密原件可解密且凭据在电脑重置后仍可取得 |
| 真实产品功能 | 历史只验收过特定短片，非全部场景 | 新环境登录、上传、任务完成、结果/视频、取消/删除、后台恢复；长片/双打/切网另验 |

建议最终保留以下恢复验收记录：新环境版本、每个归档哈希、解压检查、断裂链接检查、Xcode build/test 日志、模型 preflight 报告、数据库完整性与行数、后端健康与真实样例任务、两版宣传片抽帧和成片检查。每项都区分“历史已有证据”“本次重新验证通过”“仍未验证”。

## 12. 本草稿使用的依据

- 本次本机只读版本命令：`sw_vers`、`xcodebuild -version`、`xcrun swift --version`、`xcodegen --version`。
- `source-discovery.json`、`source-classification.json`、`source-archive-index.json`、`source-external-paths.json`、`environment-locks/`。
- `context-candidates.json`、`context-audit.md`、`simulator-candidates.json`、`full-disk-scan-errors.txt`。
- `iOS/project.yml`、`CloudConfiguration.swift`、`Info.plist`。
- `backend/requirements.txt`、`pyproject.toml`、`docker-compose.yml`、`Dockerfile`、`.env.example` 的字段名；没有在本文展示原 `.env` 内容。
- `research/cloud_upgrade/BACKUP_RESTORE.md`、`CLOUD_INFERENCE.md`、`CLOUD_PLAN.md`、`RUNTIME_HANDOFF.md`、`mobile_cloud_20261008/STATUS.md`、`pose_benchmark/README.md`、相关 CLI 源码。
- `research/hitnet/coreml/README.md`、`promo2/README.md`、两版渲染脚本。
- AutoDL 恢复包 `README.md`、`关机前检查报告.md`、`平台镜像与关机记录.md`。

本次文档工作未连接远程服务器、未运行训练、未写入原数据库、未上传任何文件。
