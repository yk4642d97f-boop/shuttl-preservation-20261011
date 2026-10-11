# 本次保全期间实际完成的构建与测试

日期：2026-10-11（Asia/Shanghai）。以下检查在独立副本中执行，原工程没有被修改或写入构建缓存。它们验证当前本机的源码与资源可以构建及通过所列测试；不是全新 Mac、GitHub 下载恢复、真机签名安装、GPU 训练或数据库恢复的替代证明。

| 检查 | 实际结果 |
|---|---|
| 完整 Shuttl App，iOS Simulator，Debug | **BUILD SUCCEEDED**，exit 0 |
| ShuttlCore Swift Package | **21 项通过，0 失败，0 跳过**，exit 0 |
| 后端序列化、手机归档契约、任务失败边界、本地上传 | **34 项通过**，exit 0；2 条依赖弃用提示 |
| 隔离 iOS/素材输入与原工程的 SHA256 对比 | **703 个文件、438,468,113 字节全部一致** |

完整 App 已生成 `Shuttl.app`，同时含 arm64 与 x86_64 模拟器架构；最低 iOS 17.0。五个模型资源实际编译进产品：TrackNetV3、RTMPoseM、ShuttleTracker、BSTStroke、HitNetDetector。构建环境为 Xcode 16.2 / 16C5032a，iPhoneSimulator 18.2 SDK；关闭签名，没有向设备安装，也没有启动应用访问云端。

Swift 测试覆盖 JSON/相机/数值/物理对照、真实视频解码与旋转、重复和跳变时间戳、解码 watchdog 等。首次仅复制小 Package 时缺少原目录布局与外部视频，曾出现 6 项跳过和 1 项失败；随后补齐原布局和原工程中已有的 14 个视频后，全套 21 项通过。测试代码没有被修改或过滤。

后端使用安全源码快照的 `app/`、`tests/` 和 `pyproject.toml` 的独立副本，复用本机现有 Python 3.12 虚拟环境。没有读取实际 `.env`，所选测试使用隔离临时文件与合成对象，不启动 PostgreSQL/Redis 实服务，不连接真实账号或远端 API。禁用 Python 字节码写入，其他缓存均放入验证目录。

## 复现命令

先完整恢复工程及二进制资源。下面的 `RESTORED_ROOT` 应指向恢复后的工程根目录，`VALIDATION_ROOT` 应是独立输出目录；从 GitHub 浏览快照单独运行会缺少模型或测试素材。

```sh
swift test \
  --package-path "$RESTORED_ROOT/iOS/Packages/ShuttlCore" \
  --scratch-path "$VALIDATION_ROOT/swift-build" \
  --cache-path "$VALIDATION_ROOT/swift-cache"

xcodebuild \
  -project "$RESTORED_ROOT/iOS/Shuttl.xcodeproj" \
  -scheme Shuttl -sdk iphonesimulator -configuration Debug \
  -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath "$VALIDATION_ROOT/DerivedData" \
  CODE_SIGNING_ALLOWED=NO build

cd "$RESTORED_ROOT/backend"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/test_serialize.py tests/test_mobile_archive.py \
  tests/test_tasks.py tests/test_local_upload.py \
  -q -o "cache_dir=$VALIDATION_ROOT/pytest-cache" \
  --basetemp="$VALIDATION_ROOT/pytest-tmp"
```

证据摘要、输入文件清单和日志哈希保存在 [validation-evidence](validation-evidence/)。本次原始编译日志留在本地保全目录的 `validation/`，没有把数百 MB 的可再生编译产物混入源码快照。
