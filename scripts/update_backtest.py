#!/usr/bin/env python3
"""
每周六运行，追加最新一周的回测数据到 v3.jsonl
增量追加：计算所有 v3 字段
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

sys.path.insert(0, '/Users/alanli/.openclaw/workspace/shared')
from stock_client import get_daily

BACKTEST_FILE = Path('/Users/alanli/.openclaw/workspace/skills/a-stock-monitor/output/backtest/backtest_20250101_20260327_v3.jsonl')


def _calc_boll_position(df: pd.DataFrame) -> float:
    if len(df) < 20:
        return 0.5
    mid = df['收盘'].rolling(20).mean().iloc[-1]
    std = df['收盘'].rolling(20).std().iloc[-1]
    upper = mid + 2 * std
    lower = mid - 2 * std
    close = df['收盘'].iloc[-1]
    if upper == lower:
        return 0.5
    return round((close - lower) / (upper - lower), 3)


def get_last_date() -> str:
    last_date = '20250101'
    with open(BACKTEST_FILE) as f:
        for line in f:
            r = json.loads(line)
            d = r.get('date', '').replace('-', '')
            if d > last_date:
                last_date = d
    return last_date


def update():
    last_date = get_last_date()
    today = datetime.now().strftime('%Y%m%d')

    print(f"当前数据截至：{last_date}")
    print(f"需要补充到：{today}")

    if last_date >= today:
        print("数据已是最新，无需更新")
        return

    # 获取已有记录里出现过的股票代码
    codes = set()
    with open(BACKTEST_FILE) as f:
        for line in f:
            r = json.loads(line)
            if r.get('code'):
                codes.add(r['code'])

    codes = list(codes)[:100]
    print(f"更新 {len(codes)} 只股票的数据")

    new_records = []

    for code in codes:
        # 多拉60天历史，用于计算新字段
        df = get_daily(code, days=120)
        if df is None or len(df) < 60:
            continue

        last_date_dt = datetime.strptime(last_date, '%Y%m%d')
        df_future = df[df['日期'] > last_date_dt].copy()
        if len(df_future) < 6:
            continue

        # 遍历新日期（每5天一取样，避免重复）
        for i in range(0, len(df_future) - 5, 5):
            row = df_future.iloc[i]
            date_str = row['日期'].strftime('%Y-%m-%d')

            # 合并历史数据（用于计算指标）
            all_before = df[df['日期'] <= row['日期']].copy()
            if len(all_before) < 30:
                continue

            close = row['收盘']
            change_pct = row.get('涨跌幅', 0)

            ma5  = all_before['收盘'].rolling(5).mean().iloc[-1]
            ma10 = all_before['收盘'].rolling(10).mean().iloc[-1]
            ma20 = all_before['收盘'].rolling(20).mean().iloc[-1]

            vol_ma5 = all_before['成交量'].rolling(5).mean().iloc[-1]
            vol_ratio = close / vol_ma5 if vol_ma5 > 0 else 1

            # RSI
            delta = all_before['收盘'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi_val = 50 if pd.isna(rs.iloc[-1]) else (100 - 100 / (1 + rs)).iloc[-1]
            if pd.isna(rsi_val):
                rsi_val = 50

            # 三档判断
            tier = 0
            tier_name = ""
            reason = ""
            if close > ma20 and ma5 > ma10 > ma20 and vol_ratio > 1.2:
                tier = 1
                tier_name = "强势"
                reason = f"MA多头+放量{vol_ratio:.1f}倍"
            elif close > ma20 and vol_ratio > 1.5:
                ma5_prev = all_before['收盘'].rolling(5).mean().iloc[-2]
                ma10_prev = all_before['收盘'].rolling(10).mean().iloc[-2]
                if ma5 > ma10 and ma5_prev <= ma10_prev:
                    tier = 2
                    tier_name = "弱势修复"
                    reason = f"金叉+放量{vol_ratio:.1f}倍"
            elif close > ma20 and 35 <= rsi_val <= 65:
                rsi_prev3 = rsi.iloc[-4] if len(rs) > 3 else rsi_val
                if rsi_prev3 < 35:
                    tier = 3
                    tier_name = "观察池"
                    reason = "RSI从" + str(int(rsi_prev3)) + "回升至" + str(int(rsi_val))

            if tier == 0:
                continue

            # 前向5日收益
            if i + 5 < len(df_future):
                fwd = (df_future.iloc[i + 5]['收盘'] - close) / close * 100
            else:
                continue

            # 计算 v3 新字段
            ma20_5d_ago = all_before['收盘'].rolling(20).mean().iloc[-6] if len(all_before) >= 26 else ma20
            ma20_slope = round((ma20 - ma20_5d_ago) / ma20 * 100, 3) if ma20 != 0 else 0
            close_vs_ma20_pct = round((close - ma20) / ma20 * 100, 2) if ma20 != 0 else 0
            ma60 = all_before['收盘'].rolling(60).mean().iloc[-1] if len(all_before) >= 60 else ma20
            close_vs_ma60_pct = round((close - ma60) / ma60 * 100, 2) if ma60 != 0 else 0
            vol_3d_increasing = bool(
                len(all_before) >= 3 and
                all_before['成交量'].iloc[-1] > all_before['成交量'].iloc[-2] > all_before['成交量'].iloc[-3]
            )
            ema12 = all_before['收盘'].ewm(span=12).mean()
            ema26 = all_before['收盘'].ewm(span=26).mean()
            macd_line = ema12 - ema26
            macd_above_zero = bool(macd_line.iloc[-1] > 0) if len(all_before) >= 26 else False
            macd_golden_cross = bool(
                len(all_before) >= 27 and macd_line.iloc[-1] > 0 and macd_line.iloc[-2] <= 0
            ) if len(all_before) >= 27 else False
            boll_position = _calc_boll_position(all_before)
            momentum_5d = round((close - all_before['收盘'].iloc[-6]) / all_before['收盘'].iloc[-6] * 100, 2) \
                if len(all_before) >= 6 else 0
            momentum_20d = round((close - all_before['收盘'].iloc[-21]) / all_before['收盘'].iloc[-21] * 100, 2) \
                if len(all_before) >= 21 else 0
            is_20d_high = bool(close >= all_before['最高'].tail(20).max()) if len(all_before) >= 20 else False

            # 评分
            score = {1: 70, 2: 55, 3: 40}.get(tier, 0)
            if change_pct > 0:
                score = min(100, score + abs(change_pct))

            new_records.append({
                'date': date_str,
                'code': code,
                'tier': tier,
                'tier_name': tier_name,
                'reason': reason,
                'close': round(float(close), 2),
                'change_pct': round(float(change_pct), 2),
                'forward_5d_return': round(float(fwd), 2),
                'score': round(float(score), 1),
                'ma5': round(float(ma5), 2),
                'ma10': round(float(ma10), 2),
                'ma20': round(float(ma20), 2),
                'vol_ratio': round(float(vol_ratio), 2),
                'rsi': round(float(rsi_val), 1),
                'ma20_slope': ma20_slope,
                'close_vs_ma20_pct': close_vs_ma20_pct,
                'close_vs_ma60_pct': close_vs_ma60_pct,
                'vol_3d_increasing': vol_3d_increasing,
                'macd_above_zero': macd_above_zero,
                'macd_golden_cross': macd_golden_cross,
                'boll_position': boll_position,
                'momentum_5d': momentum_5d,
                'momentum_20d': momentum_20d,
                'is_20d_high': is_20d_high,
            })

    # 追加到文件
    with open(BACKTEST_FILE, 'a') as f:
        for r in new_records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    print(f"✅ 新增 {len(new_records)} 条记录")
    print(f"数据已更新到 {today}")


if __name__ == "__main__":
    update()
