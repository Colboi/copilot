# copilot

Colpilot 是一个 Windows 工具集合的桌面程序原型，使用 Vue 仪表盘、Tauri 桌面容器和 FastAPI 本地服务。

## 开发环境

安装以下工具：

- Node.js 22 或更高版本
- Python 3.12 或更高版本
- Rust stable 工具链
- Windows WebView2 Runtime

## 安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
npm install
```

## 启动程序

```powershell
npm run tauri dev
```

启动后，Tauri 会创建桌面窗口、任务栏图标和右键菜单，同时在后台启动本地 FastAPI 服务。Python 服务不会创建命令提示符窗口。

程序启动时会自动显示前端工作台。单击任务栏托盘图标会显示并聚焦工作台；关闭窗口时程序会回到托盘，右键菜单当前只提供“退出”功能。点击“退出”后，Tauri 会向 Python 服务发送 `exit` 指令，随后结束本地服务和桌面程序。

## 生成客户端

```powershell
npm run build:client
```

构建完成后，完整 portable 客户端目录位于 `target`：

- `target\colpilot.exe`
- `target\backend\main.py`、`requirements.txt`
- `target\runtime`：独立 Python 运行目录、标准库、扩展模块和后端依赖
- `target\plugins\colszunet`：colszunet 插件清单、后端实现、前端组件、样式和监控程序文件
- `target\plugins\coldmmpics`：coldmmpics 插件清单、后端实现、前端组件和样式文件

将 `target` 目录整体复制到其他目录后，程序会优先读取其中的后端文件、Python 运行目录和校园网插件文件。构建过程产生的安装程序、`dist`、`src-tauri\target` 和 Python 编译缓存会在文件复制完成后自动清理，安装程序不会进入 `target`。

## 目录用途

- `backend`：FastAPI 服务源代码
- `plugins`：可选插件仓库目录，核心项目通过清单发现本机已经放入的插件
- `src`：Vue 前端源代码
- `src-tauri`：Tauri 桌面程序源代码和配置
- `scripts`：客户端构建脚本
- `target`：解压后即可运行的完整 portable 客户端目录
- `node_modules`、`.venv`：本地开发依赖
- `.learnings`：开发过程记录

每个插件按独立 GitHub 仓库管理，插件目录保存 `manifest.json`、后端实现、前端组件、样式和运行文件。核心项目通过插件清单发现本机已经放入的插件，并提供通用生命周期管理与 HTTP 接口。

## 当前接口

- `GET /api/health`：检查本地服务状态
- `GET /api/plugins`：读取功能插件清单
- `GET /api/plugins/colszunet/status`：读取校园网当前状态、监听状态和 24h/7d 历史状态段
- `POST /api/plugins/colszunet/settings`：保存校园网检查间隔，例如 `{"probe_interval_seconds":300}`
- `GET /api/plugins/coldmmpics/status`：读取 coldmmpics 插件设置、任务状态和最近一次结果
- `POST /api/plugins/coldmmpics/settings`：保存 coldmmpics 输出文件夹路径
- `POST /api/plugins/coldmmpics/run`：读取作品页面、保存元数据和下载预览图
- `POST /api/plugins/coldmmpics/open-output-directory`：打开已经选择的 coldmmpics 输出文件夹
- `POST /api/plugins/{plugin_id}/toggle`：启用或停用功能插件
- `POST /api/plugins/{plugin_id}/run`：按需运行工具，参数格式为 `{"arguments":{}}`
- `POST /api/commands`：发送程序指令，当前支持 `{"command":"exit"}`

## 工具类型

- `continuous`：持续运行工具。插件清单需要提供 `start`、`stop` 和 `runtime_status` 接口。`/api/plugins` 返回 `runtime.status`，取值为 `running`、`stopped` 或 `error`；侧边栏分别显示绿色、灰色和红色标志。
- `on_demand`：按需运行工具。插件清单需要提供 `run(arguments)` 接口；侧边栏不显示运行标志。

持续运行工具的 `error` 只表示后台脚本自身异常退出。工具正常监控到网络故障时，运行标志继续保持绿色，业务状态由插件页面单独显示。

## coldmmpics（DMM 作品资料插件）

DMM 作品资料插件属于按需运行工具。运行前需要在插件页面选择输出文件夹，选择结果会立即保存到插件目录的 `settings.json`。输入作品番号后，插件会优先使用字母和数字分开的搜索词，例如 `miad 657`，并只选择视频详情链接；DMM 返回年龄或地区确认页面时，插件会自动提交确认并继续访问。插件读取页面公开的 `Product JSON-LD`；页面只返回 Next.js 应用外壳时，插件调用 DMM 的公开 GraphQL 作品资料接口，并在输出文件夹下创建作品目录：

```text
输出文件夹\SNOS-308\metadata.json
输出文件夹\SNOS-308\snos00308pl.jpg
输出文件夹\SNOS-308\snos00308ps.jpg
输出文件夹\SNOS-308\snos00308jp-1.jpg
```

作品目录名称由作品 URL 中的 `id` 生成：字母转为大写，数字去除前导零后按至少三位数字保存。搜索、页面或 DMM 作品资料接口无法访问，或者预览图下载失败时，插件页面会显示具体错误信息。

## colszunet（校园网监控插件）

开发模式和 portable 客户端都会从 colszunet 插件仓库的 `worker` 子目录读取 `colszunet.py`、`config.json` 和 `colszunet.log`。后端启动时会启动 `colszunet` 监控进程，插件页面显示以下内容：

- 校园网目前状态
- 监听状态
- 24h / 7d 内状态

校园网默认每 300 秒检查一次，可以在插件详情页面修改检查间隔。账号和密码输入框会在停止输入约 700 毫秒后自动保存，连续输入期间只发送最后一次保存请求。24h/7d 状态条按照时间段显示检测结果，成功显示绿色，失败显示红色，无记录显示灰色。保存设置后，监控进程会按照新的配置继续运行。

插件仓库中的 `plugins\colszunet\worker\config.json` 保存空账号和空密码，适合提交至 GitHub。运行程序后，请在校园网监控页面填写账号和密码；portable 客户端请在 `target\plugins\colszunet\worker\config.json` 中保存运行配置。配置文件包含校园网账号信息，请保护整个客户端目录。
