# 平台管理

入口：前端 `/admin`，支持独立管理员或服务器明确配置的 SSO 用户。

## 使用看板

ECharts 按需加载折线图和柱状图，支持最近7／30／90天、手动刷新与分页每日明细。日期按北京时间聚合。

任务数来自 generation_jobs；已完成任务按创建日期归组，以数据库当前登记状态为准。发起用户为创建任务或发起计费生成操作的去重账号，不是登录DAU；新增用户来自 users。

Token、图片和语音字符仅统计 CAPTURED 结算记录 pricing_snapshot.settlement.usage，按 settled_at 归组。Token 总量为输入加输出，缓存Token是输入子集，不重复相加。失败、未结算及历史未记录的用量不计入，页面显示记录覆盖情况。积分仅汇总 credit_ledger 中 CAPTURE 的 delta_consumed，不把预冻结当作扣费。该指标表示平台积分，不是供应商人民币成本。

当前项目数据库时间为 Asia/Shanghai；查询将数据库会话时间转换为 UTC+8。部署时须保证 DATETIME 写入与数据库时区一致；仅修改服务器时区不能修复历史混用时间。

- 游戏：搜索、分页、下架和恢复。下架拦截本平台播放和公共作品接口，保留任务和文件；不撤回外部教师平台发布记录或已下载副本。
- 素材：缩略图、改名、停用和恢复。停用影响新选用，保留 OSS 文件及已发布作品引用。
- 用户：搜索、改昵称、禁用和恢复本平台访问，保留统一登录账号及历史数据。管理员账号保存在 users 表，platform_role=ADMIN；普通账号默认 USER。
- 改名和状态操作与 `platform_admin_audit` 审计记录在同一事务中写入。

部署时先执行 `docs/database-plan/08_platform_admin.sql` 和 `09_admin_user_account.sql`（先检查物理列，勿重复添加）。管理员账号使用 users.username 登录；password_hash 保存 scrypt N=16384,r=8,p=1 的 salt_hex:digest_hex，禁止保存明文密码。权限由 users.platform_role 决定，管理员不再使用环境变量名单、密码或会话密钥。

会话复用 auth_sessions，浏览器仅保存随机 token，数据库仅保存 SHA-256 token_hash，有效期 8 小时。HttpOnly、SameSite Strict，HTTPS 启用 Secure；退出删除当前会话。每次请求重新检查 ADMIN 权限及禁用状态，降权或禁用即时拒绝会话。写接口要求 X-Forge-Admin-Action:1，不向外站开放带凭据 CORS。

登录限流为每个连接地址5分钟内5次尝试，当前保存在进程内。多个后端副本应使用网关或共享存储补充限流。

前端包含 `/api/forge/admin/:path*` 转发规则；更改环境或转发规则后重启服务。当前配置仅在本地生效，生产服务须另外部署代码及环境变量。用户／作品限制由数据库中的 platform_resource_controls 决定。

管理员公共上传：支持图片与音频、类型分类和多选标签，单文件上限 30 MB。记录来源 UPLOADED、可见性 PUBLIC；使用无登录凭据的 platform-public-assets 归属账号保存，实际操作者记入审计。用户可以浏览、收藏后选用；普通用户不能删除平台归属文件。停用仅修改数据库状态，不删除 OSS 文件。


## 用户订阅管理

用户列表点击用户名或“查看详情”，可查看账号信息、当前订阅和有效期。管理员可设置 Free / Creator / Pro / School；非 Free 必须填写未来的到期时间，所有调整必须填写原因。

部署时需执行 `credit_system/migrations/004_admin_subscription_overrides.sql`，只新增管理覆盖表，不修改历史订单或余额。调整与操作审计在同一事务提交，并通过 revision 防止管理员之间覆盖修改。有效管理订阅参与重复购买拦截；后续成功购买可以覆盖此前的管理配置。

本功能只管理订阅身份，不扣款、不自动发放或回收积分，不更改已付款年付订单的积分发放计划。
