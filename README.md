# 🍟 麦麦优惠雷达 · mcd-deal-radar

> 一条命令看清今天麦当劳有什么活动、有什么券能领。

一个基于**麦当劳中国 MCP Server** 的极简 Skill：把「门店活动海报 + 麦麦省券中心 + 我的券包」三个入口，收敛成一次查询。

## 它解决什么问题

想吃麦当劳时，"现在划不划算"要翻三个地方：活动页看有没有联名/限时，券中心看有什么能领，券包看已经有什么。信息是分散的，有效期还要自己比对，多数人干脆放弃领券直接下单。

`mcd-deal-radar` 用三个 MCP 工具把这件事做完：

| 工具 | 回答的问题 |
| --- | --- |
| `now-time-info` | 现在几点（以服务端为准，避免误判活动是否进行中） |
| `campaign-calendar` | 这个月麦当劳在搞什么活动 |
| `available-coupons` | 我现在能领哪些券 |
| `auto-bind-coupons` | 需要时，一次性领完（可选，默认关闭） |

## 目标用户

- 每周吃 2 次以上麦当劳、但懒得翻券中心的**常客**。
- 用 WorkBuddy / Claude / Cursor 等 Agent 客户端，希望"问一句就有答案"的**开发者**。
- 想了解 MCP 工具怎么串成本地小工具的**学习者**——`scripts/mcd_mcp.py` 是不依赖任何 SDK 的完整参考实现。

## 原理

```
用户 ──► Skill（SKILL.md 指令 / CLI 脚本）
              │  Streamable HTTP + Bearer Token
              ▼
        https://mcp.mcd.cn  ──►  now-time-info / campaign-calendar / available-coupons
              │
              ▼
        聚合成一份报告：活动 → 券 → 建议
```

详见 [MCP_INTEGRATION.md](MCP_INTEGRATION.md)。

## 快速开始

### 1. 申请 MCP Token

访问 https://open.mcd.cn/mcp ，用手机号登录 → 右上角「控制台」→「激活」→ 同意服务协议 → 复制 Token。

### 2. 配置环境变量

```powershell
# Windows PowerShell
$env:MCD_MCP_TOKEN = "你的Token"
```

```bash
# macOS / Linux
export MCD_MCP_TOKEN="你的Token"
```

### 3. 运行

```bash
git clone https://github.com/6244rpjh6n-lang/mcd-deal-radar.git
cd mcd-deal-radar
python scripts/deal_radar.py
```

无需 `pip install`，只需要 Python 3.9+。

## 使用示例

```bash
# 今日活动 + 可领券
python scripts/deal_radar.py

# 顺便一键领券（会改动账户，确认后再用）
python scripts/deal_radar.py --claim

# 原始 JSON，便于接入别的脚本
python scripts/deal_radar.py --json

# 排查：列出服务端当前提供的全部工具
python scripts/deal_radar.py --tools
```

真实运行结果（2026-10-24 10:22，节选）：

```
🍟 麦麦优惠雷达 · 2026-10-24 10:22
────────────────────────────────────────────────────────────
服务端：https://mcp.mcd.cn · 协议版本：2025-06-18 · 时间为北京时间
────────────────────────────────────────────────────────────

📅 今日活动
  · [今日] 麦当劳「我就喜欢」限定丝巾正式开售🔥
      丝巾搭配棒球帽的潮流谁懂😎 任意餐品消费加 39.9 元即可得 颈间、包袋、手腕…

📅 即将到来
  · 麦当劳联动G-DRAGON
      带来韩式风味系列新品❗️ 龙焰鸡腿堡三件套 26.9 元起即刻开吃🍔 …
  · 下周麦麦省优惠预告来啦😁
      🌟麦麦省下周优惠抢先预告 🍔11.9元轻松get麦辣鸡腿堡 …
  … 还有 3 场，用 --all 查看

📅 往期回顾
  共 4 场，用 --all 查看

🎟 麦麦省优惠券（3 张）
  · 免费脆薯饼  [已领取]
  · 11.9元麦辣鸡腿堡  [已领取]
  · 19.9元王牌炸鸡任选2  [已领取]
  → 其中 0 张待领取
────────────────────────────────────────────────────────────
提示：券的可用范围、有效期与活动规则以麦当劳官方渠道为准。
```

### 为什么还需要一层解析

麦当劳 MCP 的工具返回值是**给大模型读的 Markdown**，里面夹着 `<img>` 标签和带签名的超长图片 URL（单张券就能占掉半屏）。直接打印会有大量噪音，所以 `deal_radar.py` 做了一层清洗：

- 去掉 `<img>` 标签与行尾续行符 `\`；
- 按 `#### 日期 标签` 切分活动，抽出「活动标题 / 活动内容介绍」；
- 按 `- 优惠券标题 / 状态` 抽出券，统计「已领取 / 待领取」；
- 今日 / 即将到来 / 往期 分组，正文截断到 78 字。

这层解析让同一个 MCP 返回值在终端里从"一篇 8KB 的说明文档"变成"一屏就能看完的结论"。

### 在 Agent 客户端中使用

把 `mcp-config.example.json` 的内容填入客户端（WorkBuddy / Cherry Studio / Cursor / Trae 等），把 `${MCD_MCP_TOKEN}` 换成真实 Token，再把本仓库放进技能目录即可。Agent 会按 `SKILL.md` 里的工具调用顺序执行。

## 参数

| 参数 | 说明 |
| --- | --- |
| `--claim` | 一键领取麦麦省当前可领的券（写操作，默认关闭） |
| `--json` | 输出原始 JSON 结果 |
| `--tools` | 列出服务端可用工具 |
| `--limit N` | 每节最多显示 N 条，默认 8 |
| `--timeout N` | 单次请求超时秒数，默认 30 |

环境变量：`MCD_MCP_TOKEN`（必填）、`MCD_MCP_URL`（可选，默认 `https://mcp.mcd.cn`）。

## 目录结构

```
mcd-deal-radar/
├── README.md                  # 本文件
├── SKILL.md                   # Agent Skill 指令（何时用、怎么调、怎么答）
├── MCP_INTEGRATION.md         # MCP Server / Tool / 调用流程 / 业务价值
├── CONTEST_DECLARATION.md     # 参赛声明（官方原文，未改动）
├── mcp-config.example.json    # 脱敏配置示例，仅环境变量占位符
├── scripts/
│   ├── mcd_mcp.py             # 最小 MCP Streamable HTTP 客户端（标准库）
│   └── deal_radar.py          # CLI：查询 + 聚合输出
└── LICENSE
```

## 常见问题

**Q：报 `缺少 MCP Token`？**
A：环境变量没设，或设在了另一个终端窗口。PowerShell 里用 `$env:MCD_MCP_TOKEN = "..."`，且只在当前窗口有效。

**Q：报 HTTP 401 / 403？**
A：401 是 Token 无效或过期；403 通常是没在开放平台同意服务协议，或 Token 已被回收。重新去 https://open.mcd.cn/mcp 激活一次。

**Q：为什么时间要从 `now-time-info` 取？**
A：活动时间以北京时间为准。本地时钟偏差或时区不同，会让"进行中"判断出错。

**Q：会替我下单吗？**
A：不会。本 Skill 只调用查询类工具，`auto-bind-coupons` 是唯一的写操作且默认关闭，下单/支付类工具完全没有接入。

**Q：能商用吗？**
A：本项目代码以 MIT 协议开源。麦当劳 MCP 服务本身受其《使用条款》与《麦当劳 MCP 服务规则》约束。

## 免责声明

本项目为**麦当劳程序员创意开发大赛参赛作品**，由参赛者独立开发，非麦当劳官方产品，不代表麦当劳立场。输出结果仅供参考，不构成营养、医疗或价格承诺；活动、券面、价格与供应状态以麦当劳官方渠道实时结果为准。

## License

MIT
