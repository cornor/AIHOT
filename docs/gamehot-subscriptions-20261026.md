# 2026-10-26 公众号订阅名单核对

使用者提供表格并要求加入订阅、去重。按公众号唯一标识去重，忽略英文大小写；已有 GameRes游资网、游戏那点事Gamez、TapTap发现好游戏、GameLook 等不重复添加。

## 已核实新增

服务器使用现有微信读书授权读取 `/api/mp/cover`，返回的账号名称与下列账号一致，且最新文章 reviewId 前缀匹配 feedId。此验证确认账号身份和最新文章入口，不代表文章正文、RSS 导入或摘要已完成。新账号沿用 T2、摘要和原文链接展示，不开放全文转载。

| 公众号 | 站点信源 ID | WeRSS 唯一标识 | 核验时最新文章原文 |
| --- | --- | --- | --- |
| GameQuest | `werss-gamequest` | `MP_WXS_3945841861` | [原文](https://mp.weixin.qq.com/s/HwkprOmSzNNElXJJtXEnpQ) |
| en的游戏时光 | `werss-en-games` | `MP_WXS_3949878376` | [原文](https://mp.weixin.qq.com/s/1NHcu3tJ3m_ZUiu2D5OI9w) |
| 龙虾游戏推荐 | `werss-longxia` | `MP_WXS_3541060043` | [原文](https://mp.weixin.qq.com/s/ZAXkewtPl_E4AgV2ID_sUg) |
| 游讯先锋 | `werss-youxun` | `MP_WXS_3964100586` | [原文](https://mp.weixin.qq.com/s/DSPnly8qniNvUjpOquOZiQ) |
| 橙了个橘 | `werss-chengle` | `MP_WXS_3988974300` | [原文](https://mp.weixin.qq.com/s/BGWN6mFv0S284HHzjpGWSA) |
| 竞核 | `werss-jinghe` | `MP_WXS_3902648252` | [原文](https://mp.weixin.qq.com/s/NizHvNjrT9srmIoYnJmciQ) |
| 游戏研究社 | `werss-yystv` | `MP_WXS_3237377160` | [原文](https://mp.weixin.qq.com/s/qzrO3WCa3tmqVvcc8lW1EA) |
| 网易雷火UX用户体验中心 | `werss-leihuo-ux` | `MP_WXS_3583880550` | [原文](https://mp.weixin.qq.com/s/5UJqra-bPOeLb9j6_82o8w) |
| indienova | `werss-indienova` | `MP_WXS_2392229767` | [原文](https://mp.weixin.qq.com/s/8QhAiPCIjUbfqBLUdPl3ig) |
| 游民星空 | `werss-gamersky` | `MP_WXS_2399051562` | [原文](https://mp.weixin.qq.com/s/uc6tw_9454voINfxZcZIwg) |
| 游戏动力 | `werss-youxidongli` | `MP_WXS_3566781352` | [原文](https://mp.weixin.qq.com/s/akaaXjBymLCIKezccABYMg) |
| 白鲸出海 | `werss-baijing` | `MP_WXS_3635921266` | [原文](https://mp.weixin.qq.com/s/V0Kx9ohI4D6UR75ujx3njQ) |
| 机核 | `werss-gcores` | `MP_WXS_2399032840` | [原文](https://mp.weixin.qq.com/s/oD0snMAn40TolGS1f2ydwQ) |

## 去重与名称差异

- 游戏葡萄、游戏新知、游戏茶馆、GameRes（GameRes游资网）、游戏那点事（游戏那点事Gamez）、游戏陀螺、TapTap发现好游戏、GameLook，以及 DataEye游戏观察已存在，保留原记录。
- `gamelook` / `Gamelook`、`taptap发现好游戏` / `TapTap发现好游戏`、`dataeye游戏观察` / `DataEye游戏观察` 按同一账号处理。
- “DataEye数据观察”未找到独立账号证据，暂按已有“DataEye游戏观察”理解，已请使用者提供文章链接（如指另一个号）。没有为不确定名称新建虚构订阅。
- 竞核使用当前 `MP_WXS_3902648252`，不添加搜索索引里的旧号 `MP_WXS_3259025259`；旧号 cover 名称为空。
- 白鲸出海使用当前 `MP_WXS_3635921266`，不添加 `MP_WXS_3075486737`（cover 名称明确为“账号已迁移”）。

## 使用者确认暂时跳过

| 用户名称 | 当前情况 |
| --- | --- |
| 引力引擎 | 公开材料称“引力引擎科技”，尚未取得可靠唯一标识 |
| 七麦数据 | 官网同时列出“七麦数据”和“七麦研究院”两个公众号；不直接合并到已订阅的七麦研究院 |
| 腾讯GWB游戏无界 | 腾讯官网有历史账号名及 gwboffcial 微信号，尚未取得可靠唯一标识；不直接替换成腾讯游戏学堂 |
| 游鲨游戏圈 | 已找到历史原文短链，但尚未解析出可靠唯一标识 |

使用者回复“先跳过这几个，继续进行”。以上四个不加入本次采集名单；“DataEye数据观察”也不另建账号，已有 DataEye游戏观察继续保留。若后续需要添加，再凭原文链接核实。

## 身份查找来源

公开目录与历史索引只用于寻找候选标识，最后使用微信读书返回名称核实：

- [游戏研究所 pro 公开公众号目录](https://ai.xianjianwendao.com/kb/accounts)及其公开作者列表中的原文链接。
- [网易雷火 UX 历史索引](https://freewechat.com/profile/MzU4Mzg4MDU1MA%3D%3D)、[游民星空历史索引](https://freewechat.com/profile/MjM5OTA1MTU2Mg%3D%3D)。
- [七麦官网](https://www.qimai.cn/andapp/downTotal/appid/9093670)页脚分别列出两个公众号。
- [腾讯游戏学堂历史文章](https://gwb.tencent.com/community/detail/133832)列出“腾讯GWB游戏无界”、微信号及原文链接。

每日北京时间 09:00 定时采集和扫码成功后的额外采集保持不变。微信公众号仍使用最新单篇模式，新增订阅不代表能够补齐历史文章。

## 部署结果

已在服务器 WeRSS 创建 13 个订阅，在站点 sources 表创建对应 13 个启用信源，collector 使用 `gamehot-app:sources-20261026` 读取全部 36 个去重订阅。新增记录标记等待首次采集；13 个 RSS 地址均返回合法 XML，当前文章数为 0，尚未触发文章导入及模型处理。采集计划及已消费扫码事件在部署前后完全一致，下一次定时仍为 2026-10-27 09:00（北京时间）；新扫码会额外触发一轮。

发布前备份 `private/backups/20261026-112229` 校验成功。服务器隔离测试库的 typecheck、迁移、584 项后端测试、前端构建及 34 项前端测试通过；生产内网 smoke 全部通过。仅重建 collector，其他服务保持运行。本次真实请求只用于核实账号入口与本机 RSS，没有进行额外整轮采集或测试飞书推送。

## 补充：收到四个原文链接后核实

使用者补充链接后，已读取文章发布账号及 `biz`，并在服务器通过微信读书 cover 接口二次核实，四个名称和唯一标识均匹配。此前的跳过决定不再适用于以下账号；七麦数据与七麦研究院为不同唯一标识，各自保留。

| 公众号 | 站点信源 ID | WeRSS 唯一标识 | 使用者提供的原文 |
| --- | --- | --- | --- |
| 引力引擎 | `werss-gravity` | `MP_WXS_3921683971` | [原文](https://mp.weixin.qq.com/s/NCR65YwfCOs3E-XeBw8TYw) |
| 游鲨游戏圈 | `werss-yousha` | `MP_WXS_3574816669` | [原文](https://mp.weixin.qq.com/s/khS7vF_v22veD-ayhpeicQ) |
| 腾讯GWB游戏无界 | `werss-tencent-gwb` | `MP_WXS_3080799890` | [原文](https://mp.weixin.qq.com/s/ojDSfPGqFf3l79n2JR7rnw) |
| 七麦数据 | `werss-qimai-data` | `MP_WXS_3204016236` | [原文](https://mp.weixin.qq.com/s/C7oWVmbHEFBUNquMIUNAJg) |

新增账号沿用上一批的 T2 配置、摘要及原文链接展示。提供的文章用于核实身份，不作为要求回补历史的指令。原始请求曾返回环境验证页，使用正常浏览器及带浏览器 User-Agent 的服务器请求可读取文章元数据，没有修改微信读书凭据。
