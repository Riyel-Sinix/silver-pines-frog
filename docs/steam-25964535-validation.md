# Steam build 25964535 兼容性验证

验证日期：2026-10-19。目标为 Steam app `2333000`、depot `2333001`、manifest `8784396639484429591`，Unity `6000.3.15f1`、IL2CPP metadata v39。

用户重新下载原版后，重新核对了当前游戏文件：`GameAssembly.dll` 和 `global-metadata.dat` 的 SHA256 与此前用于反编译和字段分析的文件完全一致；对当前 `GameAssembly.dll` 重跑特征检查，8 项全部通过。

| 文件 | SHA256 |
| --- | --- |
| GameAssembly.dll | `b14b782f7c24e15ba61acba1d3c18ca5fc377b9bac776f3e5856ed29b35c2d3d` |
| global-metadata.dat | `b4ca19b2caa68cf9b16f282e63151cb24b0c08371b58bfefdd713d68e6b93f5b` |

CE 表的 8 个特征均在可执行区唯一命中，方法归属、TypeInfo 引用、补丁原字节和完整指令边界检查全部通过。原表通过特征动态定位，新版无需改写功能指令；开发用校验清单中的 5 个移动 RVA 已更新。

| 定位项 | 新版特征起点 RVA | 结果 |
| --- | --- | --- |
| GameDebugCommands / 体力调试开关 | `0x876B56` | 通过 |
| GlobalReferences / 金钱指针入口 | `0x82FC18` | 通过 |
| CharacterHealth / 不死开关 | `0x7BE912` | 通过 |
| 一击必杀注入点 | `0x7BE7AB` | 通过 |
| 近战耐久扣除 | `0x6DFDBF` | 通过 |
| 装备近战耐久扣除 | `0x6E1860` | 通过 |
| 电量扣除 | `0x7C6DE2` | 通过 |
| 金钱扣除 | `0x6E79B7` | 通过 |

下列 14 个依赖字段的名称、类型、静态/实例属性和偏移均与旧版一致；偏移使用十六进制。

| 类型 | 已核对字段及偏移 |
| --- | --- |
| GameDebugCommands | `CHEAT_INFINITE_AMMO +02`、`CHEAT_INFINITE_STAMINA +03`、`CHEAT_INVINCIBLE +04`、`CHEAT_MASTER_KEY +05`、`CHEAT_MAP_SHOW_EVERYTHING +06`、`ALWAYS_WEAKPOINT_HIT +08` |
| CharacterHealth | `JESUS_PLAYER +00`、`m_minimumHealth +A8`、`m_currentHealth +AC`、`m_blockedBySaveLoad +B0` |
| GlobalReferences | `m_instance +00`、`MainInventory +50` |
| PlayerMainInventory | `m_money +100` |
| MeleeWeaponItemInstance | `m_currentDurability +60` |

一击必杀仍位于 `GameUtils.IsPlayer` 返回后，非玩家分支为 `0x7BE805`，返回原指令的位置为 `0x7BE7B6`。血量 setter 仍按最低血量和最大血量限幅。

资源原版身份使用当前 Steam manifest 的逐文件 SHA1 和大小核验。解析得到 2416 个文件，总计 `3848425448` 字节，与 appmanifest 一致；manifest 文件 SHA256 为 `fee2c7fb8b30131949e81b90ae762148f16b08e92f6fa47a1fd5f0a23c98ddea`。这是对本地 Steam 缓存清单的读取，未验证清单签名。

- 奶蛙 v6 所需的主角色 bundle 和 216 个 patch bundle，共 217 个旧原版备份，全部与新版官方文件的 SHA1 和大小一致，可以作为新版重建的原始资源。
- 旧备份中另外 7 个 bundle 也与新版官方文件一致。
- `globalgamemanagers` 已从 `442420` 变为 `442468` 字节。音频相关修改必须基于新版原文件生成。
- `catalog.bin` 已从 `9125184` 变为 `9125368` 字节，应保留新版目录数据。

检查工具为 [aobcheck.py](../scripts/aobcheck.py)、[patterns.json](../scripts/patterns.json) 和 [steam_manifest.py](../scripts/steam_manifest.py)。本地详细证据位于 `_dump/new_20261019/`、`_dump/compat-new/steam_manifest.json` 和 `_dump/compat-new/steam_manifest_backup_verification.json`；反编译数据和游戏资源不随仓库发布。

v7 保留已核验的 217 个模组 bundle，基于新版 `442468` 字节原版 `globalgamemanagers` 重新生成音频配置，仅文件偏移 `5752` 的一个字节变化。主包检查为 1929 个 Sprite，其中 1866 个重画网格全部正确、60 个紧密网格保留、3 个未修改的武器/效果四边形保留；215 个不含大笑新增对象的补丁包检查无问题。大笑 197 帧、16.42 秒，声音可解码，模板引用无缺失；头像、照片和菜单仅修改预期对象。

安装器的 14 项隔离测试通过，包括中文路径、错版/损坏拒绝和复制失败回滚。真实 Steam 目录已完成安装、卸载、再次安装；卸载后 218 个文件全部匹配当前 Steam 清单的原版 SHA1，再安装后全部匹配构建输出 SHA256。原版备份保存在 `frogmod/backup/versions/`，旧平铺备份不参与新版恢复。

以上属于离线文件、元数据和指令核验。新版游戏内的角色动作、贴图、待机笑声及 CE 功能效果尚未实测。
