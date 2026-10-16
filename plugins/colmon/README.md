# colmon

Colpilot 的持续运行插件，启动并管理一个独立的 WinForms 窗口宿主。窗口宿主负责创建三个任务栏窗口：

- Codex weekly
- Codex 5hlimit
- Tokens today

插件使用自身的 `data` 目录保存三个窗口的状态文件，刷新频率保存于插件目录的 `config.ini` 中的 `[colmon]` 配置节。Codex 配额查询会按需创建短时 App Server 进程，并由 Colpilot 统一登记和关闭。
