# 官网开发服务器交接

2026-11-02：官网仓库 development Environment 没有专用 SSH secrets，继承仓库级凭据后实际部署至另一台服务器。用户授权复用 engine_skeleton 的 development SSH 配置更新 43.138.207.82 上的官网。

开发工作流支持 `portal_action=inspect`，仅校验目标 IP、读取既有官网容器/Compose 标签及 Nginx 转发，不重建工作台或 NarAgent。待确认既有部署目录和路由后更新官网，完成后检查公开页面和静态资源。不得由另一台机器的端口布局推断这里需要改代理。

状态：只读检查入口已实现；目标服务器检查与官网更新仍待执行。凭据保留在 GitHub Environment，不复制入仓库。
