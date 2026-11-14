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
| 创作侧栏 | `components/ui/workspace-sidebar.tsx`；负责通用链接、折叠、Logo、账号容器 |
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

公共来源仍是 `linchangWeb/packages/narrativeos-ui`。门户使用 0.1.5，而 Forge 当前锁定 0.1.4，因此此次仅复用 **Forge 现有已发布的公共 API**。本次不伪造一个新的跨仓库 Sidebar npm 发布版本；真正双端源代码统一应单独发布升级该包、更新 vendor tarball 与 lockfile、同时验证两端。这也是剩余明确的跨仓库复用工作。

## 验收门槛

1. CI：TypeScript、Next.js production build、独立 NarAgent Build & Test、网关后端测试、现有作品/发布回归测试。
2. 新增架构守卫：`tests/practice_ui_architecture.test.cjs` 和旧 `tests/practice_shared_navigation.test.cjs`。
3. 浏览器：PC/手机侧栏、快捷链接、拖拽布局、登录/退出、作品版本、关闭弹窗、Footer。
4. main 独有功能：HTML 资源管理、`/practice/resources`、`/practice-tools`、配置、首页入口。
5. 仅在验证后将本 PR 合并到 `feature/quiz-card`；禁止改 PR base 为 `main`、禁止生产部署。
