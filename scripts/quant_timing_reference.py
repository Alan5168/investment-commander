#!/usr/bin/env python3
"""
量化择时参考模块

5个择时信号：
1. 动量择时（MA20/60 + 量比）
2. 市场情绪（近20日涨跌比例）
3. RSI 超买超卖
4. VaR 风险参考（波动率）
5. 庄家顶底始信号

权重：产业逻辑 70%，量化择时 30%
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
import pandas as pd
import numpy as np

# 添加 shared 目录
SHARED_DIR = Path('/Users/alanli/.openclaw/workspace/shared')
sys.path.insert(0, str(SHARED_DIR))

from stock_client import get_daily_realtime


def calc_quant_timing_score(code: str, days: int = 120) -> dict:
    """
    量化择时参考评分（0-100）
    
    Args:
        code: 股票代码
        days: 历史数据天数
    
    Returns:
        total_score: 综合评分
        interpretation: 评分解读
        signals: 各信号明细
        disclaimer: 免责声明
    """
    # 获取数据
    df = get_daily_realtime(code, days=days)
    
    if df is None or len(df) < 60:
        return {
            'total_score': 0,
            'interpretation': '数据不足，无法计算',
            'signals': {},
            'disclaimer': '⚠️ 量化择时仅供参考，决策以产业逻辑为主'
        }
    
    signals = {}
    
    # ============ 信号 1：动量择时 ============
    ma20 = df['收盘'].rolling(20).mean().iloc[-1]
    ma60 = df['收盘'].rolling(60).mean().iloc[-1] if len(df) >= 60 else df['收盘'].mean()
    price = df['收盘'].iloc[-1]
    vol_ratio = df['成交量'].iloc[-1] / df['成交量'].rolling(5).mean().iloc[-1] if df['成交量'].rolling(5).mean().iloc[-1] > 0 else 1
    
    momentum_score = 0
    momentum_detail = []
    
    if price > ma20 > ma60:
        momentum_score += 40
        momentum_detail.append(f"MA20({ma20:.1f})>MA60({ma60:.1f})")
    elif price > ma20:
        momentum_score += 20
        momentum_detail.append(f"价格>MA20({ma20:.1f})")
    else:
        momentum_detail.append(f"价格<{ma20:.1f}")
    
    if vol_ratio > 1.5:
        momentum_score += 20
        momentum_detail.append(f"放量{vol_ratio:.1f}倍")
    elif vol_ratio > 1.0:
        momentum_score += 10
        momentum_detail.append(f"量比{vol_ratio:.1f}")
    else:
        momentum_detail.append(f"缩量{vol_ratio:.1f}")
    
    signals['momentum'] = {
        'score': momentum_score,
        'detail': ' | '.join(momentum_detail)
    }
    
    # ============ 信号 2：市场情绪 ============
    recent_returns = df['收盘'].pct_change().tail(20)
    up_days = (recent_returns > 0).sum()
    sentiment_score = int(up_days / 20 * 100)
    
    if sentiment_score > 55:
        sentiment_label = '偏多'
    elif sentiment_score > 45:
        sentiment_label = '中性'
    else:
        sentiment_label = '偏空'
    
    signals['sentiment'] = {
        'score': sentiment_score,
        'detail': f"近20日上涨{up_days}天，情绪{sentiment_label}"
    }
    
    # ============ 信号 3：RSI ============
    delta = df['收盘'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi_val = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
    
    if 40 <= rsi_val <= 65:
        rsi_score = 60
        rsi_label = '健康区间'
    elif rsi_val < 30:
        rsi_score = 80
        rsi_label = '超卖，反弹机会'
    elif rsi_val > 80:
        rsi_score = 10
        rsi_label = '超买，风险区'
    else:
        rsi_score = 40
        rsi_label = '中性'
    
    signals['rsi'] = {
        'score': rsi_score,
        'detail': f"RSI(14)={rsi_val:.1f}，{rsi_label}"
    }
    
    # ============ 信号 4：VaR 风险参考 ============
    returns = df['收盘'].pct_change().tail(20)
    volatility = returns.std() * (252 ** 0.5)  # 年化波动率
    var_95 = returns.quantile(0.05)  # 95% VaR
    
    if volatility < 0.3:
        var_score = 70
        var_label = '低波动'
    elif volatility < 0.5:
        var_score = 50
        var_label = '中等波动'
    else:
        var_score = 20
        var_label = '高波动'
    
    signals['var'] = {
        'score': var_score,
        'detail': f"年化波动率{volatility:.1%}，单日最大亏损{var_95:.1%}，{var_label}"
    }
    
    # ============ 信号 5：庄家顶底始信号 ============
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from zhuangjia_indicator import check_zhuangjia_buy_signal
        zj = check_zhuangjia_buy_signal(df)
        
        if zj['signal']:
            zj_score = 80
        elif zj['signal_type'] == '持续上行':
            zj_score = 50
        else:
            zj_score = 20
        
        signals['zhuangjia'] = {
            'score': zj_score,
            'detail': zj['reason']
        }
    except Exception as e:
        signals['zhuangjia'] = {
            'score': 40,
            'detail': f"庄家指标计算异常"
        }
    
    # ============ 综合评分 ============
    weights = {
        'momentum': 0.30,
        'sentiment': 0.20,
        'rsi': 0.20,
        'var': 0.15,
        'zhuangjia': 0.15
    }
    
    total_score = sum(
        signals[k]['score'] * weights[k]
        for k in weights
    )
    
    # 解读
    if total_score >= 70:
        interpretation = "量化信号偏强，技术面支持介入"
    elif total_score >= 50:
        interpretation = "量化信号中性，建议结合产业逻辑判断"
    else:
        interpretation = "量化信号偏弱，建议观望或等待更好时机"
    
    return {
        'total_score': round(total_score, 1),
        'interpretation': interpretation,
        'signals': signals,
        'disclaimer': "⚠️ 量化择时仅供参考，决策以产业逻辑为主"
    }


def format_quant_report(code: str, name: str, result: dict) -> str:
    """格式化量化择时报告"""
    
    lines = [
        f"📐 量化择时参考（{code} {name}）",
        "",
        f"综合评分：{result['total_score']}/100 — {result['interpretation']}",
        "",
        "信号明细："
    ]
    
    signal_names = {
        'momentum': '动量择时',
        'sentiment': '市场情绪',
        'rsi': 'RSI状态',
        'var': '风险参考',
        'zhuangjia': '庄家信号'
    }
    
    for key, label in signal_names.items():
        if key in result['signals']:
            s = result['signals'][key]
            lines.append(f"  {label}：{s['score']}/100  {s['detail']}")
    
    lines.append("")
    lines.append(result['disclaimer'])
    
    return '\n'.join(lines)


# ============ 测试 ============

if __name__ == "__main__":
    print("=" * 60)
    print("📊 量化择时参考测试")
    print("=" * 60)
    
    # 测试 688190
    code = '688190'
    name = '云路先进材料'
    
    result = calc_quant_timing_score(code)
    report = format_quant_report(code, name, result)
    
    print()
    print(report)
    print("\n" + "=" * 60)