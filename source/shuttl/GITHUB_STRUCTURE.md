# Shuttl - GitHub 开源目录结构规划

## 📁 建议的开源目录结构

```
Shuttl/
│
├── 📄 README.md                    # 项目介绍(中英文)
├── 📄 README_EN.md                 # 英文版README
├── 📄 LICENSE                      # 开源协议
├── 📄 CONTRIBUTING.md              # 贡献指南
├── 📄 CHANGELOG.md                 # 版本更新日志
├── 📄 .gitignore                   # Git忽略文件
│
├── 📁 docs/                        # 📚 文档目录
│   ├── README.md                   # 文档索引
│   ├── ARCHITECTURE.md             # 架构设计文档
│   ├── API.md                      # API文档
│   ├── USER_GUIDE.md               # 用户使用指南
│   ├── DEVELOPMENT.md              # 开发指南
│   ├── TEST_REPORT.md              # 测试报告
│   └── images/                     # 文档图片
│
├── 📁 iOS/                         # 🍎 iOS应用
│   ├── README.md                   # iOS项目说明
│   ├── project.yml                 # XcodeGen配置
│   ├── Shuttl.xcodeproj/           # Xcode项目文件
│   │
│   ├── Sources/                    # 应用源码
│   │   ├── App/                    # 应用入口
│   │   ├── Features/               # 功能模块
│   │   │   ├── Matches/            # 比赛管理
│   │   │   ├── Analysis/           # 分析页面
│   │   │   ├── Calibration/        # 校准界面
│   │   │   └── Settings/           # 设置页面
│   │   ├── Services/               # 服务层
│   │   └── Core/                   # 核心工具
│   │
│   ├── Packages/                   # Swift Package模块
│   │   ├── ShuttlCore/             # 核心功能
│   │   ├── ShuttlDetector/         # 检测器
│   │   ├── ShuttlPlayers/          # 球员识别
│   │   ├── ShuttlRally/            # 回合分析
│   │   ├── ShuttlReconstruct/      # 3D重建
│   │   ├── ShuttlDesign/           # 设计系统
│   │   └── ShuttlResultsUI/        # 结果展示
│   │
│   ├── Resources/                  # 资源文件
│   │   ├── Assets.xcassets/        # 图标、颜色
│   │   ├── Models/                 # ML模型文件
│   │   └── Legal/                  # 法律文档
│   │
│   └── Tests/                      # 测试代码
│       ├── AppTests/               # 应用测试
│       └── UITests/                # UI测试
│
├── 📁 backend/                     # 🐍 Python后端(可选)
│   ├── README.md                   # 后端说明
│   ├── requirements.txt            # Python依赖
│   ├── setup.py                    # 安装脚本
│   │
│   ├── app/                        # FastAPI应用
│   │   ├── __init__.py
│   │   ├── main.py                 # 应用入口
│   │   ├── api/                    # API路由
│   │   ├── services/               # 业务逻辑
│   │   │   ├── tracking/           # 轨迹追踪
│   │   │   ├── calibration/        # 相机校准
│   │   │   └── analysis/           # 数据分析
│   │   ├── models/                 # 数据模型
│   │   └── core/                   # 核心工具
│   │
│   ├── ml/                         # 机器学习
│   │   ├── weights/                # 模型权重
│   │   ├── training/               # 训练脚本
│   │   └── exports/                # 导出工具
│   │
│   ├── scripts/                    # 工具脚本
│   │   ├── swift_fixtures/         # Swift测试数据生成
│   │   └── accuracy/               # 精度验证
│   │
│   └── tests/                      # 测试代码
│
├── 📁 examples/                    # 📹 示例和演示
│   ├── README.md                   # 示例说明
│   ├── videos/                     # 示例视频
│   │   ├── sample_match.mp4        # 示例比赛
│   │   └── calibration_demo.mp4    # 校准演示
│   ├── results/                    # 分析结果示例
│   └── screenshots/                # 应用截图
│       ├── match_list.png
│       ├── analysis.png
│       └── calibration.png
│
├── 📁 tools/                       # 🛠️ 开发工具
│   ├── README.md                   # 工具说明
│   ├── icon/                       # 图标生成
│   ├── resign/                     # 重签名工具
│   └── device-test/                # 设备测试脚本
│
├── 📁 promo/                       # 🎬 宣传材料
│   ├── README.md                   # 宣传材料说明
│   ├── demo_video.mp4              # 演示视频
│   └── presentation.pdf            # 演示文稿
│
└── 📁 .github/                     # GitHub配置
    ├── workflows/                  # CI/CD
    │   ├── ios_build.yml           # iOS构建
    │   └── python_test.yml         # Python测试
    ├── ISSUE_TEMPLATE/             # Issue模板
    └── PULL_REQUEST_TEMPLATE.md    # PR模板
```

---

## 🚫 不应该上传的文件/目录

### 敏感信息
- ❌ `.DS_Store` - macOS系统文件
- ❌ `.env` - 环境变量(包含密钥)
- ❌ `*.pem`, `*.p12`, `*.mobileprovision` - 签名证书
- ❌ `*.log` - 日志文件

### 构建产物
- ❌ `build/`, `DerivedData/` - Xcode构建产物
- ❌ `*.xcodeproj/xcuserdata/` - Xcode用户数据
- ❌ `*.xcodeproj/project.xcworkspace/xcuserdata/` - 工作区用户数据
- ❌ `.venv/`, `venv/` - Python虚拟环境
- ❌ `__pycache__/`, `*.pyc` - Python缓存
- ❌ `node_modules/` - Node依赖

### 临时文件
- ❌ `.agent-logs/` - AI会话日志
- ❌ `.handoff/` - 项目交接文件
- ❌ `.claude/` - Claude配置
- ❌ `.ui-backup/` - UI备份
- ❌ `.ml-backup/` - ML备份
- ❌ `.remote-inbox/` - 远程收件箱
- ❌ `/tmp/` - 临时文件夹
- ❌ `screenshots/review-*` - 内部审查截图

### 大文件
- ❌ `*.mp4` (超过100MB的视频)
- ❌ `*.mlmodel` (大型ML模型,考虑用Git LFS)
- ❌ `deliverables/` - 交付物(内部使用)

---

## 📝 必须创建的核心文档

### 1. README.md (根目录)
```markdown
# 🏸 Shuttl - AI羽毛球分析助手

<p align="center">
  <img src="docs/images/app_icon.png" width="200"/>
</p>

<p align="center">
  <strong>使用计算机视觉和机器学习分析你的羽毛球比赛</strong>
</p>

## ✨ 功能特性

- 🎯 **自动轨迹追踪** - AI识别羽毛球飞行轨迹
- 👥 **球员检测** - 自动识别场上球员位置
- 📊 **数据分析** - 球速、落点、回合统计
- 📱 **移动端运行** - 无需联网,iPhone本地分析
- 🎥 **视频导入** - 支持多种视频格式

## 🎬 演示视频

[观看演示](promo/demo_video.mp4)

## 📱 系统要求

- iOS 18.0+
- iPhone 12 或更新机型(需要神经引擎)
- 约500MB存储空间

## 🚀 快速开始

[查看完整安装指南](docs/USER_GUIDE.md)

## 🏗️ 技术架构

- **前端**: SwiftUI + UIKit
- **ML框架**: Core ML + Vision
- **后端**(可选): Python FastAPI
- **轨迹追踪**: 基于TrackNet的改进模型

## 📚 文档

- [用户指南](docs/USER_GUIDE.md)
- [开发文档](docs/DEVELOPMENT.md)
- [API文档](docs/API.md)
- [架构设计](docs/ARCHITECTURE.md)

## 🧪 测试

查看[测试报告](docs/TEST_REPORT.md)了解完整测试结果。

## 🤝 贡献

欢迎贡献!请阅读[贡献指南](CONTRIBUTING.md)。

## 📄 开源协议

本项目采用 [MIT License](LICENSE)

## 🙏 致谢

- TrackNet论文及开源实现
- Core ML社区
- 所有贡献者

## 📧 联系方式

- 提Issue: [GitHub Issues](https://github.com/你的用户名/shuttl/issues)
- 邮箱: your-email@example.com
```

### 2. docs/TEST_REPORT.md (测试报告)
```markdown
# Shuttl 测试报告

## 测试环境
- 设备: iPhone 16 Pro
- iOS版本: 18.0
- 构建版本: final-1001b
- 测试日期: 2026-10-02

## 测试结果摘要

✅ **6/7 测试通过** (86% 覆盖率)

| 测试 | 状态 | 说明 |
|------|------|------|
| T1: 基础功能 | ✅ PASS | 1分钟视频分析 |
| T2: 长视频 | ✅ PASS | 10分钟视频分析 |
| T3: 锁屏恢复 | ✅ PASS | 应用锁屏后能恢复 |
| T4: 崩溃恢复 | ✅ PASS | 强制关闭后能恢复 |
| T5: 抖动检测 | ✅ PASS | 正确识别手持抖动 |
| T6: 无球检测 | ✅ PASS | 正确识别无羽毛球 |
| T7: 三脚架测试 | ⏸️ SKIP | 待补充 |

## 关键发现

### 1. ✅ Checkpoint恢复机制
- 保存成功率: 100% (60/60)
- 恢复成功率: 100% (2/2)
- 零数据丢失

### 2. ⚠️ 热管理
- 长时间分析会导致设备发热
- 建议: 分析后等待15-20分钟冷却

### 3. ✅ 错误检测
- 11-12秒内快速检测问题
- 准确的中文错误提示

## 性能数据

- 1分钟视频: ~60秒分析 (~1x实时)
- 10分钟视频: ~10分钟分析 (不含热等待)
- 内存峰值: ~430 MB
- 存储占用: ~50 MB/分钟原始视频

详见: [完整测试报告](/tmp/shuttl-device-final-v5-1002-1237/FINAL-REPORT.md)
```

### 3. docs/ARCHITECTURE.md (架构文档)
```markdown
# Shuttl 架构设计

## 系统概览

```
┌─────────────────────────────────────┐
│        iOS App (SwiftUI)            │
│  ┌─────────────────────────────┐   │
│  │   UI Layer (Features)       │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │   Services Layer            │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │   Analysis Packages         │   │
│  │ ┌─────────┐ ┌────────────┐ │   │
│  │ │Detector │ │  Players   │ │   │
│  │ └─────────┘ └────────────┘ │   │
│  │ ┌─────────┐ ┌────────────┐ │   │
│  │ │  Rally  │ │ Reconstruct│ │   │
│  │ └─────────┘ └────────────┘ │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │   Core ML Models            │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

## 核心模块

### 1. ShuttlDetector
羽毛球检测和轨迹追踪

### 2. ShuttlPlayers
球员位置识别

### 3. ShuttlRally
回合分析和切分

### 4. ShuttlReconstruct
3D轨迹重建

## 数据流

1. 视频导入 → 2. 帧提取 → 3. ML检测 → 4. 轨迹重建 → 5. 数据分析 → 6. 结果展示

## ML模型

- **检测模型**: 基于TrackNet的改进版本
- **运行环境**: Core ML + ANE(神经引擎)
- **推理速度**: ~200 fps

详见各Package的README
```

### 4. docs/USER_GUIDE.md (用户指南)
```markdown
# Shuttl 用户指南

## 📱 安装

### 方式1: TestFlight(推荐)
1. 在iPhone上安装TestFlight
2. 扫描邀请二维码
3. 点击"安装"

### 方式2: Xcode直接安装
需要Mac电脑和开发者账号...

## 🎥 如何使用

### 第一步: 录制视频
1. **使用三脚架** - 保持相机稳定
2. **距离**: 底线后约5米
3. **高度**: 约1.6米
4. **位置**: 场地中间
5. **时长**: 建议10分钟以内

### 第二步: 导入视频
1. 打开Shuttl
2. 点击"+"
3. 选择视频
4. 等待分析(约1-2倍实时)

### 第三步: 查看结果
- 轨迹动画
- 球速统计
- 落点分布
- 回合分析

## ⚠️ 注意事项

1. **设备发热**: 分析长视频后,建议等待15-20分钟
2. **存储空间**: 确保有足够空间(约视频大小的2倍)
3. **网络**: 不需要联网,本地分析

## ❓ 常见问题

### Q: 为什么检测失败?
A: 可能原因:
- 相机抖动太大
- 光线不足
- 视频中没有羽毛球

### Q: 多久能分析完?
A: 约等于视频时长(不含热等待)

### Q: 可以分析职业比赛吗?
A: 可以,但需要稳定的拍摄角度
```

### 5. LICENSE
```
MIT License

Copyright (c) 2026 [你的名字]

Permission is hereby granted, free of charge...
(完整MIT协议文本)
```

### 6. CONTRIBUTING.md
```markdown
# 贡献指南

感谢你对Shuttl的兴趣!

## 如何贡献

1. Fork这个仓库
2. 创建你的特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交你的修改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建Pull Request

## 开发设置

查看[开发文档](docs/DEVELOPMENT.md)

## 代码规范

- Swift: 遵循Swift API设计指南
- Python: 遵循PEP 8

## 测试

提交前请确保所有测试通过
```

---

## 🔧 .gitignore 建议

```gitignore
# macOS
.DS_Store
*.swp

# Xcode
build/
DerivedData/
*.xcodeproj/xcuserdata/
*.xcodeproj/project.xcworkspace/xcuserdata/
*.xcworkspace/xcuserdata/

# Swift
.swiftpm/
*.playground

# Python
__pycache__/
*.py[cod]
.venv/
venv/
*.egg-info/
.pytest_cache/

# ML Models (使用Git LFS)
*.mlmodel
*.mlmodelc

# 证书和密钥
*.pem
*.p12
*.mobileprovision
.env

# 日志和临时文件
*.log
/tmp/
.agent-logs/
.handoff/
.claude/
.ui-backup/
.ml-backup/
.remote-inbox/

# 测试产物
screenshots/review-*/
deliverables/

# 大文件
*.mp4
*.mov
```

---

## 📦 Git LFS 配置(大文件)

如果要上传ML模型和示例视频,建议使用Git LFS:

```bash
# 安装Git LFS
git lfs install

# 追踪大文件
git lfs track "*.mlmodel"
git lfs track "*.mlmodelc"
git lfs track "examples/videos/*.mp4"
git lfs track "promo/*.mp4"

# 提交.gitattributes
git add .gitattributes
git commit -m "Add Git LFS tracking"
```

---

## 🚀 开源步骤建议

### 阶段1: 准备(1-2天)
1. ✅ 创建以上所有文档
2. ✅ 清理敏感信息(密钥、证书)
3. ✅ 添加License
4. ✅ 准备README和截图
5. ✅ 测试从零开始的构建流程

### 阶段2: 首次发布
1. 创建GitHub仓库
2. 推送代码
3. 创建Release v1.0.0
4. 添加Tags

### 阶段3: 完善(后续)
1. 添加CI/CD
2. 完善文档
3. 回应Issues
4. 接受PR

---

## 📊 推荐的GitHub项目设置

### Topics(标签)
- `swift`
- `ios`
- `machine-learning`
- `computer-vision`
- `badminton`
- `sports-analytics`
- `coreml`
- `swiftui`

### About
简短描述: "🏸 AI-powered badminton match analysis app for iOS"

### Features
- [x] Issues
- [x] Wiki (可选)
- [x] Projects (可选)
- [x] Discussions (推荐)

---

这个结构能让其他开发者:
1. ✅ 快速了解项目
2. ✅ 轻松上手开发
3. ✅ 找到需要的文档
4. ✅ 看到真实的测试数据
5. ✅ 理解技术实现

需要我帮你生成具体的某个文档内容吗?
