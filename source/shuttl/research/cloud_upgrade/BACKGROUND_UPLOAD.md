# 手机后台上传准备（2026-10-07）

本轮改动为真实 iOS 后台文件传输、持久完成回执及应用重启后重接。云端尚未部署，Release 默认本机分析保持原配置；
这些代码会用于后续云分析路径，不会把当前用户录像发送到一个未验收的服务。

## 实现

- VideoUploadService 使用固定标识 `com.ycyangcong.shuttl.video-upload.v1` 的后台 URLSession；
  `uploadTask(with:fromFile:)` 交给系统读取文件，没有将整段录像装入应用内存。
- ShuttlAppDelegate 接收系统的后台会话事件。UploadTransport 将 delegate 回调按顺序转交 actor，
  完成状态落盘后才调用 iOS completion handler，避免系统结束后台时间时丢掉回执。
- Application Support/Uploads/receipts-v1.json 保存比赛的哈希命名空间、文件身份、每次上传的 generation 和状态。
  以原子写入保存，使用首次解锁后的文件保护并排除设备备份。应用自己的回执不保存上传 URL、签名或账号 token；
  系统 URLSession 自行管理正在传输的请求。
- 新上传先创建暂停的系统任务，再保存 generation，最后 resume。重启枚举系统任务，通过 taskDescription 的 generation 重接。
  崩溃发生在创建任务但回执尚未写入时，该未知任务被取消；不会把未知任务认作成功。
- 同场比赛的并发调用复用一次传输；已完成的回执可在重启后直接使用，不必重新取签名或重传。
  文件路径、长度、修改时间用于检测本地录像变更（不是完整内容哈希）。录像不应原地修改；后端也禁止不同文件覆盖已发布 key。
- 签名地址只在确需新尝试时取得。网络错误、服务端暂时性失败、401/403 等最多尝试 3 次，每次重新取签名；
  超出大小/冲突等问题直接报告。系统中断与用户明确取消分开处理；明确取消不会重试。
- 如果服务器报告录像丢失，MatchPipeline 先清除本地完成回执，再上传；不会被旧回执卡住。
- 退出登录会取消系统上传，云流水线停止等待；删除本地比赛会清除对应上传回执并取消传输。
  这是文件上传的取消，云端分析任务的远端取消/录像删除仍须接通。
- 回执文件损坏时保留诊断副本、取消无法归属的系统任务，再从新上传开始。回执无法写入时不会报成功。

## 证据

- `cloud/ios_background_verified.xcresult` / `.log`：46 项检查，包含原有 MatchPipeline 30 项、
  后台状态/恢复/取消/重试 15 项，以及真实后台 URLSession 的本地 HTTP 文件传输 1 项。
  真传输检查核对服务器收到的 256 KiB 文件 SHA256。
- `cloud/upload_relaunch_smoke/relaunch-verification.json`：独立模拟器应用直接编译实际 uploader、transport、VideoStore 和 AppDelegate 源文件。
  上传 16 MiB 测试文件，服务器收到 512 KiB 后 SIGKILL 测试应用，再启动一个新进程。
  两次应用启动仅请求一次上传地址，服务器仅收到一次完整 PUT，最终 SHA256 一致。
  这验证了模拟器上的实际进程重接；没有用模拟回调代替这项检查。报告包含实际源文件哈希。
- 原有状态测试还模拟了丢失系统任务、已完成回执、旧回调、文件变更、回执损坏/写入失败、过期签名、服务端丢失文件和退出登录。
- 初期真传输测试失败：`CODE_SIGNING_ALLOWED=NO` 产生的应用未绑定 bundle ID，nsurlsessiond 拒绝连接。
  使用正常模拟器 ad-hoc 签名后通过；保留原失败日志，不修改系统安全配置或改用普通会话冒充后台传输。

本地复现（需要 Xcode 16.2、iOS 18.3 simulator；使用实际设备 ID）：

```bash
xcodegen generate --spec ios/project.yml
xcodebuild -project ios/Shuttl.xcodeproj -scheme Shuttl \
  -destination 'platform=iOS Simulator,id=模拟器ID' -parallel-testing-enabled NO \
  -only-testing:ShuttlTests/VideoUploadServiceTests \
  -only-testing:ShuttlTests/MatchPipelineTests \
  -only-testing:ShuttlTests/BackgroundUploadTransportTests \
  CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=- test
```

独立进程重启检查位于 `cloud/upload_relaunch_smoke/`：先 xcodegen/build（必须签名），启动 `python3 server.py`，
再运行 `python3 check_relaunch.py --simulator 实际ID`。只对 fixture bundle `com.ycyangcong.shuttl.uploadsmoke` 操作；
不删除主 Shuttl 应用或访问其录像。每轮使用新 server 状态文件，旧报告须先归档；检查脚本拒绝混合已有上传记录。

## 明确边界与下一步

- SIGKILL 后主动重新打开的模拟器检查，不等同于真机上各种退出/重启方式都通过。
  用户从应用切换器强制划掉 App 时，iOS 可以取消后台传输，并且不会保证自动唤醒；再次打开后才恢复检查或重试。
- 当前仍是整文件 PUT。只要系统保留原任务，就可重接；若原任务丢失，需要从头传该文件。
  尚未实现服务端分块/按字节偏移续传，不能宣称任意断网都从原字节继续。
- 后台上传完成会保存回执；云分析触发由已存在的登录流水线或下一次打开应用负责，不保证冷启动后台时间内一定提交分析。
- 真机锁屏、低电量、Wi-Fi/蜂窝切换、长时间/大文件上传、TLS 和真实 OSS bucket 尚未验收。
  后续需联调手机远端取消/删除、账号数据归属/保留与云端存储生命周期。
- 这些可靠性检查没有新增模型精度结果；单打/双打能力仍按已有模型卡和待完成数据验收判断。
