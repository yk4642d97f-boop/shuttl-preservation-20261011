# 两次短租之间的备份与恢复

2026-10-07：已完成本地磁盘存储方案的实际导出、空库恢复和训练续跑演练。入口是 `backend/app/maintenance/recovery.py`。没有租用 GPU，没有读取或备份用户的实际比赛数据库；所有数据库演练使用隔离容器和合成比赛。

## 保存什么

一次快照包含 PostgreSQL 自定义格式导出、已发布录像、所指定的模型/代码/训练输出目录，以及配置文件。文件逐项记录 SHA256 和长度，采用流式读写，不将整段录像读进内存。完成后重新读取整个归档校验，才发布为 `.tar`。

备份目录另有 `latest-deletions.json`，保留这个数据库所有已知删除记录及递增版本。恢复较旧快照时必须叠加它，先删除相关比赛、级联结果和恢复出来的录像，再生成可启动配置。这个文件必须与快照一起保存和转移；不能只拿一个旧 `.tar` 恢复。数据库的 `shuttl_recovery_identity` 小表记录稳定来源标识，防止不同实例的删除记录混用。

归档不包含 Redis 消息：数据库已经是任务的权威来源。恢复后原 queued/running/retry 任务回到 queued，清除旧 claim token、进度、投递和心跳，保留尝试次数；已完成和已取消任务保持原状态。dispatcher 会重新投递仍应执行的任务。

配置中的四项显式模型路径会根据归档目录重新定位：SHUTTL_WEIGHTS_DIR、SHUTTL_HITNET_WEIGHTS、SHUTTL_BST_MANIFEST、SHUTTL_RTMPOSE_WEIGHTS。恢复生成新的 `runtime.env`，替换数据库、Redis 和媒体路径，其他配置值保留。模型、训练数据及脚本内部使用的其他路径仍须按新目录传入；训练数据应与其 manifest 一起归档。

## 一致性与失败行为

- 操作前停止 API、dispatcher、worker 和训练进程，等待训练断点写完。不要让原实例和恢复实例同时处理同一批任务。
- 工具另外会锁定 Shuttl 表，之后才导出同一个 PostgreSQL 快照；仍允许 pg_dump 读表，但阻止本地上传的最终发布和其他写入。若有持有比赛锁的活跃 worker，备份拒绝继续。
- 检查 BST `.run.lock`，复制期间保留共享锁；逐文件和整棵目录检查写入/替换/新增/删除。训练应先停止，不能把文件校验当成任意训练器的在线事务快照。
- 未完成 `.part` 上传与 `.analysis` 下载缓存不归档；状态尚为 uploading 的比赛允许暂缺录像，由手机重新上传。其他比赛缺视频时拒绝备份。
- 配置指向归档之外的模型、目录重叠、符号链接、特殊文件或源文件在复制时发生变化，都会拒绝发布快照。
- 恢复先完整校验，再创建一个全新的目录，并只接受空数据库。现有库、现有目录、损坏/缺失/落后的删除记录及来源不符均拒绝覆盖。
- pg_restore 用单事务导入；后续删除重放/文件落盘失败时不生成 `runtime.env`，保留 `RESTORE_IN_PROGRESS.json` 的 failed 标记。整个数据库和文件系统无法组成一个共同事务，因此失败目标需检查后放弃，重试到另一个空库和新目录，不能启动失败目标。
- 只有 `restore-report.json` 中 state 为 complete、且没有 `RESTORE_IN_PROGRESS.json` 时才启动服务。恢复目录不保留另一份旧数据库 dump。

## 第一次租卡结束前

以下路径是部署布局示例，不是已经存在或已经部署的服务器。原始录像与备份库不能位于被归档的模型目录里。所有依赖必须纳入指定 asset 目录；虚拟环境可以根据固定依赖重建。

先在受控终端环境中设置 `SHUTTL_RECOVERY_DSN`，值为原 PostgreSQL 连接 URL；不要把它作为命令行实参写进历史。配置文件必须明确写 `STORAGE_BACKEND=local`，且包含实际部署使用的显式模型路径。

```sh
cd /srv/shuttl/runtime/backend
python -m app.maintenance.recovery backup \
  --repository /mnt/durable/shuttl-backups \
  --media /srv/shuttl/media \
  --config /srv/shuttl/live.env \
  --asset runtime=/srv/shuttl/runtime \
  --asset training=/srv/shuttl/training-runs
```

本机须有与 PostgreSQL 服务兼容的 pg_dump/pg_restore。若使用标准 PostgreSQL Docker 容器，可增加 `--pg-container 容器名`；工具通过环境传递连接字段，不在 argv 或成功输出中显示密码。容器模式要求指定容器就是该数据库服务器，容器内 PostgreSQL 端口为 5432；宿主 Python 仍用提供的 DSN 连接并导出快照。

备份结束后，把整个备份目录复制到租赁盘之外的持久存储或自己的电脑，包括 `latest-deletions.json`。在接收端再次运行：

```sh
python -m app.maintenance.recovery verify /保存位置/shuttl-backups/实际快照名.tar
```

接收端验证通过以后再释放租赁盘。工具不能确认所选目录是否随租赁实例销毁；本机演练也不能代替真实跨主机传输验证。快照含账号密码哈希、录像和部署密钥，以 0600 权限写入；不应进入公开代码包，复制时使用受控的加密传输/存储。SHA256 检查损坏，不提供对任意第三方备份的身份认证。

## 第二次租卡启动时

建立空 PostgreSQL 数据库和新的 Redis 实例/数据库。将 `SHUTTL_RECOVERY_DSN` 指向新空库，`SHUTTL_RECOVERY_REDIS_URL` 指向新的 Redis；这些地址应能被后续运行的 API/worker 访问。恢复命令不清空任何 Redis，也不会检查或连接该地址。

```sh
python -m app.maintenance.recovery restore \
  --repository /mnt/durable/shuttl-backups \
  --snapshot /mnt/durable/shuttl-backups/实际快照名.tar \
  --destination /srv/shuttl/restored
```

检查完成报告后，从 `runtime.env` 加载环境，在恢复的代码目录启动 API、单并发 worker、dispatcher。使用新目录运行模型前向检查，再连接手机；CUDA、依赖和 TLS 的验收仍是单独步骤。原 `.env` 保存在 config/source.env 作参考，启动时应使用生成的 runtime.env。

恢复中的 active 任务并不等于从视频中断帧继续计算：当前分析 worker 会重算该任务。训练断点是另一条机制，包含 optimizer/RNG，按训练器的 `--resume` 接着训练。

## 实际证据

- `cloud/recovery_final.xml` / `.log`：20 项检查，0 失败、0 跳过，使用实际 PostgreSQL 16 pg_dump/pg_restore。
- 覆盖数据库/录像/配置/训练状态恢复、旧快照叠加新删除记录、缺失/损坏/过期删除记录、拒绝覆盖现有数据、损坏快照拒绝、文件变化、活跃训练/worker、上传发布锁、等待删除事务后再取快照、恢复后 outbox 再投递并完成分析、恢复中途失败标记，以及不安全归档路径/链接拒绝。
- `cloud/recovery_training.json`：使用真实发布的 BST 初始模型和既有小型机制测试数据，在 CPU 训练至第 3 步，备份后移走原代码/数据/训练目录；在恢复目录续跑到第 6 步。94 个归档文件校验通过，恢复前后断点 SHA256 相同，最终参数最大误差 0，验证记录和 CPU RNG 与既有不中断 6 步参考完全一致。
- 以上是恢复和续跑机制验证，不是精度提升实验，不代表 CUDA 跨版本确定性。保存了源文件和证据哈希，见 `cloud/recovery_verification.json`。

复现测试需要有 `shuttl.test=recovery` 标签、端口仅绑定 127.0.0.1 的专用测试 PostgreSQL Docker 容器。测试会创建并删除自己生成的数据库，不得使用实际部署库：

```sh
cd backend
SHUTTL_TEST_RECOVERY_DSN='postgresql://postgres:local-test-only@127.0.0.1:64260/postgres' \
SHUTTL_TEST_RECOVERY_CONTAINER=shuttl-recovery-pg \
SHUTTL_RECOVERY_TRAINING_REPORT='../research/cloud_upgrade/cloud/recovery_training.json' \
.venv/bin/python -m pytest tests/test_recovery.py -q
```

## 当前范围

这是本地磁盘存储部署的自包含备份；`STORAGE_BACKEND=oss/auto` 会明确拒绝，避免仅保存对象 key 就冒充已备份录像。OSS 导出/异地对象恢复尚未实现和联调，不能把本次结果覆盖到 OSS 部署。

最新删除记录只能覆盖它最后一次备份时已知的删除；之后新增的删除需要再次备份并复制最新记录。旧归档本身仍保留当时的历史内容，需要按保留策略销毁，不能宣称所有备份中的数据已物理擦除。

完整 GPU/API 部署包、服务器分块上传、真实异机传输、CUDA、TLS 和真机联调仍待完成。runtime-v3 计算包保持冻结，尚不包含本工具。
