# 两次短租 GPU：实施与采购单

> **2026-10-08 最新：**已换至5090 32GB并完成环境、真实模型CUDA、GPU断点恢复验收。
> BST首轮2000步完成，候选86.59%低于原十模型87.30%，保留原模型；全姿态验证与视觉模型训练正在执行。
> 5090使用PyTorch2.8/CUDA12.8/ORT-GPU1.23.2及显式float32姿态配置，不运行下文旧cu124安装配方。
> 用户负责续费并明确不关机。本次事实与证据以`cloud_runs/autodl_5090_20261008/README.md`为准；下文旧实例/等待GPU文字为历史记录。


更新：2026-10-07。已完成一轮本地 HitNet 训练和评测；云训练包用于接下来较重的球轨迹模型实验。
**云端训练、双打训练、iOS 云端迁移尚未完成。**

用户已提供AutoDL实例并明确授权开始；此前已连通SSH并完成上传。
2026-10-08早上复查时实例已关机，尚未正式训练，正在确认是否重新开机。无需再购买实例。

## 第一次租赁

实际实例：[AutoDL](https://www.autodl.com/home)，RTX4090 24GB×1，22vCPU、90GB内存，
系统盘30GB、免费数据盘50GB；Ubuntu22.04、Python3.12、PyTorch2.5.1、CUDA12.4。
用户提供按量价格约¥2.08～2.19/小时，最终以实例账单为准。

先检查真实GPU、挂载点、可用空间及已有进程。代码、数据和隔离环境优先放数据盘；
不自动购买额外磁盘，不覆盖基础镜像环境。检测训练脚本使用torch2.6/cu124，
冻结推理/姿态脚本使用torch2.4.1/cu124，安装前须核算实际空间，不能把所有依赖重复塞进系统盘。

先做CUDA前向/断点检查，再做短时试训；首批两路检测训练各最多0.5小时，
根据实际速度、验证结果决定后续，而非直接启动原计划的两路6小时。
这两路训练的1 GPU小时约¥2.08～2.19；上传、安装、评测、空闲和其他训练也在计费，不能将其当作总费用上限。
这是一轮低成本有对照实验，不保证单打和双打都达到领先水平。

### 已准备的包

`dist/shuttl-cloud-training-v1.tar.gz`：明确列出的模型代码、权重、公开轨迹数据和训练脚本。
不扫描打包整份工程；不含账号配置、密码、私钥、开发虚拟环境或手机私人录像。
压缩包旁有 SHA256 和逐文件清单，云端 preflight 会逐文件复核。

流程（这些命令由我在获得云实例连接后执行）：

```bash
tar -xzf shuttl-cloud-training-v1.tar.gz
cd shuttl-cloud
bash research/cloud_upgrade/cloud/setup.sh
.venv-cloud/bin/python research/cloud_upgrade/cloud/run_detector.py train --arch tracknetv3 --hours 0.5
.venv-cloud/bin/python research/cloud_upgrade/cloud/run_detector.py freeze --arch tracknetv3
.venv-cloud/bin/python research/cloud_upgrade/cloud/run_detector.py test --arch tracknetv3
.venv-cloud/bin/python research/cloud_upgrade/cloud/run_detector.py train --arch wasb --hours 0.5
.venv-cloud/bin/python research/cloud_upgrade/cloud/run_detector.py freeze --arch wasb
.venv-cloud/bin/python research/cloud_upgrade/cloud/run_detector.py test --arch wasb
```

上面是训练、冻结和测试命令的顺序参考；短试训结束先检查验证结果，确定不再续训后才冻结并打开Test。
实际会先执行小规模 CUDA 性能/显存检查，然后开始主实验。
本地已做 CPU 前向检查；本地没有 NVIDIA GPU，不能把这些检查说成 CUDA 验证。

训练集为 Train 中除 match8 / match16 以外的 24 场，158 个片段；验证为这两场的 14 个片段。
两路分别训练 10 轮，每轮 2,400 时间窗，batch 4，学习率 1e-4，seed 20261007。
继承已有比赛划分，禁止随机拆相邻片段。原始预训练权重可能见过这些 Train 比赛，
因此这个验证集用于微调选模，不代表从未见过的泛化。

先保存原模型的验证指标；微调没有超过原模型时选回原模型。冻结候选 SHA256 后才打开 Test。
**两个架构分别冻结后可以报告测试成绩，但不再按 Test 选架构或调阈值。**
要决定发布哪路，使用预先约定的验证集、计算预算及独立手机录像验收。

每 25 步及每轮末保存 `last.pt`，同一命令可在同一解压路径续训。
进程达到时限会请求保存，最多再给 5 分钟退出；意外中止可恢复最近成功保存的断点。
监督进程意外退出会留下预算标记，需要检查旧进程后恢复，防止重复启动。
脚本限制训练进程时间，**不会自动给租赁平台关机，也不会停止账单**。

CPU 本地检查与断点 smoke 结果放在 `cloud/local_smoke.json`；GPU 初始化、速度和显存结果
在SSH连通并完成实际检查后写入 `cloud_runs/preflight.json` 和日志。

## 训练结束后保存，演示时再开机

回传 `cloud_runs/` 中的 best / last 权重、baseline、selection、heldout、日志与配置，
记录 Python / pip 环境和 GPU 信息；逐一核对 SHA256，确认本地可读取，再释放 GPU。
缓存可删后重建；权重和数据划分不能只留在临时实例里。
平台关机后数据盘是否继续收费、释放后保留哪些文件，应以实例条款为准。

第二次租赁只加载已经选好的权重、启动推理服务和预热，演示时不再训练。
先准备单/双打固定验收视频与已生成报告，保证演示可复现。
在两次租赁之间，手机可以查看已有报告；**云 GPU 关闭时无法进行新的云端重分析**。
如果以后要随时供真实用户上传分析，需按需开机、弹性推理或常驻服务，计费方式会改变。

## App 迁移的实际缺口

```text
手机：录制/选片 → 后台文件上传 → 任务进度 → 报告与回放
云 CPU：视频解码、任务队列、标定/几何、结果组织与存储
云 GPU：球轨迹、四人检测/姿态、击球、球种等神经网络
```

“重计算全部上云”可实现。视频解码、数据库和部分几何计算仍适合云 CPU，
无需强迫每个操作都占 GPU。手机保留拍摄、上传、播放和界面工作。

当前已完成的适配及缺口：

- 新RTMPose/HitNet/BST已接入后端并通过CPU参考检查；runtime-v3是已校验的计算包，尚未做真实CUDA验收。
- 持久队列、幂等/失联恢复、取消/删除与单GPU单任务配置已本地验收；完整API部署包仍缺。
- 手机后台文件上传、重开接续、账号隔离、远端取消/删除已本地验收；服务端分块续传和真机锁屏/切网/长文件仍缺。
- 本地磁盘备份/恢复已验收；实际异机传输、OSS对象备份及真实服务联调仍缺。
- iOS Release仍默认端侧分析。HTTPS、鉴权和手机实际可达性验证通过后才能切换到已部署云服务。
- 姿态三路小面板已完成，完整验证待GPU；四人接口不代表双打精度，真实双打标注与训练仍需补齐。

后续执行CUDA和限时训练、全验证及权重回传；再完成完整服务部署、连续视频验收和真机联调。
此训练包不是已经部署好的手机后端。
