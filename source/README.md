# Shuttl 源码浏览快照

这里提供 2026-10-11 从本机整理的文本源码，便于 GitHub 阅读和检索。完整原始工程、模型、训练数据、媒体、宣传片、私有配置和历史资料位于本仓库说明所指向的加密保全归档；继续开发前请按仓库根目录的恢复说明取回原件。

目录：

- `shuttl/iOS/`：Swift App、19 个 Swift 模块、测试、XcodeGen/Xcode 配置、资源文本元信息与第三方许可。
- `shuttl/backend/`：FastAPI/Celery、分析与恢复逻辑、测试、Docker、依赖清单。
- `shuttl/research/`：训练、评测、模型导出、云端部署和研究说明。
- `shuttl/tools/`：真机测试、健壮性测试和开发工具。
- `shuttl/promo/`、`shuttl/promo2/`：宣传片渲染脚本与网页源码。
- `historical-yuxi/`、`historical-yuxi-frontend-v3/`：羽析早期原型及历史前端。

本目录仅保存文本源码。模型、图像、字体、视频、数据集、测试素材和实际配置需要从加密归档恢复；单独克隆本目录不能作为完整构建/训练环境。应用配置以 `shuttl/iOS/project.yml` 为准：Xcode 16.2、Swift 5.10、最低 iOS 17.0。`GITHUB_STRUCTURE*.md` 是历史发布构想，包含示例与未实现占位，不应当作当前工程说明。

源码结构按原工程保存。研究脚本中的旧绝对路径需要在恢复到不同位置后按说明调整。主工程原本没有 Git 提交历史；此快照不会虚构它。

提取与敏感信息检查见 [SANITIZATION.md](SANITIZATION.md)。
