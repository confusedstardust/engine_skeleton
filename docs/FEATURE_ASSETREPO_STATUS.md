# `feature/assetrepo` 分支功能与后续支付开发说明

更新日期：2026-09-25

## 1. 分支定位

`feature/assetrepo` 当前承载两部分工作：

1. 已提交的微信支付 Native 渠道基础模块。
2. 尚未提交的素材库、OSS 资源发布、数据库 JobStore、数据库结构和迁移工具。

当前分支 HEAD：

```text
1dbfe05 feat: Implement WeChat Pay Native payment module
```

本分支接下来主要用于支付相关开发。支付渠道模块已经存在，但业务订单、支付回调落库、额度发放、生成扣费和退款仍需实现。

## 2. 已提交功能

### 2.1 微信支付 Native 渠道模块

目录：`wechatpay_native/`

已实现：

- Native 下单；
- 按商户订单号查单；
- 关闭未支付订单；
- APIv3 请求签名；
- 微信支付 API 响应验签；
- 支付回调验签；
- AES-256-GCM 回调解密；
- 商户号、AppID、订单号、金额和币种校验；
- 商户私钥、APIv3 密钥和微信支付公钥的安全配置；
- 单元测试。

该模块只负责微信支付渠道通信，不注册 FastAPI 路由、不读写业务订单，也不负责额度发放和退款闭环。

验证结果：

```text
python -m pytest tests/test_wechatpay_native.py -q
8 passed
```

## 3. 当前工作区中尚未提交的功能

### 3.1 素材库基础能力

主要文件：

- `webgal_backend/asset_library.py`
- `webgal_backend/app.py`
- `forge_frontend_next/app/assets/page.tsx`
- `forge_frontend_next/app/page.tsx`
- `forge_frontend_next/app/globals.css`
- `tests/test_asset_library.py`

已实现：

- `/assets` 素材库页面及首页入口；
- 查询当前登录用户的素材；
- 按 `GENERATED`、`UPLOADED`、`IMPORTED` 筛选来源；
- 按背景、立绘、语音、BGM、音效和其他类型筛选；
- 游标分页；
- 素材所有权隔离；
- 素材实体与实际文件版本分开保存；
- 文件版本、变体、尺寸、哈希、MIME、OSS object key 和生成元数据记录；
- 素材访问 URL 接口。

新增接口：

```text
GET /assets
GET /assets/files/{file_id}/url
```

### 3.2 用户上传素材入库

已有的图片、BGM、去背景和头像裁剪流程已接入素材库：

- 用户上传素材标记为 `UPLOADED`；
- 上传文件保存到 OSS；
- 去背景结果生成新的素材文件修订；
- 头像裁剪结果保存为 `avatar` 变体；
- 游戏草稿记录 `asset_id`、`asset_file_id`、OSS object key 和访问 URL；
- 素材库功能只对正式 SSO 用户开放。

### 3.3 AI 生成素材入库

生成流水线已接入素材库：

- AI 生成图片、语音、BGM 和音效标记为 `GENERATED`；
- 生成后自动上传 OSS；
- 重新生成时创建新的文件修订；
- 同步结果写入 `state/asset_library_sync.json`；
- 同步结果登记为任务 artifact。

### 3.4 OSS 资源存储和访问

主要文件：

- `webgal_backend/oss_storage.py`
- `webgal_backend/pipeline.py`

已实现：

- AI 生成素材和用户上传素材统一上传 OSS；
- 按用户、来源、素材和修订版本生成不可变 object key；
- 上传后检查远端对象大小；
- 保存 OSS ETag；
- 公共 Bucket 返回固定 URL；
- 私有 Bucket 为素材预览返回短期签名 URL；
- OSS 凭据仅由后端读取。

对象路径格式：

```text
{prefix}/users/{user_id}/assets/{source_type}/{asset_id}/r{revision}/{file_id}.{ext}
```

### 3.5 WebGAL 发布资源改写

游戏验证通过后，发布流程会：

- 把背景、立绘、头像、BGM、音效和语音引用改写为公共 OSS URL；
- 生成 `state/oss_game_manifest.json`；
- 保存脚本原引用和 OSS 资源之间的对应关系；
- 将 manifest 登记为任务 artifact。

私有 OSS 模式不会把短期签名 URL 固化进游戏脚本。当前项目使用公共读模式，仍需使用真实游戏完成浏览器加载、音频播放和 CORS 验收。

### 3.6 数据库 JobStore

主要文件：

- `webgal_backend/database.py`
- `webgal_backend/storage.py`
- `docs/database-plan/07_database_job_store.sql`

已实现：

- 创建任务时创建 `games` 和 `generation_jobs`；
- `generation_jobs` 作为任务状态权威来源；
- `generation_job_events` 保存状态和错误历史；
- 从数据库读取和列出当前用户任务；
- 保存任务状态、阶段、错误、修订号和 artifact manifest；
- 使用 `lock_version` 防止并发状态覆盖；
- 数据库模式下不再生成新的 `job.json`；
- 文件任务模式仍可通过配置开关保留。

当前限制：实际数据库已经连通且表结构完整，但 `users` 表为 0 条。数据库 JobStore 要求任务所有者已经存在于 `users`，因此必须先接通 SSO 用户同步，才能完成真实用户的新建任务验收。

### 3.7 迁移和诊断工具

新增脚本：

- `scripts/backfill_asset_library.py`：回填历史任务素材；
- `scripts/migrate_file_jobs_to_database.py`：把正式 SSO 历史任务迁入数据库；
- `scripts/check_database_connection.py`：检查连接、版本、时区、必需表、必需字段和业务表数据量。

历史任务扫描结果：

```text
历史任务总数：53
正式 SSO 任务：1
邀请码任务：52
已迁移：0
缺少数据库用户：1
```

邀请码任务不会自动绑定或伪造正式用户归属。

### 3.8 数据库方案和 SQL

目录：`docs/database-plan/`

已提供：

- 全局 ER 图；
- 数据字典；
- 作品、任务、版本、素材和引用表；
- 点赞、收藏表；
- 商品、订单、支付尝试、通知和退款表；
- 额度批次、冻结、分摊和流水表；
- outbox 可靠事件表；
- 事务、锁顺序和幂等方案；
- 一致性检查 SQL；
- MySQL 自动验证脚本。

实际数据库验证结果：

```text
MySQL：8.0.36
数据库：narrativeos_dev
表数量：25
必需表：完整
必需字段：完整
会话时区：UTC
业务表：当前均为空
users：0
```

## 4. 配置项

`.env.example` 已增加：

```env
NARRATIVEOS_DATABASE_URL=mysql://user:password@127.0.0.1:3306/narrativeos?charset=utf8mb4
WEBGAL_DATABASE_JOB_STORE_ENABLED=false
WEBGAL_ASSET_LIBRARY_ENABLED=false

WEBGAL_OSS_ACCESS_MODE=public
WEBGAL_OSS_SIGNED_URL_TTL=900
```

真实数据库地址、OSS 密钥、微信支付密钥和私钥文件不得提交到 Git。

## 5. 尚未完成的素材和作品功能

- `draft_asset_usages` 草稿引用登记；
- `game_versions` 不可变版本创建；
- `asset_usages` 发布版本素材引用冻结；
- 发布时原子更新 `games.current_version_id`；
- 素材库直接上传、选入游戏、搜索、标签和重命名；
- 素材逻辑删除、恢复和安全垃圾回收；
- 公开游戏库；
- 点赞与收藏接口；
- 人工审核、发布、下架和恢复；
- worker 租约、heartbeat 和服务重启恢复。

## 6. 后续支付开发范围

### 6.1 第一阶段：用户和订单基础

1. 接通 SSO 用户与数据库 `users` 表。
2. 实现商品查询，只允许服务端读取 `products` 中的价格和权益配置。
3. 实现创建 `purchase_orders`，保存商品、价格、额度和退款规则快照。
4. 使用 `Idempotency-Key` 防止重复创建订单。
5. 所有支付、订单和额度接口要求正式登录用户。

建议接口：

```text
GET  /api/billing/products
POST /api/billing/orders
GET  /api/billing/orders/{order_id}
GET  /api/billing/orders
```

### 6.2 第二阶段：微信支付接入

1. 由业务订单生成唯一 `out_trade_no`。
2. 创建并持久化 `payment_attempts`。
3. 调用 `wechatpay_native` 创建 Native 支付。
4. 返回 `code_url` 给前端生成二维码。
5. 提供支付状态轮询。
6. 渠道超时进入 `UNKNOWN`，使用原订单号主动查单，不能重复创单。

建议接口：

```text
POST /api/billing/orders/{order_id}/payment
POST /api/billing/wechat/notify
```

### 6.3 第三阶段：可信回调与额度发放

1. 回调入口保留微信发送的原始请求体。
2. 先验签，再解密，再匹配本地订单。
3. 校验 AppID、商户号、订单号、币种和订单总金额。
4. 通过 `notification_id` 和 `transaction_id` 唯一约束保证幂等。
5. 同一事务更新 `payment_attempts`、`purchase_orders` 并写入 `outbox_events`。
6. outbox worker 创建 `entitlement_grants` 并追加 `credit_ledger` 发放流水。
7. 支付成功但额度暂未发放时显示“额度处理中”，不能要求用户再次付款。

### 6.4 第四阶段：生成任务扣额度

1. 创建生成任务时冻结额度并创建 `credit_reservations`。
2. 使用 `credit_allocations` 记录本次额度来自哪些购买批次。
3. 冻结成功后才允许任务进入执行队列。
4. 生成成功后扣除额度并写 `CAPTURE` 流水。
5. 生成失败后释放额度并写 `RELEASE` 流水。
6. `(job_id, operation_key)` 保证同一操作不会重复扣费。

### 6.5 第五阶段：退款、补偿和运营

1. 实现整包退款资格检查。
2. 接入微信退款和退款通知。
3. 退款成功后撤销尚未使用的额度并写流水。
4. 处理重复实收、回调遗漏、下单超时和本地关单竞态。
5. 增加订单、支付、额度和退款每日对账。
6. 增加失败重试、告警和人工处理入口。

## 7. 支付开发必须保持的边界

- 金额统一使用整数分，不使用浮点数；
- 商品价格必须来自服务端数据库，不信任浏览器提交的金额；
- 商户私钥、APIv3 密钥和 OSS 密钥不得发送到前端或写入仓库；
- 支付回调必须先验签，再使用回调内容；
- `payer_total` 可能受渠道优惠影响，业务订单金额校验使用 `amount.total`；
- 支付成功、订单履约和用户可用额度是三个不同状态；
- 重复通知必须返回幂等结果，不能重复发放额度；
- 关闭订单不代表渠道一定未收款，必须保留主动查单和补偿路径；
- 开放真实售卖前，支付、额度扣除、失败释放和退款必须形成完整闭环。

## 8. 提交前文件检查

当前功能代码、SQL、文档和脚本可以纳入提交。以下本地文件应排除：

```text
.claude/settings.local.json
docs/database-plan/~$_consistency_checks.sql
```

`docs/narrativeos-database-plan.zip` 是数据库方案压缩包。若仓库以源文件为准，可以不提交该压缩包；若需要提供可下载交付物，可以一并提交。

