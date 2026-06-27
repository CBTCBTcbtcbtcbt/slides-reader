# 一键准备项目本地运行环境。
# 这个脚本负责：
# 1. 检查 Python、Node.js 和 npm 是否可用。
# 2. 创建后端 Python 虚拟环境，并安装运行依赖和测试依赖。
# 3. 安装前端 npm 依赖。
# 4. 准备 LibreOffice，用于 PPT/PPTX 转 PDF。

# 开启严格错误处理，任何一步失败都立即中止，避免留下半初始化状态。
$ErrorActionPreference = "Stop"

# RootDir 表示当前脚本所在目录，也就是项目根目录。
$RootDir = $PSScriptRoot

# BackendDir 表示 FastAPI 后端目录。
$BackendDir = Join-Path $RootDir "backend"

# FrontendDir 表示 Vite 前端目录。
$FrontendDir = Join-Path $RootDir "frontend"

# FrontendNodeModulesDir 表示前端依赖安装后的目录。
$FrontendNodeModulesDir = Join-Path $FrontendDir "node_modules"

# ToolsDir 用来存放不会提交到 Git 的本地工具。
$ToolsDir = Join-Path $RootDir "tools"

# DownloadDir 用来缓存下载到本地的安装包。
$DownloadDir = Join-Path $ToolsDir "downloads"

# LibreOfficeRoot 用来存放 LibreOffice Portable 的安装目录。
$LibreOfficeRoot = Join-Path $ToolsDir "libreoffice"

# PortableSofficePath 是项目内 LibreOffice Portable 的 soffice.exe 预期位置。
$PortableSofficePath = Join-Path $LibreOfficeRoot "LibreOfficePortable\App\libreoffice\program\soffice.exe"

# DirectPortableSofficePath 兼容 PortableApps 安装器直接把 App 放进目标目录的结构。
$DirectPortableSofficePath = Join-Path $LibreOfficeRoot "App\libreoffice\program\soffice.exe"

# LegacyLibreOfficeRoot 兼容旧安装参数可能生成的拼接目录。
$LegacyLibreOfficeRoot = Join-Path $ToolsDir "libreofficeLibreOfficePortable"

# LegacyPortableSofficePath 是旧拼接目录中的 soffice.exe 位置。
$LegacyPortableSofficePath = Join-Path $LegacyLibreOfficeRoot "App\libreoffice\program\soffice.exe"

# BackendVenvDir 是后端 Python 虚拟环境目录。
$BackendVenvDir = Join-Path $BackendDir ".venv"

# BackendPython 是后端虚拟环境里的 Python 可执行文件。
$BackendPython = Join-Path $BackendVenvDir "Scripts\python.exe"

# BackendPip 是后端虚拟环境里的 pip 可执行文件。
$BackendPip = Join-Path $BackendVenvDir "Scripts\pip.exe"

# LibreOfficePortableUrl 是 LibreOffice Portable Standard 的官方下载入口。
# 后续如果需要升级版本，只需要替换这个 URL 和下面的安装包文件名。
$LibreOfficePortableUrl = "https://download.documentfoundation.org/libreoffice/portable/26.2.1/LibreOfficePortable_26.2.1_MultilingualStandard.paf.exe"

# InstallerPath 是下载到本地后的 PortableApps 安装包路径。
$InstallerPath = Join-Path $DownloadDir "LibreOfficePortable_26.2.1_MultilingualStandard.paf.exe"

function Write-Step {
    param(
        # Message 是当前步骤的说明文字。
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    # 用统一颜色输出步骤标题，让长脚本的进度更容易扫描。
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Resolve-CommandPath {
    param(
        # CommandName 是要检查的命令名，例如 python、node 或 npm。
        [Parameter(Mandatory = $true)]
        [string]$CommandName
    )

    # Get-Command 会搜索 PATH，找不到时返回空值。
    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    return $null
}

function Assert-CommandAvailable {
    param(
        # CommandName 是要检查的命令名。
        [Parameter(Mandatory = $true)]
        [string]$CommandName,

        # InstallHint 是命令缺失时给用户看的安装提示。
        [Parameter(Mandatory = $true)]
        [string]$InstallHint
    )

    # 系统级运行时不在脚本里静默安装，避免改动用户机器的全局环境。
    $commandPath = Resolve-CommandPath -CommandName $CommandName
    if (-not $commandPath) {
        throw "没有找到命令：${CommandName}。${InstallHint}"
    }

    Write-Host "${CommandName}：${commandPath}" -ForegroundColor Green
    return $commandPath
}

function Invoke-CheckedCommand {
    param(
        # FilePath 是要执行的程序路径或命令名。
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        # ArgumentList 是传给程序的参数数组。
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList,

        # WorkingDirectory 是命令运行目录。
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,

        # Description 是命令失败时输出的业务说明。
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    # Start-Process 可以稳定拿到退出码，避免 PowerShell 外部命令错误被吞掉。
    $process = Start-Process -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -NoNewWindow `
        -Wait `
        -PassThru

    # 非 0 退出码表示命令执行失败。
    if ($process.ExitCode -ne 0) {
        throw "${Description} 失败，退出码：$($process.ExitCode)"
    }
}

function Resolve-SofficePath {
    # 如果用户已经设置过环境变量，就优先使用用户指定的位置。
    if ($env:SLIDES_READER_SOFFICE_PATH) {
        if (Test-Path -LiteralPath $env:SLIDES_READER_SOFFICE_PATH) {
            return (Resolve-Path -LiteralPath $env:SLIDES_READER_SOFFICE_PATH).Path
        }
    }

    # localCandidatePaths 保存项目内 LibreOffice Portable 的常见固定路径。
    $localCandidatePaths = @(
        $PortableSofficePath,
        $DirectPortableSofficePath,
        $LegacyPortableSofficePath
    )

    # 先逐个检查项目内固定路径，保证已下载的便携版优先于系统安装版本。
    foreach ($candidatePath in $localCandidatePaths) {
        if ($candidatePath -and (Test-Path -LiteralPath $candidatePath)) {
            return (Resolve-Path -LiteralPath $candidatePath).Path
        }
    }

    # localSearchRoots 保存项目内可能出现 LibreOffice Portable 的根目录。
    $localSearchRoots = @(
        $LibreOfficeRoot,
        (Join-Path $LibreOfficeRoot "LibreOfficePortable"),
        $LegacyLibreOfficeRoot
    )

    # 如果安装器目录结构变化，就在项目工具目录内递归兜底查找 soffice.exe。
    foreach ($searchRoot in $localSearchRoots) {
        if (-not (Test-Path -LiteralPath $searchRoot)) {
            continue
        }

        $localMatch = Get-ChildItem -LiteralPath $searchRoot -Recurse -Filter "soffice.exe" -ErrorAction SilentlyContinue |
            Sort-Object { $_.FullName.Length }, FullName |
            Select-Object -First 1
        if ($localMatch) {
            return $localMatch.FullName
        }
    }

    # systemCandidatePaths 保存 Windows 常见的系统安装路径。
    $systemCandidatePaths = @(
        "C:\Program Files\LibreOffice\program\soffice.exe",
        "C:\Program Files (x86)\LibreOffice\program\soffice.exe"
    )

    # 项目内没有便携版时，再使用目标电脑已经安装好的 LibreOffice。
    foreach ($candidatePath in $systemCandidatePaths) {
        if ($candidatePath -and (Test-Path -LiteralPath $candidatePath)) {
            return (Resolve-Path -LiteralPath $candidatePath).Path
        }
    }

    # 如果 PATH 环境变量里已经能找到 soffice.exe，也允许直接使用。
    $sofficeCommand = Get-Command "soffice.exe" -ErrorAction SilentlyContinue
    if ($sofficeCommand) {
        return $sofficeCommand.Source
    }

    # 找不到时返回空值，由调用方决定是否下载。
    return $null
}

function Invoke-FileDownload {
    param(
        # Url 是远程文件地址。
        [Parameter(Mandatory = $true)]
        [string]$Url,

        # OutputPath 是下载后的本地保存路径。
        [Parameter(Mandatory = $true)]
        [string]$OutputPath
    )

    # 确保下载目录存在。
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPath) | Out-Null

    # 如果安装包已经存在，就复用本地文件，避免重复下载两百多 MB 的文件。
    if (Test-Path -LiteralPath $OutputPath) {
        Write-Host "已存在下载缓存：${OutputPath}" -ForegroundColor Green
        return
    }

    # 下载 PortableApps 安装包。
    Write-Host "正在下载 LibreOffice Portable，文件约 224 MB，请耐心等待。"
    Write-Host "下载地址：${Url}"
    Invoke-WebRequest -Uri $Url -OutFile $OutputPath -UseBasicParsing
    Write-Host "下载完成：${OutputPath}" -ForegroundColor Green
}

function Install-LibreOfficePortable {
    param(
        # Installer 是 PortableApps 的 .paf.exe 安装包路径。
        [Parameter(Mandatory = $true)]
        [string]$Installer,

        # Destination 是 LibreOffice Portable 的安装目标目录。
        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    # 确保目标目录存在。
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null

    # PortableApps 安装器会把应用目录名追加到 /DESTINATION 后面。
    # 如果路径末尾没有目录分隔符，可能生成 libreofficeLibreOfficePortable 这种拼接目录。
    $destinationForInstaller = $Destination
    if (-not ($destinationForInstaller.EndsWith("\") -or $destinationForInstaller.EndsWith("/"))) {
        $destinationForInstaller = "${destinationForInstaller}\"
    }

    # PortableApps 安装器支持 /S 静默安装和 /DESTINATION= 指定目标目录。
    # 这里用 Start-Process 等待安装完成，避免后续立即检测路径时安装还没结束。
    Write-Host "正在解压 LibreOffice Portable 到：${Destination}"
    $process = Start-Process -FilePath $Installer -ArgumentList @(
        "/S",
        "/DESTINATION=$destinationForInstaller"
    ) -Wait -PassThru

    # 非 0 退出码通常表示安装器执行失败。
    if ($process.ExitCode -ne 0) {
        throw "LibreOffice Portable 安装器退出码异常：$($process.ExitCode)"
    }
}

function Initialize-BackendEnvironment {
    param(
        # PythonCommand 是系统 Python 命令路径。
        [Parameter(Mandatory = $true)]
        [string]$PythonCommand
    )

    Write-Step "准备后端 Python 虚拟环境"

    # 如果虚拟环境不存在，就用系统 Python 创建。
    if (-not (Test-Path -LiteralPath $BackendPython)) {
        Write-Host "正在创建虚拟环境：${BackendVenvDir}"
        Invoke-CheckedCommand -FilePath $PythonCommand `
            -ArgumentList @("-m", "venv", $BackendVenvDir) `
            -WorkingDirectory $BackendDir `
            -Description "创建后端虚拟环境"
    } else {
        Write-Host "已存在后端虚拟环境：${BackendVenvDir}" -ForegroundColor Green
    }

    # 创建完成后再次检查，避免 Python venv 创建失败但没有抛出明确错误。
    if (-not (Test-Path -LiteralPath $BackendPython)) {
        throw "后端虚拟环境创建后仍找不到 Python：${BackendPython}"
    }

    # 先升级 pip，再安装项目依赖。
    Write-Host "正在升级后端 pip..."
    Invoke-CheckedCommand -FilePath $BackendPython `
        -ArgumentList @("-m", "pip", "install", "--upgrade", "pip") `
        -WorkingDirectory $BackendDir `
        -Description "升级后端 pip"

    Write-Host "正在安装后端运行依赖..."
    Invoke-CheckedCommand -FilePath $BackendPython `
        -ArgumentList @("-m", "pip", "install", "-r", "requirements.txt") `
        -WorkingDirectory $BackendDir `
        -Description "安装后端运行依赖"

    # 如果存在测试依赖文件，也一起安装，保证 pytest 可以直接运行。
    $requirementsDevPath = Join-Path $BackendDir "requirements-dev.txt"
    if (Test-Path -LiteralPath $requirementsDevPath) {
        Write-Host "正在安装后端测试依赖..."
        Invoke-CheckedCommand -FilePath $BackendPython `
            -ArgumentList @("-m", "pip", "install", "-r", "requirements-dev.txt") `
            -WorkingDirectory $BackendDir `
            -Description "安装后端测试依赖"
    }

    Write-Host "后端环境准备完成：${BackendPython}" -ForegroundColor Green
}

function Initialize-FrontendEnvironment {
    param(
        # NpmCommand 是 Windows 上更稳定的 npm.cmd 路径。
        [Parameter(Mandatory = $true)]
        [string]$NpmCommand
    )

    Write-Step "准备前端 npm 依赖"

    # package-lock.json 存在时优先使用 npm ci，保证依赖版本和锁文件一致。
    $packageLockPath = Join-Path $FrontendDir "package-lock.json"
    if (Test-Path -LiteralPath $packageLockPath) {
        Write-Host "检测到 package-lock.json，正在执行 npm ci..."
        Invoke-CheckedCommand -FilePath $NpmCommand `
            -ArgumentList @("ci") `
            -WorkingDirectory $FrontendDir `
            -Description "安装前端依赖"
    } else {
        Write-Host "没有 package-lock.json，正在执行 npm install..."
        Invoke-CheckedCommand -FilePath $NpmCommand `
            -ArgumentList @("install") `
            -WorkingDirectory $FrontendDir `
            -Description "安装前端依赖"
    }

    Write-Host "前端依赖准备完成：${FrontendNodeModulesDir}" -ForegroundColor Green
}

function Initialize-LibreOffice {
    Write-Step "准备 LibreOffice"

    # 脚本开始时先检查本机是否已经存在可用的 LibreOffice。
    $existingSofficePath = Resolve-SofficePath
    if ($existingSofficePath) {
        $env:SLIDES_READER_SOFFICE_PATH = $existingSofficePath
        Write-Host "已找到 LibreOffice：${existingSofficePath}" -ForegroundColor Green
        return $existingSofficePath
    }

    # 本机找不到 LibreOffice 时，下载并解压项目内便携版。
    Invoke-FileDownload -Url $LibreOfficePortableUrl -OutputPath $InstallerPath
    Install-LibreOfficePortable -Installer $InstallerPath -Destination $LibreOfficeRoot

    # 安装完成后重新搜索 soffice.exe，兼容安装器生成的目录层级发生变化的情况。
    $installedSofficePath = Resolve-SofficePath
    if (-not $installedSofficePath) {
        $installedSofficePath = Get-ChildItem -Path $LibreOfficeRoot -Recurse -Filter "soffice.exe" -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
    }

    # 如果仍然找不到 soffice.exe，就说明下载或解压结果不符合预期。
    if (-not $installedSofficePath) {
        throw "LibreOffice Portable 已下载并执行安装器，但没有在 ${LibreOfficeRoot} 下找到 soffice.exe。"
    }

    # 把路径写入当前 PowerShell 会话，方便用户马上运行测试脚本或启动脚本。
    $env:SLIDES_READER_SOFFICE_PATH = $installedSofficePath
    Write-Host "LibreOffice Portable 准备完成：${installedSofficePath}" -ForegroundColor Green
    return $installedSofficePath
}

Write-Step "检查系统运行时"
$pythonCommand = Assert-CommandAvailable `
    -CommandName "python.exe" `
    -InstallHint "请先安装 Python 3.11 或更高版本，并确认 python.exe 已加入 PATH。"
Assert-CommandAvailable `
    -CommandName "node.exe" `
    -InstallHint "请先安装 Node.js 20.19 或更高版本，并确认 node.exe 已加入 PATH。" | Out-Null
$npmCommand = Assert-CommandAvailable `
    -CommandName "npm.cmd" `
    -InstallHint "请先安装 Node.js 附带的 npm，并确认 npm.cmd 已加入 PATH。"

Initialize-BackendEnvironment -PythonCommand $pythonCommand
Initialize-FrontendEnvironment -NpmCommand $npmCommand
$sofficePath = Initialize-LibreOffice

Write-Step "环境准备完成"
Write-Host "后端 Python：${BackendPython}" -ForegroundColor Green
Write-Host "前端依赖：${FrontendNodeModulesDir}" -ForegroundColor Green
Write-Host "LibreOffice：${sofficePath}" -ForegroundColor Green
Write-Host "当前 PowerShell 会话已设置 SLIDES_READER_SOFFICE_PATH。"
Write-Host "之后可以运行：.\launch.ps1"
