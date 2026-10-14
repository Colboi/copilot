# Learnings

Corrections, insights, and knowledge gaps captured during development.

**Categories**: correction | insight | knowledge_gap | best_practice

---

## [LRN-20261013-004] broad_project_repository_scope

**Logged**: 2026-10-13
**Priority**: high
**Status**: resolved
**Area**: infra

### Summary
本项目中的“项目”表示 GitHub 仓库边界；独立插件仓库按需要保留源文件和仓库配置，根项目保留根目录 `AGENTS.md`。

### Details
- `plugins/colszunet` 与 `plugins/coldmmpics` 作为独立 GitHub 仓库管理。
- 插件目录不需要额外的 `AGENTS.md` 等代理说明文件。
- 核心项目通过插件清单发现本机已经放入的插件。

### Suggested Action
后续新增插件仓库时，只添加运行所需文件和必要的仓库配置，避免为每个插件复制核心项目管理文件。

### Metadata
- Source: user_feedback
- Related Files: README.md, plugins
- Tags: github, plugin-repository, project-boundary

### Resolution
- **Resolved**: 2026-10-13
- **Notes**: 已更新项目说明并移除插件目录中的额外 `AGENTS.md` 文件。

## [LRN-20261012-004] dmm_search_video_link_priority

**Logged**: 2026-10-12
**Priority**: high
**Status**: resolved
**Area**: integration

### Summary
DMM 搜索结果会同时包含 DVD、月租视频和视频详情链接，旧式 `cid` 链接需要按照目录类型筛选。

### Details
- 搜索番号使用字母与数字分开的形式，例如 `miad 657`。
- 搜索结果优先匹配 `/av/content/?id=...` 视频详情链接。
- 旧式 `cid` 链接只接受 `digital`、`videoa`、`video` 和 `av` 目录，跳过 DVD 与月租详情链接。
- `MIAD-657` 的有效 content id 是 `miad00657`，实际验证成功下载 12 张预览图。

### Suggested Action
处理 DMM 搜索结果时，先根据链接目录确认商品类型，再解析 content id。

### Metadata
- Source: user_feedback_and_verified_direct_http_workflow
- Related Files: plugins/dmm_metadata/backend.py
- Tags: dmm, search, content-id, preview-image

### Resolution
- **Resolved**: 2026-10-12
- **Notes**: 分词搜索和视频链接筛选已经写入插件。

---

## [LRN-20261012-003] dmm_nextjs_graphql_metadata_source

**Logged**: 2026-10-12
**Priority**: high
**Status**: resolved
**Area**: integration

### Summary
DMM 当前作品页面可能只返回 Next.js 应用外壳，作品资料与预览图通过 `api.video.dmm.co.jp/graphql` 的 `ppvContent` 查询提供。

### Details
- 保留页面 `Product JSON-LD` 读取路径，用于兼容仍然提供结构化资料的页面。
- 页面缺少 `Product JSON-LD` 时，使用已经确认年龄或地区页面的同一个 `httpx.Client` 请求 GraphQL 接口。
- 查询 `ppvContent` 的标题、描述、发行时间、演员、导演、制作信息、分类、商品价格和预览图；通过 `reviewSummary` 获取评价数据。
- GraphQL 预览图选择封面、海报和大尺寸样本图，`SNOS-308` 实际下载 13 张 JPG 文件。
- 运行环境不设置代理参数；DMM 访问失败时由插件返回具体错误。

### Suggested Action
DMM 页面资料读取应同时支持结构化数据和官方页面使用的 GraphQL 查询，并对 GraphQL 错误直接报告。

### Metadata
- Source: verified_direct_http_workflow
- Related Files: plugins/dmm_metadata/backend.py, README.md
- Tags: dmm, graphql, nextjs, metadata, preview-image

### Resolution
- **Resolved**: 2026-10-12
- **Notes**: 源代码和 portable 后端均已通过真实 DMM 请求验证。

---

## [LRN-20261008-002] portable_output_contains_runtime_assets

**Logged**: 2026-10-08
**Priority**: high
**Status**: resolved
**Area**: infra

### Summary
portable 客户端目录需要包含可执行文件、后端文件、插件文件、配置文件和运行依赖。

### Details
`target` 目录需要整体复制使用，Tauri 启动程序根据自身目录定位 `backend`、Python 运行依赖和 `plugins/colszunet`，校园网配置文件需要位于 portable 目录内。

### Suggested Action
让构建脚本生成完整 portable 目录，并让 Rust 启动器与 Python 后端优先使用自身目录中的文件。

### Metadata
- Source: user_feedback
- Related Files: scripts/build-client.ps1, src-tauri/src/lib.rs, backend/main.py
- Tags: portable, packaging, runtime

### Resolution
- **Resolved**: 2026-10-08
- **Notes**: `target\runtime\python.exe` 使用目录内部的 Python 文件和依赖；启动验证确认后端与校园网插件均使用 `target` 路径，退出后进程数量与端口监听数量均为零。

---

## [LRN-20261008-002] correction

**Logged**: 2026-10-08T12:40:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: config

### Summary
任务栏图标需要优先使用大轮廓与少量形状，并直接表达助手定位。

### Details
用户指出当前图标的纹理细节在任务栏尺寸下难以识别，同时需要强化智能助手含义。后续候选图案使用对话气泡、助手星芒和简化 `C` 形作为主要识别元素。

### Suggested Action
图标设计检查需要覆盖 16px、24px、32px 与 48px 显示尺寸，限制内部形状数量，优先保证助手符号清晰可见。

### Metadata
- Source: user_feedback
- Related Files: src-tauri/icons/colpilot-icon.png, src-tauri/icons/candidates
- Tags: icon, taskbar, assistant, simplification

### Resolution
- **Resolved**: 2026-10-08T12:12:00+08:00
- **Notes**: 已采用 C 形助手图案，更新所有应用图标来源并完成调试版与 Release 构建验证。

---

## [LRN-20261008-001] campus_history_bucket_display

**Logged**: 2026-10-08
**Priority**: medium
**Status**: resolved
**Area**: frontend

### Summary
历史状态条使用固定数量的时间段，可以保持长时间范围的状态清晰可见并控制页面数据量。

### Details
24h 使用 48 个时间段，7d 使用 168 个时间段。每个时间段出现失败记录时显示红色，全部成功时显示绿色，没有检测记录时显示灰色，同时保留精确的检测次数和成功率统计。

### Suggested Action
新增长时间范围的历史状态显示时，使用时间段汇总，并通过悬停提示展示时间范围与状态详情。

### Metadata
- Source: conversation
- Related Files: backend/main.py, src/App.vue, src/style.css
- Tags: frontend, history, status

---

## [LRN-20261008-003] portable_directory_boundary

**Logged**: 2026-10-08
**Priority**: medium
**Status**: resolved
**Area**: infra

### Summary
portable 目录只保留解压后即可运行的客户端文件。

### Details
安装程序属于安装发布文件，不属于 portable 客户端目录。`target` 需要包含可执行文件、后端文件、运行时、插件文件和插件配置。

### Suggested Action
构建脚本将安装程序留在构建过程内部，并在完成 portable 文件复制后清理构建目录。

### Metadata
- Source: user_feedback
- Related Files: scripts/build-client.ps1, README.md
- Tags: correction, portable, packaging

### Resolution
- **Resolved**: 2026-10-08
- **Notes**: 已移除 `target\installers`，重新定义 `target` 为解压后即可运行的客户端目录。

---

## [LRN-20261008-004] placeholder_plugin_cleanup

**Logged**: 2026-10-08
**Priority**: medium
**Status**: resolved
**Area**: backend

### Summary
当前插件清单只保留已经接入页面和后端功能的校园网监控插件。

### Details
占位工具会进入插件清单、侧边栏、仪表盘卡片和启用数量统计，影响用户判断可用功能。未实现的工具不应出现在运行客户端中。

### Suggested Action
从 `PLUGIN_DEFINITIONS` 移除未实现工具，并验证 `/api/plugins`、前端插件卡片和校园网监控页面仍然正常。

### Metadata
- Source: user_feedback
- Related Files: backend/main.py, src/App.vue
- Tags: correction, plugins, cleanup

### Resolution
- **Resolved**: 2026-10-08
- **Notes**: `PLUGIN_DEFINITIONS` 只保留校园网监控，接口验证返回一个插件，portable 客户端启动和退出验证完成。

---

## [LRN-20261012-001] plugin_materials_stay_with_plugin

**Logged**: 2026-10-12
**Priority**: high
**Status**: resolved
**Area**: architecture

### Summary
插件清单、后端实现、前端组件、样式和运行文件都放在对应插件目录中。

### Details
主程序负责发现插件清单、加载插件后端、管理生命周期和提供通用 HTTP 接口。前端主容器通过清单加载插件页面，插件功能页面与样式由插件目录提供。

### Suggested Action
新增插件时，在 `plugins/<plugin_directory>` 中同时维护清单、后端、前端和运行文件；主程序只扩展通用接口。

### Metadata
- Source: user_feedback
- Related Files: plugins/campus_network, backend/main.py, src/plugin-views.js, src/App.vue
- Tags: plugins, architecture, separation

### Resolution
- **Resolved**: 2026-10-12
- **Notes**: 校园网插件已经迁移为独立目录，后端和前端都通过插件清单加载，portable 输出验证通过。

---

## [LRN-20261012-002] dmm_metadata_preview_workflow

**Logged**: 2026-10-12
**Priority**: high
**Status**: resolved
**Area**: workflow

### Summary
`video.dmm.co.jp` 作品页可以通过公开的 `Product` JSON-LD 获取主要元数据和预览图地址。

### Details
- 使用 `site:video.dmm.co.jp <maker_code>` 搜索作品页，读取搜索结果实际跳转地址。
- 作品页的规范地址包含内部 `content_id`，例如 `SNOS-308` 对应 `snos00308`。
- 读取 `script[type="application/ld+json"]` 并使用 `JSON.parse` 获取 `name`、`sku`、`brand`、`image`、`offers`、`aggregateRating` 与嵌套 `VideoObject` 字段。
- 页面可见字段补充配信开始日期、商品発売日期、收录时长、导演、标签、厂家品番和配信品番。
- `image` 数组包含封面、海报和样本图的原始 CDN 地址；本次 `SNOS-308` 共取得 13 个 JPG 文件。
- 下载时通过 `127.0.0.1:7890` 代理，携带作品页 `Referer`，随后检查 JPEG 文件头、文件大小和图片尺寸。

### Suggested Action
实现同类输入时，保留“作品编号搜索、规范地址解析、JSON-LD 提取、页面字段补充、预览图下载、文件验证、JSON 输出”的顺序，并避免保存 Cookie 与授权信息。

### Metadata
- Source: verified_browser_workflow
- Related Files: artifacts/dmm/SNOS-308/metadata.json, artifacts/dmm/SNOS-308/*.jpg
- Tags: dmm, fanza, metadata, preview-image, browser, proxy

### Resolution
- **Resolved**: 2026-10-12
- **Notes**: 已使用 `SNOS-308` 成功读取元数据，下载 13 张 JPG 预览图，并验证全部图片可以由 `System.Drawing.Image` 读取。

---

## [LRN-20261013-001] campus_portal_proxy_diagnostic

**Logged**: 2026-10-13T13:55:00+08:00
**Priority**: high
**Status**: resolved
**Area**: infra

### Summary
校园网认证状态检查需要使用校园门户路径，并且门户认证请求需要明确使用直连网络。

### Details
Clash Verge 当前启用 TUN 与 fake-IP，`net.szu.edu.cn` 在 Mihomo 实时连接中匹配 `DomainSuffix szu.edu.cn` 并使用 `DIRECT`。校园网监控程序使用 Python `urllib.request.urlopen`，会继承 `HTTP(S)_PROXY=http://127.0.0.1:7890`。目标目录日志记录了多次 `SSL: UNEXPECTED_EOF_WHILE_READING`，外部网站检查和 `/cgi-bin/get_challenge` 请求同时失败。外部网站恢复后，监控程序会记录在线状态，即使门户仍然返回上网认证页面。

### Suggested Action
为校园门户请求创建明确的直连网络客户端，并使用校园网认证状态作为健康检查依据。监控生命周期需要保证同时只有一个校园网监控进程。

### Metadata
- Source: verified_diagnostic
- Related Files: plugins/campus_network/worker/campus_auto_login.py, plugins/campus_network/worker/config.json
- Tags: campus-network, clash, tun, proxy, health-check

### Resolution
- **Resolved**: 2026-10-13T14:55:00+08:00
- **Notes**: 校园网检测和门户请求已经改为显式直连 opener；进程内增加校园域名的 `NO_PROXY` 排除项；Windows 单实例锁、日志轮换和请求级别网络诊断已经加入，并同步到 portable 运行目录。

---

## [LRN-20261013-002] campus_network_request_observability

**Logged**: 2026-10-13T14:55:00+08:00
**Priority**: high
**Status**: resolved
**Area**: infra

### Summary
网络故障排查需要在每次请求中记录路径、目标、错误类别和耗时，同时保留原有连通性摘要供状态页面读取。

### Details
校园网状态页面依赖固定的 `连通性测试成功` 和 `连通性测试失败：` 日志文本。诊断信息需要增加到独立日志行，避免破坏历史统计；请求日志需要隐藏查询参数，运行上下文需要隐藏代理认证信息。

### Suggested Action
使用轮换文件日志，记录进程标识、Python 与 OpenSSL 版本、直连策略、请求编号、HTTP 状态、响应大小、错误类别和耗时。

### Metadata
- Source: best_practice
- Related Files: plugins/campus_network/worker/campus_auto_login.py, plugins/campus_network/backend.py
- Tags: campus-network, logging, observability, proxy, tls

### Resolution
- **Resolved**: 2026-10-13T14:55:00+08:00
- **Notes**: 已加入 2 MB 文件轮换、5 个历史文件、网络异常分类、请求编号以及代理信息脱敏；状态页面使用的摘要日志格式保持不变。

---

## [LRN-20261013-003] core_repository_without_plugin_submodules

**Logged**: 2026-10-13
**Priority**: high
**Status**: pending
**Area**: infra

### Summary
核心仓库保留插件入口目录并忽略插件内容，可以满足默认同步过程不取得插件文件的要求。

### Details
用户确认核心仓库保存插件加载约定，插件源代码和运行文件通过本机独立复制或外部安装方式提供。Git submodule 会增加独立插件仓库维护工作，当前需求不需要采用该方式。

### Suggested Action
核心仓库跟踪 `plugins/__init__.py` 和 `.gitkeep`，忽略 `plugins/*` 下的插件目录；构建脚本继续依据实际存在的 `manifest.json` 复制插件；更新 README 说明插件安装流程。

### Metadata
- Source: user_feedback
- Related Files: .gitignore, backend/main.py, scripts/build-client.ps1
- Tags: github, plugins, repository, synchronization

---
