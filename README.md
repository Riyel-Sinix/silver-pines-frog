# Silver Pines 奶蛙 mod + CE 修改表

单机游戏 **Silver Pines**（Wych Elm / Team17，Unity 6000.3.15f1，IL2CPP）的两个 mod：

- **奶蛙主角**：把主角换成胖胖的黄色奶蛙，走路、跑步、举枪、近战、游泳、攀爬都有对应动作，待机时会做「惊鸿一瞥」表情，
  站着不动 10 秒还会哈哈大笑、笑倒在地上打滚（带笑声），对话头像、新建游戏的难度图和背包里随受伤变化的照片
  也换成了奶蛙表情包。
- **Cheat Engine 修改表**：无敌、无限弹药、一击必杀等 12 项功能，给手残党用。

*A frog ("奶蛙") player-model replacement and a Cheat Engine table for the single-player game Silver Pines.
The source contains no game files; a prebuilt package for the current game version is on the
[Releases](https://github.com/Riyel-Sinix/silver-pines-frog/releases) page.*

![奶蛙各动作预览](docs/preview.jpg)

## 奶蛙主角 mod

### 有什么

- 主角约 2000 帧动画全部重画成奶蛙：位置、高度、身体倾斜都跟着原角色走。
- 走路时两条腿跟着原角色的脚迈步，侧面看两腿从同一个胯部摆动，不会交叉。
- 举枪、换弹、瞄准时用没有手的身体，配上奶蛙颜色的手臂，不会出现原来的人。
- 挥砍、刀、投掷等近战动作：奶蛙的手会伸到武器握把上。
- 跑步摆臂；游泳时自由泳划水，踩水时双手在胸前划圈。
- 爬梯子显示背面并双手交替往上抓；爬绳双手抓绳；扒墙沿时手一直抓着边。
- 朝镜头走、进门、楼梯转身时用奶蛙的正面 / 背面（根据三视图生成）。
- 站着待机时每个循环（约 3 秒）斜眼瞥一次「惊鸿一瞥」。
- 站着不动 10 秒，奶蛙会转过来哈哈大笑、笑倒在地上打滚，大约 16 秒后站起来，带笑声；中途走开笑声就停。
  受伤、中毒时的待机不会笑。
- 对话（包括打电话）里主角的头像换成奶蛙托腮思考的表情包。
- 新建游戏选难度时的图：轻松自在大笑、紧张刺激思考、生存恐怖哭、噩梦「切换早八模式」。
- 背包（状态页）拍立得里的照片跟着受伤程度变：没事大笑、轻伤「切换恶魔模式」、负伤「切换早八模式」、
  重伤「切换死神形态」（游戏本来就让难度图和受伤照片共用几张图）。

### 直接下载

到 [Releases](https://github.com/Riyel-Sinix/silver-pines-frog/releases) 下载最新的 `silver-pines-frog-v*.zip`，解压后**先退出游戏**，
双击 `install_frog.bat`。默认查找 `D:\SteamLibrary\steamapps\common\Silver Pines`，也会查找其他 Steam 库；
找不到时，把游戏文件夹拖到这个 bat 文件上。卸载用同一个文件夹里的 `restore_original.bat`。
v7 对应 Steam build **25964535**（Unity 6000.3.15f1）；安装前校验程序、原版资源及模组资源的 SHA256。

从 v6 或更早版本升级：游戏更新前，先用旧版卸载。游戏已经更新或重新下载过时，先在 Steam 里
「验证游戏文件的完整性」，再安装 v7。请保留旧备份；v7 会在 `backup/versions/` 单独保存与当前游戏匹配的原版。

### 自己生成

源码里没有游戏文件，也可以用你自己的原版游戏生成 mod（约 13 分钟）。生成器会重新扫描当前版本的动画和补丁资源名，
并生成安装器使用的 `manifest.json`；检测到已安装奶蛙且没有对应的原版备份时会停止。

1. 安装 Python 3.12 和依赖：

   ```bash
   pip install -r requirements.txt
   ```

2. 一次生成完整资源包；`--game` 指向包含 `Carpenter.exe` 的原版游戏文件夹：

   ```bat
   python -P -E scripts/build_frog.py --game "D:\SteamLibrary\steamapps\common\Silver Pines"
   ```

   已有 `frogmod/build/` 时，先将其改名保留，或用 `--output frogmod/build_new` 指定空目录；
   安装器读取的是 `frogmod/build/`。也可以设置环境变量 `SILVER_PINES` 供单独的扫描、生成及检查脚本使用。

3. 待机大笑的画面和笑声来自奶蛙大笑的视频（1280×720），仓库里没有这个视频。
   有视频时，在构建前先切帧；没有时构建器会跳过大笑，仍生成主角、头像及照片：

   ```bash
   python -P -E scripts/laugh_frames.py 奶蛙大笑.mp4 frogmod/laugh
   ```

4. （可选）检查生成结果；使用其他游戏目录时，先设置 `SILVER_PINES`：

   ```bash
   python -P -E scripts/verify_frog_bundle.py frogmod/build/team17_auto_base_characters_compressed_assets_player.bundle check.png 40 "原版主角.bundle"
   ```

   `原版主角.bundle` 指当前版本的原始主角 bundle；可在安装前从游戏目录复制一份。

   ```bash
   python -P -E scripts/verify_extras.py frogmod/build
   ```

### 安装 / 卸载

- 安装：**先退出游戏**，双击 `frogmod/install_frog.bat`。游戏不在默认位置时，把游戏文件夹拖到这个 bat 文件上。
  第一次安装会把原版文件备份到 `frogmod/backup/versions/`，按版本及安装位置隔离。Windows 自带的 PowerShell 执行安装，
  使用发行包不需要 Python；请保留与 bat 同目录的 `manage_frog.ps1`。
- 为了放笑声，安装还会改 `Carpenter_Data/globalgamemanagers` 里的一个开关，打开 Unity 自带的声音系统
  （游戏本身的声音走 FMOD，原本把 Unity 的声音关掉了）。这个文件基于新版原版生成并备份；版本或资源校验失败时，整个安装停止。
  所以笑声不受游戏里的音量设置影响。
- 卸载：退出游戏，双击 `frogmod/restore_original.bat`，恢复原版主角。
- 游戏更新前先卸载。已经更新后，不要用旧版卸载器覆盖新版文件；v7 卸载器会拒绝不匹配的备份。
  在 Steam 验证原版后，重新运行 `build_frog.py` 生成并安装；旧备份可以保留。

### 改奶蛙的图

奶蛙的分层图已经在 `frogmod/parts/` 里。想换图的话：

1. `scripts/cutout.py`：去掉白底，得到 `frogmod/frog_cutout.png`。
2. `scripts/frog_parts.py`：切成身体、手臂、腿等图层。
3. `scripts/frog_views.py`：从 `frogmod/source/` 里的三视图和表情包生成正面、背面和「惊鸿一瞥」的头。
4. 对话头像来自 `frogmod/source/frog_thinking.png`，`scripts/frog_extras.py` 去掉白底后裁成头像。
5. 难度图和背包照片来自 `frogmod/source/photos/`，`scripts/frog_extras.py` 的 `PHOTOS` 写着每张表情包换掉游戏里的
   哪张图、怎么裁。

## CE 修改表

需要 [Cheat Engine](https://www.cheatengine.org/) 7.4 或更新版本。

1. 启动游戏，进到主菜单。
2. 打开 Cheat Engine，点左上角的电脑图标，选择 `Carpenter.exe`。
3. 打开 `SilverPines.CT`，**先勾选第一项「激活 Silver Pines 修改器」**，再勾选想要的功能。

功能：无敌、不死（致命伤自动回满血）、无限体力、无限弹药、近战武器不掉耐久、一击必杀、必定打中弱点、
电器电量不减、花钱不减少、修改金钱、地图全显示、万能钥匙。

所有地址都靠特征码查找，并在写入前校验 IL2CPP 类名；游戏版本对不上时会直接提示，不会乱改内存。
已对 Steam build 25964535 做离线核验：8 个特征均唯一，所用字段布局不变。新版游戏内功能仍需实测。

## 目录

| 路径 | 内容 |
|---|---|
| `SilverPines.CT` | CE 修改表 |
| `scripts/frogify.py` | 奶蛙 mod 生成器（主程序） |
| `scripts/build_frog.py`, `refresh_game_data.py`, `game_paths.py` | 完整构建、刷新当前游戏索引、按版本选择原版资源 |
| `frogmod/manage_frog.ps1` | 校验版本、备份、安装和卸载 |
| `scripts/frog_extras.py`, `laugh_frames.py` | 待机大笑（切视频帧、动画、笑声）、对话头像、难度图和背包照片、打开 Unity 声音 |
| `scripts/frog_parts.py`, `frog_views.py`, `cutout.py` | 从奶蛙原图生成图层 |
| `scripts/clip_map.py`, `clip_curves.py`, `scan_*.py` | 分析游戏动画，生成 `_dump/` 里的数据 |
| `scripts/verify_*.py`, `showcase.py`, `*_probe.py` | 检查和预览 |
| `scripts/disasm.py`, `xrefs.py`, `aobcheck.py`, … | 做 CE 表时用的分析工具（需要 Il2CppDumper 的输出） |
| `frogmod/` | 安装 / 卸载脚本、奶蛙原图和分层图 |
| `MODLOG.md` | 开发记录：游戏内部结构、每个版本改了什么 |

## 声明

- Silver Pines 版权归 Wych Elm / Team17 所有。仓库源码不含游戏文件；Releases 里的资源包是修改过的游戏文件，
  仅供已拥有正版游戏的玩家使用，请勿二次分发，版权方要求时会立即删除。
- 奶蛙图片来自网络（表情包），版权归原作者所有，如有侵权请联系删除。
- 用到的工具：[UnityPy](https://github.com/K0lb3/UnityPy)、[Il2CppDumper](https://github.com/Perfare/Il2CppDumper)、
  [AddressablesTools](https://github.com/nesrak1/AddressablesTools)、[Cheat Engine](https://www.cheatengine.org/)、
  OpenCV、Pillow、NumPy、capstone。
- 代码、脚本和 CE 表由 AI 编写：Anthropic 的 Claude（Claude Opus 5.5，通过 Claude Code）。
- 代码和 CE 表使用 [MIT 许可证](LICENSE)；奶蛙图片不在许可范围内。
