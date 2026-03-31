# Investment Commander（投资团队编排器）

产业逻辑（70%）+ 量化择时（30%）= 每日3只精选推荐

## 核心定位

**"不做决策，只做调度"**

Investment Commander 是投资决策系统的编排层，负责：
1. 解析用户意图
2. 路由到对应的 Agent
3. 协调数据传递
4. 格式化最终输出

**绝不直接调用分析工具，绝不输出买卖建议。**

## 版本历史

### v1.2 (2026-03-31)
- 遗传算法指标探索（indicator_explorer v2.0）
- v3回测数据：补充MACD/布林带/动量/MA斜率等12个新字段
- 互斥约束：防止逻辑矛盾的指标组合出现
- 指标库从31扩展到41个
- 大盘过滤修复：AKShare替换Tushare指数接口
- Commander双轨推荐：产业分析师+量化分析师
- 新增脚本：us_market_signal.py、investment_research.py、news_verifier.py

### v1.0 (2026-03-29)
- 初始版本
