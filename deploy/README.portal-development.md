# 官网开发服务器交接

2026-11-02：官网仓库 development Environment 没有专用 SSH secrets，继承仓库级凭据后实际部署至另一台服务器。用户授权复用 engine_skeleton 的 development SSH 配置更新 43.138.207.82 上的官网。

开发工作流支持 `portal_action=inspect`，仅校验目标 IP、读取既有官网容器/Compose 标签及 Nginx 转发，不重建工作台或 NarAgent。待确认既有部署目录和路由后更新官网，完成后检查公开页面和静态资源。不得由另一台机器的端口布局推断这里需要改代理。

状态：只读检查入口已实现；目标服务器检查与官网更新仍待执行。凭据保留在 GitHub Environment，不复制入仓库。

## 已确认的服务器布局与执行方式

正确服务器为 43.138.207.82；官网 Compose 项目 `linchang-web`，目录 `/opt/linchang-web`，配置 `docker-compose.dev.yml`，官网使用现有 3002 端口。Nginx `/etc/nginx/sites-enabled/flowmind` 已正确转发官网至 3002、工作台至 3001、播放至 8010，无需修改。

开发工作流 `portal_action=deploy` 可复用本仓库 development SSH 配置，将 `portal_image_tag` 指定的已发布官网开发镜像部署至既有官网服务。通过独立 image override 保留原 Compose/.env，强制保留现有 3002 端口，不重建其他服务。官网启动或新版页面检查失败时尝试恢复原镜像。随后从 Actions runner 检查用户原公网网址。

本次候选镜像 `dev-sha-cda82c439307`，来自官网 `feature-refactor` 新版广场提交。执行状态以 Actions 及公开 HTML/资源验收为准，不把只读检查视作部署完成。

## 已部署与公开验收（2026-11-02）

Actions https://github.com/confusedstardust/engine_skeleton/actions/runs/41388479472 已成功将 `dev-sha-cda82c439307` 更新到正确服务器的既有官网服务。公网原网址 `/teacher-ecosystem/?returnTo=http%3A%2F%2F43.138.207.82%2Fnarrativeos%2F` 返回 200、新版 `plaza-resources`、4张作品卡片，无旧版 `ecosystem-hero`。页面引用的22个 CSS/JS 资源全部返回200；`/narrativeos/` 返回200。未修改该服务器 Nginx，未迁移数据库，未重建工作台。

后续官网开发部署暂使用此工作流 `portal_action=deploy` 和已验证镜像标签；官网自身工作流仍需在其 development Environment 设置正确 SSH secrets，当前目标校验会阻止使用错误的仓库级凭据。此交接没有复制或导出私钥。
