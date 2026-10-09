# 游戏研发情报部署

服务器 `/opt/gamehot` 使用本目录的 Compose 配置，宿主机现有 Nginx 提供 HTTP。HTTPS 证书已申请，暂不启用强制跳转。

```bash
cd /opt/gamehot
docker compose --env-file .env -f deploy/gamehot/compose.yaml up -d --build
docker compose --env-file .env -f deploy/gamehot/compose.yaml ps
docker compose --env-file .env -f deploy/gamehot/compose.yaml logs --tail 100 worker collector
bash deploy/gamehot/backup.sh
```

私有配置为 `.env`、`private/werss.env`，数据保存在 `private/`。两者不进入 Git 和镜像构建上下文。模型密钥仅供后端使用。

WeRSS 入口：`http://gamehot.paoyou.com/werss/`。先登录站点管理员，再登录 WeRSS，进入微信读书页面扫码。采集器通过内部回环地址访问 RSS，每轮之后等待 4 小时；启动时立即执行一轮。

本站用于公司内部，`private/site-access.conf` 始终包含管理员访问校验，资讯、RSS、API 和 MCP 均不对外匿名开放。WeRSS 也始终要求管理员会话。使用者已明确无需公开条款与隐私文案确认。

更新前执行备份，构建固定版本后停稳 worker 和 collector，再运行 setup 并启动各服务。回退时先停止处理，保存服务器新增数据，再恢复匹配版本和备份；只允许一端运行采集和模型任务。

备份包含 PostgreSQL、WeRSS SQLite、文件及私有配置，每日运行并保留最新 7 份。恢复 PostgreSQL 时使用空库；还原对应文件，重新扫码验证 WeRead 授权。备份目录不得公开。

## WeRSS 补丁来源

固定运行镜像：`ghcr.io/rachelos/we-mp-rss@sha256:af771f21b3f7958a5dea16911fba050a6d7b92eac2fb2499c467c1b11f07ef34`。

前端由该镜像中的源码重建，`patch-ui.mjs` 适配 `/werss/`，`patch-backend.py` 设置 ASGI root path。

`werss/weread_mp.py` 来源于 [rachelos/we-mp-rss](https://github.com/rachelos/we-mp-rss) 提交 `126993c81a00466e9a6bbab041eef34ab27abe9c`；本地修改移除了只用封面信息生成文章的回退，避免伪造发布日期。MIT 许可证保存在 `werss/LICENSE`。
