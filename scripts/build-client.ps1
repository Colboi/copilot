$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$outputRoot = Join-Path $projectRoot 'target'
$releaseRoot = Join-Path $projectRoot 'src-tauri\target\release'
$runtimeSource = Join-Path $projectRoot '.venv'
$runtimeBuilderPython = Join-Path $runtimeSource 'Scripts\python.exe'
$pluginSourceRoot = Join-Path $projectRoot 'plugins'
$pluginSourceDirectories = @(
    Get-ChildItem -LiteralPath $pluginSourceRoot -Directory |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'manifest.json') }
)
$pluginPackageInitSource = Join-Path $pluginSourceRoot '__init__.py'
$backendScriptSource = Join-Path $projectRoot 'backend\main.py'
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
    $backendRequirementsSource,
    (Join-Path $baseRuntimeRoot 'python.exe'),
    (Join-Path $baseRuntimeRoot 'pythonw.exe'),
    $baseRuntimeLibRoot,
    $baseRuntimeDllRoot,
    $venvSitePackages,
    $portableLibraryDllSources,
    $pluginPackageInitSource,
    $pluginSourceDirectories.FullName
)

foreach ($sourcePath in @($artifactSources + $portableSources)) {
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        throw "客户端文件不存在：$sourcePath"
    }
}

if (Test-Path -LiteralPath $outputRoot) {
    Get-ChildItem -LiteralPath $outputRoot -Force | Remove-Item -Recurse -Force
} else {
    New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
}

Copy-Item -LiteralPath $artifactSources[0] -Destination (Join-Path $outputRoot 'colpilot.exe')
New-Item -ItemType Directory -Path $portableBackendRoot,$portableRuntimeRoot,$portablePluginsRoot -Force | Out-Null

Copy-Item -LiteralPath $backendScriptSource -Destination (Join-Path $portableBackendRoot 'main.py')
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
foreach ($pluginSourceDirectory in $pluginSourceDirectories) {
    Copy-Item -LiteralPath $pluginSourceDirectory.FullName -Destination $portablePluginsRoot -Recurse -Force
}
Get-ChildItem -LiteralPath $portablePluginsRoot -Directory -Recurse -Filter '__pycache__' | Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $portablePluginsRoot -Directory -Recurse -Force -Filter '.git' | Remove-Item -Recurse -Force

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
