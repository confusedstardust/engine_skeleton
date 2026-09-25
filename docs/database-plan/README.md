# NarrativeOS 数据库实施包

日期：2026-09-24（于9月23日开始核对）。输入：`C:/Users/Eden/Downloads/STRUCT_narrativeos.pdf`（2 页）、当前 Forge 分支 `feature/assetrepo`、本地认证项目的 Prisma schema。

**已确认需求：购买生成次数／积分包；作品、任务、素材、支付和社区互动全部要求正式用户登录。**

交付包含数据库设计、DDL、事务说明，以及素材库的后端接入和前端页面。没有连接或修改线上 RDS；素材库需完成本文配置和迁移后才会启用。

## 先读什么

先看 [全部25张表的ER图与整体逻辑](ER_LOGIC.md)，可编辑图源为 [OVERALL_ER.mmd](OVERALL_ER.mmd)。没有将验证码、迁移表或outbox的应用关联伪画成外键。

1. [PLAN.md](PLAN.md)：现状、20 张新表的职责、现有表补充、分期实施、接口、数据迁移和验收。
2. [TRANSACTIONS.md](TRANSACTIONS.md)：支付、退款、扣额度、发布和点赞的锁、幂等及伪代码。
3. [DATA_DICTIONARY.md](DATA_DICTIONARY.md)：由本次实测数据库导出的业务表逐字段字典。

## SQL 执行顺序

| 文件 | 用途 | 是否执行 |
|---|---|---|
| `00_preflight.sql` | 只读核对版本、字符集、主键、外键、表名冲突 | 必须先检查输出；它不会自动替你阻断后续脚本 |
| `01_content.sql` | 9 张内容与任务基础表，含事务事件表 | 首期内容功能 |
| `06_asset_library.sql` | 素材来源键、查询索引和草稿素材引用表 | 素材库功能，紧跟 01 执行 |
| `07_database_job_store.sql` | 任务原文和任务状态历史 | 数据库任务状态，紧跟 01 执行 |
| `02_commerce.sql` | 6 张商品、订单、收款、通知、退款、权益表 | 首期支付功能，依赖 01 |
| `03_credit_usage.sql` | 3 张额度冻结、分摊、流水表 | 本次确认卖额度，必须随支付上线，依赖 01+02 |
| `04_auth_additions_optional.sql` | 修改现有用户、会话、验证码表 | 与认证服务协调单独发布；不要直接套到未知结构 |
| `05_consistency_checks.sql` | 只读一致性核对与告警查询 | 上线验收和定时核对 |

**20 张新业务表分阶段接入，不要求一次性开发完全部功能。** `draft_asset_usages` 固定草稿实际引用的文件版本，`generation_job_events` 保存任务状态历史，其余18张承载内容、支付和额度；评论、推荐、订阅、创作者分账等未提前建表。

## 使用边界

- 基线是 PDF 的 5 张表。其中 `_prisma_migrations` 不做任何手工修改；测试夹具只重建其余 4 张业务认证表。
- DDL 使用现有 `users.id VARCHAR(191)`、`utf8mb4_unicode_ci`，新业务 ID 用应用生成的 32 位 UUID hex。线上 collation 未连接核实，必须先跑预检；不一致时先调整 DDL 引用列，不要直接转换生产用户主键。
- 使用 JSON、生成列、3072 字节索引能力，最低按本次实测 MySQL 5.7.44 配置；不代表建议新采购 5.7。线上实际版本与配置未知，需要同版本预发布环境复验。
- `01`–`04` 是**单次迁移**，故意不用 `IF NOT EXISTS` 掩盖结构冲突；不要重复执行。失败可能留下已成功的前序 DDL，不可直接整包重跑。
- `01`–`03` 只新建业务表并增加新表之间的外键，不改原 5 表。`04` 才涉及现有认证字段和索引。
- 不直接运行 `DROP`、`TRUNCATE` 或 `migrate reset` 回滚业务；先关闭新入口，保留财务记录，再前向修复。
- 迁移必须进入已有 Prisma 6 的统一迁移历史，或明确独立 schema 的负责人；不要让 Prisma 与 Alembic 同时管理这批表。本文建议统一由 Prisma 管 DDL，Python 通过 SQLAlchemy/PyMySQL 读写业务数据。

预发布可在已选定数据库的 MySQL 交互客户端执行：

```sql
SOURCE C:/SelfCreated/MyProject/workwithflynt/engine_skeleton/docs/database-plan/00_preflight.sql;
-- 人工确认预检、备份及迁移历史后，在预发布库演练：
SOURCE C:/SelfCreated/MyProject/workwithflynt/engine_skeleton/docs/database-plan/01_content.sql;
SOURCE C:/SelfCreated/MyProject/workwithflynt/engine_skeleton/docs/database-plan/07_database_job_store.sql;
SOURCE C:/SelfCreated/MyProject/workwithflynt/engine_skeleton/docs/database-plan/06_asset_library.sql;
SOURCE C:/SelfCreated/MyProject/workwithflynt/engine_skeleton/docs/database-plan/02_commerce.sql;
SOURCE C:/SelfCreated/MyProject/workwithflynt/engine_skeleton/docs/database-plan/03_credit_usage.sql;
-- 04 单独协调发布，不包含在上面三步中。
SOURCE C:/SelfCreated/MyProject/workwithflynt/engine_skeleton/docs/database-plan/05_consistency_checks.sql;
```

生产环境应执行审核后的迁移发布流程，不把上面的手动演练和 Prisma migration 重复执行。现有库已有迁移历史，不需要重新 baseline；只有接管手动建表或历史缺失时才按 Prisma 对应版本处理。

## 启用本次素材库实现

1. 安装后端依赖：`pip install -r requirements.txt`。
2. 按上面的顺序迁移数据库，至少完成 `01_content.sql`、`07_database_job_store.sql` 和 `06_asset_library.sql`；登录用户必须已经存在于 `users`。
3. 配置 `WEBGAL_OSS_BUCKET`、`WEBGAL_OSS_ENDPOINT`、`WEBGAL_OSS_PREFIX`、`OSS_ACCESS_KEY_ID`、`OSS_ACCESS_KEY_SECRET`。当前 Bucket 为公共读时设置 `WEBGAL_OSS_ACCESS_MODE=public`；改成私有读时设置 `private`，并用 `WEBGAL_OSS_SIGNED_URL_TTL` 控制素材库预览签名有效期。
4. 配置 `NARRATIVEOS_DATABASE_URL`。先执行旧任务迁移，再设置 `WEBGAL_DATABASE_JOB_STORE_ENABLED=true` 和 `WEBGAL_ASSET_LIBRARY_ENABLED=true`，最后重启 Forge 后端。
5. 登录后访问 `/assets`。公共模式返回固定 OSS URL，发布时会把场景脚本中的背景、立绘、头像、BGM、音效和语音引用改成固定 URL，并写入 `state/oss_game_manifest.json`；私有模式只为素材库预览生成短期签名，不把临时签名写进游戏脚本。AI 产物标记 `GENERATED`，用户上传及后续抠图、头像裁剪修订标记 `UPLOADED`。

公共读模式还需在 OSS 设置 CORS：生产环境允许实际游戏域名和前端域名，开发环境按需增加 `http://127.0.0.1:3001` 与 `http://127.0.0.1:8010`；允许 `GET`、`HEAD` 和 `Range` 请求，暴露 `ETag`、`Content-Length`、`Content-Range`、`Accept-Ranges`、`Last-Modified`。公共 URL 可绕过应用登录直接访问，不能用于需要保密的素材。

历史任务先预览数量，再显式执行回填：

```powershell
python scripts/migrate_file_jobs_to_database.py
python scripts/migrate_file_jobs_to_database.py --execute
python scripts/backfill_asset_library.py
python scripts/backfill_asset_library.py --execute
```

启用数据库 JobStore 后，`generation_jobs` 是当前任务状态权威，`generation_job_events` 保存状态和错误历史，`games` 保存作品身份；job 目录只保留场景、图片、音频和诊断文件，不再写 `job.json`。旧 `job.json` 保留作迁移前快照，不参与运行时读取。迁移工具只处理正式 SSO 用户任务，邀请码历史任务会列入 `skipped_non_sso`，不会伪造用户归属。`draft_asset_usages` 已建表供冻结草稿引用，目前应用尚未写入它。

## 本次验证

详见 [VALIDATION.json](VALIDATION.json)。本机 MySQL 5.7.44、独立临时数据目录、随机本机回环端口；测试结束已关闭该实例。包含 4 张认证测试表 + 20 张新表，共 24 张表。没有重建 `_prisma_migrations`。

复验命令（需要本机 MySQL 5.7 Windows 安装；仅标准 Python 库）：

```powershell
python docs/database-plan/verify_mysql.py --mysql-bin 'C:\Program Files\MySQL\MySQL Server 5.7\bin'
```

脚本不会读取 `.env`、连接 RDS 或访问现有数据库服务；临时数据目录保留用于检查。验证范围包括建表、外键、唯一键、SQL 状态操作，以及数据库 JobStore 的创建、读取、列表、状态更新和乐观锁集成；**不包含支付/OSS 联调、真实并发压测、业务鉴权或生产数据回填**。
