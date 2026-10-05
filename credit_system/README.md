# 积分系统核心模块

该目录只负责积分账户与订单权益，不依赖 FastAPI 页面，也不会自动接入工作台。
它按 `DDL_narrativeos_dev.sql` 中已有的 `products`、`purchase_orders`、
`entitlement_grants`、`credit_reservations`、`credit_allocations` 和
`credit_ledger` 表工作。

首次使用前需执行 `migrations/001_grant_sources.sql`。原始 DDL 强制所有权益
绑定订单，无法正确表达“注册赠送”；迁移把权益来源明确拆成订单、活动赠送和
管理员赠送，避免伪造零元已支付订单。

## 稳定调用入口

```python
from credit_system import CreditService

credits = CreditService.from_env()

# 用户已写入 users 表后调用；可重复调用，只会到账一次。
credits.ensure_signup_credits(user_id)

balance = credits.get_balance(user_id)

# 文件任务准备调用模型前，先登记为可计费任务并冻结积分。
credits.ensure_billable_job(
    user_id=user_id,
    job_id=job_id,
    source_material=source_material,
    options=options,
)
reservation = credits.reserve_for_game(
    user_id=user_id,
    job_id=job_id,
    operation_key="initial-generation-v1",
    units=estimated_hold,
    pricing_snapshot=quote,
)

try:
    run_generation()
except DefiniteGenerationFailure:
    credits.release(reservation.reservation_id)
    raise
else:
    # 仅核销实际使用量，其余冻结积分在同一事务中退回。
    credits.capture(reservation.reservation_id, units=actual_units, settlement=usage_detail)
```

支付回调经过验签、金额和本地订单校验，并已在本地事务中把订单置为 `PAID`
以后，再调用：

```python
credits.fulfill_paid_order(order_id)
```

## 约束

- 注册赠送使用 `PROMOTION + signup-credits:v1` 唯一来源键，不创建虚假支付订单。
- 所有扣减均先冻结；成功核销，明确失败释放。超时或结果不确定时不要直接释放。
- 冻结额度由文本、图片和 TTS 选项动态组成；结算依据供应商 Token usage、成功图片数和实际 TTS 字符数。
- 系统不使用历史字符数冒充 Token；供应商没有返回 usage 的文本调用不会被估算扣费。
- 价格由服务端 `CREDIT_*` 环境变量控制，并随冻结和结算快照保存，浏览器不能指定价格。
- 同一个 `job_id + operation_key` 是幂等操作；换参数复用会报冲突。
- 消费按最早到期批次优先，并允许一次消费拆分到多个批次。
- 余额与只追加流水在同一个 MySQL 事务内更新，并通过 `FOR UPDATE` 防止并发超扣。
- 本模块不接受浏览器传入的价格、积分数或用户归属作为可信数据。

配置项见项目根目录 `.env.example`。优先使用服务端的
`NARRATIVEOS_DATABASE_URL`；也兼容独立的 `CREDIT_DB_*` 配置。生产环境应配置
`CREDIT_DB_SSL_CA`，数据库账号仅授予所需表的最小权限。连接串中的密码如含
URL 保留字符，应先做 percent-encoding，并且绝不能发送给浏览器。
