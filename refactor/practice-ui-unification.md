# NarAgent 创作工作台：main 同步与 UI 统一

**状态：已在 `refactor/naragent-ui-on-quiz-card` 提交，目标仅为 `feature/quiz-card`；未合并、未部署。绝不合并到生产 `main`。**

## Git 基线与冲突处理

- 原功能分支：`feature/quiz-card`（包含 NarAgent；旧侧栏重构 PR #88 已合并）。
- 整合基线：`main`（创建分支时的提交 `2c60f61fcabfca6734e756824415d281f4fee2bd`）。
- **正确方向：main → feature/quiz-card。** 先整合两者的文件，再创建以 `feature/quiz-card` 为第一父提交、`main` 为第二父提交的 merge commit，放在独立分支 `refactor/naragent-ui-on-quiz-card`，通过 PR 将变更合入 `feature/quiz-card`。不逐个 rebase 243 个提交，也绝不变更 `main`。
- 以完整 Git Tree 对比共同祖先、main 和 feature 的所有文件，而非依赖 GitHub Compare API（该 API 的文件差异列表最多 300 项）。
- 保留 main 独有的 HTML 资源管理、讲练工具后端、访问统计、封面回填及相应部署/测试文件。冲突文件逐项合并。
- 路由冲突有意拆分：`/practice` 继续是 NarAgent 创作工作台；原 main 的讲练工具列表迁移为 `/practice/resources`，由左侧栏进入。后端 `GET /practice-tools` 不变。

## 一份 UI，一套职责

| 关注点 | 唯一主实现与复用方式 |
| --- | --- |
| 图标 | `lucide-react`，与 `linchangWeb/main` 对齐；不要在业务页手写重复的 SVG glyph |
| 品牌 Logo | Forge `components/brand-logo.tsx` 适配 `@narrativeos/ui/brand-logo` |
| 账户菜单 / SSO | `components/account-menu.tsx` 适配现有 `@narrativeos/ui`；不新建会话逻辑 |
| 按钮 / 关闭 | `components/ui/button.tsx`、`components/ui/close-button.tsx` |
| 全站 Header | `components/workbench-header.tsx`；NarAgent 不自建第二套页头 |
| 全站 Footer | `components/site-footer.tsx`，在根 `app/layout.tsx` 一次渲染 |
| 创作与广场侧栏 | `@narrativeos/ui/workspace-sidebar`；统一链接、折叠、Logo、推广卡与账号容器 |
| NarAgent 导航数据 | `app/practice/practice-navigation.tsx`；只关心产品路由和最近作品 |
| 三栏布局和拖拽 | `app/practice/resizable-workspace.tsx`；属于该工作台特有的交互 |
| 弹窗 | 已有 `ModalFrame` / `ConfirmDialog` / `CloseButton`，不重复做新 modal |
| 作品卡片 | `GeneratedWorkCard` 复用 `Button`，保留按钮语义与作品预览动作 |
| 过程时间线 | `CreationTimeline` 复用 `Button` 与 Lucide 图标 |

色彩使用现有 NarrativeOS 纸张、朱砂、暖金视觉约定，样式仅在必要处保持页面差异。不为每个子组件定义新的全站按钮和 Logo 规则。

## 模块拆分

- `page.tsx`：仅负责连接页面布局、对话、预览、发布弹窗，不再直接调用后端服务。
- `practice-chat.tsx`：聊天区、状态进度、示例提示、输入与按钮。
- `use-practice-workspace.ts`：授权、对话会话持久化、生成任务、恢复与选择作品。
- `use-practice-library.ts`：保存、版本切换、发布、撤销、分享等作品生命周期。
- `practice-work-service.ts`：版本读取、作品预览投影、保存/追加版本的唯一共享服务入口。
- `practice-types.ts`：重用 `practice-session.ts` 的 SessionMessage，不另建平行消息结构。
- 单独 CSS 模块：导航、创作时间线、作品卡片；三栏布局保留在 `practice.module.css`。

业务交互及 owner-scoped API、版本 lineage、SSE/轮询状态、历史会话恢复应维持原有行为。

## 跨仓库共享包边界

资源广场和 Forge 的侧栏已接入 `linchangWeb/packages/narrativeos-ui` 中的同一组件（本地打包版本 0.1.9）。两个侧栏的「我的素材」入口都使用现有 `/my-assets` 页面，页面与账号菜单使用同一名称。以资源广场的样式为基准，两端使用 Noto Sans SC，共用「发现灵感、我的创作、我的作品、素材广场」的顺序、图标和 204px 初始宽度。资源广场保留邀请卡，NarAgent 保留新建对话和历史，标签和账号区留在原位，历史条目独立滚动。Forge 构建从 vendor 包及锁文件安装共享组件。Agent 宽度可在当前工作台内拖动，下次进入恢复为广场的默认宽度。此变更尚未部署。

同域部署使用站内路径，默认本机官网与 Forge 分别使用 3000 和 3001，开发服务器的官网与 Forge 分别使用 3002 和 3001。非标准部署由 Forge 的 `NEXT_PUBLIC_SSO_ORIGIN` 和官网的 `NEXT_PUBLIC_WORKBENCH_URL` 分别指定跨站目标。

两个应用的页脚「优质案例」都进入当前环境的教师资源广场，官网保留当前语言。

## 全站页头、页脚和侧栏

共享包 0.2.5 提供 `WorkspaceFrame`、`WorkspaceHeader`、`WorkspaceFooter` 与 `WorkspaceSidebar`。Forge 根布局按路由安装通用外框；Agent 使用相同组件，并由创作布局控制侧栏与预览分栏。linchangWeb 的广场、登录和账号设置通过 `PortalWorkspace` 接入。两个应用各自提供路由、账号适配和页面操作入口。

- 教师资源广场始终隐藏返回按钮。其余页面默认返回上一页，直接打开时回当前环境的教师资源广场。
- 官网 `/` 和各语言首页沿用门户原有的顶部导航和页脚布局。页脚的「优质案例」仍跳转到教师资源广场。
- 共享页头使用原资源广场的 60% 底色。侧栏展开时隐藏页头 Logo、标题与说明，收起时一并显示；页头操作保留。主侧栏导航使用紧凑行高，品牌标语始终为单行。
- 嵌入预览沿用原有隔离和权限，三栏显示在外层。独立 `/play` 由 WebGAL 运行时提供，无平台三栏。
- Forge 生成工作台保留未保存退出确认；资源广场保留邀请弹窗，页脚继续提供优质案例、Q&A 与公告。
- 门户首页的「进入工作台」「开始创作」以及底部创作入口打开当前语言的教师资源广场。Forge 与门户的 Q&A、公告都在当前页面弹出，按需读取原数据。门户嵌入 Forge 的 `/support/embed`，由现有应用地址配置确定嵌入来源，Forge 继续使用原问答组件与提问权限。

本地验收覆盖两端生产构建、共享组件与 Agent 回归测试、主要页面单套三栏、移动端折叠、跨应用返回和无历史回退。用模拟作品验证 iframe 外层显示三栏，用本地游戏确认独立 `/play` 返回播放器且无三栏。已登录的账号设置与真实支付未在本次端到端测试中操作。尚未部署。

本地验收已通过两端 TypeScript 检查与共享包校验。Chromium 验证了桌面侧栏折叠、移动端折叠宽度、广场邀请弹窗，以及 30 条模拟会话滚动时标签和账号区的位置。

门户和工作台页脚提供「联系我们」邮件入口。Agent 在输入框底部工具栏提供五个单选创作形式，可切换和清除。选中的标签嵌在文本框首行，正文可接在标签之后，后续行恢复左对齐。选项在普通消息提交时附加到正文，继续走现有自动路由。切换会话时清除选项，提交失败保留原正文和选项。

## 验收门槛

1. CI：TypeScript、Next.js production build、独立 NarAgent Build & Test、网关后端测试、现有作品/发布回归测试。
2. 新增架构守卫：`tests/practice_ui_architecture.test.cjs` 和旧 `tests/practice_shared_navigation.test.cjs`。
3. 浏览器：PC/手机侧栏、快捷链接、拖拽布局、登录/退出、作品版本、关闭弹窗、Footer。
4. main 独有功能：HTML 资源管理、`/practice/resources`、`/practice-tools`、配置、首页入口。
5. 仅在验证后将本 PR 合并到 `feature/quiz-card`；禁止改 PR base 为 `main`、禁止生产部署。
