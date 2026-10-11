# Shuttl - 完整开源目录结构(基于实际项目)

## 📁 当前项目实际目录结构

根据你的项目,这是**实际可用**的开源目录结构:

```
Shuttl/
│
├── 📄 README.md                          # ⭐ 项目介绍(中英文)
├── 📄 README_CN.md                       # 中文版详细说明
├── 📄 LICENSE                            # 开源协议(MIT推荐)
├── 📄 CONTRIBUTING.md                    # 贡献指南
├── 📄 CHANGELOG.md                       # 版本历史
├── 📄 .gitignore                         # ✅ 已有
├── 📄 project.yml                        # XcodeGen配置(如果开源)
│
├── 📁 docs/                              # 📚 完整文档
│   ├── README.md                         # 文档索引
│   ├── ARCHITECTURE.md                   # 系统架构设计
│   ├── USER_GUIDE_CN.md                  # 用户指南(中文)
│   ├── USER_GUIDE_EN.md                  # 用户指南(英文)
│   ├── DEVELOPER_GUIDE.md                # 开发者指南
│   ├── API_REFERENCE.md                  # API文档
│   ├── TEST_REPORT.md                    # ⭐ 真机测试报告
│   ├── ML_MODELS.md                      # ML模型说明
│   ├── TROUBLESHOOTING.md                # 常见问题
│   └── images/                           # 文档配图
│       ├── architecture.png
│       ├── ui_flow.png
│       └── ml_pipeline.png
│
├── 📁 iOS/                               # 🍎 iOS应用
│   ├── README.md                         # iOS项目说明
│   ├── project.yml                       # ✅ XcodeGen配置
│   ├── Shuttl.xcodeproj/                 # Xcode项目
│   │
│   ├── 📁 Sources/                       # ✅ 应用源码
│   │   ├── App/                          # 应用入口
│   │   │   └── AppIcon/                  # 图标
│   │   │
│   │   ├── Features/                     # 功能模块
│   │   │   ├── Match/                    # 比赛管理
│   │   │   ├── Replay/                   # 回放分析
│   │   │   ├── Camera/                   # 相机/导入
│   │   │   ├── Statistics/               # 统计数据
│   │   │   ├── Auth/                     # 认证(如果有)
│   │   │   └── About/                    # 关于页面
│   │   │
│   │   ├── Services/                     # 服务层
│   │   │   ├── OnDevice/                 # 本地分析服务
│   │   │   ├── Auth/                     # 认证服务
│   │   │   └── Network/                  # 网络(如果有)
│   │   │
│   │   └── Core/                         # 核心功能
│   │       ├── Design/                   # 设计系统
│   │       ├── Platform/                 # 平台工具
│   │       ├── Storage/                  # 存储
│   │       ├── ML/                       # ML工具
│   │       ├── Tracking/                 # 追踪工具
│   │       └── Rendering/                # 渲染工具
│   │
│   ├── 📁 Packages/                      # ✅ Swift Package模块
│   │   ├── ShuttlCore/                   # 核心框架
│   │   ├── ShuttlDetector/               # ⭐ 羽毛球检测
│   │   ├── ShuttlPlayers/                # ⭐ 球员识别
│   │   ├── ShuttlCourt/                  # ⭐ 场地校准
│   │   ├── ShuttlRally/                  # ⭐ 回合分析
│   │   ├── ShuttlHits/                   # ⭐ 击球分析
│   │   ├── ShuttlReconstruct/            # ⭐ 3D重建
│   │   ├── ShuttlLinker/                 # 轨迹连接
│   │   ├── ShuttlLive/                   # 实时分析
│   │   ├── ShuttlAnalysis/               # 分析流程
│   │   ├── ShuttlRuntime/                # 运行时
│   │   ├── ShuttlPresent/                # 结果展示
│   │   ├── ShuttlDesign/                 # ⭐ 设计系统(Riso Court)
│   │   ├── ShuttlResultsUI/              # 结果UI
│   │   ├── ShuttlCalibrationUI/          # 校准UI
│   │   ├── ShuttlEval/                   # 评估工具
│   │   └── ShuttlExport/                 # 导出功能(可选)
│   │
│   ├── 📁 Resources/                     # 资源文件
│   │   ├── Assets.xcassets/              # 图标、颜色、图片
│   │   │   ├── AppIcon.appiconset/
│   │   │   ├── Colors/
│   │   │   └── Images/
│   │   ├── Models/                       # ⚠️ ML模型(大文件,用LFS)
│   │   │   ├── detector.mlmodel
│   │   │   └── player_classifier.mlmodel
│   │   └── Legal/                        # 法律文档
│   │       ├── PrivacyPolicy.md
│   │       └── Terms.md
│   │
│   ├── 📁 Tests/                         # ✅ 测试代码
│   │   ├── ShuttlTests/                  # 单元测试
│   │   └── Integration/                  # 集成测试
│   │
│   └── 📁 UITests/                       # ✅ UI测试
│
├── 📁 backend/                           # 🐍 Python后端(训练/工具)
│   ├── README.md                         # 后端说明
│   ├── requirements.txt                  # ✅ Python依赖
│   ├── setup.py                          # 安装脚本
│   ├── pyproject.toml                    # 项目配置
│   │
│   ├── 📁 app/                           # FastAPI应用(可选)
│   │   ├── __init__.py
│   │   ├── main.py                       # 入口
│   │   ├── api/                          # API路由
│   │   ├── services/                     # 业务逻辑
│   │   │   ├── tracking/                 # 轨迹追踪算法
│   │   │   ├── calibration/              # 相机校准
│   │   │   └── analysis/                 # 数据分析
│   │   ├── models/                       # 数据模型
│   │   ├── schemas/                      # API Schema
│   │   └── core/                         # 核心工具
│   │
│   ├── 📁 ml/                            # ⭐ 机器学习
│   │   ├── README.md                     # ML模块说明
│   │   ├── train_detector.py             # ✅ 检测器训练
│   │   ├── train_detector_ft.py          # ✅ 微调脚本
│   │   ├── train_hit_rescorer.py         # ✅ 击球评分器训练
│   │   ├── export_coreml.py              # ✅ CoreML导出
│   │   ├── download_dataset.py           # ✅ 数据集下载
│   │   │
│   │   ├── weights/                      # ⚠️ 模型权重(LFS)
│   │   │   ├── detector_best.pth
│   │   │   └── hit_rescorer.pth
│   │   │
│   │   ├── data/                         # 训练数据(不上传)
│   │   │   └── .gitkeep
│   │   │
│   │   ├── exports/                      # ✅ 导出的模型
│   │   └── benchmarks/                   # ✅ 性能测试
│   │
│   ├── 📁 scripts/                       # 工具脚本
│   │   ├── swift_fixtures/               # Swift测试数据生成
│   │   │   ├── live_e2e.py
│   │   │   └── court.py
│   │   └── accuracy/                     # 精度验证
│   │
│   ├── 📁 tests/                         # ✅ 后端测试
│   │   └── data/                         # 测试数据
│   │
│   └── 📁 media/                         # 媒体文件(不上传)
│       └── .gitkeep
│
├── 📁 examples/                          # 📹 示例和演示
│   ├── README.md                         # 示例说明
│   │
│   ├── 📁 videos/                        # ⚠️ 示例视频(小文件或LFS)
│   │   ├── README.md                     # 视频说明
│   │   ├── sample_1min.mp4               # 1分钟示例(~50MB)
│   │   └── sample_calibration.mp4        # 校准示例
│   │
│   ├── 📁 results/                       # 分析结果示例
│   │   ├── match1/
│   │   │   ├── trajectory.json
│   │   │   ├── statistics.json
│   │   │   └── visualization.png
│   │   └── match2/
│   │
│   └── 📁 screenshots/                   # ⭐ 应用截图
│       ├── 01_match_list.png
│       ├── 02_import.png
│       ├── 03_analysis.png
│       ├── 04_trajectory.png
│       ├── 05_statistics.png
│       └── 06_calibration.png
│
├── 📁 tools/                             # 🛠️ 开发工具
│   ├── README.md                         # 工具说明
│   │
│   ├── 📁 icon/                          # ✅ 图标生成
│   │   └── generate_icons.sh
│   │
│   ├── 📁 resign/                        # ✅ 重签名工具
│   │   ├── resign.sh
│   │   └── 立即续签.command
│   │
│   ├── 📁 device-final/                  # ✅ 设备测试脚本
│   │   ├── run-device-tests-v5.sh        # ⭐ 最新测试脚本
│   │   └── README.md
│   │
│   ├── 📁 venue/                         # ✅ 场地工具
│   └── 📁 robustness/                    # ✅ 健壮性测试
│       ├── REPORT.md                     # ⭐ 测试报告
│       └── test_suite.py
│
├── 📁 promo/                             # 🎬 宣传材料
│   ├── README.md                         # 宣传材料说明
│   │
│   ├── 📁 out/                           # ✅ 输出文件
│   │   └── Shuttl-宣传片.mp4             # ⚠️ 64MB(LFS或YouTube链接)
│   │
│   ├── 📁 web/                           # ✅ 网页版宣传页
│   │   ├── index.html
│   │   ├── style.css
│   │   └── script.js
│   │
│   ├── 📁 assets/                        # ✅ 素材
│   │   ├── mascot.png
│   │   └── logo.svg
│   │
│   └── render.py                         # ✅ 渲染脚本
│
├── 📁 .github/                           # ⭐ GitHub配置
│   ├── workflows/                        # CI/CD
│   │   ├── ios_build.yml                 # iOS构建
│   │   ├── ios_test.yml                  # iOS测试
│   │   ├── python_lint.yml               # Python代码检查
│   │   └── python_test.yml               # Python测试
│   │
│   ├── ISSUE_TEMPLATE/                   # Issue模板
│   │   ├── bug_report.md
│   │   ├── feature_request.md
│   │   └── question.md
│   │
│   ├── PULL_REQUEST_TEMPLATE.md          # PR模板
│   └── FUNDING.yml                       # 赞助链接(可选)
│
└── 📁 deliverables/                      # ⚠️ 不上传(内部交付物)
    └── .gitkeep
```

---

## 🚫 绝对不要上传的目录(已在.gitignore)

```
# 构建产物
iOS/build/
iOS/DerivedData/
iOS/Shuttl.xcodeproj/xcuserdata/
iOS/Shuttl.xcodeproj/project.xcworkspace/xcuserdata/

# Python
backend/.venv/
backend/__pycache__/
backend/**/__pycache__/
backend/.pytest_cache/

# 内部文件
.agent-logs/          # AI会话日志
.handoff/             # 项目交接
.claude/              # Claude配置
.ui-backup/           # UI备份
.ml-backup/           # ML备份
.remote-inbox/        # 远程收件箱
deliverables/         # 交付物
screenshots/review-*/ # 内部审查截图

# 临时文件
/tmp/
*.log
.DS_Store

# 敏感信息
*.pem
*.p12
*.mobileprovision
.env
```

---

## 📝 完整的.gitignore文件

```gitignore
# macOS
.DS_Store
.AppleDouble
.LSOverride
*.swp
*~

# Xcode
build/
DerivedData/
*.xcodeproj/xcuserdata/
*.xcworkspace/xcuserdata/
*.xcodeproj/project.xcworkspace/xcuserdata/
*.moved-aside
*.hmap
*.ipa
*.dSYM.zip
*.dSYM

# Swift Package Manager
.swiftpm/
.build/
Packages/
Package.resolved

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.venv/
venv/
ENV/
env/
*.egg-info/
dist/
build/
.pytest_cache/
.coverage
htmlcov/
.tox/
.mypy_cache/

# Jupyter
.ipynb_checkpoints/
*.ipynb

# ML & Data
backend/ml/data/raw/
backend/ml/data/processed/
backend/ml/runs/
backend/media/
*.pth
*.pt
*.onnx

# 大文件 (使用Git LFS或不上传)
# *.mlmodel
# *.mlmodelc
*.mp4
*.mov
*.avi

# 敏感信息
*.pem
*.p12
*.mobileprovision
*.provisionprofile
.env
.env.local
secrets/
credentials/

# 日志
*.log
logs/

# 临时和缓存
/tmp/
.cache/
*.tmp

# 项目特定 - 不开源的内部文件
.agent-logs/
.handoff/
.claude/
.ui-backup/
.ml-backup/
.remote-inbox/
deliverables/
screenshots/review-*/

# IDE
.vscode/
.idea/
*.sublime-*

# npm/Node (如果promo/web用到)
node_modules/
package-lock.json
```

---

## 📦 Git LFS配置(.gitattributes)

对于大文件(ML模型、示例视频),使用Git LFS:

```gitattributes
# ML模型
*.mlmodel filter=lfs diff=lfs merge=lfs -text
*.mlmodelc filter=lfs diff=lfs merge=lfs -text
*.pth filter=lfs diff=lfs merge=lfs -text
*.pt filter=lfs diff=lfs merge=lfs -text

# 示例视频 (仅examples目录)
examples/videos/*.mp4 filter=lfs diff=lfs merge=lfs -text
examples/videos/*.mov filter=lfs diff=lfs merge=lfs -text

# 宣传视频 (或者用YouTube链接代替)
promo/out/*.mp4 filter=lfs diff=lfs merge=lfs -text
```

**注意**: 宣传片64MB可能太大,建议:
1. 上传到YouTube/Bilibili
2. 在README里放链接
3. 或者做个压缩版(10-20MB)用LFS

---

## ⭐ 核心文档内容模板

### 1. 根目录 README.md

```markdown
<div align="center">

# 🏸 Shuttl

**AI-Powered Badminton Match Analysis**

<p>
  <img src="docs/images/app_icon.png" width="150" alt="Shuttl Logo"/>
</p>

[![Platform](https://img.shields.io/badge/platform-iOS%2018%2B-blue.svg)](https://www.apple.com/ios/)
[![Swift](https://img.shields.io/badge/Swift-5.9-orange.svg)](https://swift.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

[English](README.md) | [简体中文](README_CN.md)

</div>

---

## ✨ Features

- 🎯 **Automatic Shuttle Tracking** - AI-powered shuttlecock trajectory detection
- 👥 **Player Detection** - Identify player positions automatically
- 📊 **Match Analytics** - Speed, landing points, rally statistics
- 📱 **On-Device Processing** - No internet required, all ML runs locally
- 🎥 **Video Import** - Support various video formats
- 💾 **Checkpoint Recovery** - Resume from interruptions without data loss

## 🎬 Demo

[![Shuttl Demo](docs/images/demo_thumbnail.png)](https://youtu.be/your-video-id)

**Screenshots:**

<p float="left">
  <img src="examples/screenshots/01_match_list.png" width="200" />
  <img src="examples/screenshots/03_analysis.png" width="200" />
  <img src="examples/screenshots/04_trajectory.png" width="200" />
</p>

## 🚀 Quick Start

### Requirements

- iOS 18.0+
- iPhone 12 or later (Neural Engine required)
- ~500MB storage
- Xcode 16.0+ (for development)

### Installation

#### Option 1: TestFlight (Recommended)
[Join TestFlight Beta](https://testflight.apple.com/join/your-link)

#### Option 2: Build from Source
```bash
git clone https://github.com/yourusername/shuttl.git
cd shuttl/iOS
# Install XcodeGen
brew install xcodegen
# Generate Xcode project
xcodegen
# Open in Xcode
open Shuttl.xcodeproj
```

See [User Guide](docs/USER_GUIDE_EN.md) for detailed instructions.

## 📚 Documentation

- [User Guide](docs/USER_GUIDE_EN.md) | [用户指南](docs/USER_GUIDE_CN.md)
- [Developer Guide](docs/DEVELOPER_GUIDE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API Reference](docs/API_REFERENCE.md)
- [Test Report](docs/TEST_REPORT.md)
- [ML Models](docs/ML_MODELS.md)

## 🏗️ Tech Stack

**iOS:**
- SwiftUI + UIKit
- Core ML + Vision Framework
- AVFoundation
- Combine

**ML:**
- PyTorch (training)
- Core ML (inference)
- Custom TrackNet-based detector
- On-device Neural Engine acceleration

**Backend (Optional):**
- Python FastAPI
- NumPy, OpenCV
- scikit-learn

## 🧪 Test Results

✅ **6/7 tests passed** (86% coverage)

- Checkpoint recovery: 100% success rate
- Error detection: <15s
- Processing speed: ~1x realtime
- Memory peak: ~430 MB

See [full test report](docs/TEST_REPORT.md).

## 🤝 Contributing

Contributions are welcome! Please read [Contributing Guide](CONTRIBUTING.md).

## 📄 License

This project is licensed under the [MIT License](LICENSE).

## 🙏 Acknowledgments

- [TrackNet](https://nol.cs.nctu.edu.tw:234/open-source/TrackNet) - Badminton tracking paper
- Core ML community
- All contributors

## 📧 Contact

- Issues: [GitHub Issues](https://github.com/yourusername/shuttl/issues)
- Email: your-email@example.com
- Discussions: [GitHub Discussions](https://github.com/yourusername/shuttl/discussions)

---

<div align="center">
  Made with ❤️ for badminton players
</div>
```

### 2. README_CN.md (中文版)

把上面翻译成中文,重点突出:
- 本地处理,保护隐私
- 真机测试报告
- 使用场景(业余爱好者、教练)

---

## 🎯 开源前检查清单

### 必做项 ✅

- [ ] 删除所有敏感信息
  - [ ] 清理`.agent-logs/`
  - [ ] 清理`.handoff/`
  - [ ] 删除签名证书
  - [ ] 删除API密钥

- [ ] 添加核心文档
  - [ ] README.md (英文)
  - [ ] README_CN.md (中文)
  - [ ] LICENSE (MIT推荐)
  - [ ] CONTRIBUTING.md
  - [ ] docs/TEST_REPORT.md

- [ ] 准备媒体文件
  - [ ] 至少6张截图
  - [ ] 1个示例视频(小于100MB或YouTube链接)
  - [ ] App图标PNG

- [ ] 配置Git
  - [ ] .gitignore完整
  - [ ] .gitattributes(如果用LFS)
  - [ ] 测试clean clone能否构建

### 推荐项 🌟

- [ ] CI/CD配置
  - [ ] GitHub Actions workflow
  - [ ] 自动测试
  - [ ] 自动构建

- [ ] 完善文档
  - [ ] 架构图
  - [ ] API文档
  - [ ] 开发指南

- [ ] 社区功能
  - [ ] Issue模板
  - [ ] PR模板
  - [ ] Discussion分类

---

## 📊 推荐的GitHub项目设置

### About
```
🏸 AI-powered badminton match analysis app for iOS using Core ML and Vision
```

### Topics (标签)
```
swift, ios, swiftui, machine-learning, computer-vision, 
coreml, sports-analytics, badminton, tracking, swift-package
```

### Homepage
你的项目网页或演示视频

### Features
- ✅ Issues
- ✅ Wiki (放详细文档)
- ✅ Discussions (推荐开启,用户交流)
- ✅ Projects (可选,管理开发)

---

需要我帮你生成具体的某个文档吗(README/测试报告/用户指南)?
