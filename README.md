# Shuttl 开发与恢复备份

这是 2026-10-11 为电脑重置准备的 **私有** 开发保全仓库。主工程原位置是 `/Users/yangcong/Downloads/华北五省`。

**Git 克隆不等于完整恢复。** `source/` 是可浏览、经过凭据扫描的源码快照；模型、视频、训练数据、历史版本、数据库、实际配置和开发会话存放在 Release 的加密归档。原始源码和配置均按原字节保留。恢复需要仓库访问权限和持有人单独保存的 age 恢复密钥。

## 备份是否已经完成

完整交付以 Release 中 `github-verification.json` 的 `complete: true` 为准，其中记录每个资产从 GitHub 实际下载后的 SHA-256。尚未出现该文件时，备份仍在进行，不能据此重置电脑。

## 内容入口

| 内容 | 位置 |
|---|---|
| 可浏览的 iOS、后端、研究、宣传工程和早期原型 | [source/](source/README.md) |
| 完整开发环境、业务数据、路径迁移及继续开发说明 | [docs/RESTORE_GUIDE.md](docs/RESTORE_GUIDE.md) |
| 完整性范围和已知缺口 | [docs/COVERAGE.md](docs/COVERAGE.md) |
| 原始文件归档与三部独立宣传/演示视频 | [备份 Release](https://github.com/yk4642d97f-boop/shuttl-preservation-20261011/releases/tag/backup-20261011) |
| 标准库备份读取器及格式文档 | [tools/README.md](tools/README.md) |
| 加密分卷资产索引 | `recovery/payload-index.json` |

## 在新电脑恢复

先安装 GitHub CLI、age 和 Python 3.9+（macOS 可使用 Homebrew），登录拥有仓库访问权的 GitHub 账号。大密文通过 **128 MiB 分片**传输，恢复工具会逐片校验、按序重组并再次核对原完整密文哈希。默认完整恢复会同时保留约 103 GB 密文分片、103 GB 解密归档与约 186 GB 原始文件；建议目标磁盘预留至少 **450 GB 可用空间**，可使用外置磁盘。工具每次只临时拼接一个父密文，解密结束后清理，不永久保存额外一整套合并密文。不要把私有恢复密钥提交到本仓库。

```sh
brew install gh age python
gh auth login
gh repo clone yk4642d97f-boop/shuttl-preservation-20261011
cd shuttl-preservation-20261011
python3 tools/recover_from_github.py \
  --identity /你的安全位置/shuttl-preservation-20261011-RECOVERY-KEY.txt \
  --workdir /足够空间的位置/shuttl-download \
  --destination /一个尚不存在的目录/shuttl-restored
```

恢复目标下的 `Downloads/华北五省` 是完整开发工程。恢复工具会按原路径保存其他目录，将指向旧用户目录的绝对软链迁移到新目标，逐文件验证内容。不要直接把旧版虚拟环境当作新机器可用的环境；依赖清单和具体重建步骤见恢复指南。

仅恢复主工程或宣传工程时可以添加一个或多个 `--include-prefix`，例如 `--include-prefix /Users/yangcong/Downloads/华北五省/promo2`。选取恢复仍需下载归档；它不代表全量资料已恢复。

原始目录清单和每文件 SHA-256 位于解密后的 `manifest.sqlite3`。同字节内容只保存一份数据块，但所有原始路径、软链、硬链和文件元数据均记录在清单中。

## 宣传视频

- [Shuttl-promo-v1.mp4](https://github.com/yk4642d97f-boop/shuttl-preservation-20261011/releases/download/backup-20261011/Shuttl-promo-v1.mp4)：竖屏宣传片，76 秒。
- [Shuttl-promo-v2.mp4](https://github.com/yk4642d97f-boop/shuttl-preservation-20261011/releases/download/backup-20261011/Shuttl-promo-v2.mp4)：横屏宣传片，60 秒。
- [Shuttl-demo-competition.mp4](https://github.com/yk4642d97f-boop/shuttl-preservation-20261011/releases/download/backup-20261011/Shuttl-demo-competition.mp4)：创意与程序演示，约 128 秒。

它们作为普通视频资产保存在私有 Release 中，完整可编辑制作工程、音乐、分镜、截图和中间文件同时保存在加密归档中。

## 交给下一位开发者

授予这个私有仓库的访问权限，并通过独立的安全渠道交付恢复密钥。先完成下载、解密和校验，再阅读恢复指南。历史 AutoDL 备份、早期说明和现在的代码有版本差异，指南明确区分了这些时间点；不要把历史测试结果当作今天重新测试的结果。
