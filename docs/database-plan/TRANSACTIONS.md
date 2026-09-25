# 服务事务与失败恢复规范

这些是实现模板，`:name` 为驱动绑定参数，不是直接粘贴执行的SQL。调用方必须执行标出的分支、回滚和状态检查；仅执行DDL不会自动获得支付、权限或余额正确性。

## 1. 统一约束

- 数据库连接使用UTC、严格模式、InnoDB；ID由服务生成，用户ID只从可信会话取。日期展示时再转本地时区。
- 凡涉及同用户的付款履约、退款、额度冻结/结算，首期先 `SELECT id FROM users WHERE id=:user_id FOR UPDATE` 作为该用户额度操作的串行入口。它会短暂阻塞同一用户的其他写入，规模增大再拆专用锁行。
- 后续固定锁顺序：用户→业务订单（多个按ID）→payment_attempt→job→reservation→grant（多个按ID）→outbox；不得在另一路径反向拿锁。不涉及的行跳过。
- 批次选择策略可按最早到期排序，但实际加锁按ID一致排序；锁后重新检查可用数量和有效期。余额不足全事务回滚，不留下半个reservation。
- 网络请求和AI生成不在数据库事务内；deadlock/lock timeout整个事务按有上限退避重试，沿用同一业务幂等键。
- DDL无触发器。金额/余额守恒和状态转换由业务服务实现：不能允许其他代码随意 UPDATE 这些列。
- 禁用不加区分的 `INSERT IGNORE` 与 `REPLACE INTO`；唯一键冲突应判断具体约束并读取已有记录，不能吞掉类型错误、截断或引用错误。
- 各种 `*_fen`、额度数量、quantity都要有正值及业务上限，计算不得溢出；额度单批及累计操作限制在有符号BIGINT可表达范围内，因为ledger delta是有符号数。

## 2. 幂等下单

读取ACTIVE商品，校验kind仅CREDIT_PACK，服务端解析benefit版本。将 `product_id + quantity + accepted_product_revision` 规范化后哈希。事务中锁/核对商品版本，插入订单完整快照。

`UNIQUE(user_id, request_key)` 冲突时返回已有订单；如果 request_hash 不同则409。不能因后来产品涨价，把同一幂等请求变成第二张订单。

金额必须满足：

```text
quantity > 0
total_fen = snapshot.unit_price_fen * quantity
0 <= discount_fen <= total_fen
payable_fen = total_fen - discount_fen > 0
currency = CNY
```

首期不开放商户优惠券时固定 discount_fen=0；渠道优惠引起payer_total减少不改业务订单应付。0元赠送不是本支付下单接口，后续单独设计可审计发放来源。

创建payment_attempt时锁订单，检查订单未支付/未关闭/未到期，并复用已有active_attempt。生成一个6–32位、符合现有 `OUT_TRADE_NO_RE` 的唯一out_trade_no，提交后调用渠道。由订单金额生成expected_fen，不接受前端金额。

调用成功后按条件把CREATING/UNKNOWN更新PENDING并保存code_url；如果回调已经把它变SUCCESS，不能倒退覆盖。调用失败按“明确未创建”与“结果未知”区分，UNKNOWN先用原号查询。

## 3. 支付回调与主动查单共用结算函数

1. 回调用**原始body字节**验签、校验时间戳及密钥标识，解密并识别事件；不要重序列化JSON后再验签。
2. 验证成功后按(channel, merchant_id, out_trade_no)找payment；读取订单归属以确定用户锁。未知订单保存脱敏异常线索、告警，不创建任意用户权益。
3. 验签失败只进入受限安全日志，不向可信notification表插入攻击者给的notification_id，以免占住合法通知键。
4. 开事务按统一锁顺序锁user、order、payment，再插入/读取notification。只有已有status=PROCESSED且与原业务匹配时才直接成功；RETRY/RECEIVED继续处理。
5. 核对payment与order金额、币种、商户、AppID、渠道交易类型；payment.expected_fen也必须等于order.payable_fen。
6. 若payment已SUCCESS，要求transaction_id和金额与已存一致，幂等返回；不同渠道交易号不能覆盖旧值，应告警调查。
7. 把真实交易事实写入payment.SUCCESS、paid_total_fen、payer_total_fen、paid_at；不可仅用状态字符串代替交易唯一号。
8. 订单还没有paid_attempt_id且允许履约：设置paid_attempt_id、PAID、paid_at，并 `INSERT outbox(event_key='order-paid:'+order_id)`。
9. 如果订单接受了另一笔付款：保留这笔payment.SUCCESS，写独立事件 `duplicate-payment:<payment_id>` 供退款，不重复发权益。已本地关闭但渠道实收的情况也必须走明确的补偿策略。
10. notification置PROCESSED，提交成功后回复渠道成功。事务失败则不回成功，由通知重试/查单补偿。

主动查单也必须验签渠道响应并核对相同字段，调用同一个 `settle_verified_payment()`，幂等的业务键是payment和transaction_id，不能依赖存在notification_id。

## 4. 权益发放

outbox worker消费ORDER_PAID，先锁user、order、被接受的payment、相关grant。

- order非已支付、正常付款不是SUCCESS：拒绝发放并告警。
- 正常付款存在REQUESTED/PROCESSING/UNKNOWN退款：延后发放，等待退款结果。
- 正常付款已全额退款：将履约标REVOKED，不再发放。
- 查 `UNIQUE(order_id,benefit_key)`，已存在且发放完整则幂等成功。
- 根据订单快照固定计算units，创建grant；同时插GRANT流水、设置fulfillment_status=FULFILLED、标事件DONE。全部同事务提交。

首次grant：available=granted，其余计数0。GRANT流水delta_available=granted，其余delta0。不能先加余额、提交、再写发放记录。

如果worker仅支持不同数据库的独立事务，不能靠这段同库事务假设，必须另行引入消费去重记录和补偿。本轮建议共用业务MySQL。

## 5. 额度冻结、消费、释放

### 5.1 冻结与任务入队

```sql
START TRANSACTION;
SELECT id FROM users WHERE id=:user_id FOR UPDATE;
SELECT id, owner_user_id, status, lock_version
FROM generation_jobs WHERE id=:job_id FOR UPDATE;
-- 检查归属；同job不能同时启动另一项未结算操作。
SELECT * FROM credit_reservations
WHERE job_id=:job_id AND operation_key=:operation_key FOR UPDATE;
-- 已存在：验证报价/请求内容后返回原结果，不新扣。
-- 读取候选grants，按固定ID顺序锁定并再次计算可用总数。
SELECT * FROM entitlement_grants
WHERE user_id=:user_id AND kind='CREDITS' AND status='ACTIVE'
ORDER BY id FOR UPDATE;
-- 在锁内排除starts_at未到、expires_at已过、余额为0的批次。
INSERT INTO credit_reservations
(id,user_id,job_id,operation_key,units,pricing_snapshot)
VALUES(:reservation_id,:user_id,:job_id,:operation_key,:units,:pricing_snapshot);
-- 对每个被选批次：
UPDATE entitlement_grants
SET units_available=units_available-:take, units_reserved=units_reserved+:take
WHERE id=:grant_id AND user_id=:user_id AND kind='CREDITS'
  AND status='ACTIVE' AND units_available>=:take
  AND starts_at<=UTC_TIMESTAMP(3)
  AND (expires_at IS NULL OR expires_at>UTC_TIMESTAMP(3));
-- 必须影响1行，否则全事务回滚。
INSERT INTO credit_allocations(reservation_id,grant_id,user_id,units)
VALUES(:reservation_id,:grant_id,:user_id,:take);
-- 追加RESERVE流水：delta_available=-take, delta_reserved=take，其余0；保存四项after余额。
-- 更新job为QUEUED，CAS条件包含原lock_version；写outbox事件，payload含reservation_id与operation_key。
COMMIT;
```

首期用户额度批次数有限，可直接锁该用户全部有效批次；大规模再分页选批次并保持固定锁序。每次锁内重新计算，不能拿事务外的“余额显示值”来授权。

### 5.2 成功核销

用户→job→reservation→grants固定顺序锁。确认reservation为RESERVED，job操作和worker fencing token匹配，且本次承诺的可用生成产物已经持久化：

```text
每个allocation：reserved -= units；consumed += units
CAPTURE流水：delta_reserved=-units，delta_consumed=units
reservation.status=CAPTURED，settled_at=now
同事务记录本次操作终态，不能先标job成功再丢失扣费结果
```

CAPTURED再次收到成功消息直接返回；RELEASED收到迟到成功消息属于执行冲突，不能再次免费产出/强行补扣，必须告警并阻断旧worker发布。

### 5.3 失败释放

同样锁序，确认该操作已终止且旧租约失效：reserved-=units，available+=units，写RELEASE，reservation=RELEASED。已到期额度不能恢复可消费状态：改入revoked并写对应过期流水。

心跳丢失只能触发恢复判断，不直接视为可退；供应商超时请求可能已执行，必须依据provider请求标识/产物与作业租约决策。系统重试保持operation_key，用户主动再生成使用新key。

### 5.4 额度流水口径

| action | available | reserved | consumed | revoked |
|---|---:|---:|---:|---:|
| GRANT | +N | 0 | 0 | 0 |
| RESERVE | -N | +N | 0 | 0 |
| CAPTURE | 0 | -N | +N | 0 |
| RELEASE | +N | -N | 0 | 0 |
| REVOKE/EXPIRE 未用额度 | -N | 0 | 0 | +N |

示例：买10点→冻3点→成功扣3点，四项依次是 `10/0/0/0`、`7/3/0/0`、`7/0/3/0`。退款不删除旧GRANT流水；它追加REVOKE并更新批次。

## 6. 全额退款与重复付款补偿

### 正常订单

请求退款：锁user→order→accepted payment→grants；必须全包未使用且未冻结，检查 `paid_total_fen - refunded_fen - refund_reserved_fen >= requested_amount`。余额守恒/资格/所有权全部满足后：

```sql
UPDATE payment_attempts
SET refund_reserved_fen=refund_reserved_fen+:refund_fen
WHERE id=:payment_id AND status='SUCCESS'
  AND paid_total_fen >= refunded_fen + refund_reserved_fen + :refund_fen;
-- 影响1行；新增refund REQUESTED，grant状态REFUND_HOLD；写refund-requested事件；COMMIT。
```

渠道调用失败/超时不会自动释放refund_reserved_fen；先确认退款结果。相同request_key异参返回409；重试沿用out_refund_no。

成功通知/查退款：锁相同行，退款已经SUCCESS则幂等返回；否则验证渠道退款号、原交易、金额和币种，refund_reserved-=amount、refunded+=amount；撤销该订单权益并写REVOKE流水；订单状态REFUNDED、fulfillment=REVOKED。服务必须确保预占存在，不允许无预占直接减成负数。

明确失败：释放该笔预占；若没有其他在途退款，取消REFUND_HOLD。若从未发权益，重新触发order-paid履约重试。不要重新插入一个已DONE的同名outbox事件并以为会重试，需要显式重新排队/新补偿事件键。

退款amount按渠道订单金额口径，不把payer_total当商户退款上限；优惠涉及的现金/代金券退回由渠道规则决定。超过首期整包规则的部分退款仅后台人工处理，不能复用全包撤销代码。

### 意外重复收款

若payment不是order.paid_attempt_id，对该额外payment创建全额退款；只调整该payment的退款累计值，不把正常订单置REFUNDED，也不撤销正常grant。失败进入人工告警，保持每条实收可追溯。

## 7. 点赞/收藏与计数

以点赞为例：事务内锁game，校验该登录用户能访问作品；PUT查询关系，不存在才INSERT并 `like_count=like_count+1`，存在直接成功；DELETE真正删除一行才减计数。所有同game写路径使用这一锁序。

不要用toggle：网络重试两次会变回原状。不要用“客户端读到count=9，然后写10”，否则并发丢失更新。减计数时如果缓存已0但有关系删除，应记录漂移，不能让无符号数下溢；定时按事实表核对修正。

收藏同样实现。关系表允许其他用户对公开作品操作，**不能**加“点赞人必须等于作者”的错误外键；访问范围靠服务检查。计数修复需要锁game，与在线关系修改遵循同一顺序，不能用不一致的快照覆盖并发更新。

## 8. 发布与文件引用

给每个发布请求预生成稳定version_id，由客户端/服务重试复用；先锁game分配version_no，不能无锁 `MAX(version_no)+1`。版本已存在则核对source_job、draft_revision与构建参数一致，异参409。

构建阶段用唯一前缀写文件。文件上传完成后开启短事务：锁game、version以及所有拟引用asset_files（按ID排序），检查READY及授权，写usages和manifest，提交。READY版本的内容字段、manifest和usages不再修改，重新生成新version。

切换当前版本时锁game→version→必要文件，校验审核和状态，条件更新lock_version。数据库复合外键保护版本属于该game，状态规则仍需应用层完成。

**草稿引用的限制**：本版asset_usages只存候选/发布版本引用，正在编辑的草稿仍在任务manifest里。首期禁用自动物理垃圾回收，只做逻辑软删除；否则复用到另一草稿但尚未形成版本的文件可能误删。启用GC前必须增加草稿引用登记表或把所有草稿文件映射迁移到可事务查询的引用结构，并让编辑、发布和GC统一锁文件。不能仅凭asset_usages计数为0就删OSS。

## 9. outbox及任务租约

MySQL5.7不依赖SKIP LOCKED。首期单调度器或使用短事务的 `SELECT ... ORDER BY ... LIMIT 1 FOR UPDATE` 抢一条事件，写随机lease_token及截止时间后提交，事务外执行网络动作。

```sql
START TRANSACTION;
SELECT id FROM outbox_events
WHERE status='PENDING' AND available_at<=UTC_TIMESTAMP(3)
ORDER BY available_at,id LIMIT 1 FOR UPDATE;
-- 有记录时：
UPDATE outbox_events
SET status='PROCESSING',lease_token=:token,
    lease_expires_at=DATE_ADD(UTC_TIMESTAMP(3),INTERVAL 60 SECOND),attempts=attempts+1
WHERE id=:event_id AND status='PENDING';
COMMIT;
```

完成标记必须 `WHERE id=:id AND status='PROCESSING' AND lease_token=:token`。租约回收重置过期事件到PENDING，超过次数进DEAD；事件消费者用领域唯一键幂等，不能认为拿到事件一次就实现exactly-once。

生成任务租约同理；长任务定期续期，写回比较token和lock_version。过期worker即使返回了结果也不能发布/结算。外部供应商调用是否可安全重复由其请求幂等能力决定；不具备时保存受限的请求记录并人工/查询确认，不盲目重复付费调用。
