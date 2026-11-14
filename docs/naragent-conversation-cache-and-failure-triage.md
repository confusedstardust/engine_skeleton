# NarAgent 对话查询缓存、路由切换与错误追踪

## 发现的重复刷新根因

原代码存在独立且叠加的重复查询入口：

1. 侧栏 `window.focus` 监听，每次从 DevTools 或其他窗口返回都重新请求 `/conversations`。
2. 当前会话每次 `applyDetail` 都递增 `serverRevision`，再驱动**整张**会话列表和产物列表刷新。
3. `/practice/chat/:id` 路由对应新的 `PracticeShell key={id}`，导致 Header、侧栏、工作区 React 树卸载重建，重复检查登录状态和数据库 readiness。
4. 历史产物预览重复请求完整 HTML，即使是不可变 artifact ID。

## 本次改法与成熟生态的对应关系

参考 TanStack Query 官方重要默认行为及 Window Focus Refetching：
- https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults
- https://tanstack.com/query/latest/docs/framework/react/guides/window-focus-refetching
- https://tanstack.com/query/latest/docs/framework/react/guides/caching
- https://nextjs.org/docs/app/guides/preserving-ui-state

实现为复用的 `lib/conversation-query-cache.ts`（不再引入一套组件级 fetch）：
- **按登录账号 + query key 隔离**：`<owner>::readiness`、`list`、`artifacts`、`detail:<cid>`、`preview:<artifactId>`。
- 仅在内存中持有服务器已返回的数据。不是 `sessionStorage` 聊天持久化，也不提供离线会话来源。
- **stale-while-revalidate**：已有缓存时立即绘制，不清空消息；超过 `staleTime` 后才后台更新；同 key 的并发请求合并为一条。
- **局部更新**：会话新建、发送或完成只更新对应侧栏摘要；生成产物成功才使产物列表过期。不会把会话详情更新等同于列表整体变更。
- **不监听 `window.focus`**。用户重新聚焦不会触发全量请求。
- **持久布局**：`/practice/layout.tsx` 保留 Header、侧栏、分栏与 composer；`/practice`、`/practice/chat/:id` 仅切换当前数据，不重挂载所有 UI。

| 服务器查询 | 缓存有效期 | 获取时机 |
|---|---:|---|
| SSO 会话 readiness | 5 分钟 | 首次登录进入工作区；切换会话重用 |
| 最近对话摘要 | 60 秒 | 进入侧栏一次；新对话局部插入 |
| 最近产物摘要 | 60 秒 | 第一次切到「产物」标签；新产物成功后有针对性地失效 |
| 会话详情与近期消息 | 2 分钟 | 首次打开；往返切换可直接显示缓存 |
| 不可变产物 HTML 预览 | 10 分钟 | 用户实际点击预览时才读取 |

运行中的任务仍仅轮询**该对话的当前轮次**，而非每次轮询整个列表。未来若需要进一步减低运行中任务轮询，可以单独加 owner-scoped SSE 进度流，但不应将它和聊天历史缓存混合。

## Agent 错误原因与定位

用户提供的具体失败：
- `conversationId=21d8df99806349ebb5112c08b6df5af8`
- `turnId=7fc5641d30a1413fb852024a016067d9`
- `runId=16696fa0c1fc404fbeb26c9101291bcd`
- `status=FAILED`，`phase=DESIGNING`，`errorCode=AGENT_ERROR`，`elapsed_ms=1136`。

这些证据说明失败发生在 Agent **设计/模型编排阶段**，还没有进入 HTML 草稿提交、浏览器检查或截图。**不等于已经证实是哪一种 SDK、模型、网络或配额故障。** 原代码的通用异常捕获将所有底层错误压成 `AGENT_ERROR`，前端再覆盖为泛化提示。

现在新增 provider 状态码分类（认证、限流、请求不兼容、上游 5xx、超时），但不暴露供应商异常值、凭据、历史提示或内部堆栈。Forge 将公开错误信息、阶段和错误码持久化为现有 `nar_messages` 助手消息，不需新增 SQL 字段。前端显示公开的 `task.error`、`task.phase`、`task.error_code` 和运行编号。

### 查这一次失败的服务器日志

在**开发服务器**对应 Compose 目录，使用你实际部署时的 compose 文件组合：

```bash
docker compose -f docker-compose.dev.yml -f docker-compose.nar-agent.yml \
  logs --since '2026-11-14T18:53:35Z' --until '2026-11-14T18:54:15Z' --no-color nar-agent \
  | grep -F '16696fa0c1fc404fbeb26c9101291bcd'
```

注意上面 UTC 时间来自用户提供的执行时间；如果日志输出里的时间是服务器本地时间，需按实际时区调整。开发运维还应核对 `NAR_AGENT_MODEL`、`NAR_AGENT_BASE_URL`、`NAR_AGENT_API_KEY` 的存在性与模型可用性，**不要在聊天或 CI 日志中打印 API Key**。这些配置不是本 PR 新加的环境变量。相关的错误类别会从该运行的安全日志中判断，但只有实际服务日志能定位已经发生过的异常。

## 运行前验收

- 会话 A→B→A：第二次返回 A 使用有效的内存缓存，Header/侧栏不卸载。
- 切换浏览器标签、DevTools 触发 focus：不请求全量会话列表。
- 创建新会话：提交后更新单条摘要并导航，不能重新拉取所有产物或清空侧栏。
- 运行中的任务：只轮询该轮次；切到其他会话立即停止旧页面的轮询；后台任务保留数据库状态。
- 失败任务：公开错误文本/阶段/代码/任务编号可见，刷新后助手错误消息仍存在；失败轮次允许用户开始下一轮请求。
- 不同 SSO 用户的缓存隔离；浏览器刷新时重新从数据库获取（内存缓存自然清空）。
- 测试只用 GitHub Actions 的临时 MySQL，不访问生产数据库。
