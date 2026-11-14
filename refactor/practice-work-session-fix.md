# NarAgent 作品会话隔离与广场侧栏视觉对齐

目标分支：`feature/quiz-card`（开发环境），**禁止向 `main` 合并**。

## 故障根因

过去侧栏 recent-work 使用 Next `Link` 变更 `/practice/?work=<id>`，但页面根组件中的 `usePracticeWorkspace()` 继续复用相同 React state：消息、当前 artifact 和预览均不重置。用于恢复对话的 effect 仅监听 `authReady/sessionUserId`，深链接加载 effect 仅运行一次 `[]`；所以单页内切换 query 会看到上一件作品。

作品 HTML、版本及作者权限由后端 `/works/:id`、`/assets/:versionId` 管理，和对话记录不同。对话/生成过程/选中作品仅按 `narrativeos:practice:session:v1:<userId>:<workId|general>` 保存于**本标签页 sessionStorage**；这不是永久服务器聊天历史，浏览器会话结束可能丢失。此前多数未从 work deep link 开始的旧对话实际保存在 `general` 桶中。

## 变更

- 使用 `useSearchParams` 读取 `work`，并用 `key={workspaceScope}` 为每件作品创建不同的 React 工作区实例，避免跨作品请求和预览污染。
- 恢复/写入会话与深链作品加载均使用同一个 `workspaceScope`；旧异步加载通过 mounted/active guard 失效。
- `recoverPracticeSession` 优先读取当前作品独立缓存；对于不存在独立缓存的历史作品，仅从旧 `general` 缓存中恢复携带匹配 `artifactId` 的生成回复及其紧邻用户提示。**不猜测**未标识的对话属于哪件作品，也不重写旧 general 缓存。
- 对新保存作品，在本标签页内尝试创建对应 workId 的消息快照；若用户已经有该作品的会话，不覆盖。
- 切换到「新建对话」从作品会话退出时不清空该作品的 sessionStorage 历史；仅在普通 `general` 新建时清空 general。
- 左侧高亮当前 work；右侧无法恢复独立会话时说明「作品仍可打开预览，但没有可恢复的独立对话」。
- 运行时在聊天区域用现有 `components/ui/state.tsx` 的 `Spinner` 和 `LoadingState`，而不是新增 Loading SVG 或动画逻辑。
- 以 `linchangWeb/main` 的 `teacher-plaza.css` 导航尺寸、配色、边缘布局、二级入口、底部推广卡片和账户底栏规则为参考，去掉 Forge 的悬浮圆角卡片外壳；保持 NarAgent 特有的最近作品、快捷创建与三栏拖拽。
- `WorkspaceSidebar` 的新 `promo` 为通用 slot；推广卡片实际链接到现有资源广场，不伪装成一个未实现的邀请对话框。

## 已知界限

- 无法从后端作品 HTML/版本表推导完整聊天；只能恢复浏览器会话中仍存在且可明确关联的消息。若需跨设备长期完整对话历史，必须单独设计持久化后端 conversation schema/API，并补上用户级权限/保留策略。
- 门户与 Forge 虽复用同一家 `@narrativeos/ui` 源头，但门户 package 为 0.1.5，Forge vendor 仍为 0.1.4。当前仅更新侧栏布局/样式与复用现有的 Forge AccountMenu，不声明已经升级新版本共享包，也不复制一套账户认证逻辑。
- 这是一份修复 PR；CI 通过不等于已部署。合并到 `feature/quiz-card` 会触发开发环境 CI/CD，请先确认开发部署策略。

## 验证

`tests/practice_session_switch.test.cjs` 动态转译并测试浏览器会话快照隔离、恢复及 general 清理边界，同时静态审查路由隔离和 Spinner；另跑现有 `practice_ui_architecture`、`practice_shared_navigation` 和 Next 生产构建。浏览器手动测试还应在同一标签内依次点击 A→B→A，观察对话/版本/高亮是否一致，尝试运行中的切换、刷新、退出新建及侧栏收起。
