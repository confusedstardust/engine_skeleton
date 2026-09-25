# 业务表字段字典

由本次独立 MySQL 实例的 information_schema 导出；20 张新业务表。完整索引/外键以 SQL 为准。

用户 ID 沿用 VARCHAR(191)，其余 CHAR(32) 业务 ID 由应用生成 UUID hex；AUTO_INCREMENT 流水 ID 除外。

余额与金额关系、所有权授权、合法状态转换等应用层规则见 PLAN.md 与 TRANSACTIONS.md。

## games

作品稳定身份；一个作品有多个任务和发布版本

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |
|---|---|---|---|---|---|
| id | char(32) | NO | — | PRI | — |
| owner_user_id | varchar(191) | NO | — | MUL | — |
| title | varchar(200) | NO | — | — | — |
| description | text | YES | — | — | — |
| slug | varchar(96) | YES | — | UNI | — |
| status | enum('DRAFT','PUBLISHED','ARCHIVED','BLOCKED') | NO | DRAFT | MUL | — |
| visibility | enum('PRIVATE','UNLISTED','PUBLIC') | NO | PRIVATE | — | — |
| current_version_id | char(32) | YES | — | MUL | 当前线上版本；只能通过发布事务切换 |
| cover_file_id | char(32) | YES | — | MUL | — |
| like_count | bigint(20) unsigned | NO | 0 | — | 关系表的可重建缓存 |
| favorite_count | bigint(20) unsigned | NO | 0 | — | — |
| lock_version | bigint(20) unsigned | NO | 0 | — | — |
| first_published_at | datetime(3) | YES | — | — | — |
| last_published_at | datetime(3) | YES | — | — | — |
| deleted_at | datetime(3) | YES | — | — | — |
| created_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |
| updated_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | on update CURRENT_TIMESTAMP(3) |

## generation_jobs

生成执行实例；数据库接入后作为业务状态权威

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |
|---|---|---|---|---|---|
| id | char(32) | NO | — | PRI | 沿用现有 job_id |
| game_id | char(32) | NO | — | MUL | — |
| owner_user_id | varchar(191) | NO | — | MUL | — |
| source_material | mediumtext | YES | — | — | — |
| request_key | varchar(64) | NO | — | — | — |
| request_hash | char(64) | NO | — | — | 规范化请求哈希；同键异参返回409 |
| status | enum('CREATED','QUEUED','RUNNING','WAITING_INPUT','SUCCEEDED','FAILED','CANCELLED') | NO | CREATED | MUL | — |
| phase | varchar(64) | YES | — | — | — |
| legacy_status | varchar(64) | YES | — | — | 迁移保留旧 *_READY 等值 |
| progress_percent | tinyint(3) unsigned | NO | 0 | — | 服务保证0..100 |
| draft_revision | bigint(20) unsigned | NO | 0 | — | — |
| published_revision | bigint(20) unsigned | NO | 0 | — | — |
| build_state | varchar(24) | NO | NONE | — | — |
| dirty_scopes | json | YES | — | — | — |
| options_json | json | YES | — | — | — |
| artifact_manifest_json | json | YES | — | — | — |
| job_storage_prefix | varchar(1024) | NO | — | — | 本地相对路径或对象前缀；不存签名URL |
| source_sha256 | char(64) | YES | — | — | — |
| error_code | varchar(64) | YES | — | — | — |
| error_message | text | YES | — | — | 脱敏；完整堆栈放受限日志 |
| attempt_count | int(10) unsigned | NO | 0 | — | — |
| lock_version | bigint(20) unsigned | NO | 0 | — | — |
| lease_token | char(32) | YES | — | — | — |
| lease_expires_at | datetime(3) | YES | — | — | — |
| heartbeat_at | datetime(3) | YES | — | — | — |
| started_at | datetime(3) | YES | — | — | — |
| finished_at | datetime(3) | YES | — | — | — |
| created_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |
| updated_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | on update CURRENT_TIMESTAMP(3) |

## game_versions

发布快照；READY后内容不可编辑，状态和审核可变

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |
|---|---|---|---|---|---|
| id | char(32) | NO | — | PRI | — |
| game_id | char(32) | NO | — | MUL | — |
| source_job_id | char(32) | NO | — | MUL | — |
| version_no | int(10) unsigned | NO | — | — | 作品内单调递增；锁住games分配 |
| source_draft_revision | bigint(20) unsigned | NO | — | — | — |
| version_label | varchar(64) | YES | — | — | — |
| release_notes | text | YES | — | — | — |
| status | enum('BUILDING','READY','FAILED','REVOKED') | NO | BUILDING | — | — |
| review_status | enum('PENDING','APPROVED','REJECTED') | NO | PENDING | — | — |
| review_reason | varchar(1000) | YES | — | — | — |
| reviewed_at | datetime(3) | YES | — | — | — |
| reviewed_by_user_id | varchar(191) | YES | — | MUL | — |
| engine_version | varchar(64) | NO | — | — | — |
| manifest_json | json | YES | — | — | 相对路径到不可变asset_file的映射 |
| manifest_sha256 | char(64) | YES | — | — | — |
| build_storage_prefix | varchar(1024) | YES | — | — | 必须含version_id，不覆盖 |
| entrypoint | varchar(255) | NO | index.html | — | — |
| published_at | datetime(3) | YES | — | — | — |
| created_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |
| updated_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | on update CURRENT_TIMESTAMP(3) |

## assets

逻辑素材；跨作品复用，来源和授权可追溯

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |
|---|---|---|---|---|---|
| id | char(32) | NO | — | PRI | — |
| owner_user_id | varchar(191) | NO | — | MUL | — |
| source_job_id | char(32) | YES | — | MUL | — |
| name | varchar(200) | NO | — | — | — |
| kind | enum('BACKGROUND','FIGURE','AVATAR','VOICE','BGM','SFX','VIDEO','SCRIPT','OTHER') | NO | — | — | — |
| source_type | enum('GENERATED','UPLOADED','IMPORTED') | NO | — | — | — |
| visibility | enum('PRIVATE','PUBLIC') | NO | PRIVATE | — | — |
| status | enum('ACTIVE','BLOCKED','DELETED') | NO | ACTIVE | — | — |
| license_code | varchar(64) | YES | — | — | 公开展示不代表允许他人复用 |
| attribution | text | YES | — | — | — |
| generation_metadata | json | YES | — | — | 模型、参数、seed；敏感prompt单独受控 |
| deleted_at | datetime(3) | YES | — | — | — |
| created_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |
| updated_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | on update CURRENT_TIMESTAMP(3) |
| source_key | varchar(512) | YES | — | — | 来源任务中的稳定逻辑键，例如figure/name或vocal/file |

## asset_files

物理文件不可变；URL按权限临时生成

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |
|---|---|---|---|---|---|
| id | char(32) | NO | — | PRI | — |
| asset_id | char(32) | NO | — | MUL | — |
| revision | int(10) unsigned | NO | 1 | — | — |
| variant | varchar(32) | NO | original | — | — |
| storage_provider | enum('LOCAL','OSS') | NO | — | — | — |
| bucket | varchar(63) | NO | — | — | LOCAL用空串 |
| region | varchar(64) | YES | — | — | — |
| object_key | varchar(1024) | NO | — | — | OSS key或受限本地相对路径 |
| object_version_id | varchar(128) | NO | — | — | 未开启OSS版本控制用空串 |
| location_hash | binary(32) | NO | — | UNI | SHA256规范元组(provider,bucket,key,version)，服务生成并逐项比对 |
| sha256 | char(64) | YES | — | MUL | 文件内容哈希；不能用ETag代替 |
| etag | varchar(128) | YES | — | — | — |
| mime_type | varchar(127) | NO | — | — | — |
| size_bytes | bigint(20) unsigned | NO | — | — | — |
| width_px | int(10) unsigned | YES | — | — | — |
| height_px | int(10) unsigned | YES | — | — | — |
| duration_ms | bigint(20) unsigned | YES | — | — | — |
| status | enum('UPLOADING','READY','FAILED','DELETING','DELETED') | NO | UPLOADING | MUL | — |
| uploaded_at | datetime(3) | YES | — | — | — |
| delete_after | datetime(3) | YES | — | — | — |
| deleted_at | datetime(3) | YES | — | — | — |
| created_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |
| updated_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | on update CURRENT_TIMESTAMP(3) |

## asset_usages

版本精确引用文件revision，防止重生成破坏旧作品

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |
|---|---|---|---|---|---|
| game_version_id | char(32) | NO | — | PRI | — |
| logical_path | varchar(512) | NO | — | PRI | 版本内相对路径；禁止..和绝对路径 |
| asset_file_id | char(32) | NO | — | MUL | — |
| usage_role | varchar(32) | NO | — | — | — |
| created_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |

## game_likes

点赞事实；取消时删除这一条关系

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |
|---|---|---|---|---|---|
| game_id | char(32) | NO | — | PRI | — |
| user_id | varchar(191) | NO | — | PRI | — |
| created_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |

## game_favorites

收藏默认仅本人可见；总数可公开

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |
|---|---|---|---|---|---|
| game_id | char(32) | NO | — | PRI | — |
| user_id | varchar(191) | NO | — | PRI | — |
| created_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |

## outbox_events

与业务写入同事务；投递至少一次，消费者必须幂等

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |
|---|---|---|---|---|---|
| id | char(32) | NO | — | PRI | — |
| event_key | varchar(191) | NO | — | UNI | — |
| event_type | varchar(64) | NO | — | — | — |
| aggregate_id | varchar(64) | NO | — | — | — |
| payload_json | json | NO | — | — | 只放必要ID与版本，不放密钥和支付明文 |
| status | enum('PENDING','PROCESSING','DONE','DEAD') | NO | PENDING | MUL | — |
| attempts | int(10) unsigned | NO | 0 | — | — |
| available_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |
| lease_token | char(32) | YES | — | — | — |
| lease_expires_at | datetime(3) | YES | — | — | — |
| last_error | varchar(1000) | YES | — | — | — |
| processed_at | datetime(3) | YES | — | — | — |
| created_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |

## products

服务端价格来源；改价不改已创建订单

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |
|---|---|---|---|---|---|
| id | char(32) | NO | — | PRI | — |
| sku | varchar(64) | NO | — | UNI | — |
| name | varchar(200) | NO | — | — | — |
| kind | enum('CREDIT_PACK','MEMBERSHIP','GAME_ACCESS') | NO | — | — | 首期仅开放CREDIT_PACK，其余需权益实现 |
| status | enum('DRAFT','ACTIVE','INACTIVE') | NO | DRAFT | MUL | — |
| price_fen | bigint(20) unsigned | NO | — | — | — |
| currency | char(3) | NO | CNY | — | — |
| benefit_json | json | NO | — | — | 带schema_version；积分数、有效期或商品目标 |
| revision | int(10) unsigned | NO | 1 | — | — |
| created_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |
| updated_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | on update CURRENT_TIMESTAMP(3) |

## purchase_orders

买什么、应付多少、权益是否发放；支付与履约分开

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |
|---|---|---|---|---|---|
| id | char(32) | NO | — | PRI | — |
| order_no | varchar(32) | NO | — | UNI | — |
| user_id | varchar(191) | NO | — | MUL | — |
| product_id | char(32) | NO | — | MUL | — |
| quantity | int(10) unsigned | NO | 1 | — | — |
| product_snapshot | json | NO | — | — | 名称、SKU、单价、benefit、revision和退款规则快照 |
| total_fen | bigint(20) unsigned | NO | — | — | — |
| discount_fen | bigint(20) unsigned | NO | 0 | — | — |
| payable_fen | bigint(20) unsigned | NO | — | — | — |
| currency | char(3) | NO | CNY | — | — |
| status | enum('PENDING','PAID','CLOSED','PARTIALLY_REFUNDED','REFUNDED') | NO | PENDING | MUL | — |
| fulfillment_status | enum('PENDING','PROCESSING','FULFILLED','FAILED','REVOKED') | NO | PENDING | — | — |
| paid_attempt_id | char(32) | YES | — | MUL | 被业务接受的收款；额外收款单独退回 |
| request_key | varchar(64) | NO | — | — | — |
| request_hash | char(64) | NO | — | — | — |
| lock_version | bigint(20) unsigned | NO | 0 | — | — |
| expires_at | datetime(3) | NO | — | — | — |
| paid_at | datetime(3) | YES | — | — | — |
| closed_at | datetime(3) | YES | — | — | — |
| created_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |
| updated_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | on update CURRENT_TIMESTAMP(3) |

## payment_attempts

每次渠道下单；超时先查询；允许记录意外重复实收

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |
|---|---|---|---|---|---|
| id | char(32) | NO | — | PRI | — |
| order_id | char(32) | NO | — | MUL | — |
| channel | enum('WECHAT_NATIVE') | NO | — | MUL | — |
| merchant_id | varchar(32) | NO | — | — | — |
| app_id | varchar(64) | NO | — | — | — |
| out_trade_no | varchar(32) | NO | — | — | — |
| transaction_id | varchar(64) | YES | — | — | — |
| status | enum('CREATING','PENDING','UNKNOWN','CLOSING','SUCCESS','CLOSED','FAILED') | NO | CREATING | MUL | — |
| active_order_id | char(32) | YES | — | UNI | STORED GENERATED |
| expected_fen | bigint(20) unsigned | NO | — | — | — |
| paid_total_fen | bigint(20) unsigned | YES | — | — | 渠道amount.total；必须匹配应付 |
| payer_total_fen | bigint(20) unsigned | YES | — | — | 优惠券后实付，不用于代替total验单 |
| refunded_fen | bigint(20) unsigned | NO | 0 | — | — |
| refund_reserved_fen | bigint(20) unsigned | NO | 0 | — | — |
| currency | char(3) | NO | CNY | — | — |
| code_url | text | YES | — | — | 二维码链接，非支付成功凭证 |
| expires_at | datetime(3) | NO | — | — | — |
| paid_at | datetime(3) | YES | — | — | — |
| closed_at | datetime(3) | YES | — | — | — |
| last_queried_at | datetime(3) | YES | — | — | — |
| next_query_at | datetime(3) | YES | — | — | — |
| error_code | varchar(64) | YES | — | — | — |
| error_message | varchar(1000) | YES | — | — | — |
| created_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |
| updated_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | on update CURRENT_TIMESTAMP(3) |

## payment_notifications

可信通知收件箱；验签失败不可占用合法notification_id

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |
|---|---|---|---|---|---|
| id | char(32) | NO | — | PRI | — |
| channel | enum('WECHAT_NATIVE') | NO | — | MUL | — |
| merchant_id | varchar(32) | NO | — | — | — |
| notification_id | varchar(128) | NO | — | — | — |
| event_type | varchar(64) | NO | — | — | — |
| payment_attempt_id | char(32) | YES | — | MUL | — |
| resource_no | varchar(64) | YES | — | — | out_trade_no或out_refund_no |
| body_sha256 | char(64) | NO | — | — | — |
| payload_redacted | json | YES | — | — | 只存验签通过且脱敏后的排错字段 |
| status | enum('RECEIVED','PROCESSED','RETRY','REJECTED') | NO | RECEIVED | MUL | — |
| receive_count | int(10) unsigned | NO | 1 | — | — |
| last_error | varchar(1000) | YES | — | — | — |
| received_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |
| last_received_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |
| processed_at | datetime(3) | YES | — | — | — |

## refunds

申请和渠道成功分开；退款中的金额占用额度

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |
|---|---|---|---|---|---|
| id | char(32) | NO | — | PRI | — |
| order_id | char(32) | NO | — | MUL | — |
| payment_attempt_id | char(32) | NO | — | MUL | — |
| out_refund_no | varchar(32) | NO | — | UNI | — |
| channel_refund_id | varchar(64) | YES | — | — | — |
| request_key | varchar(64) | NO | — | — | — |
| request_hash | char(64) | NO | — | — | — |
| amount_fen | bigint(20) unsigned | NO | — | — | — |
| currency | char(3) | NO | CNY | — | — |
| status | enum('REQUESTED','PROCESSING','UNKNOWN','SUCCESS','CLOSED','FAILED') | NO | REQUESTED | MUL | — |
| reason | varchar(500) | NO | — | — | — |
| requested_by_user_id | varchar(191) | YES | — | MUL | 空表示系统退款；系统操作另记审计 |
| error_message | varchar(1000) | YES | — | — | — |
| next_query_at | datetime(3) | YES | — | — | — |
| succeeded_at | datetime(3) | YES | — | — | — |
| created_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |
| updated_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | on update CURRENT_TIMESTAMP(3) |

## entitlement_grants

订单履约凭证及额度批次；同一权益不能发放两次

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |
|---|---|---|---|---|---|
| id | char(32) | NO | — | PRI | — |
| user_id | varchar(191) | NO | — | MUL | — |
| order_id | char(32) | NO | — | MUL | — |
| benefit_key | varchar(64) | NO | credits | — | — |
| kind | enum('CREDITS','MEMBERSHIP','GAME_ACCESS') | NO | CREDITS | — | — |
| target_game_id | char(32) | YES | — | MUL | — |
| status | enum('ACTIVE','REFUND_HOLD','REVOKED','EXPIRED') | NO | ACTIVE | — | — |
| units_granted | bigint(20) unsigned | NO | — | — | — |
| units_available | bigint(20) unsigned | NO | — | — | — |
| units_reserved | bigint(20) unsigned | NO | 0 | — | — |
| units_consumed | bigint(20) unsigned | NO | 0 | — | — |
| units_revoked | bigint(20) unsigned | NO | 0 | — | — |
| starts_at | datetime(3) | NO | — | — | — |
| expires_at | datetime(3) | YES | — | — | — |
| revoked_at | datetime(3) | YES | — | — | — |
| metadata_json | json | YES | — | — | — |
| created_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |
| updated_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | on update CURRENT_TIMESTAMP(3) |

## credit_reservations

冻结额度后启动任务；成功核销，确定失败释放

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |
|---|---|---|---|---|---|
| id | char(32) | NO | — | PRI | — |
| user_id | varchar(191) | NO | — | MUL | — |
| job_id | char(32) | NO | — | MUL | — |
| operation_key | varchar(64) | NO | — | — | 同一job的首次生成/不同重生成操作独立计费 |
| units | bigint(20) unsigned | NO | — | — | — |
| status | enum('RESERVED','CAPTURED','RELEASED') | NO | RESERVED | — | — |
| active_job_id | char(32) | YES | — | UNI | STORED GENERATED |
| pricing_snapshot | json | NO | — | — | — |
| settled_at | datetime(3) | YES | — | — | — |
| created_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |

## credit_allocations

一次消费可占多个额度批次；支持退款溯源

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |
|---|---|---|---|---|---|
| reservation_id | char(32) | NO | — | PRI | — |
| grant_id | char(32) | NO | — | PRI | — |
| user_id | varchar(191) | NO | — | — | — |
| units | bigint(20) unsigned | NO | — | — | — |

## credit_ledger

只追加，禁止改历史流水；与批次余额在同一事务

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |
|---|---|---|---|---|---|
| id | bigint(20) unsigned | NO | — | PRI | auto_increment |
| event_key | varchar(191) | NO | — | MUL | — |
| grant_id | char(32) | NO | — | MUL | — |
| reservation_id | char(32) | YES | — | MUL | — |
| user_id | varchar(191) | NO | — | MUL | — |
| action | enum('GRANT','RESERVE','CAPTURE','RELEASE','REVOKE','EXPIRE') | NO | — | — | — |
| delta_available | bigint(20) | NO | — | — | — |
| delta_reserved | bigint(20) | NO | — | — | — |
| delta_consumed | bigint(20) | NO | — | — | — |
| delta_revoked | bigint(20) | NO | — | — | — |
| available_after | bigint(20) unsigned | NO | — | — | — |
| reserved_after | bigint(20) unsigned | NO | — | — | — |
| consumed_after | bigint(20) unsigned | NO | — | — | — |
| revoked_after | bigint(20) unsigned | NO | — | — | — |
| created_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |

## draft_asset_usages

草稿对确切素材文件的引用；发布时冻结为asset_usages

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |
|---|---|---|---|---|---|
| job_id | char(32) | NO | — | PRI | — |
| user_id | varchar(191) | NO | — | MUL | — |
| logical_path | varchar(512) | NO | — | PRI | — |
| asset_file_id | char(32) | NO | — | MUL | — |
| usage_role | varchar(32) | NO | — | — | — |
| created_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |
| updated_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | on update CURRENT_TIMESTAMP(3) |

## generation_job_events

生成任务状态与错误历史；generation_jobs保存当前快照

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |
|---|---|---|---|---|---|
| id | bigint(20) unsigned | NO | — | PRI | auto_increment |
| job_id | char(32) | NO | — | MUL | — |
| event_type | varchar(32) | NO | — | — | — |
| status | varchar(64) | YES | — | — | — |
| phase | varchar(64) | YES | — | — | — |
| message | text | YES | — | — | — |
| metadata_json | json | YES | — | — | — |
| created_at | datetime(3) | NO | CURRENT_TIMESTAMP(3) | — | — |

