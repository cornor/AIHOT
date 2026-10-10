// 这个行业的分类体系：类别、标签词表、公司（主体）名录，以及防止张冠李戴的身份词典。
// 模型按这里的词表打标签，主题页（topics.json）按标签归类，筛选栏按类别分组。
// 换行业时：类别的 key 会出现在网址里（/all?category=…），上线后就不要再改；标签和名录可以随时增减。

/**
 * 网页上的类别（筛选栏、卡片角标、RSS 分类订阅）。key 是网址和接口里的身份，上线后不要改。
 * section 是日报里的分节标题（几个类别可以共用一节，按这里的顺序排）；guide 告诉模型怎么归类。
 * 没归上类的资料在日报里放进第一个 key 为 industry 的类别所在的节（没有就放最后一节）。
 */
export const CATEGORIES = [
  { key: "game-tech", label: "研发技术", section: "研发技术", guide: "引擎、图形渲染、性能优化、服务器、工具链、美术管线、AI 辅助研发与游戏创作工具和研发实践；工具发布也归本类，分类不代表达到精选门槛" },
  { key: "game-products", label: "产品玩法", section: "产品玩法", guide: "玩法设计、系统拆解、竞品研究与产品复盘；核心必须包含玩法或设计分析，单纯上线排期不归本类" },
  { key: "game-market", label: "市场发行", section: "市场发行", guide: "发行与上线排期、买量、商业化、运营、出海、市场数据、融资并购与公司经营" },
  { key: "industry", label: "行业政策", section: "行业政策", guide: "版号、监管、未成年人保护、平台规则、行业协会公告及产业政策" },
] as const;

/**
 * 内容理解一步给每篇资料判的“内容类型”（写在 prompts/content-understanding.md 里，改了类型要同步改那份提示词）。
 * 评分提示词（prompts/selection-score.md）按类型给五个维度不同的权重。
 */
export const ITEM_TYPES = ["model_release", "product_launch", "tool_or_prompt", "research_paper", "industry_event", "opinion_analysis", "tutorial_explainer"] as const;

// ── 标签词表 ────────────────────────────────────────────────────────────────────────────

/** 每篇资料的第一个标签必须是这些“分类标签”之一。 */
export const CATEGORY_TAGS = ["引擎更新", "产品更新", "研发实践", "玩法设计", "市场发行", "行业动态", "政策/监管", "论文/研究", "开源/仓库", "教程/实践", "现象/趋势", "观点分析", "评测/基准", "其他"] as const;

/** 可选的主题标签。 */
export const TOPIC_TAGS = ["Unity", "Unreal Engine", "小游戏", "图形渲染", "性能优化", "服务端", "美术管线", "游戏设计", "AI辅助研发", "商业化", "出海", "买量", "用户留存", "版号", "独立游戏"] as const;

/** 可选的实体标签（公司、机构、平台）。 */
export const ENTITY_TAGS = ["腾讯", "网易", "米哈游", "Epic Games", "Unity", "Valve", "中国音数协"] as const;

/** 模型常写的近义词，统一成词表里的写法。 */
export const TAG_SYNONYMS: Readonly<Record<string, string>> = {
  引擎: "引擎更新", 渲染: "图形渲染", 优化: "性能优化", 玩法: "玩法设计", 发行: "市场发行",
  政策: "政策/监管", 监管: "政策/监管", 融资: "行业动态", 收购: "行业动态", 观点: "观点分析",
  教程: "教程/实践", 开源: "开源/仓库", 研究: "论文/研究", UE: "Unreal Engine", UE5: "Unreal Engine",
};
export const CATEGORY_BY_ITEM_TYPE: Readonly<Record<string, string>> = {
  model_release: "引擎更新", product_launch: "产品更新", tool_or_prompt: "研发实践", research_paper: "论文/研究",
  industry_event: "行业动态", opinion_analysis: "观点分析", tutorial_explainer: "教程/实践",
};

// ── 公司与主体 ──────────────────────────────────────────────────────────────────────────

/** 公司主题：id → 显示名、卡片上显示的标签（null 表示只用 entity:<id> 归类）、别名。 */
export const ENTITIES: Record<string, { name: string; displayTag: string | null; aliases: string[] }> = {
  "tencent": {
    "name": "腾讯",
    "displayTag": "腾讯",
    "aliases": [
      "腾讯",
      "Tencent"
    ]
  },
  "netease": {
    "name": "网易",
    "displayTag": "网易",
    "aliases": [
      "网易",
      "NetEase"
    ]
  },
  "mihoyo": {
    "name": "米哈游",
    "displayTag": "米哈游",
    "aliases": [
      "米哈游",
      "miHoYo",
      "HoYoverse"
    ]
  },
  "epic": {
    "name": "Epic Games",
    "displayTag": "Epic Games",
    "aliases": [
      "Epic Games",
      "虚幻引擎",
      "Unreal Engine"
    ]
  },
  "unity": {
    "name": "Unity",
    "displayTag": "Unity",
    "aliases": [
      "Unity",
      "团结引擎"
    ]
  },
  "valve": {
    "name": "Valve",
    "displayTag": "Valve",
    "aliases": [
      "Valve",
      "Steam"
    ]
  },
  "cadpa": {
    "name": "中国音数协",
    "displayTag": "中国音数协",
    "aliases": [
      "中国音数协",
      "游戏工委"
    ]
  }
};

export const IDENTITY_LEXICON: ReadonlyArray<{ id: string; name: string; patterns: RegExp[] }> = [
  { id: "tencent", name: "腾讯", patterns: [/腾讯|Tencent/i] },
  { id: "netease", name: "网易", patterns: [/网易|NetEase/i] },
  { id: "mihoyo", name: "米哈游", patterns: [/米哈游|miHoYo|HoYoverse/i] },
  { id: "epic", name: "Epic Games", patterns: [/Epic Games|虚幻引擎|Unreal Engine/i] },
  { id: "unity", name: "Unity", patterns: [/Unity|团结引擎/i] },
  { id: "valve", name: "Valve", patterns: [/Valve|Steam/i] },
  { id: "cadpa", name: "中国音数协", patterns: [/中国音数协|游戏工委/i] },
];
export const PUBLISHER_DOMAINS: ReadonlyArray<{ entityId: string; domains: readonly string[] }> = [{"entityId": "tencent", "domains": ["tencent.com", "qq.com"]}, {"entityId": "netease", "domains": ["163.com"]}, {"entityId": "mihoyo", "domains": ["mihoyo.com", "hoyoverse.com"]}, {"entityId": "epic", "domains": ["unrealengine.com", "epicgames.com"]}, {"entityId": "unity", "domains": ["unity.cn", "unity.com"]}, {"entityId": "valve", "domains": ["steampowered.com"]}, {"entityId": "cadpa", "domains": ["cgigc.com.cn"]}];
export const IDENTITY_CONTEXT_ALIASES: ReadonlyArray<{ entityId: string; pattern: RegExp }> = [];
