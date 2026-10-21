# Windows PowerShell 5.1 路径长度修复（v7.2）

v7 安装器将游戏原始目录结构放进带版本标记的临时备份目录，最长文件路径超过 Windows PowerShell 5.1 的 260 字符限制，因此可能提示「创建原版备份失败，游戏资源尚未修改」。原来的资源暂存文件还会在长 bundle 文件名后追加事务编号，产生同样的问题。

v7.2 将备份内容保存为 `files/<原版文件的 SHA256>.bin`，并在备份的 `manifest.json` 中记录 `backup_layout: "sha256-v1"`。游戏资源的暂存和回滚文件改用独立短名称，仍与目标文件位于同一目录并采用原子替换。游戏资源与 SHA256 清单沿用 v7，对应 Steam build `25964535`。

## 已经下载 v7

1. 退出游戏。
2. 下载 v7.2 Release 中单独提供的 `manage_frog.ps1`，覆盖原解压目录中的同名文件，例如 `D:\silver-pines-frog-v7\manage_frog.ps1`。
3. 在这个原目录重新双击 `install_frog.bat`。不需要重新下载资源或重新下载游戏。

报错留下的 `backup/versions/*.pending-*` 不会被当成可恢复备份，也不会阻止重试。保留其他备份，尤其是包含 `manifest.json` 的完整版本备份。

## 新下载

下载 `silver-pines-frog-v7.2.zip`，完整解压到可写目录，退出游戏后双击 `install_frog.bat`。找不到游戏时，把含 `Carpenter.exe` 的游戏目录拖到 bat 上。

## 恢复与验证

使用同目录的 `restore_original.bat` 恢复。新版管理脚本支持 v7 的旧目录式版本备份及 v7.2 的哈希文件备份；新格式备份必须搭配新版管理脚本，保留整个 `backup/versions/` 和其中的清单。

修复已在 Windows PowerShell 5.1 下使用临时游戏目录验证，覆盖真实最长 bundle 文件名、安装/重装、删除构建资源后恢复、旧备份兼容、损坏备份拒绝和文件占用时回滚；未修改实际 Steam 游戏目录。
