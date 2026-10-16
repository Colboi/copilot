# Colpilot

Colpilot 是一个 Windows 桌面插件宿主和仪表盘，使用 Vue、Tauri、FastAPI 与本地 Python 运行环境。程序提供统一的插件卡片、插件生命周期管理、插件进程管理、程序级配置保存和本地 HTTP 接口。

当前项目不预装任何插件。全新项目目录中的 plugins 目录只包含插件包初始化文件；没有插件清单时，程序不会显示插件卡片。每个插件的功能、使用条件、外部服务、安装步骤、配置项、运行文件和故障处理说明，都写在对应插件目录的 README.md 中。

## 开发环境

安装以下工具：

- Node.js 22 或更高版本
- Python 3.12 或更高版本
- Rust stable 工具链
- Windows WebView2 Runtime

## 安装依赖

~~~powershell
python -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -r backend\\requirements.txt
npm install
~~~

## 放置插件

将插件目录放在 plugins\\<plugin-id> 中。插件目录需要提供 manifest.json、后端入口和前端组件；具体文件结构、依赖、配置项和使用步骤以该目录中的 README.md 为准。

插件需要在启动开发服务或构建客户端之前放入 plugins 目录。程序启动时会读取每个插件的 manifest.json，并按照清单加载后端实现。前端组件会在 Vite 构建时读取，已经生成的 portable 客户端不会在运行时加载后来加入的前端组件。

## 启动程序

~~~powershell
npm run tauri dev
~~~

启动后，Tauri 会创建桌面窗口、任务栏图标和右键菜单，同时在后台启动本地 FastAPI 服务。Python 服务不会创建命令提示符窗口。

程序启动时会显示前端工作台。单击任务栏托盘图标会显示并聚焦工作台；关闭窗口时程序会回到托盘，右键菜单提供退出功能。点击退出后，Tauri 会向 Python 服务发送 exit 指令，随后结束本地服务、插件进程和桌面程序。

## 生成客户端

~~~powershell
npm run build:client
~~~

构建完成后，portable 客户端目录位于 target：

- target\\colpilot.exe
- target\\backend\\main.py、requirements.txt
- target\\runtime：独立 Python 运行目录、标准库、扩展模块和后端依赖
- target\\plugins\\<plugin-id>：构建时存在于本地 plugins 目录中的插件文件

构建时本地没有插件目录时，客户端不会包含任何插件。将 target 目录整体复制到其他目录后，程序会优先读取其中的后端文件、Python 运行目录和插件文件。

程序级设置首次保存时，会在 colpilot.exe 所在目录创建 config.ini；插件设置首次保存时，会在对应的 plugins\\<plugin-id> 目录创建 config.ini。构建脚本和 portable 输出不会包含这些配置文件，portable 应用压缩包解压后保存设置时，程序会在对应目录创建新的配置文件。

程序目录的 config.ini 保存 [colpilot] 配置节中的插件启用状态和插件显示顺序。左侧插件导航支持拖拽排序，右侧插件卡片使用相同顺序。插件目录的 config.ini 保存该插件的配置。更新请求只写入请求中提供的配置项；空值的含义和清除方式由插件自己的 README.md 说明。

## 目录用途

- backend：FastAPI 服务源代码
- config.ini：程序运行后生成的程序级配置文件
- plugins：可选插件目录，核心项目通过清单发现本机已经放入的插件
- src：Vue 前端源代码
- src-tauri：Tauri 桌面程序源代码和配置
- scripts：客户端构建脚本
- target：构建生成的 portable 客户端目录
- node_modules、.venv：本地开发依赖
- .learnings：开发过程记录

## 插件加载规则

每个插件通过 manifest.json 描述自身信息和入口。核心项目会检查以下内容：

- 插件标识、名称、说明、图标、分类和显示颜色
- tool_type：continuous 或 on_demand
- 后端模块和工厂函数
- 前端视图入口

continuous 插件需要提供 start、stop 和 runtime_status 方法。on_demand 插件需要提供 run(arguments) 方法。插件产生的进程需要交给 Colpilot 的进程管理器登记，程序退出时统一结束这些进程。

## 通用接口

- GET /api/health：检查本地服务状态
- GET /api/plugins：读取已经发现的插件清单
- POST /api/plugins/order：保存插件显示顺序，参数格式为 {"order":["plugin-a","plugin-b"]}
- GET /api/plugins/{plugin_id}/status：读取插件状态
- POST /api/plugins/{plugin_id}/settings：保存插件设置
- POST /api/plugins/{plugin_id}/toggle：启用或停用插件
- POST /api/plugins/{plugin_id}/run：按需运行插件，参数格式为 {"arguments":{}}
- POST /api/plugins/{plugin_id}/open-output-directory：打开插件提供的输出目录
- POST /api/commands：发送程序指令，当前支持 {"command":"exit"}

插件专用接口、参数、返回数据和外部服务说明，写在对应插件目录的 README.md 中。
