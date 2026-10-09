# 游戏研发情报：公司 SSO 与 HTTPS

访问地址为 https://gamehot.paoyou.com ，公司登录按钮位于 `/admin/login`。原管理员密码作为备用入口保留。WeRSS 入口为 `/werss/`，要求本站管理员权限，进入后仍需 WeRSS 自身登录及微信读书授权。

## 登录与权限

1. 本站生成有效期 10 分钟的一次性登录请求，与当前浏览器 HttpOnly cookie 绑定。
2. 跳转至 `https://account.xmpaoyou.com/sso?url=...`，回调地址为 `https://gamehot.paoyou.com/sso/callback?state=...`。
3. SSO 返回临时 token。独立回调页立即清除地址栏查询参数，将 token 和 state 同源 POST 至后端。
4. 后端以表单 POST 至 `https://account.xmpaoyou.com/api/sso/check-token` 校验。必须业务码为 0 且返回有效 account，才继续本地权限判断。
5. 以不可变的 account 作为唯一身份，只保存 account、姓名及权限；不保存公司 token、手机号或微信身份。本站另发随机的 8 小时会话，数据库仅存会话 hash。Cookie 为 HttpOnly、SameSite=Lax，生产使用 Secure。
6. 读者可浏览资讯及数据接口；管理员可操作后台和访问 WeRSS。每次请求检查账号当前状态。停用、改角色或重新保存权限均撤销该账号所有已有本站会话。管理写操作要求 CSRF token，权限修改记录审计。

`SSO_ENABLED=true` 才启用公司登录。默认 `SSO_ALLOW_ALL=false`：新账号首次成功验证公司身份后会记为“未开通”，无法访问资讯。管理员进入 **后台 → 账号与权限**，填写准确 account、选择读者或管理员、勾选允许访问、填写原因并保存；也可以提前开通。

仅在业务负责人明确允许全部公司 SSO 账号阅读时，才设置 `SSO_ALLOW_ALL=true`；新账号自动获得读者权限，不会获得管理员权限，已停用账号也不会自动恢复。配置更改后重启 API。

退出仅清理本站会话。公司文档未提供全局退出、离职事件或 token 有效期协议，因此公司账号停用不会自动即时撤销本站已有会话；需在本站停用该账号，或等待最多 8 小时会话到期。本站不推断公司 SSO 返回的 account 天然属于有阅读资格的员工。

## HTTPS 与日志

Nginx 使用 `/etc/nginx/ssl/paoyou.com.pem` 和 `/etc/nginx/ssl/paoyou.com.key`，后者权限 600。现有证书覆盖 `*.paoyou.com`，到期时间为北京时间 2027-01-19 07:59:59，续期后 `nginx -t && systemctl reload nginx`。证书文件由运维更新，本次未新增自动续期任务。

HTTP 跳转 HTTPS，HTTP 回调直接返回干净登录入口，避免在重定向中复制 token。HTTPS 回调关闭请求日志、在代理前移除查询参数；独立页面使用 no-store、no-referrer 和 CSP，不加载分析脚本。后端不记录 token、上游身份载荷或带 token 的异常。

API、Web、WeRSS 仅在容器网络或宿主机回环端口开放。Nginx 的 `/_gamehot_site_auth` 只接受有效读者或真实管理员，`/_gamehot_auth` 仅接受管理员；旧 `private/site-access.conf` 不再作为实际访问规则。

## 发布与回退

- 新增兼容迁移 `0042_company_sso.sql`。运行迁移前执行 `bash deploy/gamehot/backup.sh` 并验证成功。
- 应用 `.env` 设置 HTTPS 的 SITE_URL、SSO_ENABLED=true、SSO_ALLOW_ALL=false。不将任何凭据放入前端、Git 或镜像。
- 更新 api/web/worker/collector 应用镜像。`WERSS_VERSION` 可独立固定原生 WeRSS 镜像，避免跟随应用版本构建。
- 修改 Nginx 配置后先 `nginx -t`，成功再 reload。验证 HTTPS 证书、未登录拦截、备用密码登录、SSO 跳转及读者/管理员边界。
- 若应用需回退，先停止 worker/collector，恢复旧应用版本与旧 compose 配置，但保留 HTTPS。旧版不支持公司 SSO，应把全站 auth_request 临时改回管理员校验；使用原管理员密码。不要删除新增表或回滚已有业务数据。涉及恢复备份时先保存发布后新增数据。

本地测试使用独立 `_test` 数据库与合成身份，上游 SSO 请求全部替身化，采集、通知和真实模型调用关闭。实际公司扫码登录需要使用者亲自完成，合成身份测试不代表生产 SSO 端到端登录已验证。
