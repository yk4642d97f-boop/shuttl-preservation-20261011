# 云端比赛删除与取消：本地验收记录

2026-10-07。本轮已完成手机端与后端的协议实现、故障恢复和本地测试；没有部署云服务，没有租用 GPU。

## 手机端行为

- 新比赛使用手机生成的稳定 UUID。发送创建请求之前，先保存原账号、服务器地址和创建意图；创建重试仍用同一个 UUID。
- 删除之前先将请求原子写入 Application Support/RemoteActions/pending-v1.json，再停止后台上传并清理手机录像、分析文件和检查点。无法保存请求时保留本地数据并显示错误。
- 删除和取消待办没有密码或令牌，只记录账号/服务器命名空间、比赛和任务编号。前台恢复、网络恢复及“重试同步”都会执行一次有界同步；应用被系统终止后保留待办，下次运行继续处理。
- 退出登录后仍可为已知原账号记录删除意图，只有再次登录该账号并连接原服务器才发送。请求在发送前、响应返回后及令牌刷新重试时都校验账号；旧刷新响应不能覆盖新账号的登录。
- 原账号字段为空的旧云端记录，必须先通过鉴权查询确认归属；404 不会触发向当前新账号重新上传私人录像。升级之前已经遗失服务端 UUID 的创建请求无法凭空恢复。
- 用户取消携带确切 job_id；重跑分析尚未返回新任务编号时不显示取消按钮。取消尚未确认时不允许发起下一次分析。删除同一比赛会取代其未完成取消待办。
- 本地分析的录像继续只在本机删除；尚未开始创建云端记录的录像也可以直接删除。演示模式不连接服务器。
- 比赛页显示未完成同步的数量和重试入口；详情/列表删除会明确说明已上传比赛也会请求云端删除。队列文件损坏时保留原文件并显示错误，不悄悄丢弃删除意图。

## 后端行为

- POST /matches 接受可选客户端 id；同账号重复创建复用现有比赛。创建与删除使用同一生命周期事务锁，避免并发请求互相穿越。
- DELETE /matches/{id} 返回 202，在一个数据库事务里创建 media_deletions 清理记录并删除比赛；关联分析任务、回合和击球由外键级联删除。同账号可重复请求。
- 删除一个尚不存在的 UUID 也保存删除记录，因此晚到的创建请求不能将它复活。其他账号不能删除已有比赛或别人的删除记录。
- POST /matches/{id}/cancel 接受 job_id；若已换成新任务则返回 409，手机将旧任务取消视为已失效，不会取消新任务。
- 本地 PUT 在读取请求体之前验证比赛，写入私有临时文件后再次锁定/检查归属，再原子发布。读完整个请求体期间不持有比赛行锁；用户删除不必等待慢上传结束。已删除比赛的旧上传令牌不能重新发布文件。
- dispatcher 执行 collect_due：每批最多 10 个到期记录，借用分析 worker 的同一比赛锁；计算占用文件时延后 5 秒，清理失败 60 秒后重试，成功后每小时复查。
- 本地清理包含原视频、对应 .part 文件及按视频 key 归档的 worker 临时目录。OSS 清理只针对完全相同的 key，删除当前对象、历史版本及删除标记，每轮最多 20 页；真实 OSS 尚未联调。
- 删除记录长期保留，处理删除后才完成的旧 OSS 签名 PUT 和进程崩溃遗留文件。202 代表逻辑删除已提交，不代表所有物理副本已立即永久消失。运行中的 GPU 算子可能仍会计算到下一检查点，但已删除任务无法写回结果。

## 验证证据

- cloud/lifecycle_backend.xml：64 项通过，0 失败、0 跳过。包含 9 项真实 PostgreSQL/本地文件生命周期测试，以及任务恢复、上传、OSS 协议和 worker 回归。
- cloud/ios_lifecycle_verified.xcresult 和同名 .log：104 项通过，0 失败、0 跳过。cloud/ios_lifecycle_summary.json 为 xcresulttool 导出的摘要。
- 新增 15 项生命周期检查和 6 项 API 检查，覆盖断网重开、账号与服务器切换、令牌刷新竞态、取消进行中被删除取代、并发同步去重、损坏队列、磁盘写入失败、创建途中删除、旧账号 404、取消未同步的重试阻断、未上传录像删除、本地删除及 SwiftData 持久化。
- 迁移测试用 code_backups/remote_lifecycle 中的原模型定义建立真实 SQLite 旧库，再用当前模型打开；录像路径、比赛类型、回合及击球保留，新可选字段为空。此结果不能替代用户全部历史数据库样本的迁移测试。
- cloud/lifecycle_verification.json 保存本次修改源文件的 SHA256、测试摘要和验证范围。
- 本轮修改前的现有文件备份在 code_backups/remote_lifecycle；新文件没有对应旧版本。中间编译失败的日志保留，最终成功记录以 verified 为准。

后端复现（仅限专用可丢弃测试数据库，测试会清空数据）：

```sh
cd backend
SHUTTL_TEST_JOB_DSN='postgresql://postgres:local-test-only@127.0.0.1:64250/shuttl_job_test' \
SHUTTL_TEST_JOB_REDIS='redis://127.0.0.1:64251/15' \
.venv/bin/python -m pytest tests/test_analysis_jobs_postgres.py tests/test_media_lifecycle_postgres.py \
 tests/test_local_upload.py tests/test_tasks.py tests/test_oss_input.py -q
```

手机复现：先在项目根目录执行 `xcodegen generate --spec ios/project.yml`，再执行：

```sh
xcodebuild test -project ios/Shuttl.xcodeproj -scheme Shuttl \
 -destination 'platform=iOS Simulator,id=B6BB64E2-0809-48A6-9AB3-07F454936BBD' \
 -derivedDataPath ios/build/dd \
 -only-testing:ShuttlTests/MatchPipelineTests \
 -only-testing:ShuttlTests/OnDevicePipelineTests \
 -only-testing:ShuttlTests/RemoteLifecycleTests \
 -only-testing:ShuttlTests/RemoteAPITests \
 -only-testing:ShuttlTests/PipelineCorrectionsTests \
 -only-testing:ShuttlTests/PipelineOutcomeTests \
 -only-testing:ShuttlTests/PipelineDebugInboxTests \
 -only-testing:ShuttlTests/VideoUploadServiceTests \
 CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=-
```

## 部署边界与后续

本轮没有重新打包 runtime-v3；它仍是先前冻结的计算包，不含完整 API。手机 Release 仍未启用未部署的云端地址。

部署时须先停止旧 worker，并按 DURABLE_JOBS.md 升级后端；create_tables 会创建 media_deletions，dispatcher 和 worker 必须共享 media_data。云存储身份需要对指定视频前缀具备历史版本查询和删除权限，否则清理保持 pending；不能把权限失败标为完成。删除记录也需要纳入数据库备份，恢复旧备份时须保留删除意图，避免被删除数据重新出现。完整备份/恢复演练尚待完成。

仍需完成：服务端分块续传、完整部署包与备份恢复、真实 OSS/TLS/真机锁屏及切网测试。本轮没有产生新的模型准确率结果；更强姿态比较、真实双打视频与标注缺口、CUDA 性能和训练阶段仍按 PRE_GPU_READINESS.md 推进。
