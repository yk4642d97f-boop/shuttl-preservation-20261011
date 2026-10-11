# 手机接入 RTX 5090：2026-10-08

用户约束：保留现有 iPhone UI；不关闭 GPU、不设自动关机；由用户自行续费。已完成 iPhone 数据备份和保留数据的覆盖安装。用户已确认开发者信任、App 能打开，并已登录。用户随后授权寻找公开视频测试并显示到手机，已完成约 21 秒标注单打回合的真实手机上传、GPU 分析、完整报告保存；用户明确确认报告与录像回放都能打开。详见 `../mobile_sample_20261008/REPORT.md`。仅此短片通过真机验收，不扩展为长视频/双打/蜂窝网络保证。

## 已完成

- AutoDL 实名认证及《实例自定义服务》补充协议均由用户本人完成。
- 公网 HTTPS：`https://u1207069-82c4-95dc741d.westc.seetacloud.com:8443`。
- 实例 `e46b4582c4-95dc741d`，RTX 5090 32GB，持续运行。
- PostgreSQL 14、Redis、FastAPI、Celery 单 GPU worker、持久任务 dispatcher、Nginx 已部署，独立 Supervisor 管理进程退出后的重启。
- 数据库只监听 127.0.0.1:5433，Redis 只监听 127.0.0.1:6381，API 127.0.0.1:8000，Nginx 6006 由 AutoDL 映射 HTTPS。上传直接流式写盘，保留原有账号隔离、签名上传、幂等发布和取消/删除机制。日志不记录签名上传 URL 的查询参数。
- `/ready` 检查数据库、Redis 和数据盘基本余量；真实公网 TLS、注册、上传、任务执行、结果下载、跨账号 404 均已验证。
- 云端新增原生分析存档接口 `/matches/{id}/analysis/archive`。保留 VFR 时间戳、逐帧轨迹、置信度/缺失掩码、相机、球员世界坐标、3D 飞行、回合、比分和诊断。手机后台保存到原来的 AnalysisStore，原有报告页面直接读取；旧任务保留旧接口回退。
- 手机将手动球场角点与相机标定传到云端；手动重分析使用稳定幂等键，已确认终态失败后允许用新键重试，网络重试继续沿用原键。
- Release 默认使用已配置的 HTTPS 云端，不再强制启动手机分析模型；旧的本地历史记录不删除。
- 104 个视图、设计、渲染与视觉资源文件 SHA256 均未改变，见 `ui-verification.json`。Info.plist 的 API 地址及云端开关属于连接配置变更。
- 5090 服务使用已验证的 PyTorch 2.8/cu128、NumPy 1.26、ORT 1.23.2。CUDA 推理关闭 TF32，包含姿态模型的 ORT provider 精度修正。

## 验证结果

- 后端本次相关测试：39 passed。另 15 项恢复测试要求专用 Docker 测试容器，未在该命令运行；已另做真实 PostgreSQL 14 全量恢复演练。
- iOS：90 项登录/账号切换/任务生命周期/上传/原生报告/本地分析/修正测试全部通过；追加的终态重试回归及该测试组共 32 项通过（包括先前 31 项），共 91 项不同测试。
- 首次模拟器测试未签名导致 nsurlsessiond 无法建立后台会话；使用正常 ad-hoc 签名重跑后，包括真实后台 URLSession 文件上传，全部通过。没有绕过或跳过该上传测试。
- Release 真机包编译、开发签名通过，路径 `iOS/build/cloud-device/Build/Products/Release-iphoneos/Shuttl.app`，应用标识保持 `com.ycyangcong.shuttl`，团队 `F878S66X7Q`。
- 已在配对、启用开发者模式的 iOS 27.0 iPhone 16 Pro 上覆盖安装，未卸载旧 App。签名校验通过；用户本人完成开发者信任，明确确认 App 能打开、已登录。安装与校验证据见 `device-install.json`、`signature-check.json`。
- 2026-10-08 09:48 UTC（北京时间 17:48）云端检查：6 个服务均运行，公网 `/ready` 返回 ready；生产库已有 1 个非样例账号，尚无非样例比赛或分析任务。用户表示暂时没有录像，未提交真机分析；见 `phone-acceptance.json`。
- 当前个人开发签名有效至 2026-10-15 09:07 UTC（北京时间 17:07）；长期使用需定期续签或使用正式分发方式。
- `https-smoke-report.json`：固定公开验证录像，303 帧，约 10 秒，6,359,136 字节，提供已知球场角点。训练结束后的云端处理约 6.03 秒，含轮询约 6.35 秒。上传约 2.33 秒、压缩报告下载约 0.23 秒（同时在下载实验备份）。5 次击球为 [60,74,87,101,123]，真值 [60,73,86,99,122]，全部在 2 帧内。所有阶段成功。
- 冷启动处理约 26.01 秒；并行训练时复测约 11.30 秒。这些都是单个固定短视频、电脑网络测试，不等于手机蜂窝网络、长视频或双打准确率保证。
- 后续真实手机测试：固定选择 ShuttleSet 验证比赛 041 的第一个标注回合，619 帧、20.63 秒、13 次击球，自动识别球场。手机上传任务处理 12.275 秒；±2 帧击球匹配 13/13，无漏检或多报；球路分类 11/13（84.62%），错误是挑球与推球的两次混淆。手机保存的报告与云端一致，用户确认报告和录像回放均可查看。没有按此片段调参或修改推理结果。
- 本次样例导入修复使已有 `DebugInbox` 入口也支持云端模式，无 UI 修改；7 项相关测试通过。手机原有 30 场 ID 全部保留，新增 1 场样例后为 31 场、241 个回合、6731 个击球点；数据库完整性检查通过。

## 备份与恢复

- 手机备份位于本机私有目录 `/Users/yangcong/Library/Application Support/Shuttl/DeviceBackups/20261008-before-cloud/`（0700）：99 个文件、14,082,015,318 字节，覆盖 Documents、Library/Application Support、Library/Preferences；清单包含逐文件 SHA256，SQLite 完整性检查通过。
- 安装前后均为 30 场比赛、240 个回合、6,718 个击球点，行数完全一致，见 `device-backup-verification.json`、`device-data-preservation.json`。安装后用于核对的数据库副本在备份目录的 `after-install/` 下。
- 设备目录整体复制会卡住，已改用 `/tmp/shuttl-backup-phone-files.py` 逐文件完成备份。再次备份应使用 devicectl 单文件复制；不要将目录复制超时产生的部分文件当成成功备份。
- 服务目录：`/root/autodl-tmp/shuttl-service`。
- 云端完整快照：`backups/20261008T090807Z-5dbf27c876bc.tar`，307,640,320 字节，177 个文件；包括数据库、公开视频测试记录、模型、后端源码、配置。
- 已下载到本机私有目录 `/Users/yangcong/Library/Application Support/Shuttl/CloudBackups/20261008/` 并逐文件核验。该目录含私有配置，权限 0700；不要上传到公共仓库或打印凭据。
- 快照 SHA256：`b6d9108f3a075b0c3604bde707f0fb3d11fd02e3aebc98f2011ed3dbc2440798`。
- 实际恢复到独立数据库 `shuttl_restore_check_20261008`、目录 `restore-check-20261008`，验证恢复的完整报告及视频 SHA256，与生产数据库隔离。见 `restore-rehearsal.json`。
- 快照生成后还有额外的合成账号/公开样例测试记录，不含手机私人录像。第一次快照包含完整部署及一个已完成样例。
- 服务配置/凭据在云端 `config/` 的私有文件；不使用项目中旧开发 `.env`。
- API 退出后的自动恢复已实测约 1.47 秒，见 `api-recovery.json`；本次没有重启容器验证整机开机启动，不应宣称已验证容器重启自动恢复。

## 运维命令

已有 SSH ControlMaster：`/Users/yangcong/.ssh/shuttl_5090_session/control`，SSH `root@connect.westc.seetacloud.com -p 49996`。若会话失效，使用 AutoDL 复制的密码建立新会话，不将密码存入仓库或日志。

服务器上查看服务：

```sh
/root/autodl-tmp/shuttl-service/env/bin/python -m supervisor.supervisorctl -c /root/autodl-tmp/shuttl-service/config/supervisor.conf status
```

若整个应用 Supervisor 未运行，可启动：

```sh
/root/autodl-tmp/shuttl-service/env/bin/python -m supervisor.supervisord -c /root/autodl-tmp/shuttl-service/config/supervisor.conf
```

`bootstrap_service.py` 和 `initialize_service.py` 记录了部署过程；首次 bootstrap 依赖已安装 PostgreSQL/Redis/Nginx/acl 和 service venv。不要在运行时盲目重跑 bootstrap，它会重写配置；日常用 supervisorctl。

## 模型选择

- BST 原始十模型集成验证 983/1126 (87.30%)；本轮训练候选 975/1126 (86.59%)。线上保留原集成。
- 固定 1,154 次带标注击球的全量姿态对比：RTMPose-m 982，RTMPose-X 976，ViTPose++ 981。线上保留 RTMPose-m；这些数字不是整体击球检测 F1 或双打准确率。
- TrackNetV3/WASB 各最多 0.5 小时的首轮训练已结束；实例没有关机。67 个实验结果/日志/权重文件已下载并逐文件 SHA256 核验，凭据见 `cloud_runs/autodl_5090_20261008/results/verified-backup.json`。
- TrackNet 候选最佳验证 F1 0.9598（原模型 0.9555）；最后一步 0.9575。两个固定验证片段复测没有解决 Rally10 的错误击球（仍为 18，真值 60）。因此没有仅按单帧 F1 自动替换线上整条链路；线上仍使用验证过的原始 detector 权重。
- 未将 held-out Test 用于调参。本轮未运行冻结后的最终 held-out。

## 后续验证范围

1. 连接、备份、覆盖安装、开发者信任、App 打开、登录及一个公开短片的完整真机验收均已完成，不要重复要求这些步骤。
2. 设备 CoreDevice ID `0F92DDA9-7A87-4F05-8368-0E834177D8F3`，硬件 UDID `00008140-001159211A3B801C`。
3. 尚未真机验证长录像、双打、离开 App 后恢复、手动球场修正及蜂窝网络切换。用户之后有真实比赛录像时继续；本次已通过的短片上传、报告和录像回放不需要重复补验。
4. 当前个人开发签名到期时间是北京时间 2026-10-15 17:07，届时需要续签或改用正式分发；未配置自动续签，不要承诺长期免维护安装。
