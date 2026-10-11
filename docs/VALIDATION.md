# 本次归档与恢复验证

实际 App 编译、21 项 Swift 测试和 34 项后端测试结果见 [构建与测试报告](../VALIDATION.md)。

本机已从原始归档实际恢复 438 个目录、文件与链接条目到独立新目录，范围包含 Swift/后端源码、CoreML 模型、完整宣传视频、PostgreSQL dump、实际 .env、SSH 部署私钥、Apple 签名身份包、开发历史和应用备份样本。工具逐块及逐文件验证字节和哈希，恢复结果为成功，0 错误、0 警告。此项是明确选择范围的恢复抽查，不是全新系统的全量还原。

完整磁盘访问补扫后，又对新增 8 个项目路径做了实际恢复，包含全部 275 个新增文件及归档中的祖先/子目录，共 **430 个条目**。恢复到全新 `restore-supplement-v2/`，最终 `restored=true`、0 错误、0 警告；报告为 [supplement-restore-report.json](../validation-evidence/supplement-restore-report.json)。两组验证范围包含重复祖先目录，不将条目数相加作为唯一文件总数。

首次补充恢复发现两个微信 ZIP 的原始权限是 0444；旧工具先恢复只读权限，导致 macOS 拒绝后续写入扩展属性。已修复为先恢复扩展属性，再应用最终权限与时间戳，并处理共享硬链接已变只读的情况。新增只读文件及硬链接回归在旧实现上复现失败、修复后通过；18 组归档工具检查与 8 组下载/解密/恢复检查全部通过。两份真实 ZIP 的权限、纳秒修改时间和 quarantine 属性回读均与原件一致；一份 ZIP 的系统管理属性 `com.apple.provenance` 在系统接受写入后仍变成新的值，不能声称恢复后该属性也逐字节相同。原始扩展属性字节已在只读归档清单中逐项核对保存，见 [只读元数据核对](../validation-evidence/supplement-readonly-metadata-check.json)。原失败目录及失败报告保留在本机保全目录，归档原始内容未因修复改变。

完整归档已通过全量校验并封存：825,653 个普通文件、609,438 个数据块逐项验证成功，0 错误。报告见 `validation-evidence/verify-report.json`。加密交付共 209 个资产、103,733,079,102 字节；206 个加密资产全部通过实际解密和明文 SHA-256 回读，另有 3 个独立视频。见 `validation-evidence/encryption-report.json`。GitHub 远端下载回读由上传流程执行；以 Release 中 `github-verification.json` 的 complete=true 为完整上传成功条件。
