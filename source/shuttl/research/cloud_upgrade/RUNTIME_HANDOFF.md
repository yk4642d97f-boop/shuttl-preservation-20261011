> 2026-10-08 手机云端部署最新状态见 [mobile_cloud_20261008/STATUS.md](mobile_cloud_20261008/STATUS.md)。原先的局域网地址和“尚未部署 API”描述已过时。

# 2026-10-07 云计算准备续作记录

实际工程根目录 `/Users/yangcong/Downloads/华北五省`；无 Git、无 AGENTS.md。
用户此前要求先做租卡前准备；最新已提供自己的 AutoDL 4090 实例并明确“你来开始吧”，现已授权云端配置、上传和训练。无需再次询问租卡。
Goal 仍 active，不能把整个租卡前阶段或顶尖模型目标标记 complete。

## 最新状态：2026-10-08 15:26（北京时间），新 5090 部署中

- 用户更换为西北B区928机，实例 e46b4582c4-95dc741d，RTX5090 32GB，25vCPU/90GB，数据盘50GB；明确继续主任务、从空实例重建。
- 用户最新明确“快到期了我续费，不会让关机的”：**不设置自动关机，不主动关机或释放，续费由用户处理。**
- SSH已成功连接：root@connect.westc.seetacloud.com:49996，socket `/Users/yangcong/.ssh/shuttl_5090_session/control`。
  密码通过实例页复制及一次性SSH_ASKPASS使用，不输出、不落盘；helper已删除。无需用户再次手输密码。
- 新云目录 `/root/autodl-tmp/shuttl-5090-20261008`；本地本轮脚本 `cloud_runs/autodl_5090_20261008/`。
- 实机 PyTorch2.8.0+cu128 / torchvision0.23.0+cu128 / CUDA12.8，sm_120，驱动595.91.07。基础CUDA张量运算通过。
- 隔离overlay已安装完成：NumPy1.26.4/OpenCV4.11/ORT-GPU1.23.2，复用镜像torch，不运行旧cu124 setup脚本。
  所有直接依赖由PyPI元数据校验SHA256后本地安装；环境与日志保存在云端logs/。
- runtime-v3 已上传、哈希验证、解压；training-v1已上传，正在哈希与解压；pose-eval-v1仍上传中。
- 正在进行真实模型CUDA preflight，未开始正式训练。下步GPU断点恢复检查、BST限时训练/十模型对照、检测训练与全姿态验证；结果逐项回传。

## 最新状态：2026-10-08 09:42（北京时间），实例已关机

- 中断后继续检查，AutoDL同一实例明确显示“已关机”，数据盘13.55%；SSH主socket已消失，旧连接提示Connection closed。
  没有自行重启；已向用户询问“现在开机继续，先限时一小时”或“保持关机，完善本地准备”，等待答复。
  用户此前授权代为复制实例密码并登录，已实际成功一次；不要重复让用户手输密码。
- 三个归档的rsync均已exit0：runtime-v3、training-v1、pose-eval-v1。
  runtime和training已经云端SHA256校验并成功解压；pose包尚未做云端哈希/解压。
  runtime根shuttl-runtime，training根shuttl-cloud；pose归档无统一顶层，须解压到新建pose-eval目录。
- 仍未执行模型CUDA preflight、GPU断点smoke或正式训练，不能声称训练已开始。
  只通过了nvidia-smi及基础CUDA张量运算。数据和环境均在数据盘，未增加付费磁盘。
- 依赖下载排障：pip默认HTTP和HTTPS实际都约130KB/s；curl下载同一个完整18MB wheel约5.1MB/s。
  本地新增cloud_runs/autodl_20261007/prefetch_wheels.py，云端已执行成功，25个固定包/大依赖已下载到wheels，
  逐个按官方PyPI JSON的SHA256校验，wheels/verified.json记录来源。
  原onnxruntime-gpu1.20.1在该Python3.12/Linux索引不可用，当前overlay明确固定1.20.2（未验收CUDA）。
  复用基础torch2.5.1+cu124；不宣称已按原脚本2.4.1安装。
- 前一bootstrap使用--find-links仍被pip选中相同网络包，安装进程在关机时中断，最终状态不明。
  **本地bootstrap.sh已修正为逐包哈希复核后生成显式本地路径requirements-local.txt；此修正尚未重新上传。**
  rtmlib/ultralytics仍单独--no-index --no-deps，避免引入CPU ORT/重叠OpenCV。
- 新的check_bst_resume.py支持--root/--out/--report/--device cuda，已上传云incoming，尚未实际执行GPU检查。
  compare_bst.py已上传：在同一1126验证片段比较初始化单模型、原十模型mean-logits、训练候选；复核训练checkpoint指标。
  该评测器尚未运行；不能把训练对单成员的提升说成胜过原十模型集成。
- 下一步：根据用户答复决定是否开机。若开机，先确认SSH端口是否变化，复制当前密码建立主会话，检查远端进程/文件。
  上传修正bootstrap后续装；保留全部失败安装日志，做模型CUDA preflight、6步GPU恢复检查，再启动限时训练。
  用户仍要求低投入；此前拟定的检测各0.5小时不是现在的额外授权额度。若选择总一小时，安装/评测也计入。


## 最新：4090 已连接，上传和环境配置中

- 用户明确要求代为复制/登录后，已从AutoDL复制实例密码，通过一次性SSH_ASKPASS建立SSH主会话；密码未输出/未写入文件。
  非秘密askpass辅助脚本已自动删除。复用socket仍是`/Users/yangcong/.ssh/shuttl_autodl_session/control`。
  不再要求用户手输密码；直接用该socket调用SSH/rsync。
- 实机nvidia-smi确认4090 24564MiB、驱动550.107.02、空闲；数据盘50GB可用。
  Python在`/root/miniconda3/bin/python`（非交互PATH默认不含）；torch2.5.1+cu124、torchvision0.20.1+cu124，CUDA张量求和通过。
- 云工作目录`/root/autodl-tmp/shuttl-20261007`；incoming收包，logs记录安装和验证，env为隔离overlay。
  复用镜像torch2.5.1，不改基础环境；numpy1.26.4/OpenCV4.11/ORT-GPU1.20.1等放数据盘。
  这是与冻结脚本torch2.4.1不同的明确环境变体，必须通过实际模型参考检查才接受。
  本地安装清单/脚本在`cloud_runs/autodl_20261007/`。
- 正在上传runtime-v3和training-v1并安装依赖；尚未通过模型CUDA preflight或启动训练。
  runtime解压根为shuttl-runtime（约383MB），training解压根为shuttl-cloud（约1.94GB）。
  training归档SHA256为6d337736caaf9ebc425a2ac083f00b7fc291df12e685ff5f7e355d979005614f。

### 先前登录排障记录（已解决）

- 用户提供镜像 PyTorch2.5.1 / Python3.12 / Ubuntu22.04 / CUDA12.4；4090 24GB×1，22vCPU、90GB RAM、系统30GB/数据50GB，按量约2.08–2.19元/小时。
- 已在用户Chrome的AutoDL实例列表核实运行中的 `43764580c0-714e1db4`，西北B/060机。
  从该实例“登录指令”复制得到 `ssh -p 43310 root@connect.westb.seetacloud.com`。用户不知道SSH指令，已由我定位。
- 本机默认key及 `~/.ssh/shuttl_deploy` 均 BatchMode 登录失败。`~/.ssh/config`不存在，另有lele-server公钥但未尝试无关密钥。
- 用户正在手工建立复用会话：
  `ssh -M -S /Users/yangcong/.ssh/shuttl_autodl_session/control -o ControlPersist=1800 -o ServerAliveInterval=30 -fN -p 43310 root@connect.westb.seetacloud.com`
  父目录已创建0700。用户首次提示Permission denied；我已在Chrome点击真实密码复制按钮（成功提示），让用户回终端⌘V+回车再试。
  未读取/记录密码。最后 `ssh -S ... -O check` 尚无socket。后续先检查是否已连好，再用 `ssh -S ... -o BatchMode=yes -p 43310 root@...` 运行命令。
- 原生Terminal.app界面工具被安全检查拒绝，已向用户解释并请求手工密码登录；不可改用其他终端UI绕过此拒绝。
  Chrome extension缺auth token，但原生Chrome AX可用。CUA变量chromeApp为com.google.Chrome。
  临时TextEdit文档只含SSH命令，未保存；关闭时保存对话框的取消/undo清理被“应用不活跃”打断，仍需适时收尾，不能改用户原有完成情况说明.md。
- 现阶段优先连接、检查nvidia-smi/数据盘，部署已验收runtime/training包，CUDA preflight，然后有预算/断点的训练。
  不要把此前“不具备GPU/不得启动云阶段”的旧阶段约束沿用到现在。还未实际连接/上传/启动GPU任务。

## 最新：姿态候选CPU对照完成

- `pose_benchmark/` 新增RTMPose-X RGB384×288、ViTPose++ base RGB256×192/COCO expert0研究适配。
  原RTMPose-m维持BGR256×192。X的SDK尺寸字段错误，按实际ONNX/codec和训练配置校正。
- 三路同一冻结small面板：041已知类别每类SHA排序取2，共44片段/1334帧/2633姿态；保留2个缺框弃权。
  m=39/44，X=38/44，ViTPose++=39/44；无直接替换收益，产品基线不换。
  11项接口/分母/四框顺序检查通过；真实单帧native参考误差m<0.000036、X<0.000041、ViT=0。
  四框是同双人帧的不同裁剪，仅接口证据。classification at labeled hits，不是联合F1/姿态AP/双打质量。
- 全验证已冻结1154已知事件，46未知/冲突事件单列；未在test上选模。full尚未推理。
- 新旧m缓存最大差78.56px：9个姿态>1px，4个>10px。审计9帧发现原图/框/warp矩阵全同，
  旧OpenCV5.0/NumPy2.5.3/ORT1.30环境可精确重现旧缓存；当前OpenCV4.11/NumPy1.26.4/ORT1.19.2裁剪插值像素最多差3。
  同tensor交叉ORT误差<1.5e-6，确认大差异来自预处理。旧cache在44片段的分类与fresh逐条同39/44。
  不改写旧训练集或历史指标；全数据影响仍待验证。证据checks/cache_audit_verified.json及cache*.npz。
- Sapiens2新候选已调查，custom license、torch>=2.7、1024×768；未下载权重/安装/执行模型。
  AST读取308→COCO17索引[0,1,2,3,4,5,6,7,8,62,41,9,10,11,12,13,14]，不能截前17。
- `pose_benchmark/.venv`单独安装transformers4.51.3等并以.pth只读复用backend；numpy已固定1.26.4，backend环境未改。
- 新独立评测包 `dist/shuttl-pose-eval-v1.tar.gz`：1,622,295,063 bytes，95文件，SHA256
  f618024db296f4375283ed093c20e1cb99944deb70437fb447a20e121f6a2353。
  包含041视频、输入、三姿态权重和BST十权重、源码/许可/manifest，不是API部署包。冻结runtime-v3未改。
  已异目录解压并完成cloud_eval.py preflight CPU回放：95文件校验，三姿态模型和BST参考误差均0。
  replay_location.json记录路径，replay_verified.json和replay_verified_retry.log记录通过结果。
  初次回放缺torchinfo（原目录从BST旧venv补入，异目录无该venv）；已向独立pose环境安装1.8.0。
  包内requirements-extra.txt本就声明torchinfo1.8.0，归档无需改动；初次失败日志replay_verified.log保留。
- 实测和限制见pose_benchmark/REPORT.md、README.md；MODEL_SURVEY/PRE_GPU_READINESS/CLOUD_PLAN已同步。

## 最新追加：本地磁盘备份/恢复与训练迁移（本次已验收）

- 新增 backend/app/maintenance/recovery.py 和 backend/tests/test_recovery.py；backup/verify/restore CLI。
  仅显式 STORAGE_BACKEND=local 的自包含备份；包含真实pg_dump、录像、指定模型/代码/训练目录和配置，逐文件SHA256。
  备份前建 shuttl_recovery_identity 来源标识；锁表后才取MVCC snapshot，pg_dump共享同一快照。
  阻止本地上传发布/DB写入，活跃worker/训练锁则拒绝；树/配置变化拒绝发布；排除.part和.analysis缓存。
- repository/latest-deletions.json是递增且不遗忘的删除账本，必须随归档复制；旧快照恢复时先重放最新已知删除。
  不接受不同lineage、缺失/过期/损坏账本。原始历史归档仍保留旧内容，不声称全备份物理擦除。
- restore只接受空DB+新目录，先校验归档再导入；恢复active任务为queued、清旧token/心跳/进度但保留attempt。
  runtime.env重写DB/Redis/media和四个显式模型路径；归档/配置0600。Redis不备份，也不清空，要求新实例/库。
  恢复中途失败保留failed标记、不生成可启动配置；跨DB/FS不保证单事务。重试应使用新空库/新目录。
- recovery_final.xml/log：20项通过0跳过；真pg_dump/restore、损坏/覆盖拒绝、删除事务快照竞态、outbox恢复实际完成任务。
  recovery_training.json：真实BST从3步备份，移走原代码/数据/断点，恢复目录跑到6步；与既有full6参考参数误差0/history/RNG相同。
  94文件校验，模型测试是CPU机制证明，不是模型质量新结论或CUDA保证。
  recovery_verification.json保存源hash。使用postgres:16-alpine专用容器，无实际用户库/视频、无GPU费用。
- 说明和复现见BACKUP_RESTORE.md；初始2轮测试因fixture driver/SQL参数/publisher签名问题失败日志保留，最终通过。
  runtime-v3仍冻结、不含恢复工具。实际异机传输、OSS对象备份/恢复、完整部署包和分块续传未完成。
  本轮专用 shuttl-recovery-pg 容器已停止并自动移除；无后台测试/训练进程需要等待。

## 最新追加：远端删除/取消与存储生命周期（本次已验收）

- 详见 REMOTE_LIFECYCLE.md；新增 media_deletion.py/media_cleanup.py，API DELETE 202 与清理意图同事务保存。
  创建支持客户端 UUID 且与删除串行；未知 UUID 删除留墓碑，阻断晚到 create。旧本地签名 PUT 不能复活已删视频。
  本地上传先 stage、再锁行复查发布；清理复用 worker 比赛锁，避免删除正在读的输入。
  dispatcher 挂载 media_data 并扫清理队列；成功每小时复查，失败60秒重试。OSS清完全相同key的历史版本与标记；仅协议测试。
- 手机新增 RemoteCommandQueue.swift：原子持久意图、账号/服务器隔离、删除取代取消、前台/网络恢复和手动同步。
  Match 新增可选 cloudUserID/cloudBaseURL/cloudCreateRequested；先保存账号和稳定UUID再请求创建。
  scoped backend 与 API 请求/响应/refresh 核对原账号，旧 refresh 不能覆盖新登录。旧无归属记录先鉴权查询，404不可跨账号重传。
  discard 变 async throws，先保存删除意图再清手机数据；调用它的视图和测试已更新。队列写失败保留录像/行。
  取消携带准确 job_id，只有 poll 阶段可取消；取消未同步前阻止再分析。新录像在create尚未发送前可本地删除。
  队列损坏不覆盖原文件，UI显示待同步数量/错误与重试。演示/本地录像删除不发云端命令。
- backend 测试 64 项通过（含9项真实DB生命周期）；ios_lifecycle_verified.xcresult 104 项通过（15生命周期+6 API+83回归）。
  真实旧SQLite schema升级保留录像/回合/击球，新可选字段为空；并测试创建中删除、离线重开、换账号/服务器、refresh竞态。
  ios_lifecycle_summary.json、lifecycle_backend.xml、lifecycle_verification.json 记录摘要和源hash。
- xcodegen 已生成工程；模拟器测试采用 CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=-。
  初次编译失败日志保留，最终 verified 通过。未新增子代理。Release 云端开关未改、runtime-v3冻结包未改。
- 逻辑删除立即提交，物理文件异步清理且持续复查；不保证GPU算子立即停/云对象所有副本立即永久擦除。
  真实OSS、真机条件、完整部署/备份恢复与服务端分块续传仍未验收。本轮不产生新的模型精度结论或租卡费用。

## 最新追加：手机后台上传（本次已验收）

- 重写 iOS/Sources/Services/Network/VideoUploadService.swift，新增 UploadTransport.swift。
  使用固定后台URLSession + uploadTask(fromFile)，actor内持久回执；API origin/match UUID哈希key，单次generation关联taskDescription。
  先建暂停task、写回执、再resume；完成回执落盘后才释放系统background completion；不保存签名URL/账号token到应用回执。
- MatchBackend上传改成matchID+file并延迟获取上传地址；完成回执/现有系统task不需要访问签名API。
  401/403/临时错误重新签名且最多3次；系统取消可重试，用户Task取消不重试。
  MatchPipeline取消本地上传、server400时清理旧回执再传、discard清理对应上传；ContentView签出停止cloud流水线。
  APIClient.logout改为async并取消系统上传；AppDelegate增加后台URLSession回调。云端分析远端cancel/delete仍未接。
- 测试：ios_background_verified.xcresult及log，46项通过（30 pipeline +15恢复状态 +1真实后台HTTP）。
  独立upload_relaunch_smoke直接编译真实上传/transport/VideoStore/AppDelegate，16MiB上传到512KiB时SIGKILL、重新启动，
  两个应用进程、一个target请求、一个完整PUT，SHA256一致；relaunch-verification.json记录源hash。
- 最初真实后台测试因CODE_SIGNING_ALLOWED=NO未绑定bundleID而被nsurlsessiond拒绝。使用正常模拟器ad-hoc签名通过，未改系统安全配置。
  复现必须CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=-。当前xcodeproj由xcodegen重新生成，加入新源/测试文件。
- code_backups/background_upload保存原有修改文件；实现、验证和复现说明见BACKGROUND_UPLOAD.md。
- 尚不包含服务端分块续传：系统保留任务可重接，系统任务丢失则整文件重试。SIGKILL+主动重开不等于用户划掉App后自动唤醒。
  真机锁屏/低电量/切网/长文件、TLS、OSS实服务、远端取消/删除和完整备份恢复仍待完成。
- 未启用Release未部署的云端地址；runtime-v3冻结计算包未改。此轮没有产生训练精度新结论或租卡费用。

## 最新追加：持久任务与录像输入（本次已验收）

- 新增 backend/app/models/analysis_job.py、services/analysis_jobs.py；API 先在事务中保存任务与比赛指针，再投递。
  并发提交/完成结果复用/force/可选 Idempotency-Key、60秒重投、120秒失联恢复、最多3次尝试、30秒重试。
- 会话 advisory lock 防止正常重复计算；claim_token+当前比赛指针保护写入；结果和任务done原子提交。
  数据库是新任务轮询权威，取消接口已完成。手机远端取消、删除仍未接。
- tasks.py 拆为 compute_analysis + _save_results（事务由job runner持有）。旧 analyze_match 消息明确拒绝；部署前必须停旧worker。
- 本地 save_stream 改为非空/上限校验、fsync、同文件系统硬链接原子发布，禁止覆盖；相同内容允许重试。
  OSS提交固定ETag/长度/可用version ID，下载If-Match；更换或删除时明确失败。OSS仅模拟协议测试，未访问真实bucket。
- Dockerfile/Compose worker单并发solo，dispatcher，media共享，API健康依赖，容器内DB/Redis地址，DB端口仅回环。
  compose配置结构验证通过；没有构建或部署完整镜像，未切换手机Release到云端。
- 19项真实PostgreSQL合约检查通过，包含真实Redis/Celery/dispatcher进程SIGKILL后同job恢复。
  另60项上传/OSS/任务/流水线/序列化通过。job_contracts.xml、job_regressions.xml、job_verification.json保存计数和源文件hash。
- 测试曾因多个TestClient在线程内共享async引擎卡住，改为同事件循环AsyncClient+12并发请求；覆盖未降低。
- 测试都在专门本机容器完成，不涉及用户数据库或付费资源。计算进程测试使用合成结果，不代表模型质量。
- 运行边界、迁移步骤、复现方式见 DURABLE_JOBS.md。取消是协作式；不保证网络分区下恰好一次计算。
- code_backups/durable_jobs 保留修改前文件（Dockerfile备份是在单并发修正后取得，其旧CMD原为 --concurrency=2）。
- runtime-v3计算包保持冻结，不含本次API/队列改动；后续完整服务发布须另打包、另验收。

## 本轮完成

- 后端新增 hitnet_core.py / hitnet.py，已接 pipeline_v2 与 tasks 的 SHUTTL_HITNET_WEIGHTS。
  player slots far-first，时间戳一致性/PTS 缺口、非有限结果、双打拒绝、缺观察处理。
- 新增 bst.py、bst_vendor/（上游 MIT、来源 commit/文件哈希），rtmpose.py / rtmpose_core.py。
  BST 保留十模型 mean-logits 与无偏移窗口；RTMPose-m 原始 BGR裁剪流程，按击球窗口推理。
  可选模型依赖延迟导入；backend/requirements-cloud-models[-cuda].txt 提供后端附加依赖。
- pipeline 配置 SHUTTL_BST_MANIFEST/SHUTTL_RTMPOSE_WEIGHTS；推理失败/双打/缺姿态明确保留 rules。
  BST 全部弃权时 used=rules，evaluated_model=BST_CG_AP_seq30，不把尝试分类当作实际已采用模型输出。
- serialize.py 新增 cross_net/short_serve/long_serve 的 legacy映射。
- /matches/{match}/job/{job} 已校验 match、user、job 归属；任务幂等化后续已完成，见最新追加。
- 原有文件备份 code_backups/cloud_inference；serialize 原始内容按唯一已知修改逆向恢复在备份中。

## 证据

- cloud_hitnet_parity.json：033/041，184 回合/87,800帧，raw/features/logits/events 全一致。
- cloud_bst_parity.json：041 全56,416帧特征一致，17有效clip的十模型logits完全一致。
- cloud_pose_parity.json：041真实4帧/8姿态，单人reference vs batch输出误差0。
- 后端模型/流水线/任务/序列化测试共42项通过；上传/任务归属24项通过；最后新改的BST/流水线31项通过。
- cloud/runtime_smoke.json：所有模型CPU加载/前向/参考输出通过；本机torch2.4.1，ORT1.19.2。
  setup_inference.sh固定ORT1.20.1、torch2.4.1（GPU cu124）；全新Linux依赖安装及CUDA尚未验证。
- cloud/runtime_integration.json：041回合10（241帧），有给定球场角点；阶段都运行，但GT相对60帧，云预测18，BST未知。
  该旧记录的 used=BST 是修正诊断之前生成，refined=0表明实际保留rules。不可声称质量通过。
- cloud_feature_shift.json：同一失败例 reference 原输入也预测52（离GT60超过容差）；不是纯云接口错误。
  混合特征分析保留，未按该例修改阈值/训练。
- cloud/runtime_integration_041_r69.json：选择“至少5拍中最短回合”，303帧，GT60/73/86/99/122，预测59/74/87/101/123，全部±2内。
  BST接受3分类，2个窗口缺姿态覆盖保留rules。两例都不是整场质量评测。
- 各check_cloud_*.py / audit_cloud_feature_shift.py可重现；两个实际clip/raw存cloud_runs/，不进分发包。

## BST 准备

- prepare_bst_training.py 按固定窗口/RTMPose准备001–006的6522训练片段，041的1126验证片段。
  data/bst_fixed30有训练/验证NPZ和哈希清单，约95MB。007因提取文件重复全局帧号隔离并写入manifest。
- cloud/run_bst.py train / freeze：仅单个初始权重（不平均参数），validation选最好，训练前基线保留。
  固定配置/数据哈希、原子保存state/optimizer/RNG/step/累计时长、fcntl同目录进程锁、SIGTERM安全中断。
  没有自动test入口。GPU真实训练仍未执行；严重kill可能丢最近25步及未保存用时，文档明确限制。
- check_bst_resume.py / cloud/bst_smoke.json：CPU6步，3步中断再恢复参数和验证记录完全一致；拒绝冻结后重训及heldout训练。
- 尚无新BST效果提升结论；smoke不能当正式训练或准确率结果。

## 分发

- 旧 detector训练包 v1 1.87GB保持不动。
- 最新 `dist/shuttl-cloud-runtime-v3.tar.gz`：360,939,427 bytes，79文件。
  SHA256 e91b261701b99803c57c4a65865535c51f8e337b444b7f116d50d9f1654c9e21。
- `dist/runtime_verification.json`对应v3：异目录解压、所有文件hash、HitNet/BST/pose参考输出、TrackNet/WASB前向、YOLO/NMS全通过。
- v2是此前中间快照，v3加入可选依赖和延迟导入。不要再用v2当最新。
- 这是计算CLI/BST训练准备包，不是API/手机云端部署包。不含用户视频、账号密钥和venv。
- CLOUD_INFERENCE.md / PRE_GPU_READINESS.md在包冻结后新增验证状态和上传现状修正，当前文档比包内快照新。
  包内关于“旧上传整文件读内存”的文字已过时，当前VideoUploadService.swift已是upload(fromFile:)。

## 明确剩余工作

1. 持久任务队列/恢复/单并发配置、手机远端取消/删除与存储生命周期已完成本地验收；本地磁盘备份/恢复已验收；完整部署包、OSS对象备份/恢复、异机传输仍待完成。
   backend无alembic目录：app/core/database.py create_tables 用 create_all+ALTER补现有列。
   旧 `.delay` 先于提交的路径已移除；最新实现以数据库outbox和claim token为准。不要恢复旧队列直接写入路径。
2. 手机后台上传/持久回执/进程重接已验收（最新追加）。服务端分块续传和真机条件测试仍缺。
   当前使用固定后台URLSession上传文件；没有把录像整段读入内存。系统任务丢失时仍需整文件重试。
   Release在OnDeviceAnalyzers.makeDefault强制本地分析；不要直接开启未部署地址。
3. 更强姿态候选公平比较入口、小面板及异目录CPU回放已完成，全验证及CUDA仍待执行；连续录像负样本、真实球馆、双打配对视频/时钟与标注仍缺。
   DOUBLE_DATA_PROTOCOL.md明确四人身份/遮挡/未知标签/源比赛隔离及验收指标。
4. 用户已有4090并授权云端工作；打通SSH后做CUDA/吞吐/显存/视觉训练/网络TLS/真实手机联调，无需再购买。

无当前挂起进程。后台上传用的本机HTTP服务已停止、独立fixture应用已卸载、模拟器恢复最初Shutdown状态。本次自建 PostgreSQL/Redis 测试容器已停止并自动移除（Docker app 保持开启）。没有新建子代理。所有模型对外仍是候选，不能称单打双打已顶尖。
