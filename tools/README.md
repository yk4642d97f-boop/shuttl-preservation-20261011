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

`recover_from_github.py` 按清单中的每个确切名称执行 `gh release download`。本次大密文采用 **128 MiB 传输分片**：先验证每片的字节数和 SHA-256，再按序串流验证原完整密文的 SHA-256，使用外部私钥 `age --decrypt` 解密后验证明文 SHA-256。它核对封存资产列表，执行完整 `shuttl_backup.py verify`，最后恢复到指定新目录。不会重新 seal。GitHub token 和私钥内容不写入命令日志，不复制私钥。

索引仍使用 `shuttl-delivery-v1`，分片运输标记为 `transport: "ciphertext-parts-v1"`。每个逻辑资产保留原 `name`、密文 `bytes`/`sha256`、`plaintext_sha256` 和 `restore_path`；大资产另有有序 `parts` 数组，每项包含 `name`、`bytes`、`sha256`。片名为原 `.age` 名去掉后缀，再加 `.part-000001.age`，序号从 1 连续递增。所有片的长度之和必须等于原密文长度。分片不是可独立解密的 age 文件，需按清单顺序拼回原密文。旧版没有 `parts` 的索引仍可恢复。

只下载并验证密文，可不提供私钥和恢复目录：

```sh
python3 tools/recover_from_github.py --workdir /new/disk/shuttl-recovery-cache --download-only
```

支持断点重跑：工作目录绑定同一仓库、tag 和可信清单哈希；已经存在且校验一致的密文分片/明文直接复用。损坏的缓存会改名保留为 `.invalid-*`，随后仅重新下载受损分片或重新解密。`--download-only` 逐片和串流校验完整密文，不落盘保存合并后的父密文。实际解密每次只临时拼接一个逻辑资产，解密结束后清理临时父密文；持久缓存仅保留分片、未分片小密文与明文归档。已存在的非空普通目录没有恢复标记时拒绝作为缓存目录。恢复目的目录必须不存在；失败后留下的目的目录不能直接覆盖，应排查后选择另一新目录。

只恢复若干目录/文件时添加可重复 `--include-prefix`，值必须使用清单中的原电脑绝对路径：

```sh
python3 tools/recover_from_github.py --identity /secure/location/shuttl-recovery-key.txt --workdir /new/disk/shuttl-recovery-cache --destination /new/disk/shuttl-media-sample --include-prefix /Users/yangcong/Downloads/华北五省/promo2 --include-prefix /Users/yangcong/Downloads/shuttl.mp4
```

范围选择只限制最后恢复出的文件；为了验证完整归档，helper 仍会下载、解密并验证全部归档资产。完整恢复需容纳约 103 GB 密文分片、103 GB 明文归档与 186 GB 原始文件，建议至少 **450 GB 可用空间**；该估算依赖每次仅临时拼接一个父密文并及时清理，不额外永久保留全部合并密文。损坏缓存和重复恢复目录会额外占用空间。`recovery-report.json` 记录 `full_archive_restored`；抽样恢复不会被标成完整恢复。完整命令与退出码保存在缓存的 `commands.json`，归档/恢复详细报告也保存在缓存。失败返回退出码 2，不会报告成功。

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

重复执行完全相同的 `create` 命令可续传。已完成且文件签名未变的条目复用；其他条目重新读取并按内容哈希复用块。断电后未提交到 SQLite 的完整块会校验并重新索引；末卷未提交的残帧可截断重建。已被清单引用的截断或损坏不会自动丢弃。默认要求配置完全相同。

未封存归档后续发现遗漏来源时，可以仅追加 roots，并显式执行：

```sh
python3 tools/shuttl_backup.py create --config expanded-config.json --archive archive --extend-scope
```

新配置必须完整保留所有旧 root 的原 path/category，且 excludes 完全一致；删除旧 root、改变类别、改变排除项或重复 root 路径都会拒绝。验证通过后记录扩大的配置并重新遍历，复用已完成文件和持久化块，完成同样的最终源一致性检查。若中途失败，使用扩大后的配置继续续传；不得退回较小配置。已封存归档即使指定此选项也不能修改。需要改变旧范围或排除规则时创建新的归档。

每 250 条或约 1 秒批量将当前数据卷 flush/fsync，然后提交 SQLite；大文件读取过程中也按约 1 秒持久化新对象。轮换旧卷前先 fsync。只会在数据已持久化后提交其清单引用。`.create.lock` 使用 flock 拒绝同一归档的并发 create。

创建时每约 10 秒输出 JSON 进度，最后进行来源二次遍历与存在性检查。工具没有创建文件系统原子快照；需要减少源文件变动，并在任何变化报错后重新运行 create。`create-report.json` 的 `complete=true` 与 `verify` 的 `verified=true` 是后续交付的必要检查项。

## 上传前封存

创建与恢复抽查完成后，可在验证时加 `--seal`：

```sh
python3 tools/shuttl_backup.py verify --archive archive --seal --output archive/verify-report.json
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
- mode、mtime/atime、xattr 恢复接口返回失败会明确报告。先写入 xattr，再应用最终权限与时间戳；只读硬链接共享 inode 时会临时恢复 owner-write 权限。macOS 可能重新生成系统管理的 `com.apple.provenance`，即使写入接口返回成功，恢复后的值也可能与原值不同；原始 xattr 字节仍保存在清单。uid/gid 保留在清单但不自动 chown，恢复内容属于当前用户；ACL、文件系统 immutable 标志和稀疏布局没有单独重建。文件字节包括稀疏区域逻辑零字节均保存。
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

`python3 tools/test_recovery.py` 使用隔离的模拟 gh CLI 和真实 age 加密/解密，不访问网络。验证旧版与分片索引、确切资产名、安全路径/序号/名称冲突/大小和、跳过独立视频、download-only 串流父哈希、缺片/损片/错误父哈希、缓存保留与重跑、临时父密文清理、全新解密目录首次只读校验、部分与完整恢复、拒绝覆盖、错误私钥与明文哈希、不复制私钥；结果见 `recovery-test-report.json`。

## 在原电脑继续生成传输分片

本次备份已完成完整归档验证与 age 加密回读验证。以下命令用于在原电脑的现有交付目录中生成 128 MiB 传输分片；新电脑直接使用前面的 GitHub 恢复命令。

```sh
python3 -B /Users/yangcong/Downloads/shuttl-preservation-20261011/tools/fragment_delivery.py --base /Users/yangcong/Downloads/shuttl-preservation-20261011 --reclaim-parent-ciphertexts
```

`fragment_delivery.py` 只读取生成的 `delivery` 密文，不读取工程来源、明文归档或恢复私钥。它按原密文顺序分片，验证每片及所有片拼接后的完整 SHA-256，持久化每个文件和包含完整分片信息的索引。指定 `--reclaim-parent-ciphertexts` 后，只有完成上述检查和持久化的原大密文才被删除，以控制磁盘占用；小密文与三个独立宣传/演示 MP4 不拆分、不回收。原逻辑资产的名称、大小、密文/明文哈希与恢复路径保持不变。

**中断后重新执行完全相同的 fragment 命令即可继续。** 已写完但尚未记录的分片会先与父密文切片核对再复用；已回收父密文的资产按完整分片索引重新校验。已记录分片损坏或索引不完整且父密文缺失时明确失败，不覆盖损坏证据。转换期间 `payload-index.json` 为 `complete=false`，全部分片校验结束且新的 `SHA256SUMS` 持久化后，才最后发布 `complete=true`。校验表列出实际传输分片、未拆分文件及最终索引，不列已回收的父密文。

**分片开始后不要在同一目录重跑 `prepare_delivery.py`。** 工具会在访问归档/私钥或写入前识别传输标记或任何 `parts` 字段，明确拒绝，并提示继续运行 `fragment_delivery.py`；需要重新准备交付时，应使用新的 base 目录。分片转换按固定顺序同时持有 `.prepare.lock` 和 `.upload.lock`，与准备、上传互斥，避免索引在上传中变化。

`python3 tools/test_fragment_delivery.py` 的 18 项隔离测试覆盖完整拼接哈希、逐字节元数据保留、断点恢复、父文件回收时序、损坏拒绝、最终校验表、锁与软链安全；结果见 `fragmentation-test-report.json`。`python3 tools/test_prepare_delivery.py` 的 5 项回归测试证明已分片或刚开始分片的交付会被旧准备流程拒绝，索引、校验表和全部分片字节保持原样，旧版未分片索引仍进入原有验证流程；结果见 `prepare-guard-test-report.json`。这些测试只操作临时夹具。
