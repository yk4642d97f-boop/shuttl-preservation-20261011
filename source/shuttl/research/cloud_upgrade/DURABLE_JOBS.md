# 云端分析任务可靠性（2026-10-07）

已在本机的隔离 PostgreSQL 16、Redis 7 及真实 Celery 子进程中验证。没有租卡、上传私人录像或部署公网服务。
这部分不改变模型准确率；它防止重复消耗计算资源、丢失任务状态和旧结果覆盖新结果。

## 提交、执行与查询

- `POST /matches/{id}/analyze` 将任务输入、状态和比赛当前任务指针在同一数据库事务中提交。
  同一比赛同时点击 12 次只产生一个任务。角点先转为 JSON 表示，重复请求不会因 tuple/list 差异冲突。
- 进行中的相同请求返回同一 job_id；参数不同返回 409。完成结果默认复用；明确传 `force: true` 才重新计算。
  force 不会重复启动正在运行的任务。
- 可选 `Idempotency-Key`（1–128 字符）用于精确重放。一个 key 不能用于不同参数或已被后续任务替代的请求。
  已取消/失败的同 key 请求返回原状态；重新尝试应使用新 key 或不传 key。
- API 提交后的投递是尽力而为。独立 dispatcher 每 5 秒查询已提交的任务，距上次投递至少 60 秒才重投。
  Redis 丢消息或暂时不可用不丢数据库里的请求。
- worker 对每个比赛取得 PostgreSQL 会话 advisory lock，正常重复投递不会重复计算。
  每次实际执行另有 claim_token；写结果时锁定比赛、核验当前任务和 token，然后在同一事务保存结果和完成状态。
- 临时错误最多尝试 3 次，每次延迟 30 秒；输入文件缺失、录像版本改变、无可用回合等确定性问题直接失败。
  dispatcher 对超过 120 秒没有心跳的 running 任务重新投递；存活 worker 的会话锁仍会拒绝重复计算。
- `GET /matches/{id}/job/{job_id}` 校验登录用户、比赛和当前任务，直接读取数据库。
  对手机保留 PENDING / PROGRESS / RETRY / SUCCESS / FAILURE / REVOKED 状态和字符串 info，Redis 结果过期不影响新任务状态。
- `POST /matches/{id}/cancel` 取消排队/执行中的任务。进度检查和心跳配合中止；晚到结果不能写回。
  新任务在旧计算释放比赛锁前不能开始。手机远端取消/删除后续已完成本地验收，见 REMOTE_LIFECYCLE.md。

## 录像输入

- 本地存储先流式写临时文件，校验非空及大小上限并同步到磁盘，再以硬链接原子发布。
  已发布 key 不可覆盖。相同字节的重试允许成功，不同录像返回 409；更换录像需创建新比赛。
  空请求和并发上传不破坏已有录像。临时文件和目标文件必须在同一文件系统。
- OSS 在提交时记录 ETag、大小以及可用的 version ID；下载使用 If-Match 和可用的 versionId，下载后再核验大小和 ETag。
  未启用版本保留时，被替换/删除的输入会明确失败，不会分析新对象冒充原录像。
  若 bucket 保留对应版本，下载可指定旧版本。ETag 是对象版本校验值，不宣称它一定是文件 SHA256。
- OSS 检查只用了本地 SDK 模拟，没有真实 bucket 联调。必须在部署前验证条件请求、版本保留策略、权限和失败响应。
  本地文件管理、删除后的旧上传凭证和残留文件回收已完成本地验收，见 REMOTE_LIFECYCLE.md；账号整体删除尚未实现。

## 升级顺序

1. 备份数据库、media、模型权重、配置及必要密钥。备份必须保存到租赁盘以外。本地磁盘方案的备份/恢复自动化及 BST 续跑演练已完成，见 BACKUP_RESTORE.md；OSS 对象备份与实际异机传输尚待完成。
2. 停止接收旧分析请求，确认所有旧 worker 已退出，再升级代码。不能让旧 worker 与新 worker 混跑：旧代码没有结果写入保护。
3. 启动 API；现有 create_tables 会注册 analysis_jobs 并保留旧比赛/结果，补齐旧 fps/analysis 列。真实旧表升级及重复启动已测。
4. 启动 dispatcher 和单卡 worker：

   ```bash
   python -m app.services.analysis_jobs dispatch
   celery -A app.worker.celery_app worker --loglevel=info --concurrency=1 --pool=solo
   ```

5. 旧的 analyze_match 队列消息被新代码拒绝，不能静默写入。旧未完成比赛需要重新调用 analyze 创建持久任务；
   已完成比赛保留原结果，只有 force 才新算。旧任务的轮询仍有兼容路径。

`backend/docker-compose.yml` 已加入 dispatcher、共享 media 卷、单并发 worker、API 就绪依赖和容器内数据库/Redis 地址；
PostgreSQL/Redis 端口仅绑定回环。`docker compose config --quiet` 通过。
这是开发 Compose（含 reload、默认开发密码），不是已验收的 GPU/TLS 公网部署方案；镜像完整构建仍待验证。
默认 Dockerfile worker 也改为单并发，避免绕过 Compose 时启动两个显卡任务。

## 验证证据

- `cloud/job_contracts.xml`：19 项真实 PostgreSQL 合约检查，包括并发提交、投递丢失、重复执行、
  临时/确定性失败、会话丢失、半写入回滚、取消、旧 token、权限、参数重放、录像版本和旧表升级。
- 其中一项实际启动 Redis/Celery worker 与 dispatcher，SIGKILL 正在计算的 worker，重启两进程，确认同一 job 第二次执行成功、
  只保留一份回合/击球结果。仅模型计算替换为合成输出；没有把它当作模型质量测试。
  测试将心跳时间调旧来加速，不声称测出了真实故障恢复耗时。
- `cloud/job_regressions.xml`：60 项上传、OSS 输入协议、计算任务、流水线与序列化检查通过。
- `cloud/job_verification.json`：以上记录及当前相关源文件哈希。原计算包 runtime-v3 保持不变，不含本次 API/队列修改。

复现时使用**专门创建的本地测试容器**，数据库名必须为 shuttl_job_test，Redis 使用该专用容器的 15 号库：

```bash
cd backend
# 以下两个变量使用测试容器的实际地址，不得指向应用数据库。
export SHUTTL_TEST_JOB_DSN='postgresql://postgres:local-test-only@127.0.0.1:测试端口/shuttl_job_test'
export SHUTTL_TEST_JOB_REDIS='redis://127.0.0.1:测试端口/15'
.venv/bin/python -m pytest tests/test_analysis_jobs_postgres.py -q
.venv/bin/python -m pytest tests/test_oss_input.py tests/test_local_upload.py tests/test_tasks.py tests/test_pipeline_v2.py tests/test_serialize.py -q
```

## 边界

取消是计算阶段/进度点的协作中止，不会在一个长 GPU kernel 中立即抢占。worker 崩溃会重算当前任务，尚不保存每阶段计算中间态。
会话锁和结果 token 保护正常重投及旧写入；它们不是网络分区下全局“恰好计算一次”的保证。演示部署应保持一张卡一个 worker。
极端断连可能使旧计算继续到下一个检查点；旧会话恢复前后都必须通过当前 token 才能写结果。

手机后台上传与重接的代码及模拟器验收后续已完成，见 BACKGROUND_UPLOAD.md。
手机远端取消/删除及本地磁盘备份/恢复已完成本地验证，见 REMOTE_LIFECYCLE.md、BACKUP_RESTORE.md。
GPU 性能、真实网络/TLS、手机真机上传、分块续传、OSS 备份和异机传输仍须完成。
