# 准备项目本地运行环境中的外部工具。
# 当前脚本只负责 LibreOffice Portable，因为 Python 和 Node.js 仍由开发者按系统方式安装。

# 开启严格错误处理，任何下载、安装或路径检测失败都会立即中止脚本。
$ErrorActionPreference = "Stop"

# RootDir 表示当前脚本所在目录，也就是项目根目录。
$RootDir = $PSScriptRoot

# ToolsDir 用来存放不会提交到 Git 的本地工具。
$ToolsDir = Join-Path $RootDir "tools"

# DownloadDir 用来缓存下载到本地的安装包。
$DownloadDir = Join-Path $ToolsDir "downloads"

# LibreOfficeRoot 用来存放 LibreOffice Portable 的安装目录。
$LibreOfficeRoot = Join-Path $ToolsDir "libreoffice"

# PortableSofficePath 是项目内 LibreOffice Portable 的 soffice.exe 预期位置。
$PortableSofficePath = Join-Path $LibreOfficeRoot "LibreOfficePortable\App\libreoffice\program\soffice.exe"

# LibreOfficePortableUrl 是 LibreOffice Portable Standard 的官方下载入口。
# 后续如果需要升级版本，只需要替换这个 URL 和下面的安装包文件名。
$LibreOfficePortableUrl = "https://download.documentfoundation.org/libreoffice/portable/26.2.1/LibreOfficePortable_26.2.1_MultilingualStandard.paf.exe"

# InstallerPath 是下载到本地后的 PortableApps 安装包路径。
$InstallerPath = Join-Path $DownloadDir "LibreOfficePortable_26.2.1_MultilingualStandard.paf.exe"

# Resolve-SofficePath 用来查找当前机器上已经可用的 soffice.exe。
function Resolve-SofficePath {
    # candidatePaths 保存按优先级排列的候选路径。
    $candidatePaths = @()

    # 如果用户已经设置过环境变量，就优先使用用户指定的位置。
    if ($env:SLIDES_READER_SOFFICE_PATH) {
        $candidatePaths += $env:SLIDES_READER_SOFFICE_PATH
    }

    # 检查项目内的 LibreOffice Portable。
    $candidatePaths += $PortableSofficePath

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

    # 找不到时返回空值，由调用方决定是否下载。
    return $null
}

# Invoke-FileDownload 用来下载大文件，并打印清晰的状态信息。
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
        Write-Host "已存在下载缓存：$OutputPath" -ForegroundColor Green
        return
    }

    # 下载 PortableApps 安装包。
    Write-Host "正在下载 LibreOffice Portable，文件约 224 MB，请耐心等待。"
    Write-Host "下载地址：$Url"
    Invoke-WebRequest -Uri $Url -OutFile $OutputPath -UseBasicParsing
    Write-Host "下载完成：$OutputPath" -ForegroundColor Green
}

# Install-LibreOfficePortable 用来把 PortableApps 安装包解压到项目 tools 目录。
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

    # PortableApps 安装器支持 /S 静默安装和 /DESTINATION= 指定目标目录。
    # 这里用 Start-Process 等待安装完成，避免后续立即检测路径时安装还没结束。
    Write-Host "正在解压 LibreOffice Portable 到：$Destination"
    $process = Start-Process -FilePath $Installer -ArgumentList @(
        "/S",
        "/DESTINATION=$Destination"
    ) -Wait -PassThru

    # 非 0 退出码通常表示安装器执行失败。
    if ($process.ExitCode -ne 0) {
        throw "LibreOffice Portable 安装器退出码异常：$($process.ExitCode)"
    }
}

# 脚本开始时先检查本机是否已经存在可用的 LibreOffice。
$existingSofficePath = Resolve-SofficePath
if ($existingSofficePath) {
    $env:SLIDES_READER_SOFFICE_PATH = $existingSofficePath
    Write-Host "已找到 LibreOffice：$existingSofficePath" -ForegroundColor Green
    Write-Host "当前 PowerShell 会话已设置 SLIDES_READER_SOFFICE_PATH。"
    exit 0
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
    throw "LibreOffice Portable 已下载并执行安装器，但没有在 $LibreOfficeRoot 下找到 soffice.exe。"
}

# 把路径写入当前 PowerShell 会话，方便用户马上运行测试脚本或启动脚本。
$env:SLIDES_READER_SOFFICE_PATH = $installedSofficePath

# 输出最终结果。
Write-Host "LibreOffice Portable 准备完成。" -ForegroundColor Green
Write-Host "soffice.exe：$installedSofficePath"
Write-Host "当前 PowerShell 会话已设置 SLIDES_READER_SOFFICE_PATH。"
Write-Host "之后可以运行：.\launch.ps1"

