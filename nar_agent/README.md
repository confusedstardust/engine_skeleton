# NarAgent

面向教学场景的独立 Deep Agents SDK 服务。与 `webgal_backend/` 平级，独立依赖、进程和配置，不导入现有后端业务模块。

当前为开发验证版本：Deep Agents 循环、教学对话，以及可选 anatomy 动画执行链路。动画包含独立 broker、临时 Node/Chromium 容器、异步状态和 HTML 预览；默认关闭，真实 Docker 验收待 CI。没有可靠持久化队列、数据库计量账本、OSS 或积分扣费。具体实现、限制、首次启用与验证见 [anatomy 部署交接](../refactor/nar-agent-deployment.md)。

## 本地启动

### 一起启动 NarrativeOS 与 NarAgent（Windows）

首次在仓库根目录执行：

```powershell
uv sync --project nar_agent --frozen
python tools/configure_nar_agent_local.py
.\start_forge_full.bat
```

配置脚本只修改被 Git 忽略的根 `.env` 和 `nar_agent/.env`，生成/同步服务 token；NarAgent 尚无模型 key 时，复用根 `.env` 已有的 DeepSeek key 和 base URL，不输出凭据。生产环境应独立配置凭据，不运行这个本地配置脚本。

`start_forge_full.bat` 调用已纳入仓库的 `tools/start-development.ps1`，同时启动前端 3001、Forge 8010、NarAgent 8020；Ctrl+C 停止本次启动的三个服务。启动前先关闭已运行的旧服务，端口被占用时脚本会报告 PID，不会自动杀进程。

三端口可通过脚本参数修改：`powershell -ExecutionPolicy Bypass -File tools/start-development.ps1 -BackendPort 8010 -FrontendPort 3001 -AgentPort 8020`。不同文件夹启动时必须使用各自工作目录；脚本已处理。

### 单独启动 Agent

要求 Python 3.13 与 uv。以下命令均在 `nar_agent/` 执行：

```powershell
uv sync --frozen
Copy-Item .env.example .env
# 编辑 .env：设置独立随机 SERVICE_TOKEN 和模型 API_KEY。
uv run uvicorn app.main:app --host 127.0.0.1 --port 8020
```

配置变量全部使用 `NAR_AGENT_` 前缀，见 [.env.example](.env.example)。只读取当前工作目录的 `.env`，不自动读取仓库根目录密钥；从其他目录启动时通过环境变量配置。不要把 root `.env` 整份复制过来。DeepSeek/OpenAI-compatible 接口通过 `NAR_AGENT_BASE_URL`、`NAR_AGENT_MODEL` 和独立的 API key 配置；其他供应商需后续添加适配，不宣称所有兼容接口已验证。

`GET /health` 仅验证进程存活；`GET /ready` 检查 token/key 是否已配置，不代表供应商网络可达。默认只在本机监听，勿直接公开到公网。

## 请求示例

```powershell
$headers = @{
  Authorization = "Bearer <你配置的服务token>"
  "X-User-ID" = "local-test-teacher"
}
$body = @{ prompt = "给初中生设计一个串联电路交互演示方案" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8020/v1/runs `
  -Headers $headers -ContentType 'application/json; charset=utf-8' `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

接口为同步开发接口 `POST /v1/runs`，不是规划中的异步 `/v1/animations`。返回 `id/user_id/status/output/duration_ms/usage/usage_status`，以及明确的 `persisted=false`、`artifact_generated=false`。`SUCCEEDED` 只表示本次教学方案调用完成，不能表示动画构建通过。

服务 token 用于可信后端调用；`X-User-ID` 是可信调用方已验证的身份断言，不是用户登录凭据。任何持有服务 token 的调用方都能指定这个 header，因此禁止浏览器持有 token；NarrativeOS 的身份适配尚未接入。不存在运行历史查询接口或可供其他用户访问的共享工作区。

方案对话每请求创建图和独立 StateBackend，skill 注入虚拟 `/skills/teaching-plan/SKILL.md`；动画图读取 `/skills/anatomy/` 并调用受限构建工具。两者均无宿主 shell 和通用子 Agent。未配置 checkpointer，因此无自动执行恢复。

## 运行限制与错误

- `NAR_AGENT_TIMEOUT_SECONDS`：整次请求超时，默认 120 秒。
- `NAR_AGENT_MAX_OUTPUT_TOKENS`：每次模型调用的输出限制，不是整个任务的 token 预算。
- `NAR_AGENT_RECURSION_LIMIT`：图执行步数限制，默认 20。
- `NAR_AGENT_MAX_CONCURRENT_RUNS`：每进程同时运行上限，默认 2；不提供持久化排队，多进程上限会分别计算。
- 模型客户端关闭自动重试；超时/断流仍不能证明供应商不收费。
- 401：服务凭据错误；503：配置不全；429：容量已满；504：超时；502：Agent/供应商错误。失败仅返回安全错误码和运行 ID，不暴露供应商响应正文。
- 成功响应的 usage 是 callback 聚合、尚未持久化；存在部分调用缺少 usage 的可能，`reported` 不代表完整账单核对成功。失败响应暂不回传用量，完整失败计量列入后续必做事项。

## 验证与版本

```powershell
uv run python -m pytest -q
```

依赖精确解析保存在 `uv.lock`，部署与 CI 使用 `--frozen`；当前安装 Deep Agents 0.7.32。无需更新现有后端 requirements。

2026-11-01 验证结果：6 项测试通过；脚本化假模型驱动真实 SDK 的 skill read_file 工具调用，验证鉴权、用量聚合、输入校验、错误脱敏、超时、容量与初始文件隔离。另通过 ASGI 接口发起一次最小真实 DeepSeek 调用，返回 200，输入 6728 token、输出 315 token、合计 7043 token（包含缓存读 3328，为输入子集，不额外相加），约 3.9 秒。请求模型名 `deepseek-chat`，供应商报告 `deepseek-flash`，后续计量需同时保留请求名和返回名，不据此推断价格。此验证不等于真实动画生成或生产验收。

提供开发容器 Dockerfile（容器监听 8020，非 root 用户）；当前机器没有 Docker，尚未构建验证。配置由运行时注入，不写入镜像。此容器是 API 服务镜像，不是允许生成代码执行的沙箱。

## NarrativeOS 讲练对话入口（开发集成）

前端首页选择「讲练工具」进入 `/practice`（生产 basePath 下为 `/narrativeos/practice/`）。页面调用 `/api/forge/nar-agent/chat`，Next 转发至 Forge 的 `/nar-agent/chat`，Forge 验证 SSO 后调用本服务 `/v1/runs`。浏览器没有服务密钥，也不传用户 ID。

配置方法：

1. 在 NarAgent 环境配置模型 API key 与至少 32 字符的随机 `NAR_AGENT_SERVICE_TOKEN`。
2. 在 Forge 后端环境配置相同的 `NAR_AGENT_SERVICE_TOKEN`，以及 `NAR_AGENT_URL=http://127.0.0.1:8020`；不同容器用私有服务名，不能用容器内的 localhost 指向另一容器。
3. 按上文启动 NarAgent，重启 Forge 使环境变量生效，重启/重建 Next 使 rewrite 生效。
4. 登录 NarrativeOS，从讲练工具发送问题并追问；未登录不可发送，未配置时显示明确的服务提示。

同步调用默认 Agent 120 秒、Forge 上游 135 秒、Next proxy 150 秒；正式部署 Nginx 等网关的读取超时需覆盖完整请求（例如 160 秒），或后续迁到异步任务。修改 Agent 时限时同步调整这些层。

`history` 是请求内历史，最多 20 条 user/assistant 消息，每条 12000 字符；连同当前 prompt 总计上限 36000 字符。禁止 system/tool 角色。它不是持久化会话、服务器可信事实或检查点恢复；不保存跨页历史，十轮后提示开始新对话。当前不结算积分；制作动画需另外启用隔离执行服务。

验证：NarAgent 7 项测试、Forge 网关 4 项测试通过，前端 TypeScript 检查通过。`python tests/practice_chat.browser.py` 在现有本地 Next 上模拟 API，验证发送、追问 history、新对话、失败恢复输入、未登录禁发与 390px 布局。截图在 `reports/nar-agent/`。浏览器测试使用模拟登录及回复，不代表生产登录和真实三服务网络端到端验收；尚未部署。

### 本地 404 排查记录

2026-11-01：页面存在但发送返回 JSON `404 Not Found`。实际 8010 旧 uvicorn 进程的 `/openapi.json` 不含 `/nar-agent/chat`，8020 也未监听；不是模型输出错误。补齐本地配置并重启 Forge、启动 NarAgent 后，8010 路由已存在，8020 `/ready` 为 200，8020 真实模型请求为 200，3001 代理在未携带登录 Cookie 时为预期 401。当前用户的浏览器登录链仍需在页面实际发送验证，不以未认证探针代替。

- 404：检查请求路径、Next rewrite，以及 Forge 是否重启加载了新路由。
- 401：确认浏览器已登录，且本地 SSO 的 Cookie 域名、端口代理及服务配置正确；不要用服务 token 代替浏览器登录。
- 503：检查 NarAgent 是否启动，两端 token 是否一致，模型 key 是否配置；查各服务终端日志。
- 504：检查模型网络及完整调用链超时设置。

如果使用本次修复启动的后台进程，日志位于仓库 `logs/forge-local.stderr.log` 与 `logs/nar-agent-local.stderr.log`；统一启动脚本则直接在终端输出带服务前缀的日志。不要同时启动第二份占用相同端口的服务。

## 接下来做什么

按 [实施清单](../refactor/nar-agent-implementation-backlog.md) 逐项推进；总体边界见 [架构方案](../refactor/nar-agent-architecture.md)。anatomy 的代码接入不能代替真实 Docker、模型生成质量和生产验收；完整计量、持久化及计费仍待实施。
