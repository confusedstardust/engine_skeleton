# NarAgent：先 dev 验收，再 prod

## Development

`feature/**` / `feature-*` 分支的 `docker-publish-deploy-dev.yml` 已接入 NarAgent：

1. 路径检测选择 Agent 改动。
2. 调用 reusable workflow，先运行真实 Docker anatomy 测试。
3. 在 GitHub `development` Environment 下构建、推送三份 `dev-sha-<commit>` 镜像；main 的生产 SHA 标签与凭据选择保持独立。
4. 使用 `development` 中现有 `DEPLOY_HOST / DEPLOY_USER / DEPLOY_SSH_KEY / DEPLOY_PATH` 上传配置并部署到开发目录。
5. 第一次尚无 Agent 配置时，只准备镜像和配置文件，日志会打印初始化命令；不猜测模型 key，也不读取生产目录。

首次 CI 完成文件同步后，在 **DEV 服务器、development 的 DEPLOY_PATH 目录** 执行：

```bash
cd <development的DEPLOY_PATH>
python3 deploy/setup-nar-agent.py --environment development --enable
```

按隐藏提示输入用于测试的模型 API key。脚本在该目录写入：

```text
.env                         # 仅增加/同步本环境的 NAR_AGENT_SERVICE_TOKEN
deploy/nar-agent.env          # 独立开发模型 key、服务 token、执行 token
deploy/nar-execution.env      # 独立开发执行 token
.nar-agent-enabled           # 下一次开发部署启用覆盖配置
```

然后对同一个 feature 分支运行 development workflow 的 `workflow_dispatch`，选择 deploy=true，完成一次全量 dev 部署。不要在 prod 的 `/var/www/myproject` 目录执行上述命令；实际 dev 目录由你现有 `development` 的 DEPLOY_PATH 决定，不能用官网 dev 目录替代。

脚本校验 `docker-compose.dev.yml`，并拒绝覆写已标记为 production 的 Agent 凭据。dev CI 同样检查 environment 标记和 `dev-sha-*` 镜像 pin，不接受生产 Agent 标签。

## 网络、数据与验收

动画在 DESIGNING / attempts=0 失败时，先查看 `docker logs --tail 120 <本环境nar-agent容器>`。服务端记录任务 ID、阶段、构建次数、异常类型、HTTP 状态与调用位置；不记录异常消息、响应正文、提示词或局部变量。`/ready` 只验证配置，不代表模型供应商连接成功。2026-11-01 开发环境此类失败的根因仍待部署诊断版本后复现确认。

2026-11-01 开发服务器发现 execution `/ready` 持续 503：Docker SDK 7.1.0 的 DockerClient 不支持上下文管理器，旧版 `with docker.from_env(...)` 会抛 TypeError。已改为 try/finally 显式 close，并补成功/失败路径关闭连接测试。服务器需要发布包含修复的 execution 镜像后再运行重启脚本；旧镜像反复重启无效。线上验证仍待完成。

日常修改 env 后重新创建服务，可将 [restart-nar-agent.sh](restart-nar-agent.sh) 上传到部署根目录或 `deploy/` 中，在该脚本所在目录执行 `bash restart-nar-agent.sh`。默认 development；生产必须显式加 `--environment production`。脚本加载 CI 镜像 pin、检查两组 token、补拉缺失镜像，依次重新创建 execution、NarAgent、backend 并检查健康和鉴权；不删除卷、不打印密钥、不重建前端。它会中断进行中的 Agent 任务，应在任务结束后执行。

开发 Compose 合并方式：

```bash
set -a
. ./.deploy-images.env
set +a
docker-compose --env-file .env -f docker-compose.dev.yml -f docker-compose.nar-agent.yml ps
```

backend 同时保留 `narrativeos-development` 官网网络与本项目 default 网络；NarAgent 在 default 网络，execution 在私有 internal 网络。Agent/execution 不映射公网端口。named volume 随 Compose 项目隔离；dev/prod 必须使用各自既有的部署目录/Compose project，禁止故意设置成同一个 project name。

启用后，CI 自动启动 execution/NarAgent、重启 backend 应用内部地址和 token，并从 backend 验证 `/ready` 和受鉴权任务查询（预期 404），不消耗模型 token。镜像准备成功不等于用户验收：还需在 dev 网页登录、发送对话、制作一个简单动画、操作预览、检查另一个账号无法读取该产物，再决定是否进入 prod。

现有内存任务、产物本地卷与计量限制没有因 dev 接入而消失；测试期间保持动画并发 1。不要直接复用生产 key、token 或产物目录。

## Production

main 仍使用生产 workflow 和普通 `sha-*` 镜像标签。生产首次配置命令保留：

```bash
cd <production的DEPLOY_PATH>
python3 deploy/setup-nar-agent.py --environment production --enable
```

只有 dev 验收通过并审阅生产变更后，再触发生产部署；本次 dev 接入不自动启用 prod。
