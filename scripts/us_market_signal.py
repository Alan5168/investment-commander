#!/usr/bin/env python3
"""
美股信号分析
1. 分析纳指/道指/标普前1-5日热门题材
2. YANG指数监控（YANG涨 → 次日A股大概率跌）
"""

import akshare as ak
import pandas as pd
from datetime import datetime, timedelta


def get_yang_signal() -> dict:
    """
    YANG（三倍做空富时中国ETF）信号
    YANG大涨 -> 次日A股大概率下跌
    YANG大跌 -> 次日A股可能反弹
    """
    try:
        df = ak.stock_us_daily(symbol="YANG", adjust="")
        df = df.sort_values('date').tail(6)

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        yang_change = (latest['close'] - prev['close']) / prev['close']

        df['ret'] = df['close'].pct_change()
        yang_5d_avg = df['ret'].tail(5).mean()

        if yang_change > 0.05:
            signal = 'bearish'
            advice = f"⚠️ YANG昨日涨{yang_change:.1%}，今日A股注意回避风险"
        elif yang_change < -0.05:
            signal = 'bullish'
            advice = f"✅ YANG昨日跌{yang_change:.1%}，今日A股可能偏强"
        else:
            signal = 'neutral'
            advice = f"YANG昨日变动{yang_change:.1%}，信号中性"

        return {
            'yang_change': round(yang_change, 4),
            'yang_5d_avg': round(yang_5d_avg, 4),
            'signal': signal,
            'advice': advice,
            'date': str(latest['date'])
        }
    except Exception as e:
        return {'signal': 'unknown', 'advice': f'YANG数据获取失败: {e}'}


def get_us_hot_sectors(lookback_days: int = 3) -> dict:
    """
    获取美股近N日热门题材
    映射到A股催化剂关键词
    """
    try:
        results = []

        for etf, name in [('QQQ', '纳指'), ('SPY', '标普500')]:
            df = ak.stock_us_daily(symbol=etf, adjust="")
            df = df.sort_values('date').tail(lookback_days + 1)
            ret = (df.iloc[-1]['close'] - df.iloc[-lookback_days-1]['close']) / \
                  df.iloc[-lookback_days-1]['close']
            results.append({'etf': etf, 'name': name, 'return': ret})

        qqq_ret = next(r['return'] for r in results if r['etf'] == 'QQQ')

        catalysts = []
        if qqq_ret > 0.02:
            catalysts.extend(['AI', '算力', '芯片'])
        if qqq_ret > 0.05:
            catalysts.extend(['半导体', '大模型'])

        return {
            'lookback_days': lookback_days,
            'qqq_return': round(qqq_ret, 4),
            'suggested_catalysts': catalysts,
            'summary': f"纳指近{lookback_days}日{'上涨' if qqq_ret > 0 else '下跌'}{abs(qqq_ret):.1%}"
        }
    except Exception as e:
        return {'suggested_catalysts': [], 'summary': f'美股数据获取失败: {e}'}


def get_morning_context() -> dict:
    """
    早上8:50推送前调用
    整合YANG信号 + 美股热门题材
    """
    yang = get_yang_signal()
    us_sectors = get_us_hot_sectors(lookback_days=3)

    return {
        'yang_signal': yang,
        'us_market': us_sectors,
        'auto_catalyst': us_sectors.get('suggested_catalysts', []),
        'risk_warning': yang['signal'] == 'bearish'
    }


if __name__ == "__main__":
    ctx = get_morning_context()
    print("=== 早盘市场背景 ===")
    print(f"YANG信号: {ctx['yang_signal']['advice']}")
    print(f"美股背景: {ctx['us_market']['summary']}")
    print(f"建议题材: {ctx['auto_catalyst']}")
    if ctx['risk_warning']:
        print("⚠️ 风险预警：今日建议轻仓或观望")
