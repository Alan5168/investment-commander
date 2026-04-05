# invest-evolution 投研自进化系统

> 让 Investment Commander 的投研系统越用越准。

## 概述

四大组件形成反馈闭环：追踪战绩 → 发现催化变化 → 诊断失败原因 → 验证进化建议。

```
每日推荐记录（memory/daily-log）
       ↓
catalyst_radar.py → 发现新/冷却催化剂 → 钉钉推送
       ↓
performance_tracker.py → 追踪战绩 → data/performance/{date}.jsonl
       ↓
failure_diagnosis.py → 归因诊断 → data/diagnosis/{date}_{stock}.json
       ↓
backtest_validator.py → 验证建议 → 钉钉推送（等待确认）
```

## 四大组件

### 1. catalyst_radar.py（催化剂雷达）
- **触发**: 每天 08:00（盘前）
- **功能**: 自动发现新催化剂、监测旧催化剂冷却
- **输入**: 新闻监控输出 + 现有催化剂知识库
- **输出**: 
  - `data/catalyst_updates/{date}.json`
  - 钉钉推送（新催化剂 / 升级 / 冷却预警）

### 2. performance_tracker.py（战绩追踪器）
- **触发**: 每天 16:30（收盘后）
- **功能**: 追踪 Investment Commander 每天推荐的股票实际表现
- **输入**: `workspace/memory/daily-log` 中的推荐记录
- **输出**: `data/performance/{date}.jsonl`
- **判定规则**:
  - `win`: 10天内最高收益 > 5%
  - `fail`: 10天内最大回撤 > 5% 或触发止损
  - `neutral`: 其余

### 3. failure_diagnosis.py（归因诊断器）
- **触发**: 每天 17:00
- **功能**: 对 `result=="fail"` 的推荐做反事实归因
- **三维度归因**:
  1. **产业催化剂（70%权重）**: 催化剂是否真实/price in/知识库过时
  2. **量化择时（30%权重）**: 买入时点/技术指标矛盾
  3. **风控**: 大盘环境/止损设置
- **三种结论**:
  - `催化剂失效` → 建议更新知识库
  - `择时失败` → 建议触发 indicator_explorer 重新进化
  - `市场环境` → 建议调整风控参数
- **输出**: `data/diagnosis/{date}_{stock_code}.json`

### 4. backtest_validator.py（回测验证器）
- **触发**: 每天 17:30
- **功能**: 验证归因诊断器的建议是否经得起回测
- **验证逻辑**:
  - `action=="update_catalyst"`: 近30天该赛道表现差 → 支持降级
  - `action=="retrain_indicator"`: 对比 indicator_explorer 新旧参数
  - `action=="adjust_risk"`: 对比调整前后风控效果
- **原则**: 不自动执行，只生成报告推送钉钉，等用户确认

## Cron 时间线

```
08:00  → catalyst_radar.py        （催化剂雷达）
09:15  → 早盘选股                  （已有，不动）
15:30  → 盘后异动筛选              （已有，不动）
16:30  → performance_tracker.py    （战绩追踪）
17:00  → failure_diagnosis.py      （归因诊断）
17:30  → backtest_validator.py     （回测验证）
```

## 目录结构

```
skills/invest-evolution/
├── SKILL.md
├── README.md
├── scripts/
│   ├── catalyst_radar.py        # 催化剂雷达
│   ├── performance_tracker.py   # 战绩追踪器
│   ├── failure_diagnosis.py     # 归因诊断器
│   └── backtest_validator.py   # 回测验证器
└── data/
    ├── performance/             # 战绩记录 (.jsonl)
    ├── diagnosis/               # 诊断报告 (.json)
    └── catalyst_updates/        # 催化剂变动 (.json)
```

## 安装

无需额外安装，直接使用：

```bash
# 单独运行某个组件
python3 skills/invest-evolution/scripts/performance_tracker.py
python3 skills/invest-evolution/scripts/catalyst_radar.py
python3 skills/invest-evolution/scripts/failure_diagnosis.py
python3 skills/invest-evolution/scripts/backtest_validator.py
```

## 配置

依赖环境变量：
- `TUSHARE_TOKEN`: Tushare Pro API Token（用于获取行情数据）

```bash
echo "your_token_here" > ~/.tushare_token
```

## 数据依赖

- **催化剂知识库**: `skills/investment-commander/industry_analyst.py` 或 `catalyst_kb.json`
- **每日推荐记录**: `workspace/memory/YYYY-MM-DD.md`
- **新闻监控输出**: `workspace/output/news/*.json`

如果上述文件不存在，系统会使用内置的默认知识库结构继续运行。

## 核心原则

1. **所有修改建议只推送不自动执行**，等用户确认后再操作
2. 与 `skills/meta-harness/` 完全独立运行
3. 数据存在 `data/` 子目录下，不污染其他目录
4. 只使用标准库 + tushare + requests

## 典型输出示例

### 催化剂雷达（钉钉推送）
```
【催化剂雷达】
🆕 新发现：
  • 固态电池：某公司宣布全固态电池量产突破
⬆️ 催化剂升级：
  • 半导体/芯片：近期催化事件从2个增至5个
❄️ 冷却预警：
  • SST固态变压器：连续5天无新催化事件
📊 当前活跃赛道：4个
```

### 回测验证（钉钉推送）
```
【投研进化】诊断验证报告
✅ 301268 铭利达
   归因：催化剂失效
   建议：update_catalyst
   验证：近30天SST赛道平均收益 -6.2%，支持降级
   📋 建议操作：确认后更新知识库
— 共1条诊断待确认 —
```

## 版本

- v1.0.0 (2026-04-05): 初始版本
