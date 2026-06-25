# Slides Reader

Slides Reader 是一个在本机运行的 AI slides 阅读工具。你可以上传 PDF、PPT 或 PPTX 课件，应用会把课件整理成可阅读的 PDF 页面，并使用你配置的大语言模型生成课程简介、逐页讲稿、当前页答疑、试卷、错题本和阶段考试。

`AI` 在这里指通过模型服务生成文字回答。`LLM` 是 `Large Language Model` 的缩写，中文通常叫“大语言模型”。本项目支持 OpenAI-compatible API，也就是接口格式兼容 OpenAI Chat Completions 的模型服务。

## 你需要准备什么

运行源码版需要：

- Python 3.11 或更新版本。
- Node.js 20 或更新版本。
- 一个可用的模型服务地址、API Key 和模型名。
- 如果要上传 PPT 或 PPTX，需要安装 LibreOffice；只上传 PDF 时不需要。

`Python` 用来启动后端程序。`Node.js` 和 `npm` 用来安装和构建网页界面。`LibreOffice` 是一个办公软件套件，本项目用它把 PPT/PPTX 转换成 PDF。

## Windows 启动

1. 打开项目文件夹。
2. 在文件夹空白处按住 `Shift` 并点击鼠标右键。
3. 选择“在终端中打开”或“在 PowerShell 中打开”。
4. 在打开的窗口里运行：

```powershell
python start.py
```

第一次启动会自动创建后端虚拟环境、安装依赖、安装前端依赖并构建网页。这个过程可能需要几分钟。

启动成功后会自动打开浏览器。如果没有自动打开，请在终端里找到这一行：

```text
Open: http://localhost:8000/
```

然后把 `Open:` 后面的地址复制到浏览器地址栏。

停止程序时，回到终端窗口，按：

```text
Ctrl+C
```

## macOS 或 Linux 启动

在项目根目录运行：

```bash
python3 start.py
```

启动成功后浏览器会自动打开。如果没有自动打开，就复制终端中 `Open:` 后面的地址到浏览器。

停止程序时，在终端按 `Ctrl+C`。

## 配置模型服务

第一次打开网页后，进入“设置”页面，填写：

- `Base URL`：模型服务地址，例如 `https://api.openai.com/v1`。
- `API Key`：模型服务密钥。
- `Model`：模型名。
- `Timeout`：请求超时时间。
- 各类 prompt：课程简介、逐页讲稿、当前页问答和试卷生成使用的指令文本。

`Prompt` 是发送给大语言模型的指令文本，用来告诉模型应该扮演什么角色、看哪些内容、输出什么格式。

保存设置后，可以点击测试连接，确认模型服务能正常回答。

## 使用流程

1. 启动应用并打开网页。
2. 进入设置页，配置模型服务。
3. 回到文件页，上传 PDF、PPT 或 PPTX。
4. 等待课程简介和逐页讲稿生成。
5. 点击阅读，查看课件、讲稿和当前页问答。
6. 在文件页可以生成试卷。
7. 在答题后可以查看结果和错题本。
8. 可以选择多份课件创建阶段考试。

上传 PPT/PPTX 时，如果系统找不到 LibreOffice，会提示转换失败。此时可以先安装 LibreOffice，再重新上传。

## 常用命令

不自动打开浏览器：

```powershell
python start.py --no-open
```

只检查环境，不启动服务：

```powershell
python start.py --diagnostics
```

显示更详细的启动日志：

```powershell
python start.py --log-level DEBUG
```

指定端口：

```powershell
python start.py --port 8010
```

如果指定端口已经被占用，启动器会自动寻找后面的空闲端口。实际打开哪个地址，以终端里的 `Open:` 为准。

## 日志和运行数据

运行数据默认保存在：

```text
storage/
```

这里包括数据库、上传后的 PDF、页面截图、聊天图片和日志。不要随意删除 `storage/`，否则历史文档和答题记录会丢失。

日志默认保存在：

```text
storage/logs/
```

常用日志文件：

- `launcher.log`：启动器日志。
- `backend-install.log`：后端依赖安装日志。
- `frontend-install.log`：前端依赖安装日志。
- `frontend-build.log`：前端构建日志。
- `slides-reader.log`：后端服务和业务运行日志。
- `diagnostics.txt`：环境诊断结果。

启动失败时，优先运行：

```powershell
python start.py --diagnostics
```

然后查看 `storage/logs/` 里的日志文件。

## Windows EXE

如果项目目录里已经有 `SlidesReader.exe`，可以双击它启动。这个 exe 是轻量启动器，旁边仍然需要保留：

```text
backend/
frontend/
storage/
README.md
```

也就是说，不要只复制单独的 `SlidesReader.exe`；它需要和项目文件夹一起使用。

## 开发者文档

如果你要修改代码、排查接口、理解数据库结构或重新打包 exe，请阅读：

[开发者文档入口](./docs/developer/README.md)
