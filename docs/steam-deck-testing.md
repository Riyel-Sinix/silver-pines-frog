# Steam Deck / SteamOS 测试说明（v7）

本说明供有 Steam Deck 的测试者验证奶蛙资源包。目标版本是 Steam app `2333000` 的 Windows build `25964535`（depot `2333001`，manifest `8784396639484429591`，Unity `6000.3.15f1`，IL2CPP metadata v39）。当前项目只对这个 Windows Standalone build 做过离线资源和版本校验；没有 Steam Deck 或 Proton 实机测试结果。

## 兼容性边界

v7 直接替换游戏资源，不注入代码：发布包清单有 **218 个目标文件**，即 1 个主角色 AssetBundle、216 个补丁 AssetBundle，以及 `Carpenter_Data/globalgamemanagers`。217 个 bundle 的目标目录是 `Carpenter_Data/StreamingAssets/aa/StandaloneWindows64/`；音频开关文件映射到 `Carpenter_Data/globalgamemanagers`。每个发布包 `build/manifest.json` 条目都有 `build_path`、`game_path` 和 SHA256，可用于逐项核对。

由于目标是 Windows IL2CPP 游戏，Steam Deck 必须通过 Proton 运行 Windows build 才有合理的兼容预期。资源替换没有依赖 Windows API 的运行时注入，故在 Proton 下可能工作；但 Proton 版本、Unity 资源加载、文件系统大小写行为和 Unity 音频行为都未在 Deck 验证，不能据此承诺兼容。

如果 Steam 提供或用户选择了原生 Linux build，本包不支持该版本：资源位于 `StandaloneWindows64`，且当前版本校验与构建均针对 Windows 可执行文件和 Windows IL2CPP metadata。Cheat Engine 表 `SilverPines.CT` 也不适用于 SteamOS/Proton 测试，本次测试只检查资源 mod。

## 准备

1. 在 Steam Deck 切到 Desktop Mode，确保 Steam 已退出游戏。
2. 在 Steam 的 Silver Pines 属性页打开「Installed Files」并点「Browse」，确认游戏安装位置。Steam 游戏可以安装在内置盘、microSD 或其他可写 Steam library；包内 SteamOS 安装器会从 `libraryfolders.vdf` 搜索这些库，也支持手动传入游戏根目录。
3. 在「Compatibility」里勾选强制使用兼容工具，选择已安装的 Proton 版本（建议先用 Proton Experimental 或当前稳定版）。启动原版一次确认可进入游戏，再退出。记下所选 Proton 版本。
4. 在「Updates」或游戏文件中确认 build。库目录下的 `steamapps/appmanifest_2333000.acf` 包含 `buildid`；应为 `25964535`。可用桌面模式终端在游戏根目录执行 `sha256sum GameAssembly.dll Carpenter_Data/il2cpp_data/Metadata/global-metadata.dat`，再与目标版哈希核对：`GameAssembly.dll` 为 `b14b782f7c24e15ba61acba1d3c18ca5fc377b9bac776f3e5856ed29b35c2d3d`，metadata 为 `b4ca19b2caa68cf9b16f282e63151cb24b0c08371b58bfefdd713d68e6b93f5b`。Steam build ID 和这两个文件的哈希应一起记录。
5. 下载并解压 `silver-pines-frog-v7-steamos-test.zip` 到可写位置。测试包内有自带备份和校验的 SteamOS 安装器；不要把压缩包解压到游戏目录里。

## 安装与恢复

在桌面模式打开 Konsole，进入测试包里的 `frogmod` 文件夹并运行：

```sh
cd "/解压位置/silver-pines-frog-v7-steamos-test/frogmod"
sh install_frog.sh
```

安装器会自动搜索 Steam 库（包括 `libraryfolders.vdf` 中登记的 microSD/其他库），校验 Windows build、218 个原始目标文件及测试包内资源，然后在游戏目录外创建带版本和路径标记的备份并安装。结束信息应显示 `Installed 218 resources` 和备份目录。若自动搜索不到游戏，可把游戏根目录作为参数传入：

```sh
sh install_frog.sh "/实际 Steam 库/steamapps/common/Silver Pines"
```

安装前确保游戏已完全退出。安装器发现版本或文件哈希不匹配时会停止，不会继续覆盖。测试后退出游戏，在同一个 `frogmod` 目录执行：

```sh
sh restore_original.sh
```

恢复会使用安装时保存的原版文件，不依赖 `build/` 资源。保留测试包和 `frogmod/backup/versions/` 直到恢复成功。若安装器无法恢复，使用 Steam「验证游戏文件的完整性」还原原版。不要在游戏更新到其他 build 后恢复旧备份。

## 测试项目

安装后从 Steam 启动游戏，确认仍使用相同 Proton 版本。测试时尽量使用可丢弃的存档或避免覆盖已有存档，并记录：

- 游戏能否启动并进入已有存档/新游戏场景；是否有启动崩溃、黑屏或明显卡顿。
- 主角在站立、走跑、瞄准/换弹、近战等动作中的贴图和动画；有条件时检查游泳、爬梯和攀爬动作。
- 对话头像、新游戏难度图、背包照片是否显示奶蛙图片；不必为了测试覆盖现有存档。
- 正常待机的斜眼表情；保持站立约 10 秒后是否播放笑动画和笑声，约 16 秒后能否恢复；笑声是否会随移动中断。注意该笑声走 Unity 音频系统，不一定遵从游戏音量滑块。
- 退出并重新启动一次，检查资源是否持续加载；观察 Proton/Unity 日志中是否有 AssetBundle、序列化对象或音频错误。

## 日志、恢复和反馈

Unity `Player.log` 通常位于该 Steam library 的 `steamapps/compatdata/2333000/pfx/drive_c/users/steamuser/AppData/LocalLow/Wych Elm/Silver Pines/Player.log`。若启用 Proton 日志，可在 Steam 启动选项临时填写 `PROTON_LOG=1 %command%`；退出游戏后日志通常写到 `/home/deck/steam-2333000.log`。测试结束后移除该启动选项。实际路径可能随 Steam library 位置和 Proton prefix 状态不同而变化。

如遇黑屏、启动失败或贴图缺失，先退出游戏，不要继续覆盖其他文件。在测试包的 `frogmod` 目录运行 `sh restore_original.sh`；若没有完整备份或脚本无法恢复，再在 Steam 中执行「Verify integrity of game files」。不要在已更新到其他 build 的游戏上使用旧版备份。

请回报以下信息，日志中可遮去账号名、用户名和其他个人路径：

- Steam Deck 型号、SteamOS 版本、系统更新频道。
- Steam build ID；Proton 版本；游戏安装库位置（内置盘、microSD 或其他）。
- 是否先验证过原版可运行、安装是否完成以及实际覆盖文件数。
- 每个测试项目的结果、复现步骤、截图/短视频；失败时提供 `Player.log` 和 Proton 日志中的相关片段。
- 是否成功运行 `restore_original.sh`；若使用 Steam 文件完整性验证，也请记录结果。
