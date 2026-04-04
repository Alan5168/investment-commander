# Investment Commander（投资团队编排器）

> 🤖 产业逻辑（70%）+ 量化择时（30%）= 每日 3 只精选推荐
> 不做决策，只做调度 —— 让专业的人做专业的事

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 一句话说明

Investment Commander 是**A股投资决策系统的编排层**，通过多 Agent 协作——产业分析师 × 量化择时官 × 风控验证员——每日输出 3 只精选股票，并给出精确的买卖点位与操作清单。

**使用方式**：在钉钉或 Telegram 对我说"今日选股"，90 秒内收到报告。

---

## 核心特色

### 🎯 双轨推荐：产业 × 量化

| 轨道 | 分析师 | 负责 |
|------|--------|------|
| 产业逻辑（70%） | 产业分析师 | 赛道景气度、竞争格局、催化剂事件 |
| 量化择时（30%） | 量化分析师 | 均线、MACD、RSI、布林带、动量指标综合打分 |
| 仲裁 | 风控验证员 | 过滤高杠杆、流动性风险，输出最终推荐 |

两个通道独立打分，最终加权融合——既有基本面的深度，又有技术面的择时。

### 📊 遗传算法指标探索

指标组合不是拍脑袋定的，是用**遗传算法在 1831 条历史回测记录上进化**出来的。

- **指标库**：41 个指标（均线交叉、RSI、MACD、布林带、动量、MA 斜率等）
- **互斥约束**：防止逻辑矛盾的指标组合（如同时出现"金叉"和"死叉"）
- **composite_score**：分离度 × 0.6 + alpha × 0.4，高区分度才是好策略

```
指标库: 41 个 | 互斥组: 11 组
随机基准: 22.1%（高区必须跑赢）
回测记录: 1849 条（2025-01 至 2026-03）
```

### 🔬 回测驱动进化

每次市场环境变化，指标组合可能失效。系统会持续用**最新回测数据**重新评估组合表现，动态淘汰低效指标。

### 🛡️ 三层风控

1. **宏观风险过滤**：大盘指数（沪深 300）下行趋势时自动降仓
2. **基本面风控**：排除亏损股、微盘股（流通市值 < 50 亿）
3. **量化风控**：单一行业仓位上限、止损纪律

---

## vs 竞品：为什么选 Investment Commander？

| 维度 | Investment Commander | `ai_stock_selection`（竞品 A） | `a-stock-monitor`（竞品 B） |
|------|---------------------|--------------------------------|------------------------------|
| **架构** | Agent 编排层（调度型） | 4-Agent 直接决策 | 单体脚本 |
| **推荐方式** | 产业 + 量化双轨融合 | 单一 AI 直接给买卖点 | 多策略选股池 |
| **指标进化** | 遗传算法 + 回测验证 | 无 | 无 |
| **回测数据** | 1831 条 v3 数据 | 无 | 有限 |
| **通知渠道** | 钉钉 / Telegram | Web 界面 | Web 界面 |
| **输出形式** | 股票 + 理由 + 买点 + 止损 + 操作清单 | 评级 + 交易计划 | 评分排名列表 |
| **部署** | OpenClaw Cron，本地运行 | 需要 Node.js + Vue 部署 | 需要 Flask |
| **语言** | 中文报告 | 中文 | 中文 |

**核心差异**：Commander **不做决策，只做调度**——这意味着你可以替换任何一个 Agent 的实现，而不需要改变整体架构。

---

## 快速开始

### 前置依赖

```bash
pip install akshare pandas numpy
# OpenClaw 已包含在系统中
```

### 使用方式

**方式一：钉钉 / Telegram 触发**
```
/选股 今日
/持仓分析 301268
/问股 688190
```

**方式二：命令行直接运行**
```bash
cd skills/investment-commander
python3 scripts/commander_final.py --stock 301268
```

---

## 目录结构

```
investment-commander/
├── SKILL.md                    # 技能定义（OpenClaw 加载用）
├── RULES.md                    # Agent 角色规则
├── README.md                   # 本文件
├── scripts/
│   ├── commander_final.py      # 编排主入口
│   ├── indicator_explorer.py   # 遗传算法指标探索
│   ├── industry_analyst.py     # 产业分析师
│   ├── quant_timing_reference.py # 量化择时官
│   ├── alan_custom_screener.py # Alan 定制选股器
│   ├── historical_backtest.py  # 历史回测生成
│   └── market_filter.py        # 大盘宏观过滤
├── config/
│   ├── best_indicators.json    # 当前最优指标组合
│   ├── indicator_history.jsonl # 探索历史记录
│   ├── indicator_library.json  # 指标库定义
│   └── screener_params.yaml    # 选股参数配置
└── templates/
    └── report_template.md      # 报告模板
```

---

## 版本历史

### v1.3 (2026-04-04)
- 持仓股产业背景自动注入：portfolio.json → STOCK_CATALYST_MAP → 早报/推荐自动带产业说明
- 持仓排除逻辑：推荐时自动过滤用户已持仓股票（需配置 portfolio.json）
- 持仓产业亮点：支持持仓股独立产业描述（需在 portfolio.json 配置）
- 量化指标升级：best_indicators v2（composite_score 17.09 → 19.31，高区胜率 28.1% vs 随机 22.1%）
- 新增7个未来产业主题：脑机接口/低空经济/卫星互联网/生物制造/量子计算/核聚变/AI Agent
- 产业分析师 v2：支持 get_stock_industry_context() 动态获取产业背景
- 选股流程：产业优先（催化剂 → 产业池 → 技术打分 → 候选池 → 3只推荐）

### v1.2 (2026-03-31)
- 遗传算法指标探索（indicator_explorer v2.0）
- v3 回测数据：MACD / 布林带 / 动量 / MA 斜率等 12 个新字段
- 指标库 31 → **41 个**
- 互斥约束防止逻辑矛盾的指标组合
- 大盘过滤：AKShare 替换 Tushare 指数接口
- Commander 双轨推荐：产业分析师 + 量化分析师

### v1.0 (2026-03-29)
- 初始版本

---

## 致谢

- 数据源：[AKShare](https://github.com/akfamily/akshare) · [Tushare](https://tushare.pro/)
- 量化框架灵感：[TradingAgents](https://github.com/goldgeyser/TradingAgents)
- A股监控基础：[JamesMei/a-stock-monitor](https://github.com/JamesMei/a-stock-monitor)
