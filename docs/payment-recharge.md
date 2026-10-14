# 积分欠费与微信充值

## 当前行为

- 每次预扣后，账户可用余额必须 ≥ -15；全部任务共享额度，用户行锁串行化预扣。
- 成功按实际量核销，剩余退回；明确失败释放预扣。原有注册赠送仍只到账一次。
- CREDIT_LINE 批次从 0 开始记账，不发放免费积分、不到期。真实积分批次优先使用，短缺才计入欠费批次。
- 余额为全部有效批次的净额。例如 -10 分充值 100 分，余额为 90 分。原欠费和充值批次均保留，便于追溯。
- 账户浮窗中的“充值”进入 `/recharge`。页面显示服务端有效档位、微信二维码、订单状态与最近 20 条充值记录；刷新页面可以恢复未完成订单。
- 同一请求键返回同一订单；同账号只允许一个未完成订单。二维码不是支付成功凭据。
- 回调验签、解密并核对商户、订单、币种、金额后，支付成功状态、订单状态、积分权益、积分流水和通知去重在同一事务提交。
- 页面每 5 秒查询订单；后端最多每 5 秒向微信查单一次。签名查单可补偿丢失的回调。超时或网络故障保留订单，不能推断付款失败。
- 30 分钟订单到期后，先经微信关单/查询确认，再关闭本地订单。支付与关单竞态通过微信结果和本地事务处理；真实迟到付款仍可入账。

## 上线步骤

本次没有修改共享数据库结构、创建正式产品或真实支付订单。上线前必须完成以下配置。

这是首次启用支付，没有邀请码用户、历史订单或历史余额需要搬迁。下文 SQL 文件的 migration 指数据库表结构版本调整：此前建好的积分表不允许负数，需要在首次启用欠费前扩展字段类型。邀请码身份不会转换为付款账户；充值仍要求 NarrativeOS 登录。

1. 检查目标库表结构：若缺少 source/source_key 等字段，先执行 `credit_system/migrations/001_grant_sources.sql`；已存在则跳过，不能重复执行。已有积分表执行 `002_credit_overdraft.sql`，扩展来源类型，并将批次可用余额与流水余额快照改为有符号整数。这是结构准备，不搬迁邀请码用户或业务数据；全新空库也可直接按最终结构初始化。对已有共享库先备份；结构准备完成后再部署新的积分预扣代码。MySQL DDL 有隐式提交，不能依赖事务回滚。
2. 在 `products` 中创建正式 `CREDIT_PACK` 档位：32 位十六进制 ID、唯一 sku、名称、人民币 `price_fen` 整数分、`currency='CNY'`、`benefit_json={"schema_version":1,"credits":整数}`。先设 DRAFT，确认价格后改为 ACTIVE。页面从数据库读取，不接受浏览器指定金额或到账积分。不附带示例售价，避免误上线。
3. 配置 `.env.example` 中的 `WECHATPAY_*` 项。私钥与微信支付公钥放在服务端只读目录，生产 Compose 的 `WECHATPAY_KEYS_DIR_HOST` 挂载到 `/run/secrets/wechatpay`；文件须可被容器 appuser 读取。不要提交 PEM 或密钥。
4. 确认微信普通商户号已开通 Native 支付，AppID 与商户号关联；公网 HTTPS 回调指向实际部署基路径的 `/api/forge/payments/wechat/notify`，代理保留原始请求体和 Wechatpay 签名头，不要求用户登录。`WEBGAL_FRONTEND_URL` 要与实际站点 origin 一致。
5. 构建并更新 backend/frontend 镜像。后端镜像已加入 `wechatpay_native`，requirements 加入本地 QR 编码库；前端增加支付接口转发。`WECHATPAY_ENABLED` 默认 false，配置和正式验收准备好后设 true 并重建/重启后端进程。
6. 完成受控实付验收：扫码、支付回调、订单 FULFILLED、只到账一次、重复通知、刷新恢复、欠费抵扣。再检查正式档位后开放给用户。

## 补偿与核对

### 年付按月到账

年付 Creator 为 899 元、每月 600 积分；年付 Pro 为 2700 元、每月 2500 积分（折合 225 元/月）。
付款确认时只发首月额度，同时创建 `subscription_credit_schedules`；其余 11 个月在付款日期的月度周年日到账。
遇到月底日期（例如 1 月 31 日）时，短月份使用该月最后一天，下个月恢复原始日号，不按固定 30 天递推。
积分发放及月份进度在同一事务提交，并使用订单与月份作为唯一来源键，重复回调或多进程不会重复发放。
后端每分钟检查一次；查看余额和发起积分预扣时也会补发已到期的月份。停机期间的遗漏在恢复后补发。
订单进入退款或撤销状态时停止后续月份的发放。积分到期策略仍未启用。

部署新后端前执行新增的 `credit_system/migrations/003_subscription_credit_schedules.sql`，这是新增发放计划表，不搬迁用户。
新增两档一次性加速体验包：16.9 元/100 积分、139 元/1000 积分；这两档不受月付/年付切换影响。

用户关闭页面后回调仍会到账。可在后端容器执行一次有界补偿：

```sh
python -m webgal_backend.reconcile_payments
```

每次最多处理 100 条待查询订单，通过微信签名查单确认到账或到期关单。应在部署环境安排周期执行；本次未创建定时任务。金额核对、账单下载对账、退款审批和退款到账仍需后续接入；当前页面不提供退款功能。

检查积分守恒时须使用更新后的 `docs/database-plan/05_consistency_checks.sql`。有符号欠费余额与无符号已消耗等字段相加，需要显式 CAST，避免 MySQL 无符号溢出。

## 验证

```sh
python -m pytest tests/test_payment_api.py tests/test_wechatpay_native.py tests/test_credit_system.py tests/test_credit_billing.py tests/test_credit_api.py -q
# 可选：连接配置数据库，但只创建连接级 TEMPORARY TABLES；不修改真实表、数据或支付配置。
CREDIT_MYSQL_TEST=1 python -m pytest tests/test_payment_credit_mysql.py -q
```

临时 MySQL 表测试覆盖 -15 边界、跨任务共享额度、部分结算、释放、重复结算、充值抵扣欠费、重复通知/查单、金额篡改回滚、迟到支付恢复。API 测试使用本地生成的密钥验证真签名/篡改通知，但不连接微信生产支付。

协议参考：[微信支付 Native 下单](https://pay.wechatpay.cn/doc/v3/merchant/4012791877)、[普通支付回调说明](https://pay.wechatpay.cn/doc/v3/merchant/4012791861)。


## 私人真实支付测试

入口 `/payment-test/` 不加入导航。数据库 `users.is_tester` 为独立 tester 权限标记，默认 0；只有明确授予此角色的 SSO 账号可使用。保留原有 USER/ADMIN 角色。其他用户访问测试 API 返回 404。部署前执行 `credit_system/migrations/005_user_tester_role.sql`，不使用测试环境变量。

隐藏产品 SKU `forge-private-payment-test-v1` 保持 DRAFT，固定 1 分人民币 / 1 积分；普通套餐列表不会返回，普通下单接口不能购买。测试下单请求仅接受 request_key，价格、积分与产品 ID 全部由服务端固定。真实交易由本人点击创建订单并微信扫码，测试代码不能代替真实验收。

页面复用正式下单、二维码、订单查询、关闭订单、入账逻辑，并显示验签回调、积分 grant 与 GRANT 流水证据。主动查询确认支付不能证明回调已接通。完成测试后将对应账号的 `users.is_tester` 设为 0 即可立即关闭测试权限，无需重启后端；历史订单和流水保留。

公网回调必须部署到配置中的实际 URL。本地后端主动查询可以验证支付与入账，但无法替代公网回调部署及验收。
