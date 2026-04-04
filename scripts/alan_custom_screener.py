#!/usr/bin/env python3
"""
Alan Li 定制化选股脚本 v2.1 - 统一数据源版

更新日志:
- v2.2 (2026-03-29): 新增技术面综合打分（MA20买卖信号、量比、RSI）
- v2.1 (2026-03-27): 使用统一数据源 stock_client，解决东方财富接口问题
- v2.0 (2026-03-27): 三档筛选逻辑，适应弱势震荡市场

投资风格适配：
- 中线（几个月）+ 长线/价值投资（一年以上）
- 技术+题材面结合
- 不碰消费、金融、地产
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import json
import argparse
import pandas as pd
import numpy as np

# 添加 shared 目录到路径
SHARED_DIR = Path('/Users/alanli/.openclaw/workspace/shared')
sys.path.insert(0, str(SHARED_DIR))

from stock_client import get_daily_realtime, get_realtime, get_ma, get_rsi

# ============ 配置参数 ============

EXCLUDE_INDUSTRIES = [
    '银行', '非银金融', '房地产', '地产', '房产',
    '食品饮料', '白酒', '家用电器', '商贸零售', '社会服务', '美容护理', '零售', '旅游', '酒店', '餐饮'
]
EXCLUDE_KEYWORDS = ['金融', '银行', '地产', '房产', '白酒', '食品', '零售', '旅游', '酒店', '餐饮', '美容']

PREFERRED_INDUSTRIES = [
    '汽车', '电子', '交通运输', '机械设备', '电力设备', '计算机', '通信', '国防军工'
]

# ============ 中证1000成分股 ============

_csi1000_cache = None

def get_csi1000_stocks():
    """获取中证1000成分股列表"""
    global _csi1000_cache

    if _csi1000_cache is not None:
        return _csi1000_cache

    try:
        import akshare as ak
        print("📡 正在获取中证1000成分股...")
        df = ak.index_stock_cons_weight_csindex(symbol='000852')

        stocks = []
        for _, row in df.iterrows():
            code = str(row['成分券代码']).zfill(6)
            name = row['成分券名称']

            if 'ST' in name or '退' in name or '*' in name:
                continue

            stocks.append({
                'code': code,
                'name': name,
            })

        _csi1000_cache = stocks
        print(f"✅ 获取到 {len(stocks)} 只中证1000成分股")
        return stocks

    except Exception as e:
        print(f"❌ 获取中证1000成分股失败: {e}")
        return []

# ============ 行业分类 ============

import json
from pathlib import Path

_industry_cache = None
_INDUSTRY_CACHE_FILE = Path.home() / ".openclaw" / "workspace" / "data" / "industry_cache.json"

def get_stock_industry(stock_code: str) -> str:
    """获取股票所属行业（带本地缓存）"""
    global _industry_cache

    if _industry_cache is None:
        # 1. 尝试从本地缓存加载
        try:
            if _INDUSTRY_CACHE_FILE.exists():
                age = (datetime.now() - datetime.fromtimestamp(_INDUSTRY_CACHE_FILE.stat().st_mtime)).total_seconds()
                if age < 86400:  # 24小时内有效
                    _industry_cache = json.loads(_INDUSTRY_CACHE_FILE.read_text())
                    print(f"✅ 行业缓存加载：{len(_industry_cache)} 只（{age/3600:.1f}小时前）")
        except Exception:
            pass

        # 2. 缓存为空则从 Tushare 查询
        if _industry_cache is None:
            try:
                import tushare as ts
                ts.set_token('999b3d72d28eb44644acc8dd6797d5f69b7ce727ecae1b6812c73892')
                pro = ts.pro_api()
                basic = pro.stock_basic(fields='ts_code,industry', list_status='L')
                _industry_cache = {}
                for _, row in basic.iterrows():
                    code = row['ts_code'].split('.')[0]
                    _industry_cache[code] = row['industry'] or '未知'
                # 保存到本地缓存
                _INDUSTRY_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                _INDUSTRY_CACHE_FILE.write_text(json.dumps(_industry_cache, ensure_ascii=False))
                print(f"✅ 行业数据加载并缓存：{len(_industry_cache)} 只")
            except Exception as e:
                print(f"⚠️ 行业加载失败: {e}")
                _industry_cache = {}

    return _industry_cache.get(stock_code.zfill(6), '未知')

# ============ 庄家顶底指标 ============

try:
    from zhuangjia_indicator import check_zhuangjia_condition
    ZHUANGJIA_AVAILABLE = True
except ImportError:
    ZHUANGJIA_AVAILABLE = False

# ============ 三档分类 ============


# ============ 最优指标打分（来自遗传算法） ============

def get_optimal_indicators() -> dict:
    """加载遗传算法找到的最优指标权重（仅当跑赢基准时使用）"""
    best_file = Path('/Users/alanli/.openclaw/workspace/skills/a-stock-monitor/config/best_indicators.json')
    if best_file.exists():
        data = json.loads(best_file.read_text())
        if data.get('high_hit', 0) > 0.221:  # 跑赢基准才用
            return data.get('indicators', {})
    return {}  # 降级：返回空，用默认三档分类


def classify_tier_with_optimal(df: pd.DataFrame) -> tuple:
    """
    用遗传算法最优指标组合打分，替代硬编码三档分类。
    仅当最优指标存在且跑赢基准时启用，否则降级到 classify_tier。
    """
    optimal = get_optimal_indicators()

    if not optimal:
        # 降级到原有逻辑
        return classify_tier(df)

    if df is None or len(df) < 20:
        return 0, '数据不足', '无法获取历史数据'

    latest = df.iloc[-1]
    # 成交额过滤（≥1亿/日）；成交额列单位=万元，1亿=10000万
    turnover_wan = latest.get('成交额', 0)
    if pd.isna(turnover_wan) or turnover_wan < 10000:
        return 0, '不符合', f'成交额不足{turnover_wan:.0f}万'

    close = latest['收盘']
    ma5 = df['收盘'].rolling(5).mean().iloc[-1]
    ma10 = df['收盘'].rolling(10).mean().iloc[-1]
    ma20 = df['收盘'].rolling(20).mean().iloc[-1]
    vol_ma5 = df['成交量'].rolling(5).mean().iloc[-1]
    vol_ratio = latest['成交量'] / vol_ma5 if vol_ma5 > 0 else 1.0
    change_pct = latest.get('涨跌幅', 0) if '涨跌幅' in latest.index else 0
    if pd.isna(change_pct):
        change_pct = 0

    # 计算 RSI
    if len(df) >= 17:
        delta = df['收盘'].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, float('nan'))
        rsi = (100 - 100 / (1 + rs)).iloc[-1]
    else:
        rsi = 50

    # 用最优权重打分（跳过 score_below_50：live 数据无法准确计算）
    score = 50
    for ind, weight in optimal.items():
        if ind == 'score_below_50':
            continue  # 跳过
        elif ind == 'price_down' and change_pct < 0:
            score += weight
        elif ind == 'ma5_gt_ma10' and ma5 > ma10:
            score += weight
        elif ind == 'close_gt_ma5' and close > ma5:
            score += weight
        elif ind == 'close_above_ma20_pct' and (close - ma20) / ma20 > 0.02:
            score += weight
        elif ind == 'rsi_50_60_zone' and 50 <= rsi <= 60:
            score += weight
        elif ind == 'close_lt_ma20' and close < ma20:
            score += weight
        elif ind == 'rsi_below_50' and rsi < 50:
            score += weight
        elif ind == 'rsi_overbought' and rsi > 70:
            score += weight
        elif ind == 'vol_ratio_2x' and vol_ratio > 2.0:
            score += weight

    score = max(0, min(100, score))

    if score >= 88:
        return 1, '强势', f'最优指标评分{score:.0f}'
    elif score >= 75:
        return 2, '弱势修复', f'最优指标评分{score:.0f}'
    elif score >= 60:
        return 3, '观察池', f'最优指标评分{score:.0f}'
    else:
        return 0, '不符合', f'最优指标评分{score:.0f}'

def classify_tier(df: pd.DataFrame) -> tuple:
    """
    三档分类

    返回: (tier, tier_name, reason)
    """
    if df is None or len(df) < 20:
        return 0, '数据不足', '无法获取历史数据'

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest

    close = latest['收盘']

    # 计算均线
    ma5 = df['收盘'].rolling(window=5).mean().iloc[-1]
    ma10 = df['收盘'].rolling(window=10).mean().iloc[-1]
    ma20 = df['收盘'].rolling(window=20).mean().iloc[-1]
    ma_vol5 = df['成交量'].rolling(window=5).mean().iloc[-1]
    volume = latest['成交量']

    # 计算 RSI
    if len(df) >= 17:
        delta = df['收盘'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        rsi14 = rsi.iloc[-1]
        rsi14_prev3 = rsi.iloc[-4] if len(rsi) > 3 else rsi14
    else:
        rsi14 = 50
        rsi14_prev3 = 50

    # 第一档：强势
    tier1_cond1 = close > ma20
    tier1_cond2 = ma5 > ma10 > ma20
    tier1_cond3 = volume > ma_vol5 * 1.2 if ma_vol5 > 0 else False

    if tier1_cond1 and tier1_cond2 and tier1_cond3:
        return 1, '强势', f'MA多头+放量{volume/ma_vol5:.1f}倍'

    # 第二档：弱势修复
    ma5_prev = df['收盘'].rolling(window=5).mean().iloc[-2]
    ma10_prev = df['收盘'].rolling(window=10).mean().iloc[-2]

    tier2_cond1 = close > ma20
    tier2_cond2 = (ma5 > ma10) and (ma5_prev <= ma10_prev)
    tier2_cond3 = volume > ma_vol5 * 1.5 if ma_vol5 > 0 else False

    if tier2_cond1 and tier2_cond2 and tier2_cond3:
        return 2, '弱势修复', f'金叉+放量{volume/ma_vol5:.1f}倍'

    # 第三档：观察池
    tier3_cond1 = close > ma20
    tier3_cond2 = 35 <= rsi14 <= 65
    tier3_cond3 = rsi14_prev3 < 35

    if tier3_cond1 and tier3_cond2 and tier3_cond3:
        return 3, '观察池', f'RSI从{rsi14_prev3:.0f}回升至{rsi14:.0f}'

    return 0, '不符合', '未满足任何档位条件'

# ============ 技术面综合打分 ============

def calc_technical_score(df: pd.DataFrame) -> dict:
    """
    技术面综合打分（0-100）

    信号来源：
    1. 均线系统（MA20买卖信号）- 大V核心逻辑
    2. 量比（成交量异常放大/萎缩）
    3. 庄家顶底始信号
    4. RSI位置
    """
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    score = 0
    signals = []

    close = latest['收盘']
    ma10 = df['收盘'].rolling(10).mean().iloc[-1]
    ma20 = df['收盘'].rolling(20).mean().iloc[-1]
    ma10_prev = df['收盘'].rolling(10).mean().iloc[-2]
    ma20_prev = df['收盘'].rolling(20).mean().iloc[-2]

    vol = latest['成交量']
    vol_ma5 = df['成交量'].rolling(5).mean().iloc[-1]
    vol_ratio = vol / vol_ma5 if vol_ma5 > 0 else 1

    # === 信号1：MA20 买入（上穿20日均线）===
    if close > ma20 and prev['收盘'] <= ma20_prev:
        score += 40
        signals.append("上穿MA20，买入信号")
    elif close > ma20:
        score += 20
        signals.append("站稳MA20上方")

    # === 信号2：MA10 预警（下穿10日均线减仓）===
    if close < ma10 and prev['收盘'] >= ma10_prev:
        score -= 20
        signals.append("⚠️ 下穿MA10，减仓预警")

    # === 信号3：量比（放量确认）===
    if vol_ratio > 2.0:
        score += 25
        signals.append(f"强势放量{vol_ratio:.1f}倍")
    elif vol_ratio > 1.5:
        score += 15
        signals.append(f"温和放量{vol_ratio:.1f}倍")
    elif vol_ratio < 0.5:
        score -= 10
        signals.append(f"严重缩量{vol_ratio:.1f}倍")

    # === 信号4：RSI位置 ===
    delta = df['收盘'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, float('nan'))
    rsi = (100 - 100 / (1 + rs)).iloc[-1]

    if 45 <= rsi <= 65:
        score += 15
        signals.append(f"RSI健康({rsi:.0f})")
    elif rsi < 30:
        score += 20
        signals.append(f"RSI超卖反弹({rsi:.0f})")
    elif rsi > 80:
        score -= 15
        signals.append(f"RSI超买({rsi:.0f})")

    return {
        "score": max(0, min(100, score)),
        "signals": signals,
        "ma10": round(ma10, 2),
        "ma20": round(ma20, 2),
        "vol_ratio": round(vol_ratio, 2),
        "rsi": round(float(rsi), 1)
    }

# ============ 筛选逻辑 ============

def screen_stock(stock_code: str, stock_name: str, zhuangjia_mode: bool = False) -> dict:
    """筛选单只股票"""

    # 获取行业
    industry = get_stock_industry(stock_code)
    if industry in EXCLUDE_INDUSTRIES or any(kw in industry for kw in EXCLUDE_KEYWORDS):
        return None

    # 获取日线数据
    df = get_daily_realtime(stock_code, days=150)
    if df is None or len(df) < 30:
        return None

    # 三档分类
    tier, tier_name, reason = classify_tier_with_optimal(df)
    if tier == 0:
        return None

    # 庄家顶底信号
    zhuangjia_result = None
    if ZHUANGJIA_AVAILABLE:
        try:
            zhuangjia_result = check_zhuangjia_condition(df)
        except Exception:
            pass

    # 庄家模式过滤
    if zhuangjia_mode:
        if zhuangjia_result is None or zhuangjia_result['score'] < 50:
            return None

    # 计算技术面综合打分
    tech = calc_technical_score(df)
    tech_score = tech['score']

    # 档位基础分
    tier_base = {1: 70, 2: 55, 3: 40}.get(tier, 0)

    # 多头加分
    ma60 = df['收盘'].rolling(window=60).mean().iloc[-1] if len(df) >= 60 else 0
    ma120 = df['收盘'].rolling(window=120).mean().iloc[-1] if len(df) >= 120 else 0
    if ma60 > 0 and ma120 > 0 and df.iloc[-1]['收盘'] > ma60 > ma120:
        tier_base += 15

    # 动量
    change_pct = df.iloc[-1].get('涨跌幅', 0)
    if pd.isna(change_pct):
        change_pct = 0

    total_score = min(100, tier_base + tech_score // 2 + abs(change_pct))

    return {
        'code': stock_code,
        'name': stock_name,
        'industry': industry,
        'tier': tier,
        'tier_name': tier_name,
        'tier_reason': reason,
        'close': df.iloc[-1]['收盘'],
        'change_pct': change_pct,
        'volume': df.iloc[-1]['成交量'],
        'tech': tech,
        'rsi14': tech['rsi'],
        'zhuangjia': zhuangjia_result,
        'score': total_score,
    }

# ============ 报告生成 ============

def generate_report(results: list, zhuangjia_mode: bool = False) -> str:
    """生成选股报告"""

    date_str = datetime.now().strftime("%Y-%m-%d")

    # 按档位分组
    tier1 = [r for r in results if r['tier'] == 1]
    tier2 = [r for r in results if r['tier'] == 2]
    tier3 = [r for r in results if r['tier'] == 3]

    # 按评分排序
    for tier in [tier1, tier2, tier3]:
        tier.sort(key=lambda x: x['score'], reverse=True)

    mode_str = "（庄家顶底模式）" if zhuangjia_mode else ""

    report = f"""# 🎯 Alan Li 选股报告{mode_str}

**生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**数据源**: Tushare + mootdx
**筛选逻辑**: 三档筛选 + 技术面综合打分

| 档位 | 数量 | 说明 |
|------|------|------|
| 📈 强势 | {len(tier1)} 只 | MA多头 + 放量 |
| 🔄 弱势修复 | {len(tier2)} 只 | 金叉 + 放量 |
| 👀 观察池 | {len(tier3)} 只 | RSI低位回升 |

---
"""

    def format_tier(tier_list: list, emoji: str, name: str) -> str:
        if not tier_list:
            return ""

        text = f"\n## {emoji} {name}候选\n\n"
        for i, r in enumerate(tier_list, 1):
            zj = r.get('zhuangjia')
            zj_str = ""
            if zj and zj.get('signal'):
                zj_str = f"\n   - 庄家信号: {zj['signal']}"

            tech = r.get('tech', {})
            signals_str = '; '.join(tech.get('signals', [])) if tech else ''

            text += f"""### {i}. {r['name']} ({r['code']}) - {r['score']}分

- 分类: {r['tier_name']} ({r['tier_reason']})
- 收盘: ¥{r['close']:.2f} ({r['change_pct']:+.2f}%)
- 技术信号: {signals_str or '无'}
- RSI14: {r['rsi14']:.0f}
- 行业: {r['industry'] or '未知'}{zj_str}

"""
        return text

    report += format_tier(tier1, '📈', '强势')
    report += format_tier(tier2, '🔄', '弱势修复')
    report += format_tier(tier3, '👀', '观察池')

    if not results:
        report += "\n⚠️ 今日无符合条件的股票\n"

    report += f"""
---

*数据来源: Tushare (120积分) + mootdx*
*筛选引擎: Alan Li Custom Screener v2.2 (技术面综合打分)*
"""

    return report

# ============ 主函数（批量查询版）============

def screen_stock_with_data(stock_code: str, stock_name: str, df: pd.DataFrame, zhuangjia_mode: bool = False) -> dict:
    """给定已获取的数据，筛选单只股票"""
    global ZHUANGJIA_AVAILABLE

    # 获取行业
    industry = get_stock_industry(stock_code)
    if industry in EXCLUDE_INDUSTRIES or any(kw in industry for kw in EXCLUDE_KEYWORDS):
        return None

    if df is None or len(df) < 30:
        return None

    # 三档分类
    tier, tier_name, reason = classify_tier_with_optimal(df)
    if tier == 0:
        return None

    # 庄家顶底信号
    zhuangjia_result = None
    if ZHUANGJIA_AVAILABLE:
        try:
            zhuangjia_result = check_zhuangjia_condition(df)
        except Exception:
            pass

    # 庄家模式过滤
    if zhuangjia_mode:
        if zhuangjia_result is None or zhuangjia_result['score'] < 50:
            return None

    # 计算技术面综合打分
    tech = calc_technical_score(df)
    tech_score = tech['score']

    # 档位基础分
    tier_base = {1: 70, 2: 55, 3: 40}.get(tier, 0)

    # 多头加分
    ma60 = df['收盘'].rolling(window=60).mean().iloc[-1] if len(df) >= 60 else 0
    ma120 = df['收盘'].rolling(window=120).mean().iloc[-1] if len(df) >= 120 else 0
    if ma60 > 0 and ma120 > 0 and df.iloc[-1]['收盘'] > ma60 > ma120:
        tier_base += 15

    # 动量
    change_pct = df.iloc[-1].get('涨跌幅', 0)
    if pd.isna(change_pct):
        change_pct = 0

    total_score = min(100, tier_base + tech_score // 2 + abs(change_pct))

    return {
        'code': stock_code,
        'name': stock_name,
        'industry': industry,
        'tier': tier,
        'tier_name': tier_name,
        'tier_reason': reason,
        'close': df.iloc[-1]['收盘'],
        'change_pct': change_pct,
        'volume': df.iloc[-1]['成交量'],
        'tech': tech,
        'rsi14': tech['rsi'],
        'zhuangjia': zhuangjia_result,
        'score': total_score,
    }


def main():
    import time
    parser = argparse.ArgumentParser(description='Alan Li 选股程序')
    parser.add_argument('--zhuangjia', action='store_true', help='庄家顶底模式')
    parser.add_argument('--mode', default='both', help='筛选模式: both/strong/observe')
    parser.add_argument('--min-score', type=int, default=0, help='最低评分')
    parser.add_argument('--max-results', type=int, default=10, help='每档最大结果数')
    args = parser.parse_args()

    mode_str = "（庄家顶底模式）" if args.zhuangjia else ""
    print("=" * 60)
    print(f"🚀 Alan Li 选股程序 v2.3 批量版{mode_str}")
    print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    stocks = get_csi1000_stocks()
    if not stocks:
        print("❌ 无法获取股票列表")
        return

    # 预加载行业数据
    _ = get_stock_industry(stocks[0]['code'])
    print(f"\n🔍 开始批量筛选...")
    print(f"   数据源: Tushare 批量查询 (50只/批)")

    if args.zhuangjia:
        print("   庄家顶底模式: 只输出信号 ≥ 50 分的股票")

    results = []
    stats = {1: 0, 2: 0, 3: 0, 0: 0}
    total = len(stocks)
    batch_size = 50

    all_codes = [s['code'] for s in stocks]
    name_map = {s['code']: s['name'] for s in stocks}

    # 批量查询
    from stock_client import get_daily_batch

    for batch_start in range(0, total, batch_size):
        batch_codes = all_codes[batch_start:batch_start+batch_size]
        pct = batch_start * 100 // total
        print(f"   进度: {batch_start}-{min(batch_start+batch_size,total)}/{total} ({pct}%)")

        batch_data = get_daily_batch(batch_codes, days=150)

        for code, df in batch_data.items():
            result = screen_stock_with_data(code, name_map.get(code, code), df, args.zhuangjia)
            if result and result['score'] >= args.min_score:
                results.append(result)
                stats[result['tier']] += 1
                emoji = {1: '📈', 2: '🔄', 3: '👀'}.get(result['tier'], '❓')
                print(f"   {emoji} {result['code']} {result['name']} - {result['tier_name']} ({result['score']}分)")

        # 限流：每批之间等1.5秒
        if batch_start + batch_size < total:
            time.sleep(1.5)

    print(f"\n📊 筛选完成:")
    print(f"   📈 第一档（强势）: {stats[1]} 只")
    print(f"   🔄 第二档（弱势修复）: {stats[2]} 只")
    print(f"   👀 第三档（观察池）: {stats[3]} 只")
    print(f"   总计: {len(results)} 只")

    # 限制每档数量
    if args.max_results:
        tier1 = [r for r in results if r['tier'] == 1][:args.max_results]
        tier2 = [r for r in results if r['tier'] == 2][:args.max_results]
        tier3 = [r for r in results if r['tier'] == 3][:args.max_results]
        results = tier1 + tier2 + tier3

    # 生成报告
    report = generate_report(results, args.zhuangjia)

    # 保存报告
    output_dir = Path.home() / ".openclaw" / "workspace" / "output" / "stock-reports"
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / f"{datetime.now().strftime('%Y-%m-%d')}-Alan定制选股.md"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\n✅ 报告已保存: {report_path}")

if __name__ == "__main__":
    main()
