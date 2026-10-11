# CLAUDE.md — 羽析 (YuXi) 项目交接说明

> 本文件供 Claude Code 自动读取。由上一位助手（Claude 桌面版 Cowork 模式）于 2026-09-24 交接时编写。
> 请用**中文**与用户交流。

---

## 1. 项目是什么

**羽析**：本土化、高审美的羽毛球比赛视频 AI 分析应用，产品思路参考 SwingVision（网球），不抄其代码/界面。
用户上传手机拍的比赛视频 → 标出球场四角 → 自动分析：每个回合、每一拍的击球方与击球类型、落点界内/出界/下网（鹰眼式判定）、比分、跑动热图 → 回放 + 分享图。

**用途**：参加大学生创新创业大赛、华北五省计算机应用大赛。
**硬截止：2026-10-07** 需提交 ①可运行的作品/源码 ②计划书/设计文档。

## 2. 用户情况（非常重要）

- 大学生，**基本不会编程**，团队只有用户本人 + AI。所有操作都要给出一键脚本或可直接复制的命令；报错要主动带着排查。
- 电脑：**Apple Silicon Mac**（M 系列，无 NVIDIA 显卡）→ PyTorch 用 MPS 加速。
- 在国内：GitHub / Google Drive / HuggingFace 可能访问困难。pip 用清华镜像 `https://pypi.tuna.tsinghua.edu.cn/simple`；HuggingFace 可用 `https://hf-mirror.com`。
- 用户希望：形态最好是**原生 App**，做不好则网页兜底；**前端必须好看，最新要求是"全面对标 iPhone App Store 的风格"**（见第 7 节，尚未开始）。
- 用户要求：测试/训练用的视频**自己上网找**（不要让用户去拍），但只用开放许可/学术数据集，不扒 B站/抖音/YouTube。

## 3. 目录结构

```
yuxi/
  CLAUDE.md                 本文件
  使用说明.md               给用户看的使用说明
  安装羽析.command          一键安装 (双击运行): 找 Python -> 建 .venv -> 清华镜像装依赖 -> 自检
  启动羽析.command          一键启动: uvicorn 0.0.0.0:8000, 自动打开浏览器, 打印局域网地址供手机访问
  .venv/                    用户 Mac 上已建好的虚拟环境 (Python 3.12.14 来自 uv; 已装 torch 2.14 / opencv 5.0 / fastapi / uvicorn / numpy 2.5)
  backend/
    server.py               FastAPI 后端 + 单线程分析任务队列 + 静态托管 frontend/
    requirements.txt        torch opencv-python numpy fastapi uvicorn python-multipart
    engine/
      tracker.py            羽毛球追踪: TrackNetV3 预训练权重, 自写流式推理 (fast/accurate), 自动选 cuda>mps>cpu
      tracknet/model.py     TrackNetV3 原版模型定义 (MIT, 保留 LICENSE)
      court.py              场地几何 + 单应性标定 + 界内外判定 (含"存疑"标记)
      players.py            球员检测: YOLOX-S ONNX, 用 cv2.dnn 推理
      analysis.py           回合切分 / 击球检测 / 击球方 HMM / 落点 / 击球类型 / 跑动统计
      pipeline.py           串联全流程; 也可命令行运行
    weights/                TrackNet_best.pt (136MB), InpaintNet_best.pt (6MB), yolox_s.onnx (36MB)  ← 已内置, 无需下载
    data/                   运行时: 每个上传视频一个目录 (video.*, meta.json, track.json, result.json); 可用环境变量 YUXI_DATA 改位置
  frontend/                 原生 JS, 无构建步骤
    index.html  styles.css  court.js (球场几何/绘制/鹰眼卡)  app.js (路由与各页面)  icon.svg   —— v2: App Store 风格, 支持深色模式, 无外部字体
  tools/
    eval_tracking.py        追踪准确率评估 (TrackNet 论文标准)
    fetch_nycu.py           从 NYCU SharePoint 压缩包按需分段下载数据集文件 (需 pip install remotezip)
  dev_data/nycu/            测试数据 (见第 6 节)
```

## 4. 如何运行

```bash
cd ~/Downloads/cowork/yuxi
# 若 .venv 不完整, 可重新装依赖:
.venv/bin/python -m pip install -r backend/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
# 启动服务 (或双击 启动羽析.command)
cd backend && PYTORCH_ENABLE_MPS_FALLBACK=1 ../.venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port 8000
# 浏览器打开 http://localhost:8000
# 命令行直接分析一个视频:
cd backend && ../.venv/bin/python -m engine.pipeline 视频.mp4 --corners "x1,y1,x2,y2,x3,y3,x4,y4" --mode fast --out result.json
# 追踪准确率评估:
.venv/bin/python tools/eval_tracking.py --set Test --mode fast
```

**✅ 2026-09-23 已在用户 Mac（Apple M4, 24GB）上验证**：安装脚本自检通过（PyTorch 2.14 / OpenCV 5.0 / 计算设备 mps）；上传→截帧→分析→结果的完整 API 流程跑通；YOLOX 正常。安装脚本的 Python 候选路径已加入 `~/.local/bin/python3.12`。
**仍未验证**：浏览器播放 iPhone 拍的 HEVC .mov。
开发预览：`.claude/launch.json`（在 cowork 目录）配置了 `yuxi-dev`，端口 8765，`YUXI_DATA=/tmp/yx/data`（开发用演示数据，非提交内容）。

## 5. 算法设计与关键技术决策（计划书"技术创新"素材）

整体流程：`TrackNetV3 追踪球 → 轨迹清洗 → 回合切分 → 候选击球 → YOLOX 球员检测验证 → HMM 判击球方 → 物理约束剔除误检 → 落点判定 → 统计`

1. **追踪 (tracker.py)**：TrackNetV3 预训练权重（输入 8 帧 + 中位数背景，512×288）。自写流式滑窗推理，长视频不爆内存；`fast`=不重叠滑窗，`accurate`=步长 1 + 位置加权时序集成（慢约 8 倍）；InpaintNet 补全被遮挡帧。输出每帧坐标 + `inpainted` 标记（该帧是否由补全得到）。支持 `start_frame/end_frame` 只分析一段。
2. **场地标定 (court.py)**：用户点双打外框四角 → 单应性矩阵（像素↔米）。**只对落地点用单应性**（空中的球投影不准）。坐标系：远端左角为原点，x 0~6.10，y 0~13.40，网在 y=6.70。
3. **击球检测 (analysis.py `_detect_hits`)**：轨迹方向急转点。**羽毛球特有难点**：阻力大，高球到顶点后急剧减速近乎垂直下落，顶点在画面上也是"急转"→ 用**速度比**区分（击球后加速 ratio>1.25，顶点处减速）。角度>120° 必为击球；同向大幅加速(>2.2 倍)为扑杀/抽球。0.3s 非极大值抑制。
4. **球员检测 (players.py)**：YOLOX-S（Apache-2.0，ONNX 来自 OpenCV Model Zoo，cv2.dnn 推理，CPU 约 0.25s/帧）。只保留脚底在球场范围（两侧外扩 1.2m、底线后 2.5m）内的人，排除裁判/观众。**背景减除方案已放弃**（白衣服+浅色广告牌漏检、前后重叠的人粘连）。
5. **击球验证 + 击球方 (HMM)**：球必须在某球员"可击球范围"（人框向上扩 0.9h、左右扩 0.6h）内才算击球；只有一侧球员够得着 = 强证据(±8)，两侧都够得着（画面前后重叠）= 弱证据，交给轨迹方向证据；2 状态（近端/远端）HMM + Viterbi，转移偏好交替击球 (0.85)。
6. **物理约束迭代剔除误检 (`_resolve`)**：①同一方不可能连续击球 → 同侧相邻两拍删掉证据弱者；②判"下网"时落点必须在击球者与网之间，落在击球者身后 = 最后一拍其实没击到（如球员站在球下选择不接）。
7. **落点 (`_landing`)**：球静止(落地)前 0.8s 内画面最低点 = **第一次触地**（不是最终静止点——实测球触地后会被腿/拍碰走近 2 米）。离边线 <8cm 或离网 <0.4m 标**"存疑"**，前端提供人工改判（PATCH 接口），像真实鹰眼挑战。
8. **回合切分**：球静止或长时间消失为边界；球飞出画面顶部 <3s、短暂丢失 <1.2s 不切断回合。
9. **击球类型（实验性）**：规则法——击球者离网距离 + 飞行时间 + 出球速度：发球/高远球/杀球/吊球/平抽/网前球/挑球。界面标注"仅供参考"。

**验证结果**：两段转播视频人工逐帧核对，17 拍长回合击球方全部正确；落点判定正确；一处网前落点正确标为存疑。

## 6. 测试数据与准确率评估（✅ 正式数字见 docs/准确率评估.md）

`dev_data/nycu/`（来自 NYCU TrackNetV2 数据集，学术公开，需引用 TrackNetV2）：
- `Test/match1~3`：**= TrackNetV3 官方测试集（训练未使用）**，专业比赛转播画面，逐帧球坐标标注 `Frame,Visibility,X,Y`。已下载 9 个回合；`match3/1_05_02` 缺标注 csv（可用 tools/fetch_nycu.py 补下）。
- `Amateur/match1`：业余比赛（低机位、底线后），4 个回合视频 + 10 个 csv。可能用于过训练，结果偏乐观。
- 下载源：SharePoint 压缩包 1.7GB，服务器慢（~200KB/s），用 `tools/fetch_nycu.py` 分段只取需要的文件：`python tools/fetch_nycu.py TrackNetV2/Amateur/ 3`。

**已得出的初步结果**（旧版代码、fast 模式、9 个业余回合 2597 帧）：召回率 99.6%、位置误差>10px 仅 3 帧、总准确率 92.0%。损失几乎全来自 **FP2=194（标注无球却报球）且 TN=0**。
**已查明原因**：InpaintNet 把所有"消失段"都补上了坐标——包括被遮挡帧（人工标注记为无球）和**视频开头发球前的帧**（`_inpaint_mask` 中 `i == 0` 分支会把开头整段补全）。
**已做的修改**：tracker 输出新增 `inpainted` 字段；`eval_tracking.py` 分别报告"仅检测"和"含补全"两种口径。
**正式结果（Mac M4）**：官方测试集 3888 帧，精确模式仅检测：准确率 93.1%、精确率 98.5%、F1 95.8%；含补全召回率 99.7%。详见 `docs/准确率评估.md`。
**可选改进**：去掉视频开头的补全（改 `_inpaint_mask` 的 `i == 0` 分支）。

**其他可用的开放许可业余视频**（上次下载后因沙盒重置丢失，需重新下载，适合做业余场景定性测试）：
- Pexels（Pexels License，可免费商用）：视频 ID 35087073 / 35087074 / 35087085（同一球场，高机位底线后，全场可见，1080p）、35427619 / 35427621（竖屏手机固定机位）、32066270 / 32029245。页面 `https://www.pexels.com/video/<id>/`。
- 无人机业余双打数据集 Ding et al. 2023：`https://github.com/Ning-D/Drone_BD_ControlArea`（Google Drive，gdown 下载；每个 `Rally-N` 文件夹里 `(1).mp4` 是底线后视角，最接近目标机位，4K）。
- AI CUP 2023（Zenodo 14677727，CC-BY-4.0，14GB，大部分是转播）——不推荐。

## 7. 进度与待办（按优先级）

| # | 任务 | 状态 |
|---|------|------|
| 1 | 追踪管线 | ✅ |
| 2 | 标定 / 落点 / 回合 / 击球分析 | ✅ |
| 3 | 后端 API + 一键脚本 | ✅ Mac 实测通过 |
| 4 | 前端 v1（"球馆里的鹰眼"风格） | ✅ 但**用户不满意审美** |
| 5 | 在用户 Mac 上跑通全流程 | ✅ |
| 6 | 准确率评估（第 6 节） | ✅ |
| 7 | 前端按 App Store 风格重做 | ✅ v2 完成，等用户反馈 |
| 8 | 业余视频定性测试 + 调参 | ⏳ |
| 9 | 计划书 / 设计文档（docx） | ⏳ 未开始 |
| 10 | 打包成 App（Capacitor，可选） | ⏳ 未开始 |

### 前端 v2（已实现）——对标 iOS App Store
- 系统字体 `-apple-system / SF Pro / PingFang SC`；背景 `#F2F2F7`（分组背景）+ 白色卡片；系统蓝 `#007AFF` 为主色；标签色 `#000`，次要文字 `rgba(60,60,67,.6)`，分隔线 `rgba(60,60,67,.29)`。
- 语义色：界内 systemGreen `#34C759`，出界 systemRed `#FF3B30`，存疑 systemYellow `#FFCC00`；近端球员 `#FF9500`、远端 systemIndigo `#5856D6`（避免与主色蓝冲突）；球场图保留场地绿。
- 底部毛玻璃 TabBar（今天 / 比赛 / 设置），大标题导航（34pt Bold，滚动收起）。
- 自动跟随系统深色 / 浅色模式。应用图标 `icon.svg` 也换成了 iOS 风格的渐变图标。
- **"今天"页**：日期小字 + 大标题"今天" + 右上蓝色"+"（上传）；最新比赛的 Today 风格大卡片（视频帧做封面 + 大比分）、正在分析卡、上传卡、拍摄指南卡、"我的数据"汇总卡。
- **"设置"页**：连接状态（显示计算设备）、服务器地址（写入 `localStorage["yuxi.server"]`，手机/打包 App 用）、拍摄指南、开源组件。
- **"比赛"页**：App 列表样式——圆角方形缩略图 + 标题 + 副标题 + 灰底蓝字胶囊按钮（打开 / 分析中 48% / 去标定）。
- **比赛详情页 = App 详情页**：大图标 + 标题 + 蓝色胶囊"回放"按钮 + 分享；**信息条**（像评分/年龄/排行那一行）放 比分 | 回合 | 总拍数 | 跑动；**"预览"横向滚动卡片** = 各回合落地瞬间截图 + 界内/出界角标；"鹰眼落点"球场图；"双方数据"像"评分及评论"区；"每个回合"列表；"信息"表格（时长、分析方式、设备、引擎版本）。
- 回放弹层用 iOS 卡片式 sheet（带抓手），鹰眼卡保留。
- 标定页改为 iOS 设置表单样式 + 底部固定大按钮；上传进度用居中 HUD；分享海报也改为同一套配色。

### 其他已知问题 / 注意事项
- 前端设置 `localStorage["yuxi.server"]` 可指定后端地址（设置页可改）。
- `server.py` 删除视频用 `shutil.rmtree`；分析任务单线程排队；改标定后重新分析会复用 `track.json`（秒出）。
- 击球类型分类是规则法，平抽/吊球等易混淆。
- 转播视频（开发测试用）**不要放进提交作品**；最终演示应使用开放许可视频或用户自己拍的视频。
- 截图自检：Claude Code 桌面版的浏览器预览（`yuxi-dev`），视口 390×844，可切深色/浅色。

## 8. 开源组件与许可（计划书/README 需注明）
TrackNetV3（MIT）、YOLOX（Apache-2.0, Megvii；ONNX 来自 OpenCV Model Zoo）、PyTorch、OpenCV、FastAPI；数据集 TrackNetV2（NYCU，学术引用）。其余代码为本项目原创。
