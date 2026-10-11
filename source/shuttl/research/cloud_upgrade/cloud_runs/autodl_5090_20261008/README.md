# RTX 5090 云端首轮 · 2026-10-08

实例：西北B区928机 / e46b4582c4-95dc741d；32GB显存、25vCPU、90GB内存、50GB数据盘。
云端工作目录：`/root/autodl-tmp/shuttl-5090-20261008`。
用户负责续费，明确要求不关机；本轮脚本不会关机或释放实例。

## 已完成

- 三个原始归档上传并通过SHA256验证；本地原始归档保留不变。
- 独立环境复用PyTorch2.8.0+cu128、torchvision0.23.0+cu128；NumPy1.26.4、OpenCV4.11、ORT-GPU1.23.2。
- HitNet、BST、RTMPose、TrackNetV3、WASB、YOLO/NMS的CUDA模型检查通过。
- BST在GPU上6步中断/恢复与连续训练参数误差0、验证记录一致；拒绝冻结后重训和测试数据混入。
- BST首轮2000步完成，1126验证片段：初始化单模型966正确(85.79%)、原十模型983(87.30%)、候选975(86.59%)。
  macro-F1分别0.74498、0.77105、0.76529；新候选未超过产品集成基线，不替换生产权重。
- 本地姿态接口/四框顺序/分母等11项回归通过。

## 两个实际迁移问题

1. ONNX Runtime默认CUDA TF32使冻结参考输入关键点坐标最大偏移43.9453px。
   显式`use_tf32=0`后坐标误差0、分数误差1.64e-6。
   源码修正在`backend/app/services/tracking/rtmpose_core.py`，旧源码保存在本目录originals。
   云解压目录保留原manifest，新的manifest记录来源和变更哈希；不是把原始冻结包静默改写。
2. 同一041视频第18342帧，Mac/Linux解码每通道最多差3，均值差0.613；帧号相同。
   姿态模型数值对照采用经原pixel SHA256验证的无损参考帧；解码差异单独报告。
   三种模型数值误差均在原阈值内（m:1.49e-6，X:2.50e-6，ViT:6.10e-5）。
   full评测仍读取Linux视频，并强制三模型解码像素哈希一致；没有放松同输入公平比较。

## 正在执行

`first_round.sh continue`：1154事件完整姿态验证（29633帧/模型），随后两种球轨迹模型各最多0.5小时训练。
BST限时0.25小时、2000步；轨迹训练时限包含其数据准备与基线评测，允许最多5分钟保存退出。
所有训练只访问Train/validation；未读取held-out Test来选模，未切换手机Release至云端。

## 文件

- `results/`：云端日志、BST权重/对照和后续评测结果回传。
- `bootstrap.sh` / `requirements-overlay.txt` / `prefetch_wheels.py`：安装与依赖哈希记录。
- `apply_precision_overlay.py`：对原始包逐项验哈希后应用GPU精度修正并记录新的manifest。
- `check_pose_precision.py` / `pose-reference-image.npy`：GPU数值问题和跨平台解码对照输入。
- SSH主socket：`/Users/yangcong/.ssh/shuttl_5090_session/control`，密码未写入工程。

这是GPU计算/训练/评测环境。完整API、TLS、手机真实网络联调和双打质量验收仍待完成。
