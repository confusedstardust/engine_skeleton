# 可上传课堂工具：沙箱能力适配

2026-11-06：已实现与本地验证，尚未部署。

包内可选 `narrativeos-resource.json` 的 capabilities 只接受 print、png-export、microphone。上传及替换资源包时校验并存入 metadata.json；没有 manifest 时能力列表为空，替换成普通包会移除之前的能力。

播放页保留不透明来源 sandbox，不增加 allow-same-origin。print 仅为声明该能力的资源在 iframe 和文件 CSP 中加入 allow-modals。PNG 在宿主校验 SVG 白名单与外部引用后转换，限制 2 MB SVG 和 1000 万像素；只响应当前资源 iframe 的消息。

麦克风由宿主代理：必须是当前资源声明能力，且用户点击宿主确认按钮后才调用 getUserMedia。只向隔离 iframe 发送 RMS 功率数值、授权后的设备列表与停止状态，不发送原始音频；停止、后台、离开和重载时释放。无数据上传。

部署后才能完整支持 linchangWeb teaching-resources 工程构建的奖状和音量灯 ZIP。无需数据库迁移。普通上传资源没有新增权限。

验证：56 项 HTML 资源/封面测试；standalone_resources.browser.py 使用临时目录和临时服务，不依赖真实用户或数据库，覆盖四个 ZIP 上传、背诵随机化、诗词作答、PNG 下载、A4 两页 PDF、恶意 SVG 拒绝、麦克风确认/合成音频输入/停止释放、下架/重发布。实体麦克风与 Safari 未验证。
