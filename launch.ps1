# 启动本地开发服务：FastAPI 后端 + Vite 前端。
# 使用方式：在项目根目录运行 .\launch.ps1。

# 开启严格错误处理，避免某一步失败后脚本继续启动出半工作状态的服务。
$ErrorActionPreference = "Stop"

# RootDir 表示当前脚本所在目录，也就是项目根目录。
$RootDir = $PSScriptRoot

# BackendDir 表示后端目录，用于启动 FastAPI 服务。
$BackendDir = Join-Path $RootDir "backend"

# FrontendDir 表示前端目录，用于启动 Vite 服务。
$FrontendDir = Join-Path $RootDir "frontend"

# BackendPython 表示后端虚拟环境里的 Python 可执行文件。
$BackendPython = Join-Path $BackendDir ".venv\Scripts\python.exe"

# Resolve-SofficePath 用来查找 LibreOffice 的 soffice.exe。
# soffice.exe 是 LibreOffice 的命令行入口，后续 PPT/PPTX 转 PDF 会依赖它。
function Resolve-SofficePath {
    # candidatePaths 保存按优先级排列的候选路径。
    $candidatePaths = @()

    # 如果用户显式设置了环境变量，就优先使用用户指定的位置。
    if ($env:SLIDES_READER_SOFFICE_PATH) {
        $candidatePaths += $env:SLIDES_READER_SOFFICE_PATH
    }

    # 检查项目内由 setup-env.ps1 下载的 LibreOffice Portable。
    $candidatePaths += Join-Path $RootDir "tools\libreoffice\LibreOfficePortable\App\libreoffice\program\soffice.exe"

    # 检查 Windows 常见的系统安装路径。
    $candidatePaths += "C:\Program Files\LibreOffice\program\soffice.exe"
    $candidatePaths += "C:\Program Files (x86)\LibreOffice\program\soffice.exe"

    # 逐个检查候选路径，找到第一个真实存在的 soffice.exe 后返回。
    foreach ($candidatePath in $candidatePaths) {
        if ($candidatePath -and (Test-Path -LiteralPath $candidatePath)) {
            return (Resolve-Path -LiteralPath $candidatePath).Path
        }
    }

    # 如果 PATH 环境变量里已经能找到 soffice.exe，也允许直接使用。
    $sofficeCommand = Get-Command "soffice.exe" -ErrorAction SilentlyContinue
    if ($sofficeCommand) {
        return $sofficeCommand.Source
    }

    # 找不到时返回空值，由调用方决定如何提示用户。
    return $null
}

# 检查后端虚拟环境是否已经创建。
if (-not (Test-Path $BackendPython)) {
    Write-Host "没有找到后端虚拟环境：$BackendPython" -ForegroundColor Red
    Write-Host "请先运行：cd backend; python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt"
    exit 1
}

# 检查前端依赖是否已经安装。
if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Host "没有找到前端依赖目录：frontend\node_modules" -ForegroundColor Red
    Write-Host "请先运行：cd frontend; npm install"
    exit 1
}

# 检查 LibreOffice 是否可用；找不到时只提示安装脚本，不在启动脚本里自动下载大文件。
$SofficePath = Resolve-SofficePath
if (-not $SofficePath) {
    Write-Host "没有找到 LibreOffice 的 soffice.exe。" -ForegroundColor Yellow
    Write-Host "PPT/PPTX 转 PDF 需要 LibreOffice。请先运行：.\setup-env.ps1" -ForegroundColor Yellow
    Write-Host "如果你已经手动安装 LibreOffice，也可以设置环境变量 SLIDES_READER_SOFFICE_PATH 指向 soffice.exe。"
    exit 1
}

# 把检测到的 soffice.exe 路径写入当前 PowerShell 进程环境变量。
# Start-Process 默认会继承当前进程环境变量，因此后端也可以读取这个路径。
$env:SLIDES_READER_SOFFICE_PATH = $SofficePath

# 启动后端服务，并让窗口保持打开，方便查看 uvicorn 日志。
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$BackendDir'; & '$BackendPython' -m uvicorn main:app --reload --host 127.0.0.1 --port 8000"
)

# 启动前端开发服务，并让窗口保持打开，方便查看 Vite 日志。
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$FrontendDir'; npm run dev"
)

Write-Host "开发服务已经启动。" -ForegroundColor Green
Write-Host "LibreOffice: $SofficePath"
Write-Host "后端：http://127.0.0.1:8000"
Write-Host "前端：http://localhost:5173"

