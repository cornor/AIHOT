# 游戏研发情报：部署记录

日期：2026-10-08。状态：服务已部署，微信读书扫码授权及首轮实时采集待完成。

## 访问和运行状态

- 网站：`http://gamehot.paoyou.com`。
- 管理员后台：`http://gamehot.paoyou.com/admin`。
- WeRSS：`http://gamehot.paoyou.com/werss/`。
- 微信读书扫码页：`http://gamehot.paoyou.com/werss/weread`。
- 公司内部使用：资讯、RSS、API、MCP 和 WeRSS 均要求站点管理员会话；WeRSS 另保留自己的管理员登录。
- 按使用者要求先提供 HTTP。HTTPS 证书已申请并配置续期，暂未启用 443 或强制跳转。

服务器为 Ubuntu 26.04、x86_64，约 2 GB 内存、2 GB 交换空间。使用现有 Nginx，项目位于 `/opt/gamehot`，Docker Compose 项目名为 `gamehot`。

数据库、API、网页、worker、WeRSS、collector 六个常驻服务已运行；数据库、API、网页和 WeRSS 健康检查通过。对外监听 HTTP 80 和原有 SSH 22；3000、8001 仅绑定回环地址，数据库没有发布宿主机端口。Docker 已设置开机启动，常驻容器配置异常重启与日志轮转。

worker 已启用正常模型任务。collector 已部署，当前 `COLLECT_ENABLED=false`，等待扫码后启用。启用后逐个处理 11 个信源，每轮结束等待 30 分钟。

## 迁移和检查

迁移快照与恢复后的数量一致：307 篇文章、356 条分析记录、12 条信源记录（其中 11 条启用）、1,746 条付费回执。WeRSS 的 11 个订阅与 344 条原始文章记录已迁移。中国音数协游戏工委继续停用。

技术精选新标准和取消 DeepSeek 本地次数限制均已保留；付费回执机制保持有效。服务器验证 DeepSeek 密钥认证成功，模型列表包含 `deepseek-flash`；该检查未生成内容。

已完成的验证：

- 类型检查、570 项后端测试及新增的 2 项登录返回地址测试、31 项网页测试、网页构建。
- 本机与服务器的站点冒烟检查，包括页面、RSS、API 和 MCP。
- HTTP 登录、返回 WeRSS、未登录访问资讯与数据接口被拒绝，登录后可读取。
- 浏览器实际登录及资讯页面显示；WeRSS 登录、微信读书子页面直接打开与刷新。
- WeRSS 的 14 个前端资源、原生 RSS、阅读页、文档页、导出下载及 WebSocket。
- 微信读书二维码生成与图片读取；手机确认授权尚未完成。
- 修复 WeRSS 子路径静态资源问题，并关闭上游启动时输出全部环境变量的行为；启动日志不包含配置的密码和签名密钥。

本机 worker 和 collector 已停止，本机网页及 API 保留读取已有数据；本机 `.env` 的采集及模型调用开关已关闭，避免双端处理。

## 版本和维护

代码仓库为使用者 fork `cornor/AIHOT`，分支 `codex/game-news-rss`。应用镜像 `gamehot-app:4b97c66` 的应用代码来自提交 `4b97c66`；后续变更为部署配置及 WeRSS 补丁。WeRSS 基础镜像固定为：

`ghcr.io/rachelos/we-mp-rss@sha256:af771f21b3f7958a5dea16911fba050a6d7b92eac2fb2499c467c1b11f07ef34`

部署时因服务器镜像与依赖下载较慢，在本机构建 amd64 应用并传送；WeRSS 使用该固定 amd64 镜像、与其源码一致的本机前端构建产物及仓库补丁，镜像名为 `gamehot-werss:4b97c66`。具体服务配置和操作命令见 [部署说明](../deploy/gamehot/README.md)。

私有管理员凭据已保存在使用者本机的 `.data/deployment/private/credentials.md`，不进入 Git。服务器私有配置为 `/opt/gamehot/.env` 和 `/opt/gamehot/private/werss.env`，文件权限为 600。

每天北京时间 04:00 执行备份，保留最近 7 份，备份位置为 `/opt/gamehot/private/backups/`。已生成两份快照，并把首份 PostgreSQL 备份恢复至独立临时库，验证文章、分析与回执数量后删除该临时库；WeRSS SQLite 完整性检查通过，11 个订阅可读。

## 尚需完成的扫码与采集

1. 打开 WeRSS 入口，按本机私有凭据先登录站点，再登录 WeRSS。
2. 打开 `/werss/weread`。如出现“感谢支持”窗口，点右上角 × 关闭，无需支付。
3. 点击绿色“扫码授权”，用手机微信扫描此时生成的登录二维码，并确认微信读书网页版登录。
4. 使用者告知“已授权”后，验证真实文章列表和正文；启用服务器 collector，逐个记录 11 个信源的采集结果。
5. 验证一条新文章经 RSS 入库、DeepSeek 处理、摘要展示的完整链路；无新文章时记录去重与处理服务状态，等待实际新增。

目前已部署服务不等于微信读书已授权；在完成上述步骤前，不宣称实时采集已恢复。
