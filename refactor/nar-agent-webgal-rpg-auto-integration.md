# NarAgent → 教师工作台 WebGAL Auto（2026-11-16）

## 状态

此分支是 **待审查、待真实端到端验收** 的功能实现；未部署。依据上传的《NarrativeOS｜NarAgent 接入 WebGAL RPG Auto：零新增业务表 MVP 实施规格 v1.3》。

## 服务与职责

- NarAgent Intent V2 识别 `game`；Forge `plan_v2` 决定 `rpg.prepare` 或 `rpg.edit_link`，保留 HTML/Animation 老路由。
- RPG 创建先在现有 ConversationTurn 中落地 Assistant 确认卡（`nar_messages.public_metadata.rpg`）。此时 Turn 完成，**没有 WebGAL Job、没有 RPG 冻结，且不发起普通 Chat Builder 的 reserve_turn**。
- Agent 输入框的「互动角色扮演」标签明确指定新建 WebGAL 互动游戏。Forge 在自动路由时以该选择为准，生成 RPG 确认卡。Intent V2 对不支持的能力仍可返回 capability_review。
- 用户选择时长、图片、配音 → 服务端纯函数编译真实 `source_material + GenerationOptions` → 复用 `estimate_hold` 做报价 → 仅用户确认后使用消息行 owner-scoped CAS 认领。
- CAS 唯一获胜者调用 **同一个** `JobStore.create`、先保存 `job_id`、再复用现有 `run_job(...background=True)`。游戏生成、冻结积分及结算完全使用 WebGAL 既有 Pipeline 和钱包。
- 前端用原 Assistant message ID 显示可恢复的状态卡，读 `GET /jobs/{jobId}` 映射真实 `phase/status/build_state/has_published_build`；游戏可以新页打开，修改仅跳到现有工作台。
- 不引入新业务表、独立 Worker、第二套生成链路、聊天内 iframe、RPG 的自由文本自动编辑、HTML Artifact 迁移。

## 部署开关及顺序

1. **先锁步部署 Forge 后端与 NarAgent V2**：Intent schema 保持 2.0，增加可选 game 输出、可选 `candidate_game_job_id`、`workspace.recent_games`。不要把新 context 发给未升级的旧 NarAgent V2 解析器。
2. **2026-11-17 修复：自动意图识别只用 V2；WebGAL RPG 无需任何新增 feature flag。** Forge 已接入 WebGAL 创建、查询、执行、报价、余额等真实回调时，V2 自动获得 `game.create` / `game.edit_link` 能力；未接入时明确返回服务不可用，不会错误生成 HTML。
3. 在同一个 Forge 进程中注入真实 `JobStore`/`run_job`/`estimate_hold`/`CreditService` 回调；不要绕过现有 SSO、另建钱包或要求 NarAgent 上报 WebGAL capability。
4. 锁步升级 Forge、NarAgent 和前端后，直接验证 RPG 确认卡、游戏链接和真实生成/计费。**无需额外配置或开启 RPG 环境变量。** 旧版本的 `NAR_RPG_ENABLED` 不再参与代码执行，不能作为关闭游戏能力的开关；真正缺少回调时会阻止操作。
5. **无需数据库迁移**。但是生产 MySQL 8 仍需单独实测 JSON null 匹配、`JSON_SET`、行级 CAS 与同消息并发提交。

## V2-only 切换（2026-11-16）

- Forge 的 `mode=auto` 强制使用 `resolve_v2_live` → `plan_v2`；不再通过 `request_id` 灰度抽样或执行 V1 `resolve_intent`。V2 不可用时返回明确错误，不回退 HTML 或旧意图识别。
- NarAgent 保留对内路径 `POST /v1/intent`（**路径名称与意图 Schema 版本不同**）；实际只支持 `schema_version=2.0` + `context_v2`。显式请求 `1.0` 返回 410；未显式传 Schema 但没有 V2 上下文的调用在数据校验阶段拒绝。
- V1 的 `intent_router.py` 保留为已停用源码参考，`main.py` 已注释掉其 import；正式执行路径不再调用它。要回滚须专门还原 Git commit、重新跑兼容测试；不能通过设置环境变量静默启用。
- 必须先锁步发布兼容的新 NarAgent/Forge，旧 V1 调用方需升级。部署检查：将 `NAR_INTENT_V2_LIVE_PERCENT=0` 或不设置，`auto` 仍应调用 V2；单轮请求的路径应为 `/v1/capabilities` → `/v1/intent`（payload Schema 2.0），不可再出现 Schema 1.0。WebGAL RPG 的可用性由现有服务回调决定，不再依赖 `NAR_RPG_ENABLED`。
- 此次仅统一意图识别路由，不改变用户手动选择明确 `chat/html/animation/edit` 模式，也不修改 WebGAL Job、积分或播放权限。
- 保持已创建作品和已有会话可继续使用 V2；仍需进行真实模型的含糊请求分类测试，尤其“我想做个《春江花月夜》的互动游戏”应先澄清体验类型，不宜擅自生成 HTML。

## 澄清后 RPG 继续执行（2026-11-17）

- 已修正「制作《春江花月夜》互动游戏 → 选择互动剧情游戏 → 返回格式转换/能力复核」：Forge 的 `plan_v2` 会在**服务端已验证的单选答案**、原任务为 `create/new/unspecified`、无额外自由文本且模型已明确可执行产物时，将误标的 `continue`/`convert` 恢复成原来的新建动作。最终仍需通过现有服务能力和权限检查。
- `game` 能力由 Forge 内已有 WebGAL 回调决定（无需配置新功能开关），`rpg.prepare` 只创建可持久化确认卡，不调用游戏生成接口、冻结或扣除 RPG 生成积分。
- 安全约束：没有正式澄清答案、存在额外自由文本、新旧任务关系不匹配，或 WebGAL 回调不可用时不自动启动；原作品版本、用户归属、确认/扣费与 CAS 约束不变。
- 回归用例覆盖：真实 Forge 入口的《春江花月夜》选项流程、`continue`/`convert` 恢复为 `rpg.prepare`、HTML 形式选择、未接入 WebGAL 的拒绝行为、原有 WebGAL 报价与确认不重复创建 Job。
- 以上是网关与纯函数的模拟测试，不代表已在部署服务器验证真实模型和 WebGAL Job 流水线；发布后还须走一次真实账户的无配音/配图端到端验收。

## 本轮审查修订

- 修正：多轮澄清用户仅回答“第一个”时，从同一 owner/conversation 的原始 Turn 恢复完整用户创作材料；`source_turn_id` 只是 JSON 中的受限引用，并非新业务表或新的用户可控 GameSpec。
- 修正：`recent_rpg_games` 查询先筛选已绑定真实 `job_id` 的确认卡，再进行 `LIMIT`；新的 PREPARED 卡不会把较早的可编辑游戏挤出候选。
- 修正：前端轮询 effect 不依赖整个 `job` 对象，避免每次 GET 都重启即时轮询；`START_REJECTED/NEEDS_REVIEW` 仍可打开工作台。
- 新增 MySQL 8 回归：原始长文本恢复与归属校验、7 个新 PREPARED 卡不遮蔽历史 game Job。

## 测试范围与限制

- `python -m unittest tests.test_nar_rpg_integration_unit`（或 `python -m unittest discover -s tests -p 'test_nar_rpg_integration_unit.py'`）包含 50 条 **已经人工定义语义类别的 planner 合约示例**、创建/编辑分流，以及编译 options 与原始剧情要求保留的单元用例。这些测试**不检验 LLM 的真实意图识别准确率**。
- 合并前必须运行：真实 NarAgent Intent 50 条逐条分类评估；真实 SSO、双标签并发、CAS 原子去重、余额不足与价格变化、配音/配图开关、用户继续聊天、刷新/历史分页、会话删除、跨用户读取和修改、完整 Auto 生成/计费/播放/编辑、旧版 HTML/Animation/choice 回归。
- 不保证创建响应丢失、进程崩溃后的自动恢复或 WebGAL 的 exactly-once 结算。遇到 `NEEDS_REVIEW`、`CLAIMED` 长时间停滞，必须人工核查原 Job，**不得自动重新创建或重新执行**。
- **产品决策（2026-11-16 已确认）**：RPG 播放页与静态游戏资源沿用现有 WebGAL 的链接访问规则；持有可用播放链接的人可以访问。本次不增加私有播放鉴权。**不应在界面或文案声称播放链接仅所有者可访问**。编辑页及 Job 管理 API 仍按现有 SSO/owner 校验。
- 当前未实现聊天页面文件上传与从未上传 PDF 的提取；只使用当前轮正文及其已授权材料内容。

## 文件概览

```text
nar_agent/app/intent_v2.py
nar_agent/app/prompts/intent_v2.md
webgal_backend/nar_intent_v2.py
webgal_backend/nar_rpg_options.py
webgal_backend/nar_conversation_store.py
webgal_backend/nar_conversation_routes.py
webgal_backend/app.py
forge_frontend_next/lib/conversation-api.ts
forge_frontend_next/app/practice/practice-types.ts
forge_frontend_next/app/practice/practice-conversation.ts
forge_frontend_next/app/practice/use-nar-conversation.ts
forge_frontend_next/app/practice/rpg-task-card.tsx
forge_frontend_next/app/practice/rpg-task-card.module.css
forge_frontend_next/app/practice/practice-chat.tsx
tests/test_nar_rpg_integration_unit.py
```
