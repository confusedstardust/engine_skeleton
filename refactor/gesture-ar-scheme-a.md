# NarrativeOS 手势 AR 接入（方案 A） · feature-ar

**状态（2026-11-18）：开发分支实现；未合并 main，未部署，真实摄像头/移动端验收尚待完成。**
技术依据：上传的《open-source-hands SDK Reference NarrativeOS v1.1 方案 A》第16–18章。
上游源码固定于 [open-source-hands](https://github.com/abouchedidxcode/open-source-hands/tree/dd79fb7b3a9d2e9868e433611e6b8737dfca3936)；本分支复制源文件 + MIT LICENSE。

## 已提交代码和边界

1. `gesture_sdk/src/kit/*.ts`：固定上游源码。通过 `gesture_sdk/build.mjs` 构建版本化 ESM，构建时复制 MediaPipe 1.1.0 WASM 和下载 Hand Landmarker 模型，输出 `/gesture-sdk/v1/`。浏览器不会在运行时向 Google 下载模型。
2. `gesture_sdk/src/nar-controls.js`：运行在**作品 iframe 内**的 `GestureControls`。创建独立 `Hands`，启用 `numHands:1`、`pose.experimental:false`，从 `onFrame` 读取连续状态、`engine.on('fist')` 读取姿态事件。四种操作：`pinch-drag`、`fist-rotate`、`index-dwell`（700ms）、食指限定 `index-swipe` 翻页、`open-reset`（900ms）。没有父页摄像头桥接，也没有双重识别循环。
3. `nar_agent/templates/gesture-cards`：受审核的 AR 互动学习卡，内含触控、鼠标、键盘回退；摄像头默认关闭，点击后从同源版本化路径动态 import SDK；关闭/页面隐藏时停止流，重启新建实例。这个受控模板是**第一个 MVP**，并非允许 Agent 对所有自由生成 HTML 自动开启摄像头。
4. `nar_agent/agents/html_builder.py` + `skills/gesture-ar`：当用户明确请求手势/AR 时，引导模型优先选择 `gesture-cards` 模板。模板渲染复用原有 `TemplateCatalog` 的受约束 `title/cards` JSON，不新增工具入口或数据库表。
5. `gesture_sdk/review.py`：服务端读取作品 HTML 内的参数，调用同一个受审核模板渲染器，并做**完整字节比对**。不接受靠 `data-nar-template`、用户标志、客户端声明冒充特权，原模板 JS 被任何改动就拒绝。
6. `gesture_sdk/server.py`：独立作品源的无 Cookie、只读公开资源服务。读取现有 `forge_jobs:/data/jobs` 卷中**已发布版本**；对每次请求再次核验作品是否仍发布、源 HTML 是否仍符合唯一受审核模板；只提供特定 SDK/WASM/模型资源，CSP 仅允许同源脚本 + SHA-256 锁定的内联脚本、网络仅同源加载，禁止主站 API 访问。撤回作品后独立源立即 404。
7. `webgal_backend/work_publication.py`：在公开作品元数据里派生（不落数据库）`gesture_ar` 布尔值。普通作品仍走原有 CSP。
8. `forge_frontend_next/app/practice/works/[workId]/page.tsx`：仅对服务器审核通过且**公开**的手势作品使用 `https://ar.narrativeos.cn/works/{id}/index.html`，并加 `sandbox="allow-scripts allow-same-origin" allow="camera; fullscreen"`；普通/私有作品仍 `sandbox="allow-scripts"`。没有 `srcDoc` 授权捷径。

## 运行与部署（待执行）

生产环境独立域名 **ar.narrativeos.cn** 是本分支约定目标，并**非已配置或已验证域名**。应用服务运行时只公开在主机 `127.0.0.1:8040`，必须在单独的 HTTPS 虚拟主机反代到该端口，确保该子域名不携带主站会话 Cookie、不开放 CORS、不反代其他主站接口。主站发布服务器需允许只给该子域名的 framing 和摄像头委托，并保留前端 `Permissions-Policy`。反代不要丢失任何 `Content-Security-Policy`、`Permissions-Policy`、`Cache-Control` 等响应头。

```bash
# 仅示例：部署环境已有生产服务和 forge_jobs 卷
docker compose -f docker-compose.prod.yml -f docker-compose.ar.prod.yml build ar-player
docker compose -f docker-compose.prod.yml -f docker-compose.ar.prod.yml up -d ar-player

# 本地 dev 使用不同 jobs 卷，浏览器访问 localhost:8040；不代表公网可用
docker compose -f docker-compose.dev.yml -f docker-compose.ar.dev.yml build ar-player
docker compose -f docker-compose.dev.yml -f docker-compose.ar.dev.yml up -d ar-player
```

注意必须分别部署这一分支更新的 **Next 前端、Forge 后端、NarAgent 和新 AR player**。已有 compose 的主服务镜像部署流水线需更新，不要在 `main` 未合并或未更新镜像时直接切换线上网站。公网 HTTPS 证书和 DNS 需要运维在反向代理配置；`www.narrativeos.cn` 必须转发 `/practice/works/*` 页面的父策略头。独立页必须是 **HTTPS secure context**；iOS 用户须使用受支持浏览器显式授权。API 同源下禁止存储凭据。主站如启用 `Cross-Origin-Embedder-Policy`，需单独评估第三方嵌入策略。

## 仍需要执行的质量验收

- [ ] Docker 编译 `gesture_sdk` JS、MediaPipe WASM、任务模型；记录模型 SHA-256 校验值作为固定供应链依赖（当前构建时固定 URL，未锁定二进制 hash）。
- [ ] `pytest tests/test_gesture_ar_origin.py`、`pytest nar_agent/tests/test_ar_template.py`；NarAgent 原有测试与网关回归。
- [ ] Next `tsc --noEmit`、frontend build 和已有作品预览路由回归。
- [ ] 真机浏览器 `startCamera` -> WASM/model HTTP 200 -> `onFrame` 和 `engine.on('fist')` -> 捏合拖动/握拳旋转/食指点选与左右滑动/张掌复位的**真实视觉反馈**。
- [ ] 设备断开、权限拒绝、后台 Tab、页面卸载、关闭后重开不泄漏摄像头；无摄像头时鼠标/触屏保持可用。
- [ ] 上游 Tracker 视频轨道中断时重置作品按钮状态，允许用户再次主动启动摄像头。
- [ ] Chromium+Safari+iOS 的 Permissions Policy、CSP、同源 Cookie、隔离端点、冻结版本及缓存测试；性能及弱设备 FPS。
- [ ] 测试非手势作品绝不具有 `allow-same-origin`/camera，未发布、撤销、篡改 HTML 均 404。
- [ ] 检查用户在直接下载单独 HTML 并以 `file://` 打开时无法申请摄像头；应使用独立 HTTPS 作品地址而不是单文件离线运行。HTML 导出仍能使用鼠标/触摸。

**已知限制**：本版支持审核模板的学习卡内容变体，而不是任意生成页面/3D 游戏自由调用 SDK。后续若开放更多作品类型，必须先有**可证明的可信发布构建机制、模板或审核策略**，不能将普通 Agent 生成 JS 和摄像头授权简单关联。

**安全提醒**：本方案的 `allow-same-origin` 仅用于独立、与主站不同的源上完全审查通过的作品。任意生成 HTML 即使只在 iframe 内，也绝不自动获得摄像头权限。

## 文件维护与恢复

`README.md` 是主入口；这个文件记录实施、设计和验收状态。用户所上传的 SDK 文档不是自动部署状态的证明。若在线 CI、HTTPS 反代或真实摄像头没有验证通过，交付时必须明确说明。
