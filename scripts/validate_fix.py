#!/usr/bin/env python3
"""
验证修复效果

在历史数据上模拟加入市场过滤后的效果
"""

import sys
import json
from pathlib import Path
import pandas as pd
import numpy as np

SHARED_DIR = Path('/Users/alanli/.openclaw/workspace/shared')
sys.path.insert(0, str(SHARED_DIR))

from stock_client import get_index_daily as get_daily

# 配置
MIN_CANDIDATES = 5
MAX_CANDIDATES = 15


def get_market_state(date: str) -> dict:
    """判断大盘状态"""
    df = get_daily('000300', start_date='20241001', end_date='20260331')
    
    if df is None or len(df) < 60:
        return {"state": "unknown", "can_select": True}
    
    date_dt = pd.to_datetime(date)
    df = df[df['日期'] <= date_dt].copy()
    
    if len(df) < 60:
        return {"state": "unknown", "can_select": True}
    
    current = df['收盘'].iloc[-1]
    ma20 = df['收盘'].rolling(20).mean().iloc[-1]
    ma60 = df['收盘'].rolling(60).mean().iloc[-1]
    
    if len(df) >= 6:
        ret_5d = (current - df['收盘'].iloc[-6]) / df['收盘'].iloc[-6]
    else:
        ret_5d = 0
    
    if current > ma20 > ma60:
        state = "offensive"
        can_select = True
    elif current > ma60:
        state = "balanced"
        can_select = True
    elif current > ma60 * 0.97:
        state = "defensive"
        can_select = True
    else:
        state = "bear"
        can_select = False
    
    if ret_5d < -0.05:
        state = "crash"
        can_select = False
    
    return {"state": state, "can_select": can_select}


def simulate_with_filter(history_file: str) -> dict:
    """在历史数据上模拟加入市场过滤后的效果"""
    
    # 加载历史数据
    records = []
    with open(history_file, 'r') as f:
        for line in f:
            r = json.loads(line)
            if r.get('forward_5d_return') is not None:
                records.append({
                    'date': r.get('date'),
                    'return': r.get('forward_5d_return') / 100,
                    'code': r.get('code'),
                    'score': r.get('score'),
                })
    
    # 按日期分组
    daily_data = {}
    for r in records:
        date = r['date']
        if date not in daily_data:
            daily_data[date] = []
        daily_data[date].append(r)
    
    returns_original = []
    returns_filtered = []
    dates = sorted(daily_data.keys())
    
    for date in dates:
        day_records = daily_data[date]
        candidate_count = len(day_records)
        avg_ret = np.mean([r['return'] for r in day_records])
        
        # 原始策略：无论什么情况都选股
        returns_original.append(avg_ret)
        
        # 过滤后策略
        market = get_market_state(date)
        
        if not market['can_select']:
            # 暂停选股 → 空仓，收益为0
            returns_filtered.append(0.0)
        elif candidate_count < MIN_CANDIDATES:
            # 候选不足 → 不选，收益为0
            returns_filtered.append(0.0)
        else:
            returns_filtered.append(avg_ret)
    
    # 计算指标
    def calc_metrics(returns, label=""):
        cum = 1.0
        peak = 1.0
        max_dd = 0.0
        
        for r in returns:
            cum *= (1 + r)
            peak = max(peak, cum)
            max_dd = max(max_dd, (peak - cum) / peak)
        
        non_zero = [r for r in returns if r != 0]
        wins = [r for r in non_zero if r >= 0.03]
        
        if non_zero:
            win_rate = len(wins) / len(non_zero)
            win_returns = [r for r in non_zero if r > 0]
            loss_returns = [r for r in non_zero if r < 0]
            
            if win_returns and loss_returns:
                avg_win = np.mean(win_returns)
                avg_loss = abs(np.mean(loss_returns))
                plr = avg_win / avg_loss
            else:
                plr = 0
        else:
            win_rate = 0
            plr = 0
        
        return {
            "win_rate": win_rate,
            "max_drawdown": max_dd,
            "profit_loss_ratio": plr,
            "active_days": len(non_zero),
            "idle_days": len([r for r in returns if r == 0]),
            "final_value": cum
        }
    
    original = calc_metrics(returns_original, "原始")
    filtered = calc_metrics(returns_filtered, "过滤后")
    
    print("=" * 70)
    print("📊 修复效果对比")
    print("=" * 70)
    
    print(f"\n{'指标':<12} {'原始策略':>12} {'加过滤后':>12} {'变化':>10}")
    print("-" * 70)
    
    print(f"{'胜率':<12} {original['win_rate']:>11.1%} {filtered['win_rate']:>11.1%} "
          f"{filtered['win_rate']-original['win_rate']:>+9.1%}")
    
    print(f"{'最大回撤':<12} {original['max_drawdown']:>11.1%} {filtered['max_drawdown']:>11.1%} "
          f"{filtered['max_drawdown']-original['max_drawdown']:>+9.1%}")
    
    print(f"{'盈亏比':<12} {original['profit_loss_ratio']:>12.2f} {filtered['profit_loss_ratio']:>12.2f} "
          f"{filtered['profit_loss_ratio']-original['profit_loss_ratio']:>+10.2f}")
    
    print(f"{'最终净值':<12} {original['final_value']:>12.2f} {filtered['final_value']:>12.2f} "
          f"{filtered['final_value']-original['final_value']:>+10.2f}")
    
    print(f"{'选股天数':<12} {original['active_days']:>12} {filtered['active_days']:>12} "
          f"{filtered['active_days']-original['active_days']:>+10}")
    
    print(f"{'空仓天数':<12} {'0':>12} {filtered['idle_days']:>12} "
          f"{filtered['idle_days']:>+10}")
    
    print("\n" + "=" * 70)
    
    # 判断效果
    if filtered['max_drawdown'] < 0.30:
        print("✅ 最大回撤已降至 30% 以内，可以启动 Cron 优化")
    elif filtered['max_drawdown'] < original['max_drawdown'] * 0.7:
        print("⚠️ 回撤有所改善但仍偏高，建议继续优化过滤条件")
    else:
        print("❌ 修复效果不明显，需要进一步诊断")
    
    return {"original": original, "filtered": filtered}


if __name__ == "__main__":
    history_file = Path('/Users/alanli/.openclaw/workspace/skills/a-stock-monitor/output/backtest/backtest_20250101_20260327_v2.jsonl')
    simulate_with_filter(str(history_file))