#!/usr/bin/env python3
"""
大盘状态过滤模块

判断当前大盘状态，决定是否选股
"""

import sys
from pathlib import Path
import pandas as pd
from datetime import datetime, timedelta

SHARED_DIR = Path('/Users/alanli/.openclaw/workspace/shared')
sys.path.insert(0, str(SHARED_DIR))

from stock_client import get_index_daily


def get_market_state(date: str) -> dict:
    """
    判断当前大盘状态

    Args:
        date: YYYYMMDD 格式

    Returns:
        state: 状态（offensive/balanced/defensive/bear/crash）
        can_select: 是否可以选股
        reason: 原因说明
    """
    # 获取沪深300数据（用AKShare，无需token）
    df = get_index_daily('000300', start_date='20241001', end_date='20260331')

    if df is None or len(df) < 60:
        return {"state": "unknown", "can_select": True, "reason": "数据不足，默认可选"}

    # 过滤到指定日期之前
    date_dt = pd.to_datetime(date)
    df = df[df['日期'] <= date_dt].copy()

    if len(df) < 60:
        return {"state": "unknown", "can_select": True, "reason": "数据不足，默认可选"}

    current = df['收盘'].iloc[-1]
    ma20 = df['收盘'].rolling(20).mean().iloc[-1]
    ma60 = df['收盘'].rolling(60).mean().iloc[-1]

    # 近5日涨跌
    if len(df) >= 6:
        ret_5d = (current - df['收盘'].iloc[-6]) / df['收盘'].iloc[-6]
    else:
        ret_5d = 0

    # 状态判断
    if current > ma20 > ma60:
        state = "offensive"
        can_select = True
        reason = "大盘多头（价格>MA20>MA60），正常选股"
    elif current > ma60:
        state = "balanced"
        can_select = True
        reason = "大盘均衡（价格>MA60），正常选股"
    elif current > ma60 * 0.97:
        state = "defensive"
        can_select = True
        reason = "大盘偏弱（价格接近MA60），谨慎选股"
    else:
        state = "bear"
        can_select = False
        reason = f"大盘弱势（价格<{ma60*0.97:.0f}），暂停选股"

    # 额外规则：近5日大盘跌超5%，无论如何暂停
    if ret_5d < -0.05:
        state = "crash"
        can_select = False
        reason = f"近5日大盘急跌{ret_5d:.1%}，暂停选股"

    return {
        "state": state,
        "can_select": can_select,
        "current": round(current, 2),
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2),
        "ret_5d": round(ret_5d, 4),
        "reason": reason
    }


def get_market_regime(date: str = None) -> dict:
    """
    二八轮动：判断当前是大盘股还是小盘股行情

    逻辑：
    - 沪深300（大盘）vs 中证1000（小盘）近20日相对强弱
    - 大盘强 -> 选股偏向大市值、低波动标的
    - 小盘强 -> 选股偏向中小市值、高弹性标的
    - 均衡 -> 不偏向
    """
    try:
        import akshare as ak

        # 获取沪深300
        hs300 = get_index_daily('000300')
        if hs300 is None or len(hs300) < 25:
            return {"regime": "balanced", "advice": "数据不足，默认均衡"}

        # 获取中证1000
        zz1000 = get_index_daily('000852')
        if zz1000 is None or len(zz1000) < 25:
            return {"regime": "balanced", "advice": "数据不足，默认均衡"}

        # 按日期对齐
        hs300 = hs300.sort_values('日期').reset_index(drop=True)
        zz1000 = zz1000.sort_values('日期').reset_index(drop=True)

        # 取最新共同日期
        latest_date = min(hs300['日期'].iloc[-1], zz1000['日期'].iloc[-1])
        hs300_latest = hs300[hs300['日期'] <= latest_date].tail(25)
        zz1000_latest = zz1000[zz1000['日期'] <= latest_date].tail(25)

        r300 = (hs300_latest['收盘'].iloc[-1] - hs300_latest['收盘'].iloc[0]) / hs300_latest['收盘'].iloc[0]
        r1000 = (zz1000_latest['收盘'].iloc[-1] - zz1000_latest['收盘'].iloc[0]) / zz1000_latest['收盘'].iloc[0]

        diff = r1000 - r300  # 小盘相对大盘的超额收益

        if diff > 0.03:
            regime = "small_cap"
            advice = "小盘股领涨，关注中小市值题材股"
        elif diff < -0.03:
            regime = "large_cap"
            advice = "大盘股领涨，关注龙头蓝筹"
        else:
            regime = "balanced"
            advice = "大小盘均衡，正常选股"

        return {
            "regime": regime,
            "advice": advice,
            "hs300_20d": round(r300, 4),
            "zz1000_20d": round(r1000, 4),
            "diff": round(diff, 4)
        }
    except Exception as e:
        return {"regime": "balanced", "advice": f"数据获取失败，默认均衡 ({e})"}


if __name__ == "__main__":
    # 测试几个关键日期
    test_dates = [
        "20250610",  # 2025年6月大跌期间
        "20251008",  # 2025年10月大跌期间
        "20260327",  # 近期
    ]

    print("=" * 60)
    print("📊 大盘状态测试")
    print("=" * 60)

    for date in test_dates:
        result = get_market_state(date)
        print(f"\n{date}:")
        print(f"  状态: {result['state']}")
        print(f"  可选股: {result['can_select']}")
        print(f"  原因: {result['reason']}")
        print(f"  沪深300: {result['current']} (MA20={result['ma20']}, MA60={result['ma60']})")

    print("\n" + "=" * 60)
    print("📊 二八轮动测试")
    print("=" * 60)
    regime = get_market_regime()
    print(f"  市道: {regime['regime']}")
    print(f"  建议: {regime['advice']}")
    print(f"  沪深300 20日涨跌: {regime.get('hs300_20d', 'N/A')}")
    print(f"  中证1000 20日涨跌: {regime.get('zz1000_20d', 'N/A')}")
    print(f"  相对强弱差: {regime.get('diff', 'N/A')}")
