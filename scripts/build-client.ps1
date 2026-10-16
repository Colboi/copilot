$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$outputRoot = Join-Path $projectRoot 'target'
$releaseRoot = Join-Path $projectRoot 'src-tauri\target\release'
$runtimeSource = Join-Path $projectRoot '.venv'
$runtimeBuilderPython = Join-Path $runtimeSource 'Scripts\python.exe'
$pluginSourceRoot = Join-Path $projectRoot 'plugins'
$colmonNativeProject = Join-Path $projectRoot 'plugins\colmon\native\ColpilotColmonWindows.csproj'
$colmonNativePublishRoot = Join-Path $projectRoot 'artifacts\colmon-native-publish'
$colmonNativeExecutable = Join-Path $colmonNativePublishRoot 'ColpilotColmonWindows.exe'
$pluginSourceDirectories = @(
    Get-ChildItem -LiteralPath $pluginSourceRoot -Directory |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'manifest.json') }
)
$pluginPackageInitSource = Join-Path $pluginSourceRoot '__init__.py'
$backendScriptSource = Join-Path $projectRoot 'backend\main.py'
$backendConfigStoreSource = Join-Path $projectRoot 'backend\user_config.py'
$backendProcessManagerSource = Join-Path $projectRoot 'backend\process_manager.py'
$backendRequirementsSource = Join-Path $projectRoot 'backend\requirements.txt'
$portableBackendRoot = Join-Path $outputRoot 'backend'
$portableRuntimeRoot = Join-Path $outputRoot 'runtime'
$portablePluginsRoot = Join-Path $outputRoot 'plugins'

Set-Location -LiteralPath $projectRoot
npm run tauri build
if ($LASTEXITCODE -ne 0) {
    throw "客户端构建失败，退出代码为 $LASTEXITCODE"
}

if (-not (Test-Path -LiteralPath $runtimeBuilderPython -PathType Leaf)) {
    throw "本地 Python 构建解释器不存在：$runtimeBuilderPython"
}

$baseRuntimeRootText = (& $runtimeBuilderPython -c "import sys; print(sys.base_prefix)").Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($baseRuntimeRootText)) {
    throw "无法读取 Python 基础运行目录"
}
$baseRuntimeRoot = (Resolve-Path -LiteralPath $baseRuntimeRootText).Path
$baseRuntimeLibRoot = Join-Path $baseRuntimeRoot 'Lib'
$baseRuntimeDllRoot = Join-Path $baseRuntimeRoot 'DLLs'
$baseRuntimeLibraryBin = Join-Path $baseRuntimeRoot 'Library\bin'
$venvSitePackages = Join-Path $runtimeSource 'Lib\site-packages'
$portableLibraryDllNames = @(
    'libcrypto-3-x64.dll',
    'libssl-3-x64.dll',
    'ffi-7.dll',
    'ffi-8.dll',
    'ffi.dll',
    'sqlite3.dll',
    'zlib.dll',
    'libbz2.dll',
    'liblzma.dll',
    'libexpat.dll',
    'charset.dll',
    'iconv.dll',
    'libzstd.dll',
    'yaml-cpp.dll'
)
$portableLibraryDllSources = @(
    $portableLibraryDllNames | ForEach-Object { Join-Path $baseRuntimeLibraryBin $_ }
)

$artifactSources = @(
    (Join-Path $releaseRoot 'colpilot.exe')
)
$portableSources = @(
    $backendScriptSource,
    $backendConfigStoreSource,
    $backendProcessManagerSource,
    $backendRequirementsSource,
    (Join-Path $baseRuntimeRoot 'python.exe'),
    (Join-Path $baseRuntimeRoot 'pythonw.exe'),
    $baseRuntimeLibRoot,
    $baseRuntimeDllRoot,
    $venvSitePackages,
    $portableLibraryDllSources,
    $pluginPackageInitSource,
    $colmonNativeProject,
    $pluginSourceDirectories.FullName
)

foreach ($sourcePath in @($artifactSources + $portableSources)) {
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        throw "客户端文件不存在：$sourcePath"
    }
}

if (Test-Path -LiteralPath $colmonNativePublishRoot) {
    Remove-Item -LiteralPath $colmonNativePublishRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $colmonNativePublishRoot -Force | Out-Null
& dotnet publish $colmonNativeProject `
    -c Release `
    -r win-x64 `
    --self-contained true `
    -p:PublishSingleFile=true `
    -p:IncludeNativeLibrariesForSelfExtract=true `
    -o $colmonNativePublishRoot `
    --nologo
if ($LASTEXITCODE -ne 0) {
    throw "colmon 原生窗口宿主构建失败，退出代码为 $LASTEXITCODE"
}
if (-not (Test-Path -LiteralPath $colmonNativeExecutable -PathType Leaf)) {
    throw "colmon 原生窗口宿主文件不存在：$colmonNativeExecutable"
}

if (Test-Path -LiteralPath $outputRoot) {
    Get-ChildItem -LiteralPath $outputRoot -Force | Remove-Item -Recurse -Force
} else {
    New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
}

Copy-Item -LiteralPath $artifactSources[0] -Destination (Join-Path $outputRoot 'colpilot.exe')
New-Item -ItemType Directory -Path $portableBackendRoot,$portableRuntimeRoot,$portablePluginsRoot -Force | Out-Null

Copy-Item -LiteralPath $backendScriptSource -Destination (Join-Path $portableBackendRoot 'main.py')
Copy-Item -LiteralPath $backendConfigStoreSource -Destination (Join-Path $portableBackendRoot 'user_config.py')
Copy-Item -LiteralPath $backendProcessManagerSource -Destination (Join-Path $portableBackendRoot 'process_manager.py')
Copy-Item -LiteralPath $backendRequirementsSource -Destination (Join-Path $portableBackendRoot 'requirements.txt')
foreach ($runtimeFile in (Get-ChildItem -LiteralPath $baseRuntimeRoot -Filter '*.dll' -File)) {
    Copy-Item -LiteralPath $runtimeFile.FullName -Destination $portableRuntimeRoot -Force
}
foreach ($runtimeFile in (Get-ChildItem -LiteralPath $baseRuntimeRoot -Filter 'python*.exe' -File)) {
    Copy-Item -LiteralPath $runtimeFile.FullName -Destination $portableRuntimeRoot -Force
}
Copy-Item -LiteralPath $baseRuntimeDllRoot -Destination $portableRuntimeRoot -Recurse -Force
$portableRuntimeLibRoot = Join-Path $portableRuntimeRoot 'Lib'
New-Item -ItemType Directory -Path $portableRuntimeLibRoot -Force | Out-Null
foreach ($runtimeLibItem in (Get-ChildItem -LiteralPath $baseRuntimeLibRoot -Force | Where-Object { $_.Name -notin @('site-packages', '__pycache__') })) {
    Copy-Item -LiteralPath $runtimeLibItem.FullName -Destination $portableRuntimeLibRoot -Recurse -Force
}
New-Item -ItemType Directory -Path (Join-Path $portableRuntimeRoot 'Library\bin') -Force | Out-Null
foreach ($libraryDllSource in $portableLibraryDllSources) {
    Copy-Item -LiteralPath $libraryDllSource -Destination (Join-Path $portableRuntimeRoot 'Library\bin') -Force
}
$portableSitePackagesRoot = Join-Path $portableRuntimeLibRoot 'site-packages'
New-Item -ItemType Directory -Path $portableSitePackagesRoot -Force | Out-Null
foreach ($sitePackageItem in (Get-ChildItem -LiteralPath $venvSitePackages -Force | Where-Object { $_.Name -ne '__pycache__' })) {
    Copy-Item -LiteralPath $sitePackageItem.FullName -Destination $portableSitePackagesRoot -Recurse -Force
}
Copy-Item -LiteralPath $pluginPackageInitSource -Destination (Join-Path $portablePluginsRoot '__init__.py')

function Copy-PortablePlugin {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourcePath,
        [Parameter(Mandatory = $true)]
        [string]$DestinationPath
    )

    New-Item -ItemType Directory -Path $DestinationPath -Force | Out-Null
    foreach ($item in Get-ChildItem -LiteralPath $SourcePath -Force) {
        if ($item.Name -in @(
            '.git',
            '.gitignore',
            '__pycache__',
            'AGENTS.md',
            'README.md',
            'data',
            'settings.json',
            'config.json',
            'config.ini',
            'native'
        )) {
            continue
        }
        if ($item.Name -like '*.log' -or $item.Name -like '*.pyc') {
            continue
        }

        $destinationItem = Join-Path $DestinationPath $item.Name
        if ($item.PSIsContainer) {
            Copy-PortablePlugin -SourcePath $item.FullName -DestinationPath $destinationItem
        } else {
            Copy-Item -LiteralPath $item.FullName -Destination $destinationItem -Force
        }
    }
}

foreach ($pluginSourceDirectory in $pluginSourceDirectories) {
    Copy-PortablePlugin `
        -SourcePath $pluginSourceDirectory.FullName `
        -DestinationPath (Join-Path $portablePluginsRoot $pluginSourceDirectory.Name)
}

$portableColmonNativeRoot = Join-Path $portablePluginsRoot 'colmon\native'
New-Item -ItemType Directory -Path $portableColmonNativeRoot -Force | Out-Null
Copy-Item -LiteralPath $colmonNativeExecutable `
    -Destination (Join-Path $portableColmonNativeRoot 'ColpilotColmonWindows.exe') `
    -Force

$portablePythonCacheDirectories = @(
    Get-ChildItem -LiteralPath $portableRuntimeRoot -Directory -Recurse -Force -Filter '__pycache__' |
        Sort-Object { $_.FullName.Length } -Descending
)
foreach ($cacheDirectory in $portablePythonCacheDirectories) {
    Remove-Item -LiteralPath $cacheDirectory.FullName -Recurse -Force
}
$portablePythonCacheFiles = @(
    Get-ChildItem -LiteralPath $portableRuntimeRoot -File -Recurse -Force -Filter '*.pyc'
)
foreach ($cacheFile in $portablePythonCacheFiles) {
    Remove-Item -LiteralPath $cacheFile.FullName -Force
}

$legacyColmonFiles = @(
    Get-ChildItem -LiteralPath $outputRoot -File -Recurse -Force |
        Where-Object { $_.Name -in @('Colmon.exe', 'colmon.ico') }
)
if ($legacyColmonFiles.Count -gt 0) {
    $legacyColmonPaths = $legacyColmonFiles.FullName -join ', '
    throw "portable 客户端不应包含旧的 Colmon 运行文件：$legacyColmonPaths"
}

$portableConfigFiles = @(
    Get-ChildItem -LiteralPath $outputRoot -File -Recurse -Force |
        Where-Object { $_.Name -eq 'config.ini' }
)
if ($portableConfigFiles.Count -gt 0) {
    $configPaths = $portableConfigFiles.FullName -join ', '
    throw "portable 客户端不应包含配置文件：$configPaths"
}

foreach ($generatedPath in @(
    (Join-Path $projectRoot 'dist'),
    (Join-Path $projectRoot 'src-tauri\target'),
    (Join-Path $projectRoot 'backend\__pycache__'),
    (Join-Path $projectRoot 'plugins')
)) {
    if (Test-Path -LiteralPath $generatedPath) {
        if ($generatedPath -eq (Join-Path $projectRoot 'plugins')) {
            Get-ChildItem -LiteralPath $generatedPath -Directory -Recurse -Filter '__pycache__' | Remove-Item -Recurse -Force
        } else {
            Remove-Item -LiteralPath $generatedPath -Recurse -Force
        }
    }
}

$targetFiles = @(Get-ChildItem -LiteralPath $outputRoot -Recurse -File)
$targetSize = ($targetFiles | Measure-Object -Property Length -Sum).Sum
Write-Output ("portable 客户端已经生成：{0} 个文件，{1} MB" -f $targetFiles.Count, [math]::Round($targetSize / 1MB, 1))
