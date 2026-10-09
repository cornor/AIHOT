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

## 采集飞书通知

在服务器 `.env` 配置 `FEISHU_COLLECTOR_ENABLED=true` 和 `FEISHU_COLLECTOR_WEBHOOK_URL`（机器人地址是凭据，不进入 Git）。这两个变量只传给后端采集器；不启用逐篇精选推送或原有飞书应用通知。

- 每轮采集结束，发送公众号成功/失败数、WeRSS 抓取数、RSS 新增/更新数、失败信源和耗时。摘要异步生成，采集通知不表示模型处理已完成。失败的单个信源可能已写入部分文章，抓取数仅统计成功返回的信源。
- 每 15 分钟用书架接口检查登录凭据，采集关闭时也检查。明确的 `-2012` / `-2010` 才判定授权失效；网络失败和 `-2041` 不提示“已过期”。未配置凭据时提醒首次扫码。授权失效首次发现时提醒，之后每天最多提醒一次，恢复后通知一次；恢复授权不自动打开采集开关。
- 通知状态和待发送消息持久化在 `private/app-data/collector-notices.json`，失败约 15 分钟后重试，容器重启后保留。飞书业务码必须为 0 才记为成功。网络超时可能导致重复投递，通知编号可用于核对。
- 采集轮次串行运行，下一轮在上一轮结束 4 小时后开始。较长采集会推迟授权检查；进程或整机停机时无法自行通知，需要独立监控。

通知逻辑的离线测试：`python3 -m unittest discover -s deploy/gamehot -p 'test_*.py'`。所有外部请求使用替身。

部署接通测试（会向配置的群真实发送一条通知；先停止常驻 collector，避免同时写通知状态）：

```bash
docker compose --env-file .env -f deploy/gamehot/compose.yaml stop collector
docker compose --env-file .env -f deploy/gamehot/compose.yaml run --rm --no-deps collector python3 deploy/gamehot/collector.py --notify-test
docker compose --env-file .env -f deploy/gamehot/compose.yaml up -d --no-deps collector
```

## WeRSS 补丁来源

固定运行镜像：`ghcr.io/rachelos/we-mp-rss@sha256:af771f21b3f7958a5dea16911fba050a6d7b92eac2fb2499c467c1b11f07ef34`。

前端由该镜像中的源码重建，`patch-ui.mjs` 适配 `/werss/`，`patch-backend.py` 设置 ASGI root path。

`werss/weread_mp.py` 来源于 [rachelos/we-mp-rss](https://github.com/rachelos/we-mp-rss) 提交 `126993c81a00466e9a6bbab041eef34ab27abe9c`；本地修改移除了只用封面信息生成文章的回退，避免伪造发布日期。MIT 许可证保存在 `werss/LICENSE`。
