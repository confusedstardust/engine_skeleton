# 修复历史教师资源广场链接

新发布的互动作品通过 `webgal_backend/work_urls.py` 自动带上 `/narrativeos`
前缀（如果 `WEBGAL_FRONTEND_URL` 只配置了域名）。**历史广场目录中的
`playUrl` 已被另一服务持久化，代码部署不会自动改写这些旧链接。**

本仓库提供可审计的管理员命令（不会在请求或部署启动时自动运行）：

```bash
# 在 backend 的实际部署环境中先预览改动，默认不写任何数据
python -m webgal_backend.work_links_backfill --frontend-url http://43.138.207.82

# 确认环境、相关作品的原始作者信息和备份之后显式执行
python -m webgal_backend.work_links_backfill --frontend-url http://43.138.207.82 --execute

# 如果目录中的链接已正确，但广场仍然记录旧 URL：
python -m webgal_backend.work_links_backfill --frontend-url http://43.138.207.82 \
  --work-id <32字符作品ID> --force --execute
```

只处理确认为已发布的作品，远端必须提供原作者姓名，避免把原作者
改成通用作者名；单作品可以显式传入 `--author-name`。
先向广场重新提交正确的 `playUrl` 与 `coverUrl`，成功后才更新
本地的原有发布记录。操作不修改作品的已发布版本，也不触碰私人草稿。

如果操作失败会跳过本地更新，可检查目标环境的
`TEACHER_ECOSYSTEM_API_URL` / `TEACHER_ECOSYSTEM_SERVICE_TOKEN`
以及远端的 `publication_status` 响应后重试。

**没有对用户服务器执行此命令。** 此步骤需要在服务端检查部署状态和
远端数据归属后实施，不能只靠 CI 推断历史链接已经修复。
