# NarAgent → 教师工作台 WebGAL Auto（2026-11-16）

## 状态

此分支是 **待审查、待真实端到端验收** 的功能实现；未部署。依据上传的《NarrativeOS｜NarAgent 接入 WebGAL RPG Auto：零新增业务表 MVP 实施规格 v1.3》。

## 服务与职责

- NarAgent Intent V2 识别 `game`；Forge `plan_v2` 决定 `rpg.prepare` 或 `rpg.edit_link`，保留 HTML/Animation 老路由。
- RPG 创建先在现有 ConversationTurn 中落地 Assistant 确认卡（`nar_messages.public_metadata.rpg`）。此时 Turn 完成，**没有 WebGAL Job、没有 RPG 冻结，且不发起普通 Chat Builder 的 reserve_turn**。
- 用户选择时长、图片、配音 → 服务端纯函数编译真实 `source_material + GenerationOptions` → 复用 `estimate_hold` 做报价 → 仅用户确认后使用消息行 owner-scoped CAS 认领。
- CAS 唯一获胜者调用 **同一个** `JobStore.create`、先保存 `job_id`、再复用现有 `run_job(...background=True)`。游戏生成、冻结积分及结算完全使用 WebGAL 既有 Pipeline 和钱包。
- 前端用原 Assistant message ID 显示可恢复的状态卡，读 `GET /jobs/{jobId}` 映射真实 `phase/status/build_state/has_published_build`；游戏可以新页打开，修改仅跳到现有工作台。
- 不引入新业务表、独立 Worker、第二套生成链路、聊天内 iframe、RPG 的自由文本自动编辑、HTML Artifact 迁移。

## 部署开关及顺序

1. **先锁步部署 Forge 后端与 NarAgent V2**：Intent schema 保持 2.0，增加可选 game 输出、可选 `candidate_game_job_id`、`workspace.recent_games`。不要把新 context 发给未升级的旧 NarAgent V2 解析器。
2. 保持 `NAR_RPG_ENABLED` **默认关闭**，并核对 `NAR_INTENT_V2_LIVE_PERCENT`：RPG 入口只在 V2 实际 live 流量里生效；影子意图日志不会启动游戏。建议先内测组开启并验证灰度覆盖率，然后再扩大。
3. 在同一个 Forge 进程中注入真实 `JobStore`/`run_job`/`estimate_hold`/`CreditService` 回调；不要绕过现有 SSO、另建钱包或要求 NarAgent 上报 WebGAL capability。
4. 升级前端后验证确认卡与游戏链接，最后开 `NAR_RPG_ENABLED=1`。关闭开关能阻止**新** RPG 创建与确认，但不会停止已经启动的 WebGAL Job；既有消息和 Job 仍保留。
5. **无需数据库迁移**。但是生产 MySQL 8 仍需单独实测 JSON null 匹配、`JSON_SET`、行级 CAS 与同消息并发提交。

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
