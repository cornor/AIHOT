# 游戏研发情报部署

服务器 `/opt/gamehot` 使用本目录的 Compose 配置，宿主机 Nginx 提供 HTTPS，HTTP 自动跳转。证书使用 `/etc/nginx/ssl/paoyou.com.pem` 与 `paoyou.com.key`。

```bash
cd /opt/gamehot
docker compose --env-file .env -f deploy/gamehot/compose.yaml up -d --build
docker compose --env-file .env -f deploy/gamehot/compose.yaml ps
docker compose --env-file .env -f deploy/gamehot/compose.yaml logs --tail 100 worker collector
bash deploy/gamehot/backup.sh
```

私有配置为 `.env`、`private/werss.env`，数据保存在 `private/`。两者不进入 Git 和镜像构建上下文。模型密钥仅供后端使用。

WeRSS 入口：`https://gamehot.paoyou.com/werss/`。先登录站点管理员，再登录 WeRSS，进入微信读书页面扫码。采集器通过内部回环地址访问 RSS，每轮之后等待 4 小时；首次启动没有计划记录时立即执行一轮，后续重启沿用持久化的计划。

扫码成功且凭据通过验证、保存后，WeRSS 在 `private/collector-events/weread.json` 写入不含凭据的事件编号；collector 只读该目录，每 5 秒检查本地事件。如果采集已到期，约 5 秒内补采一轮；尚未到期则保留原计划。同一次扫码不会重复触发，采集串行执行。授权失效或任务中断不会推迟原来的到期时间，常规失败重试仍间隔 4 小时；新的扫码事件可以提前唤醒已经到期的重试。此机制不做定时联网授权探测，也不会自动打开已关闭的采集开关。手动填写 Cookie 不属于扫码事件。

计划保存在 `private/app-data/collector-schedule.json`，包含到期、重试时间及已消费的事件编号；通知投递失败仍约 15 分钟重试。部署时先创建 `private/collector-events`（目录 755），WeRSS 可写、collector 只读；事件文件只有随机编号，权限 644。扫码保存事件失败会在 WeRSS 日志中提示，原有定时采集不受影响。

临时最新单篇模式：服务器 `.env` 设置 `WERSS_LATEST_ONLY=true`，重建 WeRSS 和 collector 容器使其同时生效；`COLLECT_ENABLED=true` 启用采集。每个公众号每轮只读取最新一篇，重复文章跳过，不保证补齐两轮之间的其他文章。正文和真实发布时间来自微信读书返回的原文 HTML，缺失时报告失败，不使用采集时间代替发布时间。每轮飞书概况注明覆盖范围。默认 `WERSS_LATEST_ONLY=false` 使用文章列表；列表失败不会悄悄切换为单篇模式。

本站用于公司内部，`nginx-locations.conf` 对全站执行读者或管理员访问校验，资讯、RSS、API 和 MCP 均不对外匿名开放。WeRSS 也始终要求管理员会话。使用者已明确无需公开条款与隐私文案确认。

更新前执行备份，构建固定版本后停稳 worker 和 collector，再运行 setup 并启动各服务。回退时先停止处理，保存服务器新增数据，再恢复匹配版本和备份；只允许一端运行采集和模型任务。

备份包含 PostgreSQL、WeRSS SQLite、文件及私有配置，每日运行并保留最新 7 份。恢复 PostgreSQL 时使用空库；还原对应文件，重新扫码验证 WeRead 授权。备份目录不得公开。

## 采集飞书通知

在服务器 `.env` 配置 `FEISHU_COLLECTOR_ENABLED=true` 和 `FEISHU_COLLECTOR_WEBHOOK_URL`（机器人地址是凭据，不进入 Git）。这两个变量只传给后端采集器；不启用逐篇精选推送或原有飞书应用通知。

- 每轮采集结束，发送公众号成功/失败数、WeRSS 抓取数、RSS 新增/更新数、失败信源和耗时。摘要异步生成，采集通知不表示模型处理已完成。失败的单个信源可能已写入部分文章，抓取数仅统计成功返回的信源。
- 仅在采集开始时用书架接口检查登录凭据；采集出现失败后再核验一次，捕获采集中途失效。采集关闭或两轮之间不检查授权。明确的 `-2012` / `-2010` 才判定授权失效；网络失败和 `-2041` 不提示“已过期”。未配置凭据时提醒首次扫码。授权失效首次发现时提醒，之后每天最多提醒一次，下次采集确认恢复后通知一次；恢复授权不自动打开采集开关。
- 通知状态和待发送消息持久化在 `private/app-data/collector-notices.json`，失败约 15 分钟后重试，容器重启后保留。飞书业务码必须为 0 才记为成功。网络超时可能导致重复投递，通知编号可用于核对。
- 采集轮次串行运行，下一轮在上一轮结束 4 小时后开始。进程或整机停机时无法自行通知，需要独立监控。

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

`werss/weread_mp.py` 来源于 [rachelos/we-mp-rss](https://github.com/rachelos/we-mp-rss) 提交 `126993c81a00466e9a6bbab041eef34ab27abe9c`；本地修改移除了只用封面信息生成文章的回退，增加显式启用、读取正文真实日期的最新单篇模式。MIT 许可证保存在 `werss/LICENSE`。离线验证可在该镜像内使用 `/app/env_x86_64/bin/python3 -m unittest discover -s /tests -p 'test_*.py'`，把 `werss/` 只读挂载到 `/tests` 并使用 `--network none`。

## 低频运维通知

宿主机 `gamehot-monitor.timer` 每 10 分钟执行一次只读检查，独立于 Docker 和 worker。复用私有飞书机器人配置；不访问微信读书授权接口、不调用模型、不自动修改服务。

检查 Docker、Nginx、备份 cron、六个容器健康、HTTPS 入口、数据库查询、worker 心跳、DeepSeek 调用失败、文章处理积压、备份和磁盘空间。模型调用失败须最近一次成功后累计至少 3 次失败，且之后没有成功回执；不会因为一段时间没有新请求就宣称恢复。文章处理异常阈值是至少 10 篇等待超过两小时或至少 3 篇处理失败；磁盘 90% 起提醒。worker 心跳先以 20 分钟未更新判异常，再经过持续异常确认。

采集检查读取 collector 容器实际的 `COLLECT_ENABLED` 和数据库同步时间。开关关闭会报告“采集已暂停”；开关开启但超过 8 小时没有启用 WeRSS 信源成功同步，或从未成功同步，会报告同步异常。正常同步但没有新文章不告警。数据库或容器无法查询时不宣称恢复；暂停也不表示旧的同步异常已恢复。这些检查不访问微信读书授权接口。

低频规则：连续观测异常至少 20 分钟才告警；同一问题每 24 小时最多重复一次，反复恢复/失败也不绕过此限制。多个问题和恢复合并成一条，运维通知之间至少间隔 6 小时（包括发送失败后的重试）；正常时不发日报。恢复也需至少 20 分钟健康观测，且只对已通知的问题发送。新的故障可能因全局间隔延后通知。这些限制不改变原有每 4 小时一轮的采集概况和采集时才执行的授权检查。

备份脚本互斥执行，成功须验证 PostgreSQL 备份目录、SQLite 完整性和文件包可读取，记录在 `private/backup-status.json`；失败保留最近成功时间。最近备份失败或超过 30 小时没有成功记录会告警。仅清理带 `completed` 标记的旧备份，保留最新 7 份；早期无标记快照保留，避免误删。

状态持久化在 `private/ops-monitor-state.json`。机器人地址只在私有配置，不进入日志、通知正文或 Git。

```bash
install -m 644 deploy/gamehot/gamehot-monitor.service /etc/systemd/system/
install -m 644 deploy/gamehot/gamehot-monitor.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now gamehot-monitor.timer
systemctl start gamehot-monitor.service
systemctl list-timers gamehot-monitor.timer
journalctl -u gamehot-monitor.service -n 20 --no-pager
```

整台主机关机、断网或监控自身停掉时，无法从这台主机发送即时提醒；这需要另行配置独立外部监控。宿主机正常时，即使 Docker 或业务容器停掉，此监控仍可发送提醒。

公司登录配置、权限开通及回退步骤见 [SSO 运维说明](../../docs/gamehot-sso.md)。
