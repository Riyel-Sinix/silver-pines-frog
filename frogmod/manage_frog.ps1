param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Install', 'Restore')]
    [string]$Operation,
    [string]$GameDirectory = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ModRoot = $PSScriptRoot
$MainBundle = 'team17_auto_base_characters_compressed_assets_player.bundle'
$BundlePrefix = 'Carpenter_Data/StreamingAssets/aa/StandaloneWindows64/'
$MetadataPath = 'Carpenter_Data/il2cpp_data/Metadata/global-metadata.dat'

function Get-Hash([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "缺少文件：$Path" }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $stream = $null
    try {
        $stream = [IO.File]::OpenRead($Path)
        return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant()
    } finally {
        if ($null -ne $stream) { $stream.Dispose() }
        $sha.Dispose()
    }
}

function Get-TextHash([string]$Value) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)))).Replace('-', '').ToLowerInvariant()
    } finally { $sha.Dispose() }
}

function Get-SafePath([string]$Root, [string]$Relative) {
    if ([string]::IsNullOrWhiteSpace($Relative) -or [IO.Path]::IsPathRooted($Relative)) {
        throw "清单中有无效路径：$Relative"
    }
    $parts = $Relative.Replace('\', '/').Split('/')
    foreach ($part in $parts) {
        if ($part -eq '' -or $part -eq '.' -or $part -eq '..' -or $part.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0) {
            throw "清单中有无效路径：$Relative"
        }
    }
    return [IO.Path]::Combine($Root, ($parts -join [IO.Path]::DirectorySeparatorChar))
}

function Read-Manifest([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "缺少版本清单：$Path。请重新生成或下载完整的新版奶蛙资源包。"
    }
    $manifest = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.schema_version -ne 1) { throw "不支持的清单版本：$Path" }
    if ($null -ne $manifest.PSObject.Properties['backup_layout'] -and $manifest.backup_layout -ne 'sha256-v1') {
        throw "不支持的备份存储格式：$Path"
    }
    foreach ($field in @('gameassembly_sha256', 'metadata_sha256')) {
        if ($manifest.game.$field -notmatch '^[a-fA-F0-9]{64}$') { throw "清单缺少游戏版本校验值：$field" }
    }
    if (@($manifest.files).Count -eq 0) { throw '版本清单没有资源文件。' }
    $seenGame = @{}
    $seenBuild = @{}
    foreach ($file in $manifest.files) {
        $gameRelative = ([string]$file.game_path).Replace('\', '/')
        $buildRelative = ([string]$file.build_path).Replace('\', '/')
        $null = Get-SafePath $ModRoot $gameRelative
        $null = Get-SafePath $ModRoot $buildRelative
        $isBundle = $gameRelative.StartsWith($BundlePrefix, [StringComparison]::OrdinalIgnoreCase) -and
            $gameRelative.Substring($BundlePrefix.Length) -match '^[^/]+\.bundle$'
        if (-not $isBundle -and $gameRelative -ne 'Carpenter_Data/globalgamemanagers') {
            throw "清单包含不支持的游戏资源路径：$gameRelative"
        }
        if (($isBundle -and $buildRelative -ne ($gameRelative.Substring($BundlePrefix.Length))) -and
            ($buildRelative -ne ('patches/' + $gameRelative.Substring($BundlePrefix.Length)))) {
            throw "构建路径与游戏资源不对应：$buildRelative"
        }
        if (-not $isBundle -and $buildRelative -ne 'globalgamemanagers') {
            throw "构建路径与游戏资源不对应：$buildRelative"
        }
        if ($seenGame.ContainsKey($gameRelative) -or $seenBuild.ContainsKey($buildRelative)) { throw '版本清单包含重复文件。' }
        $seenGame[$gameRelative] = $true
        $seenBuild[$buildRelative] = $true
        foreach ($field in @('source_sha256', 'output_sha256')) {
            if ($file.$field -notmatch '^[a-fA-F0-9]{64}$') { throw "资源校验值无效：$gameRelative ($field)" }
        }
    }
    if (-not $seenGame.ContainsKey($BundlePrefix + $MainBundle)) { throw '版本清单缺少主角主资源包。' }
    return $manifest
}

function Find-GameDirectory([string]$Explicit) {
    if ([string]::IsNullOrWhiteSpace($Explicit)) { $Explicit = $env:SILVER_PINES }
    if (-not [string]::IsNullOrWhiteSpace($Explicit)) {
        $candidate = [IO.Path]::GetFullPath($Explicit.Trim('"'))
        if ([IO.Path]::GetFileName($candidate) -eq 'Carpenter.exe') { $candidate = [IO.Path]::GetDirectoryName($candidate) }
        if (-not (Test-Path -LiteralPath (Join-Path $candidate 'Carpenter.exe') -PathType Leaf)) {
            throw "找不到游戏：$candidate。请把含 Carpenter.exe 的游戏文件夹拖到 bat 文件上。"
        }
        return $candidate.TrimEnd('\', '/')
    }
    $libraries = New-Object 'System.Collections.Generic.List[string]'
    $candidates = New-Object 'System.Collections.Generic.List[string]'
    $candidates.Add('D:\SteamLibrary\steamapps\common\Silver Pines')
    foreach ($key in @('HKCU:\Software\Valve\Steam', 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam', 'HKLM:\SOFTWARE\Valve\Steam')) {
        $registry = Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue
        if ($null -ne $registry) {
            foreach ($property in @('SteamPath', 'InstallPath')) {
                if ($null -ne $registry.PSObject.Properties[$property] -and $registry.$property) { $libraries.Add([string]$registry.$property) }
            }
        }
    }
    if (${env:ProgramFiles(x86)}) { $libraries.Add((Join-Path ${env:ProgramFiles(x86)} 'Steam')) }
    foreach ($drive in @(Get-PSDrive -PSProvider FileSystem)) {
        $libraries.Add((Join-Path $drive.Root 'SteamLibrary'))
        $libraries.Add((Join-Path $drive.Root 'Steam'))
    }
    foreach ($library in @($libraries.ToArray())) {
        $vdf = Join-Path $library 'steamapps\libraryfolders.vdf'
        if (Test-Path -LiteralPath $vdf -PathType Leaf) {
            $content = Get-Content -LiteralPath $vdf -Raw -Encoding UTF8
            foreach ($match in [regex]::Matches($content, '"path"\s*"([^"\r\n]+)"')) {
                $libraries.Add($match.Groups[1].Value.Replace('\\', '\'))
            }
        }
    }
    foreach ($library in @($libraries.ToArray() | Select-Object -Unique)) {
        $candidates.Add((Join-Path $library 'steamapps\common\Silver Pines'))
    }
    foreach ($candidate in @($candidates.ToArray() | Select-Object -Unique)) {
        if (Test-Path -LiteralPath (Join-Path $candidate 'Carpenter.exe') -PathType Leaf) { return [IO.Path]::GetFullPath($candidate).TrimEnd('\', '/') }
    }
    throw '没有找到 Silver Pines。请把含 Carpenter.exe 的游戏文件夹拖到 bat 文件上，或设置 SILVER_PINES 环境变量。'
}

function Assert-GameVersion($Manifest, [string]$GameRoot) {
    if ((Get-Hash (Join-Path $GameRoot 'GameAssembly.dll')) -ne $Manifest.game.gameassembly_sha256 -or
        (Get-Hash (Get-SafePath $GameRoot $MetadataPath)) -ne $Manifest.game.metadata_sha256) {
        throw '游戏版本与资源包/备份不匹配。为避免损坏新版文件，操作已取消。请使用对应版本资源包；旧版备份不能用于更新后的游戏。'
    }
}

function Assert-Build($Manifest, [string]$BuildRoot) {
    foreach ($file in $Manifest.files) {
        $path = Get-SafePath $BuildRoot $file.build_path
        if ((Get-Hash $path) -ne $file.output_sha256) { throw "资源包校验失败：$path。请重新生成或下载完整资源包。" }
    }
    $listPath = Join-Path $BuildRoot 'patches\bundles.txt'
    if (-not (Test-Path -LiteralPath $listPath -PathType Leaf)) { throw "缺少补丁清单：$listPath" }
    $listed = @(Get-Content -LiteralPath $listPath -Encoding UTF8 | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    $expected = @($Manifest.files | Where-Object { $_.build_path.Replace('\', '/').StartsWith('patches/', [StringComparison]::OrdinalIgnoreCase) } | ForEach-Object { $_.build_path.Replace('\', '/').Substring(8) })
    if (@($listed | Select-Object -Unique).Count -ne $listed.Count -or @($listed).Count -ne $expected.Count -or
        ($listed.Count -gt 0 -and @(Compare-Object $listed $expected).Count -ne 0)) {
        throw '补丁清单与版本清单不一致，请重新生成或下载完整资源包。'
    }
}

function Get-BackupRelativePath($Manifest, $File) {
    if ($null -ne $Manifest.PSObject.Properties['backup_layout'] -and $Manifest.backup_layout -eq 'sha256-v1') {
        return 'files/' + $File.source_sha256.ToLowerInvariant() + '.bin'
    }
    return $File.game_path
}

function Assert-Backup($Manifest, [string]$BackupRoot, [string]$GameRoot) {
    if (-not [string]::Equals($Manifest.game_path.TrimEnd('\', '/'), $GameRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw '备份属于另一个游戏安装目录，操作已取消。'
    }
    Assert-GameVersion $Manifest $GameRoot
    foreach ($file in $Manifest.files) {
        $path = Get-SafePath $BackupRoot (Get-BackupRelativePath $Manifest $file)
        if ((Get-Hash $path) -ne $file.source_sha256) { throw "原版备份校验失败：$path" }
    }
}

function Assert-Targets($Manifest, [string]$GameRoot) {
    foreach ($file in $Manifest.files) {
        $path = Get-SafePath $GameRoot $file.game_path
        $hash = Get-Hash $path
        if ($hash -ne $file.source_sha256 -and $hash -ne $file.output_sha256) {
            throw "游戏资源与此版本不匹配：$path。请先卸载旧版 mod，或在 Steam 验证游戏文件完整性后重试。"
        }
    }
}

function Write-Resources($Manifest, [string]$SourceRoot, [string]$GameRoot, [bool]$Restore) {
    $staged = New-Object 'System.Collections.Generic.List[object]'
    $applied = New-Object 'System.Collections.Generic.List[object]'
    $transaction = [Guid]::NewGuid().ToString('N')
    $rollbackFailed = $false
    try {
        foreach ($file in $Manifest.files) {
            $target = Get-SafePath $GameRoot $file.game_path
            $sourceRelative = $file.build_path
            $expected = $file.output_sha256
            if ($Restore) { $sourceRelative = Get-BackupRelativePath $Manifest $file; $expected = $file.source_sha256 }
            # Never append a suffix to the game's long AssetBundle filenames.
            $directory = [IO.Path]::GetDirectoryName($target)
            $temporaryName = '.frog-' + $transaction + '-' + $staged.Count
            $entry = [PSCustomObject]@{ Target = $target; Stage = (Join-Path $directory ($temporaryName + '.stage')); Rollback = (Join-Path $directory ($temporaryName + '.rollback')) }
            $staged.Add($entry)
            Copy-Item -LiteralPath (Get-SafePath $SourceRoot $sourceRelative) -Destination $entry.Stage
            if ((Get-Hash $entry.Stage) -ne $expected) { throw "写入前校验失败：$target" }
        }
        foreach ($entry in $staged) {
            [IO.File]::Replace($entry.Stage, $entry.Target, $entry.Rollback)
            $applied.Add($entry)
        }
    } catch {
        $failure = $_
        for ($index = $applied.Count - 1; $index -ge 0; $index--) {
            $entry = $applied[$index]
            try { [IO.File]::Replace($entry.Rollback, $entry.Target, [System.Management.Automation.Language.NullString]::Value) } catch { $rollbackFailed = $true }
        }
        if ($rollbackFailed) { throw "复制失败，部分文件未能回滚。请保留 backup 并运行恢复脚本；失败前的文件另存为 .frog-$transaction-*.rollback。原始错误：$failure" }
        throw "复制失败，已撤回本次资源修改：$failure"
    } finally {
        foreach ($entry in $staged) {
            Remove-Item -LiteralPath $entry.Stage -Force -ErrorAction SilentlyContinue
            # Keep an unsuccessful rollback for manual recovery.
            if (-not $rollbackFailed) { Remove-Item -LiteralPath $entry.Rollback -Force -ErrorAction SilentlyContinue }
        }
    }
}

try {
    $gameRoot = Find-GameDirectory $GameDirectory
    if (@(Get-Process -Name Carpenter -ErrorAction SilentlyContinue).Count -gt 0) { throw '游戏正在运行，请先退出 Silver Pines 后重试。' }
    if ($Operation -eq 'Install') {
        $buildRoot = Join-Path $ModRoot 'build'
        $manifestPath = Join-Path $buildRoot 'manifest.json'
        $manifest = Read-Manifest $manifestPath
        Assert-GameVersion $manifest $gameRoot
        Assert-Build $manifest $buildRoot
        Assert-Targets $manifest $gameRoot
        $backupKey = $manifest.game.gameassembly_sha256.Substring(0, 16) + '-' + (Get-Hash $manifestPath).Substring(0, 12) + '-' + (Get-TextHash $gameRoot.ToLowerInvariant()).Substring(0, 8)
        $backupRoot = Join-Path $ModRoot "backup\versions\$backupKey"
        $backupManifestPath = Join-Path $backupRoot 'manifest.json'
        if (Test-Path -LiteralPath $backupRoot) {
            $saved = Read-Manifest $backupManifestPath
            Assert-Backup $saved $backupRoot $gameRoot
            if ((ConvertTo-Json $saved.files -Depth 8 -Compress) -ne (ConvertTo-Json $manifest.files -Depth 8 -Compress)) { throw '已有备份清单与构建不一致，请保留备份并重新生成资源包。' }
        } else {
            # Only pristine originals may seed a backup. A modded file is never an original.
            foreach ($file in $manifest.files) {
                if ((Get-Hash (Get-SafePath $gameRoot $file.game_path)) -ne $file.source_sha256) {
                    throw '检测到已安装的 mod，但没有此安装目录对应的原版备份。请先在 Steam 验证游戏文件完整性，再安装。'
                }
            }
            $pending = Join-Path $ModRoot ("backup\.pending-" + [Guid]::NewGuid().ToString('N'))
            try {
                # Short hash filenames keep both pending and final paths below MAX_PATH.
                $manifest | Add-Member -NotePropertyName backup_layout -NotePropertyValue 'sha256-v1' -Force
                foreach ($file in $manifest.files) {
                    $backupPath = Get-SafePath $pending (Get-BackupRelativePath $manifest $file)
                    $null = New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($backupPath)) -Force
                    Copy-Item -LiteralPath (Get-SafePath $gameRoot $file.game_path) -Destination $backupPath
                    if ((Get-Hash $backupPath) -ne $file.source_sha256) { throw "原版备份校验失败：$backupPath" }
                }
                $manifest | Add-Member -NotePropertyName game_path -NotePropertyValue $gameRoot -Force
                $manifest | Add-Member -NotePropertyName created_at -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
                $manifest | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $pending 'manifest.json') -Encoding UTF8
                $null = New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($backupRoot)) -Force
                Move-Item -LiteralPath $pending -Destination $backupRoot
            } catch {
                $backupFailure = $_
                Remove-Item -LiteralPath $pending -Recurse -Force -ErrorAction SilentlyContinue
                throw "创建原版备份失败，游戏资源尚未修改：$backupFailure"
            }
        }
        Write-Resources $manifest $buildRoot $gameRoot $false
        Write-Host "安装完成！已更新 $(@($manifest.files).Count) 个资源文件。"
        Write-Host "游戏目录：$gameRoot"
        Write-Host "原版备份：$backupRoot"
    } else {
        $versionsRoot = Join-Path $ModRoot 'backup\versions'
        $choices = @()
        $reasons = New-Object 'System.Collections.Generic.List[string]'
        if (Test-Path -LiteralPath $versionsRoot -PathType Container) {
            foreach ($directory in @(Get-ChildItem -LiteralPath $versionsRoot -Directory | Where-Object { $_.Name -notmatch '\.pending-' } | Sort-Object LastWriteTimeUtc -Descending)) {
                try {
                    $saved = Read-Manifest (Join-Path $directory.FullName 'manifest.json')
                    if (-not [string]::Equals($saved.game_path.TrimEnd('\', '/'), $gameRoot, [StringComparison]::OrdinalIgnoreCase)) { continue }
                    Assert-Backup $saved $directory.FullName $gameRoot
                    Assert-Targets $saved $gameRoot
                    $choices += [PSCustomObject]@{ Manifest = $saved; Root = $directory.FullName }
                } catch { $reasons.Add($_.Exception.Message) }
            }
        }
        if ($choices.Count -eq 0) {
            if ($reasons.Count -gt 0) { throw ('没有可安全恢复的备份。' + [Environment]::NewLine + ($reasons -join [Environment]::NewLine)) }
            throw '没有此游戏目录对应的版本备份。未绑定版本的旧 backup 不会恢复到新版游戏；请在 Steam 验证游戏文件完整性。'
        }
        $selected = $choices[0]
        Write-Resources $selected.Manifest $selected.Root $gameRoot $true
        Write-Host "已恢复原版资源：$gameRoot"
    }
    exit 0
} catch {
    Write-Host ("操作取消：" + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
