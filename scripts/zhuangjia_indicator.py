#!/usr/bin/env python3
"""
庄家顶底指标 - 以"始信号"为核心

核心信号：
- 始信号：短期线刚上穿中期线（今日金叉）
- 终信号：短期线 > 90，资金饱和，卖出区

注意：此为近似实现，仅供参考
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional


def calc_zhuangjia_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算庄家顶底指标
    
    输入: 日线 OHLCV DataFrame
    输出: 带信号列的 DataFrame
    """
    df = df.copy()
    
    # 1. 短期成本（EMA17）
    df['short_cost'] = df['收盘'].ewm(span=17, adjust=False).mean()
    
    # 2. 中期成本（加权平均价的 EMA13）
    df['A'] = (3 * df['收盘'] + df['最低'] + df['开盘'] + df['最高']) / 6
    
    weights = list(range(20, 0, -1))
    total_weight = sum(weights)
    
    df['X'] = _weighted_ma(df['A'], weights)
    df['mid_cost'] = df['X'].ewm(span=13, adjust=False).mean()
    
    # 3. 资金饱和度
    N4 = 34
    df['SAT'] = (df['成交额'] / df['收盘']) / (
        df['成交额'].rolling(N4).max() / df['收盘'].rolling(N4).max()
    )
    df['saturation'] = df['SAT'].clip(upper=1) * 100
    
    # 4. 持股强度
    N27 = 27
    low_min = df['最低'].rolling(N27).min()
    high_max = df['最高'].rolling(N27).max()
    range_val = high_max - low_min
    range_val = range_val.replace(0, np.nan)
    df['stoch'] = ((df['收盘'] - low_min) / range_val) * 100
    ma5_stoch = df['stoch'].rolling(5).mean()
    df['holding'] = 3 * ma5_stoch - 2 * ma5_stoch.rolling(3).mean()
    
    return df


def _weighted_ma(series: pd.Series, weights: list) -> pd.Series:
    result = []
    n = len(weights)
    total_weight = sum(weights)
    
    for i in range(len(series)):
        if i < n - 1:
            result.append(np.nan)
        else:
            window = series.iloc[i-n+1:i+1].values
            result.append(np.dot(window, weights) / total_weight)
    
    return pd.Series(result, index=series.index)


def check_zhuangjia_buy_signal(df: pd.DataFrame) -> dict:
    """
    检测庄家顶底"始"信号
    
    条件：短期线刚上穿中期线（今日金叉）
    
    Returns:
        signal: 是否触发始信号
        signal_type: 信号类型
        short_cost: 短期成本
        mid_cost: 中期成本
        saturation: 资金饱和度
        reason: 信号原因
    """
    if df is None or len(df) < 30:
        return {
            "signal": False,
            "signal_type": "数据不足",
            "short_cost": 0,
            "mid_cost": 0,
            "saturation": 0,
            "reason": "数据不足"
        }
    
    # 计算指标
    df = calc_zhuangjia_signals(df)
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    short_cost = latest['short_cost']
    mid_cost = latest['mid_cost']
    short_cost_prev = prev['short_cost']
    mid_cost_prev = prev['mid_cost']
    saturation = latest['saturation']
    close = latest['收盘']
    
    # 检查是否为 NaN
    if pd.isna(short_cost) or pd.isna(mid_cost) or pd.isna(short_cost_prev) or pd.isna(mid_cost_prev):
        return {
            "signal": False,
            "signal_type": "计算异常",
            "short_cost": 0,
            "mid_cost": 0,
            "saturation": saturation if not pd.isna(saturation) else 0,
            "reason": "指标计算异常"
        }
    
    # 核心：今天刚发生金叉（始信号）
    fresh_cross = (short_cost > mid_cost) and (short_cost_prev <= mid_cost_prev)
    
    # 已经在金叉状态
    already_above = (short_cost > mid_cost) and (short_cost_prev > mid_cost_prev)
    
    # 排除：资金饱和（终信号区域）
    saturated = short_cost > 85
    
    # 价格站在中线成本上方
    price_above_cost = close > mid_cost
    
    # 判断信号类型
    if fresh_cross and not saturated:
        signal = True
        signal_type = "始(今日金叉)"
        reason = f"始信号：短期线{short_cost:.2f}刚上穿中期线{mid_cost:.2f}"
    elif fresh_cross and saturated:
        signal = False
        signal_type = "始信号(但饱和)"
        reason = f"金叉但资金饱和({saturation:.1f}%)，谨慎"
    elif already_above and not saturated:
        signal = False
        signal_type = "持续上行"
        reason = f"短期{short_cost:.2f}持续>中期{mid_cost:.2f}"
    elif already_above and saturated:
        signal = False
        signal_type = "高位预警"
        reason = f"持续上行但饱和({saturation:.1f}%)，注意风险"
    else:
        signal = False
        signal_type = "未触发"
        reason = f"短期{short_cost:.2f}在中期{mid_cost:.2f}下方"
    
    return {
        "signal": signal,
        "signal_type": signal_type,
        "short_cost": round(short_cost, 2),
        "mid_cost": round(mid_cost, 2),
        "saturation": round(saturation, 1),
        "price_above_cost": price_above_cost,
        "saturated": saturated,
        "reason": reason
    }


def check_zhuangjia_condition(df: pd.DataFrame) -> dict:
    """
    旧版兼容接口
    """
    result = check_zhuangjia_buy_signal(df)
    
    # 转换为旧格式
    score = 0
    if result['signal']:
        score = 100
    elif result['signal_type'] == '持续上行':
        score = 70
    elif result['signal_type'] == '高位预警':
        score = 50
    
    signal_desc = None
    if result['signal']:
        signal_desc = "🟢 庄家始信号"
    elif result['signal_type'] == '持续上行':
        signal_desc = "⚡ 持续上行"
    elif score >= 50:
        signal_desc = "⚠️ " + result['signal_type']
    
    return {
        "buy_cross": result['signal'],
        "above_cost": result['price_above_cost'],
        "not_saturated": not result['saturated'],
        "holding_rising": False,  # 简化
        "saturation_value": result['saturation'],
        "holding_value": 50,  # 简化
        "score": score,
        "signal": signal_desc,
        "short_cost": result['short_cost'],
        "mid_cost": result['mid_cost'],
        "reason": result['reason'],
    }


# ============ 测试 ============

if __name__ == "__main__":
    # 测试容知日新 688768
    import sys
    from pathlib import Path
    
    SHARED_DIR = Path('/Users/alanli/.openclaw/workspace/shared')
    sys.path.insert(0, str(SHARED_DIR))
    
    from stock_client import get_daily_realtime
    
    print("=" * 60)
    print("📊 庄家顶底始信号测试 - 容知日新 688768")
    print("=" * 60)
    
    df = get_daily_realtime('688768', days=60)
    
    if df is not None and len(df) >= 30:
        print(f"\n数据范围: {df.iloc[0]['日期']} ~ {df.iloc[-1]['日期']}")
        print(f"数据条数: {len(df)}")
        
        result = check_zhuangjia_buy_signal(df)
        
        print(f"\n【庄家顶底信号】")
        print(f"  信号类型: {result['signal_type']}")
        print(f"  触发信号: {'✅ 是' if result['signal'] else '❌ 否'}")
        print(f"  短期成本: {result['short_cost']}")
        print(f"  中期成本: {result['mid_cost']}")
        print(f"  资金饱和度: {result['saturation']}%")
        print(f"  价格在成本线上方: {'✅' if result['price_above_cost'] else '❌'}")
        print(f"  原因: {result['reason']}")
        
        # 显示最近5天
        df_signals = calc_zhuangjia_signals(df)
        print(f"\n最近5天数据:")
        cols = ['日期', '收盘', 'short_cost', 'mid_cost', 'saturation']
        print(df_signals[cols].tail(5).to_string(index=False))
    else:
        print("❌ 数据不足")
    
    print("\n" + "=" * 60)