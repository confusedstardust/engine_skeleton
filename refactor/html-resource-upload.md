# 管理员 HTML 教学资源上传

状态：本地已实现；未部署，未执行生产数据库写入或线上验收。分支 `hotfix-uploadsrc` 基于 `origin/main`（`b3446a5`）。

## 设计与数据归属

管理页增加「HTML资源」，沿用共享 Button、DataTable、反馈、上传校验、上传状态、useFileUpload、adminApi 和 Radix ToggleGroup。分类词表由后端提供，前端不另抄一套。样式沿用 rice / paper / cinnabar / border 主题变量。学科至少选一个；课程体系、学段、学科、年级和自定义标签全部支持多选及添加新值。未选择的分类保存空数组。

沿用 `TEACHER_ECOSYSTEM_API_URL` / `TEACHER_ECOSYSTEM_SERVICE_TOKEN` 的既有发布桥接，调用门户 internal works API，更新其 teacherProfile / teacherWork；不创建平行的广场数据库，不要求新增表。发布作者为当前管理员账号，必须存在于门户共享用户库。jobId 是资源 UUID，不创建 generation_jobs 生成任务，也不调用生成模型。

映射：标题/简介 → title/summary；第一学科 → subject；第一年级（无年级时第一学段） → grade；全部分类值、自定义词和固定 `HTML互动资源` → tags；playUrl → 独立 HTML 体验页；quizUrl/coverUrl 为空。当前门户接口支持这些字段，公开列表可复用现有卡片和体验链接。

已核对运行中的门户 `teacher-plaza-filters.ts`：体系筛选读取 tags、学段筛选读取 grade。无具体年级时以学段填充 grade，保留独立 classification 年级空值；允许跨学段、跨年级作品，完整选项保存在 classification 数组与 tags。截图词表不包含「全部」（查询动作）作为上传值。本次不修改门户仓库，线上门户版本仍需部署时核验。

## API 与文件

- `GET /admin/html-resources/taxonomy`：管理员可用分类。
- `GET /admin/html-resources`：资源记录及 saved / publishing / published / archived 状态。
- `POST /admin/html-resources`：multipart，file、title、subject 必填；summary、curriculum、stage、grade、entry 可选。成功时文件和门户发布均完成；发布失败保留文件与原 ID，可查询列表重试。
- `POST /admin/html-resources/{id}/publication`：以同一 jobId 幂等重试发布。
- `DELETE /admin/html-resources/{id}/publication`：沿用门户归档，成功后停止公开文件访问。
- `GET /resources-play/{id}/`：可信外壳 + iframe。
- `GET /resources-play/{id}/files/{path}`：上传文件。Next rewrites 与现有 basePath 部署保持一致。

管理接口复用管理员身份与 `X-Forge-Admin-Action: 1` 校验，发布/下架复用审计，记录操作人和资源 UUID。静态数据位于 `${WEBGAL_JOBS_DIR}/.html-resources/{id}/metadata.json` 与 `files/`，需和 jobs 目录一起持久化及备份。metadata.json 使用已有原子写入工具，公开路由仅提供 files 子目录。

支持独立 HTML/HTM 或 ZIP，上传上限 30 MB，解压总量 120 MB，最多 2000 个文件。包中相对目录保持不变；默认根 index.html，否则唯一 index.html 或唯一 HTML；多入口必须指定 ZIP 内相对路径。拒绝穿越、绝对路径、链接、加密文件、重名路径和服务端可执行文件；忽略 __MACOSX。支持静态 HTML/CSS/JS、常见图片/音视频/字体/JSON/WASM/glTF/PDF。

不授予 iframe allow-same-origin，响应同时设置 CSP sandbox；脚本可运行，不能读取父页面 DOM、cookie 或本地存储。提供无凭据 CORS 以支持隔离 iframe 中的 ES modules 与相对资源。平台为 localStorage/sessionStorage 提供每作品隔离的常用 API 兼容层（各 256 KB），通过可信父页面的专用键持久化，上传脚本不获得原生同源存储权限。刷新外层体验页可恢复；多 HTML 内部跳转与原生 storage 事件/IndexedDB 不属于此单页兼容范围。脚本依赖同源接口、表单提交或登录态的页面仍需要适配；资源使用相对路径，不保证以 `/` 开头的根路径正确。HTTPS 外部依赖可以加载，离线体验应把依赖放进 ZIP。

远端发布超时可能已写入数据库：标为 publishing，保留可访问文件，前端提示待确认，不误报成功；下次用原 ID 发布覆盖同条记录。下架仅在远端确认成功后改本地状态。管理员可刷新、重试发布、下架及重新发布；暂不提供内容覆盖和永久删除。

## 配置与部署

必须配置指向目标门户数据库服务的 TEACHER_ECOSYSTEM_API_URL、相同服务密钥，以及含部署前缀的公开 WEBGAL_FRONTEND_URL。不要从开发库发布推断生产可见。

部署需同时更新 Forge 后端和 Next 前端；反向代理设置请求体上限 31 MB（30 MB 文件加 multipart 开销）；应用在 multipart 解析之后检查文件大小，入口限制用于防止超大请求先占用临时磁盘，上传超时应覆盖保存与发布过程，并将 `/resources-play/`（含应用前缀时同样）路由至 Next 或 Forge。无需部署 WebGAL 引擎 dist。确保 jobs 持久卷有容量。不要使用 Node/Next 对上传内容执行构建，不把 ZIP 里的脚本作为服务器代码运行。

## 验证

- `python -m pytest tests/test_html_resources.py -q`：20 项，通过。包含发布字段、静态文件、沙箱响应头、下架访问阻断、权限/CSRF、必填与非法标签、入口解析、穿越、压缩包限制和失败同 ID 重试。
- `npx tsc --noEmit --incremental false`（forge_frontend_next）：通过。
- `npm run build`：通过，共享 UI 0.1.4 校验及 12 页产物生成通过；现有 CSS / img / hook 警告仍保留。
- `PYTHONUTF8=1 python -m pytest tests/test_html_resources.py tests/test_platform_admin.py tests/test_teacher_ecosystem_quiz.py -q --tb=line`：上传专项全部通过，另有 2 项既有失败；两项在独立导出的未修改 origin/main 上同样失败，缺少 CREDIT_DB_HOST / 既有公共 quiz 返回 503。未用生产配置补跑。
- 浏览器验收：`tests/html_resources.browser.py`，已通过（Edge headless），截图在 `reports/html-resources/`；使用临时目录和假的门户发布函数，验证真实 Next 管理页上传、桌面/手机布局、相对 ES modules、父 DOM 隔离和下架；不连接真实数据库。运行示例见脚本使用的端口 18422 / 18424，Next 的 FORGE_BACKEND_URL 指向 18424、WEBGAL_FRONTEND_URL 指向 18422。
- 待线上验收：真实管理员上传 → teacherWork 数据库记录 → 广场列表与筛选 → 公开体验（含生产前缀/代理）→ 下架。未发布或同步到飞书；本文为本地权威。

### 本地联调修复

完整 app 中 `/admin/{resource}` 曾抢先匹配 `/admin/html-resources`，导致已登录访问列表返回 422，且前端 Promise.all 使分类一起隐藏。现将 HTML 专用路由注册在通用管理路由之前，新增完整 app 的回归测试（修复前复现 422，修复后通过）。现共 15 项测试通过；已重启本地后端并在真实登录会话确认分类和空列表正常。

### 体验入口末尾斜杠兼容修复

Next rewrite 转发时去掉末尾 `/`，原先仅注册带 `/` 的播放器路由导致前端 404、后端直连 200。现同时支持两种入口，iframe 使用 WEBGAL_FRONTEND_URL 的部署前缀构建稳定资源路径。新增回归测试，共 16 项通过。已上传资源无需重传，已在真实前端确认入口和 HTML 返回 200，浏览器显示历史对战游戏与题目。

### 提交前审查

独立安全审查未发现可复现的包路径穿越或 iframe 越权；发现并修复同资源发布/下架并发可导致远端与本地状态反转的问题。现用独立 publication.lock 文件提供跨进程排他锁，覆盖读记录、远端调用、最终写入，冲突返回 409；锁不随 metadata 原子替换而失效，异常会释放。已增加延迟下架与同时发布的确定性并发回归，以及失败后可重新获取锁的测试。

分类与列表分别应用成功响应；其中一个请求失败时不隐藏另一个结果，也不把加载失败显示成没有资源。补齐学段未选年级时与当前广场筛选的兼容性。部署仍需入口 31 MB 限制和 jobs 持久卷。

最终验证：生产构建后使用 `next start` 运行 `tests/html_resources.browser.py`，上传、发布、相对 ES modules、父页面隔离、移动布局及下架阻断全部通过。未把本地上传文件、日志、凭据或生成的截图纳入提交。提交前复审已解决上述发现，无剩余阻塞项；未合并或部署。

### 存储与下载页面兼容修复

针对教学页面 localStorage SecurityError，保留原有 opaque sandbox（不加 allow-same-origin），在作者脚本之前注入常用存储 API 兼容层。可信父外壳通过临时 URL fragment 将该作品自己的快照交给 iframe，兼容层立即清除 fragment；只接受自己 iframe 发来的 null-origin 消息，固定 localStorage/sessionStorage 类型与作品命名空间，每类 256 KB。写入按 set/remove/clear 增量应用，避免多个页面的快照覆盖其他键；不向作品暴露平台其他存储或 DOM。

上传前检查入口 HTML 直接引用的脚本、图片、媒体和样式文件；缺失时拒绝发布并提示 HTML 与 _files 一起打 ZIP。动态 fetch、CSS 内 url() 仍须作者确保齐全。允许浏览器保存的 .js.下载 文件并按 JavaScript MIME 提供，不执行服务器代码。既有上传文件不自动改写；HTML bootstrap 在响应时注入。

22 项后端测试通过；生产前端浏览器测试已覆盖模块资源加载、刷新恢复、早期脚本存储访问、父页面存储/DOM 隔离及下架阻断。已在当前本地开发资源上补齐与上传 HTML 完全一致的原下载附件；这些运行时资源不纳入代码提交。

### 多选、自定义与发布后修改标签

上传表单与编辑弹窗共享 HtmlResourceTags，复用 Radix multiple ToggleGroup、共享 Button、Dialog、DialogHeader/DialogActions。学科至少一项，其余组可空；每组最多 30 项、每项 40 字，所有分类与自定义词去重合计最多 63 项（加固定资源类型最多 64）。已保存的自定义值会进入管理员可复用词表。上传 multipart 各分类支持 JSON 文字数组，保留旧单字符串客户端兼容。

`PATCH /admin/html-resources/{id}/tags`：JSON `{classification:{subject:[...],curriculum:[...],stage:[...],grade:[...],custom:[...]}}`，复用管理员/动作头检查及资源发布锁。已发布作品同步 upsert 同一个门户 jobId；已下架作品仅保存标签，保持下架。失败时保存目标分类、保留可重试状态，不复制资源、不要求重传。列表将旧单值 classification 转为数组，旧资源可以直接编辑。若门户返回被截断的 tags，返回 409 提示先更新门户，避免误报同步成功。

配套门户仓库 linchangWeb 的 `codex/html-resource-multi-tags` 分支（基于当前 feature-refactor）：internal works API 不再截为 8 项，去重后支持 64 项，超限明确拒绝；subject/grade/stage 筛选同时兼容旧标量和 tags 中的次选值。先部署门户，再部署 Forge，才能保证新多选与自定义词完整发布并被分类筛选发现。未迁移或修改数据库结构，旧作品的单值字段继续可用。

验证：31 项 HTML 资源后端测试通过，门户 6 项分类/容量测试及 TypeScript 检查通过；Forge 生产构建与浏览器上传多选、自定义、发布后编辑并同步的完整测试通过。本地服务已更新；线上尚未部署。

### HTML 首屏封面

上传发布后自动提交后台截图，使用全新、无账号凭据的 Chromium 上下文渲染包内入口，视口 1280×720，输出同尺寸 WebP。浏览器按进程串行运行，最多加载 100 个请求/30 MB，并限制时间。外部 HTTP(S) 资源必须解析到公网 IP，TCP 固定解析结果，重定向逐次重新校验；不转发 cookie、Authorization 或表单 POST，阻止 WebSocket。包内文件只能读取当前作品 files 目录。浏览器不使用站点登录态。

admin 展示封面与生成状态，提供「生成/重新生成封面」「替换封面」「同步封面」。手动支持 PNG/JPEG/WebP，5 MB、3600 万像素以内，归一化裁切为 16:9 WebP。生成失败保留旧图；revision 防止旧后台任务覆盖较新的手动封面。只在有截图任务时短期刷新列表，其他时间不轮询。

接口：POST `/admin/html-resources/{id}/cover/generate` 返回 202；POST `/admin/html-resources/{id}/cover` 接收 multipart file；POST `/admin/html-resources/{id}/cover/sync` 重试数据库同步。公开图位于 `/resources-play/{id}/cover/{uuid}.webp`，有不可变版本地址，旧图保留以兼容缓存；下架后图与资源一样停止公开访问。图位于 jobs 持久卷，需一起备份。

门户 internal works 新增 PATCH，只更新指定 ownerUserId/jobId 的 coverUrl，不重置发布时间、标签或发布状态。必须先部署门户此接口，再部署 Forge 截图版本。后端镜像安装 Playwright 1.64.1 和 Chromium 及运行依赖；本地 Windows 使用现有 Edge。截图仅封面用途，广场卡片不运行完整 HTML。

启动时自动在后台补齐 published/publishing 且缺少封面的 HTML 作品，不覆盖已有手动图；同步失败单独记录并可重试。可通过 `WEBGAL_HTML_COVER_BACKFILL_ON_STARTUP=false` 禁用，也可手动运行 `python -m webgal_backend.html_resource_covers --backfill-missing`。线程不阻塞 API 启动；关闭时停止领取下一条。启动中断后下次启动会继续缺图记录。单条失败不终止其他记录。

本地验证：44 项上传/封面后端测试；门户 7 项测试及 TypeScript 检查；Forge 生产构建。真实截图已生成，生产构建浏览器测试覆盖上传后出图、重新生成、手动替换及继续体验。生产部署与已有记录补齐结果待回读确认。
