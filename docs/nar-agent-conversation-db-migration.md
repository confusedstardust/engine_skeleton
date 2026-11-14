# NarrativeOS NarAgent 跨设备会话：数据库迁移与启用清单

**状态：代码与迁移脚本已提交到开发专用 PR，数据库未执行迁移、服务未启用，也未部署。**  
**目标：仅针对 `feature/quiz-card` 的开发环境，切勿直接升级生产 `main`。**

依据：用户提供的《NarAgent 跨设备会话与产物历史方案》（2026-11-14）。该方案中的懂了鸭 API 路径是网络观察样本，不代表已证实其数据库设计。NarrativeOS 按本项目 Forge + MySQL + NarAgent 的实际结构实现。

## 一、先备份再手动执行

脚本：[webgal_backend/migrations/002_nar_conversation_history.sql](../webgal_backend/migrations/002_nar_conversation_history.sql)

- **请你自己在开发 MySQL 实例执行。** 程序不会启动时自动建表或自动执行迁移。
- 确认当前连接的是 **development** 库：`SELECT DATABASE(); SELECT @@version, @@session.time_zone;`。切勿误操作生产库。
- 迁移前先备份目标库（例如通过现有 DBA/云数据库备份机制），确认 MySQL 8.0+、utf8mb4、InnoDB、UTC。
- 逐句执行 SQL 后运行下方验收查询。全部通过才在**开发环境**配置 `NAR_CONVERSATIONS_ENABLED=1` 并重启 Forge 后端。默认未配置或值为 0 时，新接口被安全禁用，前端继续使用旧的浏览器 `sessionStorage` 聊天流程；不会因缺表导致旧版本页面无法工作。
- 仅合并代码并不足以启用跨设备存储；还必须执行上述开发库迁移并配置环境变量。生产环境不会自动启用。

## 二、完整新增数据表与字段

### `nar_conversations` —— 一位用户的会话

| 字段 | MySQL 类型 | 作用 |
| --- | --- | --- |
| `id` | `CHAR(32) ASCII BIN` 主键 | 服务端可验证的会话 UUID（客户端随机生成，数据库核验唯一性） |
| `owner_id` | `VARCHAR(191)` 非空 | 归属用户 ID，**从 Forge SSO 登录态推导** |
| `title` | `VARCHAR(160)` 非空 | 首条用户提示摘要，默认不从客户端任意传入 |
| `created_at` | `DATETIME(6)` | 创建时间（UTC） |
| `active_at` | `DATETIME(6)` | 最近交互时间（UTC） |

索引：主键 `id`；复合索引 `(owner_id,active_at DESC,id DESC)` 支撑按账号、稳定时间游标倒序分页。

### `nar_messages` —— 消息正文（服务端永久持久化）

| 字段 | 类型 | 作用 |
| --- | --- | --- |
| `id` | `CHAR(32)` 主键 | 消息 ID |
| `conversation_id` | `CHAR(32)` 外键 | 所属会话 |
| `seq` | `INT UNSIGNED` | 会话内单调递增序号 |
| `role` | `ENUM('user','assistant')` | 发送方 |
| `content` | `TEXT` | 用户或助手的可见文本，不存 HTML 源码 |
| `created_at` | `DATETIME(6)` | UTC 时间 |
| `turn_id` | `CHAR(32) NULL` | 对应用户轮次 |
| `public_metadata` | `JSON NULL` | 用户可见时间线、简介、学习目标等；不要保存模型内部思维链或密钥 |

约束：`UNIQUE(conversation_id, seq)`，消息 `conversation_id` 外键指向会话（级联删除），`turn_id` 建索引。会话详情默认读最近 30 条；向上翻历史通过 `before=<seq>` 分页。

### `nar_turns` —— 提交与执行状态

| 字段 | 类型 | 作用 |
| --- | --- | --- |
| `id` | `CHAR(32)` 主键 | 单轮 ID |
| `conversation_id` | `CHAR(32)` 外键 | 所属会话 |
| `client_request_id` | `VARCHAR(80) ASCII BIN` | 浏览器稳定请求键，用于去重 |
| `prompt_message_id` | `CHAR(32)` 外键 | 已原子落库的用户消息 |
| `mode` | `ENUM('chat','html','animation','edit')` | 操作类型 |
| `status` | `ENUM('QUEUED','RUNNING','SUCCEEDED','FAILED','UNKNOWN')` | 执行状态 |
| `agent_run_id` | `VARCHAR(80) NULL` | NarAgent 返回的运行 ID |
| `parent_artifact_id` | `CHAR(32) NULL` | 编辑模式的上游产物 |
| `error_code` | `VARCHAR(80) NULL` | 安全错误码（不含供应商内部报错正文） |
| `created_at,updated_at,finished_at` | `DATETIME(6)` | 全生命周期时间戳 |

唯一约束：`(conversation_id,client_request_id)`；索引 `(conversation_id,status,created_at)`。在数据库事务里锁定会话行、检查活动轮次并写入用户消息。首条有效输入可携带同一个稳定的 `conversation_id` 和请求 ID，重复 POST 不会二次派发。

### `nar_turn_dispatches` —— 可靠提交意图记录

| 字段 | 类型 | 作用 |
| --- | --- | --- |
| `turn_id` | `CHAR(32)` 主键及外键 | 对应轮次 |
| `state` | `ENUM('PENDING','ACKNOWLEDGED','UNCERTAIN','FINISHED')` | 派发状态 |
| `created_at,acknowledged_at` | `DATETIME(6)` | UTC 记录与确认时间 |

它与消息、轮次在同一数据库事务中创建。**注意：当前 NarAgent 的 POST /v1/html、/v1/animations 尚不提供持久的幂等键。** 因此 `PENDING/UNCERTAIN` 状态**不会自动重试派发**，避免一次网络超时导致重复执行；需要人工对账或后续补齐 NarAgent 侧幂等再开启调度 worker。当前版本不是“跨进程 exactly-once 执行”的承诺。

### `nar_conversation_artifacts` —— 会话与产物的关联

| 字段 | 类型 | 作用 |
| --- | --- | --- |
| `conversation_id` | `CHAR(32)` | 来源会话 |
| `artifact_id` | `CHAR(32)` | NarAgent 原始产物 ID |
| `origin_message_id` | `CHAR(32) NULL` | 生成该产物的助手消息 |
| `work_id` | `CHAR(32) NULL` | 已保存长期作品在现有 WorkStore 中的 ID |
| `title` | `VARCHAR(160)` | 展示摘要 |
| `kind` | `ENUM('html','animation')` | 产物类型 |
| `created_at` | `DATETIME(6)` | UTC 关联时间 |

复合主键 `(conversation_id, artifact_id)`；索引 `(artifact_id,created_at DESC)` 与 `(created_at DESC,artifact_id,conversation_id)`。表内**不存 HTML 大文件**：作品 HTML、截图、版本继续由现有 `WorkStore` 管理，现有 owner-scoped API 检查身份；只有明确点开预览才请求内容。

## 三、可直接执行的迁移后验收 SQL

这些 SELECT 不改变数据库：

```sql
SELECT DATABASE(), VERSION(), @@session.time_zone;
SHOW TABLES LIKE 'nar_%';
SHOW CREATE TABLE nar_conversations;
SHOW CREATE TABLE nar_messages;
SHOW CREATE TABLE nar_turns;
SHOW CREATE TABLE nar_turn_dispatches;
SHOW CREATE TABLE nar_conversation_artifacts;
SHOW INDEX FROM nar_conversations;
SHOW INDEX FROM nar_messages;
SHOW INDEX FROM nar_turns;
SHOW INDEX FROM nar_conversation_artifacts;
SELECT COUNT(*) AS conversations FROM nar_conversations;
SELECT COUNT(*) AS messages FROM nar_messages;
SELECT COUNT(*) AS turns FROM nar_turns;
```

启动后，用真实 SSO 账号验证：
1. `GET /api/forge/nar-agent/conversations/status` → `{"enabled":true}`。
2. 首次发送创建一条会话、一个用户消息、一个轮次和一个 dispatch 记录；重复相同 `client_request_id` 不新增行。
3. 同账号另一浏览器登录后能列出会话，查看历史消息；另一账号 GET 同一会话应返回 404。
4. 作品完成后形成助手消息、产物关联；点击产物时通过现有隔离预览接口按权限取得 HTML。
5. 分别测试同时多次发送、运行中刷新、前端快速切换、历史分页、网络中断和执行服务重启。重启后原内存任务可能无法恢复，需要显示 `UNKNOWN`，不得冒充成功。

## 四、启用顺序和当前限制

建议顺序：**备份开发库 → 执行 SQL → 检查结构 → 部署开发分支 → 设置开发环境变量 → 重启后端 → 两浏览器/两账号联调 → 必要时再评估生产迁移**。

现有旧作品通过 `/practice/?work=...` 与 `/works/{id}` 保持可用，不自动把旧作品和不可靠的浏览器缓存聊天强行归到新会话。完整旧聊天如果从未保存到服务器，无法通过数据库迁移凭空还原。

对于运行中任务：当前异步 NarAgent 状态以其现有运行机制为准。Forge 数据库能保留用户消息、轮次和引用，不能保证 NarAgent **服务重启后继续已经丢失的进程内任务**。这与跨设备持久化已完成的历史是两件事。

当前版本没有自动运行数据库迁移、没有注册生产迁移步骤；服务默认继续使用旧路径。上线前必须完成上述验收、人工视觉检查与运行中任务场景的真实联调。

## 五、回滚与安全

**仅在确认数据库里没有需要保留的数据、完成备份后**，才考虑按依赖逆序删除：
`nar_conversation_artifacts` → `nar_turn_dispatches` → `nar_turns` → `nar_messages` → `nar_conversations`。
不要在运行期间直接删除表；首先把开发环境的 `NAR_CONVERSATIONS_ENABLED` 改回 `0` 并重启，旧版本浏览器流程会继续工作，已写入数据库的历史不受影响。

文档中所有表和索引均由本次迁移文件提供，不要求改变已有 `works` JSON / 既有会员积分表，不会自动删除历史数据。
