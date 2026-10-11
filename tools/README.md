# Shuttl 本地保全工具

`shuttl_backup.py` 只使用 Python 3.9+ 标准库，适用于 macOS/Linux。它不连接网络、不上传、不加密、不修改来源文件。归档含原始文件内容、路径和扩展属性，必须由上层流程加密后再上传。

## 从 GitHub 恢复

新电脑先安装 Python 3.9+、GitHub CLI `gh` 和 `age`，登录有权访问私有仓库的 GitHub 账号，然后克隆仓库。macOS 可用 `brew install python gh age` 安装运行工具。恢复私钥必须从电脑之外的可靠保存位置取回；不要提交到 GitHub。

```sh
gh auth login
gh repo clone yk4642d97f-boop/shuttl-preservation-20261011
cd shuttl-preservation-20261011
python3 tools/recover_from_github.py --identity /secure/location/shuttl-recovery-key.txt --workdir /new/disk/shuttl-recovery-cache --destination /new/disk/shuttl-restored
```

仓库和 release tag 默认分别是 `yk4642d97f-boop/shuttl-preservation-20261011`、`backup-20261011`，可通过 `--repository`、`--tag` 指定。可信清单默认读取克隆目录中的 `recovery/payload-index.json`，不会从网络下载未固定的清单来替代它。此文件将由交付流程在加密完成后写入仓库；缺失或 `complete` 不为 true 时恢复会停止。

`recover_from_github.py` 按清单中的每个确切名称执行 `gh release download`，验证密文字节数及 SHA-256，再使用外部私钥 `age --decrypt` 解密每个资产，并验证明文 SHA-256。它核对封存资产列表，执行完整 `shuttl_backup.py verify`，最后恢复到指定新目录。不会重新 seal。GitHub token 和私钥内容不写入命令日志，不复制私钥。

只下载并验证密文，可不提供私钥和恢复目录：

```sh
python3 tools/recover_from_github.py --workdir /new/disk/shuttl-recovery-cache --download-only
```

支持断点重跑：工作目录绑定同一仓库、tag 和可信清单哈希；已经存在且校验一致的密文/明文直接复用。损坏的缓存会改名保留为 `.invalid-*`，随后重新下载或解密。已存在的非空普通目录没有恢复标记时拒绝作为缓存目录。恢复目的目录必须不存在；失败后留下的目的目录不能直接覆盖，应排查后选择另一新目录。

只恢复若干目录/文件时添加可重复 `--include-prefix`，值必须使用清单中的原电脑绝对路径：

```sh
python3 tools/recover_from_github.py --identity /secure/location/shuttl-recovery-key.txt --workdir /new/disk/shuttl-recovery-cache --destination /new/disk/shuttl-media-sample --include-prefix /Users/yangcong/Downloads/华北五省/promo2 --include-prefix /Users/yangcong/Downloads/shuttl.mp4
```

范围选择只限制最后恢复出的文件；为了验证完整归档，helper 仍会下载、解密并验证全部归档资产。磁盘需要容纳密文缓存、明文归档以及选定恢复结果。`recovery-report.json` 记录 `full_archive_restored`；抽样恢复不会被标成完整恢复。完整命令与退出码保存在缓存的 `commands.json`，归档/恢复详细报告也保存在缓存。失败返回退出码 2，不会报告成功。

单独宣传视频 `standalone_video` 不属于加密归档资产，helper 会明确跳过；原件仍包含在完整备份中。也可以直接下载 release 中的三个独立可播放 MP4：

```sh
gh release download backup-20261011 --repo yk4642d97f-boop/shuttl-preservation-20261011 --pattern 'Shuttl-*.mp4' --dir /new/location/promo-videos
```

## 配置与操作

配置使用 UTF-8 JSON。`roots` 是具体文件或目录；`category` 写入清单方便检索。`excludes` 只按规范化绝对路径的完整前缀排除，不作名称/通配符匹配。不隐式排除 `.git`、虚拟环境、构建物或隐藏文件。软链只保存链接本身，不跟随遍历。

```json
{
  "roots": [
    {"path": "/Users/yangcong/Downloads/华北五省", "category": "main-project"},
    {"path": "/Users/yangcong/Downloads/shuttl.mp4", "category": "promo-video"}
  ],
  "excludes": [
    "/Users/yangcong/Downloads/shuttl-preservation-20261011"
  ]
}
```

以下路径是示例，执行时换成实际配置与新归档目录：

```sh
python3 tools/shuttl_backup.py inventory --config config.json --archive archive --output inventory.json
python3 tools/shuttl_backup.py create --config config.json --archive archive
python3 tools/shuttl_backup.py verify --archive archive --output verify-report.json
python3 tools/shuttl_backup.py restore --archive archive --source-prefix /Users/yangcong --destination /new/location/shuttl-restored --output restore-report.json
```

`inventory` 只做 lstat 盘点，不读取普通文件内容。错误会记录并以退出码 `2` 返回；它不会验证某个普通文件的内容可读性，`create` 才验证。

`create` 自动排除位于来源树中的归档输出目录。它为每个文件记录绝对路径、类别、权限 mode、mtime/atime 纳秒值、uid/gid、设备/inode/硬链数、单文件 SHA-256、块顺序、xattr 和状态。软链目标逐字保存。macOS 使用标准库 ctypes 调用系统 xattr 接口；Linux 使用 os 接口。缺失、不可读、特殊文件、xattr 读取失败、读取前后文件变化以及整次运行结束时发现的源文件变化都会明确报错，`complete=false`，退出码 `2`。不静默跳过。

重复执行完全相同的 `create` 命令可续传。已完成且文件签名未变的条目复用；其他条目重新读取并按内容哈希复用块。断电后未提交到 SQLite 的完整块会校验并重新索引；末卷未提交的残帧可截断重建。已被清单引用的截断或损坏不会自动丢弃。配置不能在同一归档上改变。

每 250 条或约 1 秒批量将当前数据卷 flush/fsync，然后提交 SQLite；大文件读取过程中也按约 1 秒持久化新对象。轮换旧卷前先 fsync。只会在数据已持久化后提交其清单引用。`.create.lock` 使用 flock 拒绝同一归档的并发 create。

创建时每约 10 秒输出 JSON 进度，最后进行来源二次遍历与存在性检查。工具没有创建文件系统原子快照；需要减少源文件变动，并在任何变化报错后重新运行 create。`create-report.json` 的 `complete=true` 与 `verify` 的 `verified=true` 是后续交付的必要检查项。

## 上传前封存

创建与恢复抽查完成后，可在验证时加 `--seal`：

```sh
python3 tools/shuttl_backup.py verify --archive archive --seal --output verified-and-sealed.json
```

这会验证所有块和文件，再流式计算清单和每个卷的 SHA-256，写入 `archive/SEALED.json`，将这些资产权限置为只读，并禁止后续 create 修改此归档。封存过程也持有 create 互斥锁。加密和上传必须在封存完成后进行。将 `manifest.sqlite3`、全部 `volumes/volume-*.bin`、`SEALED.json` 以及本工具一并保存；没有清单无法恢复目录结构。`create-report.json` 可同时保存作为证据。`.create.lock`、`manifest.sqlite3-wal`、`manifest.sqlite3-shm` 不属于交付内容；正常完成并关闭连接后 WAL 已 checkpoint。

封存后恢复或验证仍可读取。需要更新备份时建立新归档，不要修改已上传卷。`SEALED.json` 包含源文件路径以外的归档资产名称、大小和哈希，不含文件内容。

封存的只读清单使用 SQLite `immutable=1` 打开，因此新电脑解密后无需先创建 WAL/SHM 边车文件；如果封存目录意外出现非空 WAL，工具会明确拒绝忽略该 journal。未封存归档仍正常读取 WAL。

## 恢复规则

磁盘空间不足时，可以抽样恢复指定来源文件/子目录；`--include-prefix` 可重复，按完整路径边界匹配，不是通配符：

```sh
python3 tools/shuttl_backup.py restore --archive archive --source-prefix /Users/yangcong --destination /new/location/sample --include-prefix /Users/yangcong/Downloads/华北五省/promo2 --include-prefix /Users/yangcong/Downloads/shuttl.mp4 --output sample-restore-report.json
```

抽样恢复会带上清单中必要的祖先目录及其元数据。报告 `scope.mode=selected-prefixes` 和 `full_archive_restored=false` 明确表示只恢复了所选范围；`restored=true` 仅说明所选范围成功。若选中的是硬链，而其原件不在恢复范围内，工具按该条目的块恢复成独立普通文件，并在 `hardlinks_restored_as_independent_files` 报告，不要求额外恢复原件。没有任何条目匹配的前缀会报错。

- `--destination` 必须是不存在的新目录，默认没有覆盖功能。不会替换原开发目录。
- `/Users/yangcong` 前缀下的条目恢复为目的目录下的同一相对路径。
- 其他绝对来源路径恢复到 `目的目录/rootfs/原绝对路径去掉开头斜线`。
- 指向原来源前缀的绝对软链重写到目的目录；相对软链保留原值。其余绝对软链保留并报告为 external。即使指向外部，也不会跟随它写文件。
- 所有目录先建立，普通文件/硬链其次，软链最后。写入时检查父目录不为软链，文件使用排他创建，拒绝 `..` 路径和重复目的路径。
- 普通文件恢复时再验证每块 SHA-256、文件 SHA-256 与大小。硬链恢复为真正的同 inode 链接。
- mode、mtime/atime、xattr 恢复失败会明确报告。uid/gid 保留在清单但不自动 chown，恢复内容属于当前用户；ACL、文件系统 immutable 标志和稀疏布局没有单独重建。文件字节包括稀疏区域逻辑零字节均保存。
- 默认拒绝不完整归档。`--allow-incomplete` 是显式抢救选项，只恢复状态为 ok 的条目，不意味着资料完整。
- 恢复失败时留下新目录供排查；重新恢复应指定另一个新的目的目录。

## 格式说明（可独立实现读取器）

每个普通文件按固定 67,108,864 字节分块，最后一块可更短。空文件无块，文件哈希是 SHA-256 空字符串。每块按未压缩字节计算 SHA-256，相同块只存一次。小于 1 MiB 的块使用 zlib level 1；更大的块分散采样四段 64 KiB（总共 256 KiB），若采样用 level 1 压缩后的比例 ≥0.99，整块用 zlib level 0，否则用 level 1。这减少对已有 tar.gz/视频再次压缩的 CPU 时间，仍是原格式的完整 zlib 流，原 SHA-256、块引用、卷上限和读取器不变。已写入的块不重编码，续传仍复用已有持久化块。不存在密钥、上传或加密实现。

每个 `volume-000001.bin` 等卷不大于 536,870,912 字节。卷开始是 8 字节 ASCII `SHUTBKP1`。随后依次连接帧：

| 字段 | 长度 | 表示 |
|---|---:|---|
| 标记 | 4 字节 | ASCII `CHNK` |
| 原始块哈希 | 32 字节 | SHA-256 二进制值 |
| 原始长度 | 8 字节 | unsigned big-endian |
| 压缩长度 | 8 字节 | unsigned big-endian |
| 压缩载荷 | 指定长度 | 单个完整 zlib 流 |

SQLite `chunks` 表映射哈希到卷名、帧偏移和长度；`files` 保存元数据和每文件哈希；`file_chunks(path,seq,hash)` 是从零开始的块顺序；`metadata` 包含格式、配置、运行状态；`issues` 保留各次运行的问题历史。历史问题不等于当前仍有问题，应检查 `metadata.latest_run` 和该次 create 报告。

内容不会直接写入清单，xattr 使用 Base64 保存以避免二进制编码损坏。清单仍含私人路径、链接目标和扩展属性，应随卷统一加密。

## 已执行的验证

`python3 tools/test_backup.py` 创建隔离临时夹具，测试真实超过 64 MiB 的文件、重复文件与去重、二进制、空文件、嵌套中文路径、排除前缀、硬链、相对/绝对/悬空软链、权限/纳秒mtime/xattr、rootfs 映射、恢复逐文件 SHA-256、前缀抽样恢复及硬链原件在范围外时的独立恢复、拒绝覆盖、残帧恢复、丢失 SQLite 提交恢复、坏块检出、源文件消失/读取中变化报错、恶意路径拒绝、封存前非空WAL安全checkpoint及无WAL恢复、缩小阈值下的卷切换。结果见 `test-report.json`。测试只创建/删除自己的临时文件，不碰项目来源。

`python3 tools/test_recovery.py` 使用隔离的模拟 gh CLI 和真实 age 加密/解密，不访问网络。验证从克隆目录自动定位可信清单、确切资产名、跳过独立视频、download-only、下载复用、全新解密目录首次只读校验、部分与完整恢复、拒绝覆盖、错误密文、错误私钥与错误明文哈希；结果见 `recovery-test-report.json`。
