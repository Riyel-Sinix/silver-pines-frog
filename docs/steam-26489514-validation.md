# Steam build 26489514 兼容性验证（2026-11-08）

游戏更新后 `GameAssembly.dll`（SHA256 `7110a036…`）和 `global-metadata.dat`（`71c78bc1…`）变化，Unity 仍为 6000.3.15f1。

奶蛙资源：主角图包、`team17_auto_base_characters_assets_player.bundle`、菜单场景和 `globalgamemanagers` 内容变化；208 个动作补丁包换了哈希文件名，另新增 `player_drawgunblockedarm` 补丁包。v7 资源不能复用，v8 由新版原版文件完整重建（219 个文件）。

- 主包：1929 个 Sprite，1866 个重画网格、60 个紧密网格、3 个未改四边形，问题 0。
- 207 个动作补丁包：142 个重画、85 个保留网格，问题 0。
- 大笑 197 帧 / 16.42 秒、声音可解码，新增 396 个预加载引用全部可解析；13 张头像、6 张照片、菜单镜像修正均只改预期对象；音频开关位于 `globalgamemanagers` 偏移 5736。
- 真实 Steam 目录安装、卸载、再安装后逐文件校验：219 个文件分别匹配构建输出 / 新版原版。

CE 修改表：体力开关所在的 `CharacterStamina.ConsumeStamina` 被重写，原特征码失效；表中改为依次尝试新、旧两个特征码。其余 7 个特征仍唯一（位置移动不影响），14 个依赖字段偏移不变，`aobcheck.py` 全部通过。

以上为离线核验，新版游戏内的奶蛙动作与 CE 功能尚未实测。
