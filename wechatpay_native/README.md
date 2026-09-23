# 微信支付 Native 核心模块

这是一个与 Forge 工作台完全解耦的 Python 包。它只实现普通商户 APIv3 的核心能力：Native 下单、查单、关单、API 应答验签、支付回调验签与 AES-256-GCM 解密。

## 安全边界

- 只支持微信支付公钥模式（`PUB_KEY_ID_...`），不自动下载或信任未知证书。
- 商户私钥只从文件读取，不接受内联字符串；不要把 PEM、APIv3 密钥提交到 Git。
- 所有微信支付 API 应答先验签，验签通过后才解析和使用正文。
- 回调先校验公钥 ID、时间窗和 RSA-SHA256 签名，再解密正文。
- `total_cents` 必须来自服务端商品/订单数据，绝不能直接采用浏览器提交的金额。校验订单金额时使用回调中的 `amount.total`；`payer_total` 在使用微信支付优惠券后可以更低。
- 回调解密成功不等于可以发货。必须查询本地订单，并调用 `assert_expected_payment` 比较订单号、总额和币种；之后在数据库事务中以 `notification_id` 或 `transaction_id` 建唯一索引，原子地将订单改为已支付。
- 回调处理成功返回 HTTP 200/204；验签或金额校验失败返回 4xx/5xx。不要在日志中记录私钥、APIv3 密钥、Authorization、回调完整明文。
- 微信支付目前没有独立 APIv3 沙箱。开发联调会产生真实交易，建议创建 1 分测试商品并在商户平台完成退款。

## 所需参数

复制 `.env.example` 的变量到部署环境。需要：已绑定的 `appid`/`mchid`、商户 API 证书序列号及私钥、32 字节 APIv3 密钥、微信支付公钥 ID 与公钥文件、外网可访问的 HTTPS 回调地址。

不要在聊天中粘贴私钥或 APIv3 密钥。私钥文件应放在仓库外，只授予运行支付服务的系统账号读取权限。

## 最小用法

```python
from wechatpay_native import WeChatPayClient, WeChatPayConfig, assert_expected_payment

config = WeChatPayConfig.from_env()

async with WeChatPayClient(config) as pay:
    native_order = await pay.create_native_order(
        out_trade_no="ORDER202609230001",
        description="测试商品",
        total_cents=1,  # 单位：分；必须由后端订单确定
    )
    # 将 native_order.code_url 转成二维码展示；code_url 不应被当作支付成功凭证。
```

业务模块通常不需要直接操作底层客户端。创建支付可以只调用一个方法：

```python
from wechatpay_native import create_native_payment

order = await create_native_payment(
    out_trade_no="ORDER202609230001",  # 业务系统生成并持久化的唯一订单号
    description="测试商品",
    total_cents=1,                     # 单位：分；必须来自服务端订单
)

print(order.code_url)  # 交给页面转换成二维码
```

如果同一服务内需要多次调用，推荐创建一个可复用的业务门面：

```python
from wechatpay_native import NativePaymentService

payments = NativePaymentService.from_env()

order = await payments.create_payment(
    out_trade_no="ORDER202609230001",
    description="测试商品",
    total_cents=1,
)

status = await payments.query_payment(order.out_trade_no)
await payments.close_payment(order.out_trade_no)  # 仅限未支付订单
```

支付回调使用同一个门面完成签名、解密、商户身份、订单号和金额核验：

```python
notification = payments.verify_payment_callback(
    headers=request.headers,
    body=await request.body(),
    expected_out_trade_no=local_order.out_trade_no,
    expected_total_cents=local_order.total_cents,
)

# 然后在业务数据库事务中使用 notification.notification_id 和
# notification.transaction.transaction_id 做唯一约束并更新订单。
```

回调入口必须保留原始请求体，不能先反序列化再重新生成 JSON：

```python
notification = pay.parse_payment_notification(headers=request.headers, body=await request.body())
order = await order_repository.get(notification.transaction.out_trade_no)
assert_expected_payment(
    notification.transaction,
    expected_out_trade_no=order.out_trade_no,
    expected_total=order.total_cents,
)
# 在一个数据库事务中去重 notification_id/transaction_id 并更新订单状态。
```

本包刻意不注册 FastAPI 路由、不创建数据库表，也不接入现有工作台。业务系统引用时，应由业务层负责鉴权、服务端定价、订单持久化和回调幂等事务。

## 官方文档

- Native 支付产品与扫码流程：https://pay.wechatpay.cn/doc/v3/merchant/4012791874
- 开发必要参数：https://pay.wechatpay.cn/doc/v3/merchant/4013070756
- 最佳安全实践：https://pay.wechatpay.cn/doc/v3/merchant/4012073699
- Native 下单：https://pay.wechatpay.cn/doc/v3/merchant/4012791877
- 支付成功回调：https://pay.wechatpay.cn/doc/v3/merchant/4012791861
