# 启动 Slides Reader：一个 PowerShell 窗口、一个浏览器地址。
# 使用方式：在项目根目录运行 .\launch.ps1

$ErrorActionPreference = "Stop"
$RootDir = $PSScriptRoot
Set-Location $RootDir

$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCommand) {
    $PythonCommand = Get-Command py -ErrorAction SilentlyContinue
}

if (-not $PythonCommand) {
    Write-Host "没有找到 Python。请先安装 Python 3，然后重新打开 PowerShell。" -ForegroundColor Red
    exit 1
}

if ($PythonCommand.Name -eq "py.exe" -or $PythonCommand.Name -eq "py") {
    & $PythonCommand.Source -3 start.py
} else {
    & $PythonCommand.Source start.py
}
