#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
战绩追踪器 - performance_tracker.py
版本: 1.2.0
作者: Alan Li
日期: 2026-04-05

功能：追踪 Investment Commander 每天推荐的股票实际表现
输入：
  - 主数据源：workspace/skills/a-stock-monitor/output/recommendations/
  - 冷启动：自动扫描历史推荐记录
输出：data/performance/{date}.jsonl
判定：win(10日收益>5%) / fail(回撤>5%或触发止损) / neutral
触发：每天 16:30（收盘后）
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 路径配置
WORKSPACE = Path.home() / ".openclaw" / "workspace"
SKILL_DIR = WORKSPACE / "skills" / "a-stock-monitor"
DATA_DIR = Path(__file__).parent.parent / "data" / "performance"
REC_DIR = SKILL_DIR / "output" / "recommendations"
SHARED_DIR = WORKSPACE / "shared"

# 确保目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 导入 Tushare 数据客户端
sys.path.insert(0, str(SHARED_DIR))
try:
    from stock_client import get_daily
    HAS_STOCK_CLIENT = True
except ImportError:
    HAS_STOCK_CLIENT = False
    print("[警告] 未找到 stock_client，将使用备用方案")


def send_telegram_notification(message: str):
    """通过 OpenClaw Telegram session 推送"""
    import subprocess
    cmd = [
        'openclaw', 'message', 'send',
        '--channel', 'telegram',
        '--target', '8710019510',
        '--message', message
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=15)
    except Exception as e:
        print(f"[通知] Telegram 推送失败: {e}")


def get_stock_returns(stock_code: str, recommend_date: str) -> dict:
    """
    获取推荐后3/5/10日真实收益
    用 stock_client.get_daily（Tushare主力，AKShare降级）
    """
    if not HAS_STOCK_CLIENT:
        return {'error': 'stock_client 不可用'}

    try:
        # 拉推荐日期后20个交易日的数据
        df = get_daily(
            stock_code,
            start_date=recommend_date.replace('-', ''),
            days=30
        )

        if df is None or len(df) < 2:
            return {'error': '数据不足'}

        df = df.sort_values('日期').reset_index(drop=True)
        entry_price = df.iloc[0]['收盘']  # 推荐日收盘价作为基准

        def get_return(n_days):
            if len(df) > n_days:
                return round(
                    (df.iloc[n_days]['收盘'] - entry_price) / entry_price, 4
                )
            return None

        returns = {
            'entry_price': round(entry_price, 2),
            'return_3d': get_return(3),
            'return_5d': get_return(5),
            'return_10d': get_return(10),
        }

        # 计算最大回撤（前10日）
        if len(df) >= 10:
            prices = df.iloc[:11]['收盘'].values
            peak = prices[0]
            max_dd = 0
            for p in prices:
                if p > peak:
                    peak = p
                dd = (peak - p) / peak
                if dd > max_dd:
                    max_dd = dd
            returns['max_drawdown'] = round(-max_dd, 4)
        else:
            returns['max_drawdown'] = 0.0

        # 判断结果
        r5 = returns.get('return_5d', 0) or 0
        r10 = returns.get('return_10d', 0) or 0
        dd = returns.get('max_drawdown', 0) or 0

        if max(r5, r10) >= 0.05:
            returns['result'] = 'win'
        elif dd <= -0.05 or min(r5, r10) <= -0.05:
            returns['result'] = 'fail'
        else:
            returns['result'] = 'neutral'

        return returns

    except Exception as e:
        return {'error': str(e)}


def parse_recommendation_file(file_path: Path):
    """解析单个推荐文件，返回推荐股票列表"""
    recommendations = []
    try:
        content = file_path.read_text(encoding="utf-8")
        # 提取日期
        date_m = re.search(r'\*\*时间\*\*[：:]?\s*(\d{4}-\d{2}-\d{2})', content)
        rec_date = date_m.group(1) if date_m else file_path.stem[:10]

        # 提取所有 6 位股票代码
        all_codes = re.findall(r'\b([68]\d{5})\b', content)
        unique_codes = list(dict.fromkeys(all_codes))  # 去重保持顺序

        # 提取推荐理由（紧跟在代码后面的文本）
        lines = content.split("\n")
        current_code = None
        current_name = ""
        current_reason = ""

        for line in lines:
            code_m = re.search(r'\b([68]\d{5})\b', line)
            if code_m:
                # 保存上一个
                if current_code and current_code in unique_codes:
                    recommendations.append({
                        "stock_code": current_code,
                        "stock_name": current_name.strip(),
                        "recommend_reason": current_reason.strip(),
                        "recommend_date": rec_date,
                    })
                current_code = code_m.group(1)
                # 提取名称（代码后的第一个词）
                name_part = re.sub(current_code, '', line).strip()
                current_name = name_part[:20]
                current_reason = ""
            elif current_code:
                # 收集推荐理由
                for kw in ["产业", "催化", "受益", "逻辑", "推荐"]:
                    if kw in line:
                        current_reason += line.strip() + " "
                        break

        # 保存最后一个
        if current_code and current_code in unique_codes:
            recommendations.append({
                "stock_code": current_code,
                "stock_name": current_name.strip(),
                "recommend_reason": current_reason.strip(),
                "recommend_date": rec_date,
            })

    except Exception as e:
        print(f"[解析] 读取 {file_path} 出错: {e}")

    return recommendations


def get_historical_recommendations() -> list:
    """
    冷启动：从现有的推荐文件里提取历史记录
    路径：a-stock-monitor/output/recommendations/
    """
    records = []
    if not REC_DIR.exists():
        print(f"[冷启动] 推荐目录不存在: {REC_DIR}")
        return records

    for f in sorted(REC_DIR.glob("*.md")):
        recs = parse_recommendation_file(f)
        records.extend(recs)
        print(f"  解析 {f.name}: {len(recs)} 条推荐")

    return records


def get_recommendations_for_date(target_date: str = None) -> list:
    """获取指定日期的推荐记录"""
    if target_date is None:
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    date_formatted = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:8]}"

    # 直接解析当天的推荐文件
    rec_file = REC_DIR / f"{date_formatted}-推荐.md"
    if rec_file.exists():
        recs = parse_recommendation_file(rec_file)
        if recs:
            print(f"[战绩追踪] 从 {rec_file.name} 解析到 {len(recs)} 条推荐")
            return recs

    # 冷启动：从所有历史文件扫描
    print(f"[战绩追踪] 未找到 {target_date} 的推荐文件，尝试冷启动...")
    all_recs = get_historical_recommendations()
    filtered = [r for r in all_recs if r.get("recommend_date", "").replace("-", "") == target_date]
    if filtered:
        print(f"[战绩追踪] 冷启动找到 {len(filtered)} 条目标日期推荐")
    return filtered


def track_performance(target_date: str = None, cold_start: bool = False):
    """主函数：追踪指定日期的推荐股票表现"""
    if target_date is None:
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    print(f"[战绩追踪器] 开始追踪 {target_date} 的推荐记录...")

    # 1. 提取推荐记录
    if cold_start:
        recommendations = get_historical_recommendations()
        recommendations = [r for r in recommendations if r.get("stock_code")]
        print(f"[冷启动] 共提取 {len(recommendations)} 条历史推荐")
    else:
        recommendations = get_recommendations_for_date(target_date)

    if not recommendations:
        print(f"[战绩追踪器] 未找到 {target_date} 的推荐记录")
        return []

    # 2. 追踪每只股票表现
    results = []
    for rec in recommendations:
        code = rec["stock_code"]
        rec_date = rec.get("recommend_date", "")

        print(f"  查询 {code} {rec.get('stock_name', '')} 从 {rec_date} 开始...")

        # 用 Tushare 获取真实收益
        returns_data = get_stock_returns(code, rec_date)

        # Convert numpy types to native Python for JSON serialization
        for k, v in returns_data.items():
            if hasattr(v, 'item'):  # numpy scalar
                returns_data[k] = v.item()
            elif hasattr(v, 'tolist'):  # numpy array
                returns_data[k] = float(v)

        if 'error' in returns_data:
            print(f"    ⚠️ 数据获取失败: {returns_data['error']}")
            # 跳过无法获取数据的股票
            continue

        result_status = returns_data.get('result', 'neutral')

        record = {
            "recommend_date": rec_date.replace('-', ''),
            "stock_code": code,
            "stock_name": rec.get("stock_name", ""),
            "recommend_reason": rec.get("recommend_reason", ""),
            "entry_price": returns_data.get("entry_price", 0),
            "stop_loss": rec.get("stop_loss", 0),
            "industry_score": rec.get("industry_score", 0),
            "quant_score": rec.get("quant_score", 0),
            "return_3d": returns_data.get("return_3d"),
            "return_5d": returns_data.get("return_5d"),
            "return_10d": returns_data.get("return_10d"),
            "max_drawdown": returns_data.get("max_drawdown", 0),
            "result": result_status,
            "tracked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        results.append(record)
        print(f"    入场价:{returns_data.get('entry_price')} "
              f"3日:{(returns_data.get('return_3d') or 0):.2%} "
              f"5日:{(returns_data.get('return_5d') or 0):.2%} "
              f"10日:{(returns_data.get('return_10d') or 0):.2%} "
              f"回撤:{(returns_data.get('max_drawdown') or 0):.2%} "
              f"→ {result_status}")

    # 3. 写入 jsonl 文件
    output_file = DATA_DIR / f"{target_date}.jsonl"
    with output_file.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"[战绩追踪器] 完成，写入 {output_file}")

    # 4. 生成汇总推送到 Telegram
    win_count = sum(1 for r in results if r["result"] == "win")
    fail_count = sum(1 for r in results if r["result"] == "fail")
    neutral_count = sum(1 for r in results if r["result"] == "neutral")

    summary = f"【战绩追踪】{target_date}\n"
    summary += f"追踪 {len(results)} 只股票：胜 {win_count} / 败 {fail_count} / 中性 {neutral_count}\n"
    if fail_count > 0:
        fails = [r for r in results if r["result"] == "fail"]
        summary += "失败股票："
        summary += "、".join([f"{f['stock_code']}{f['stock_name']}" for f in fails[:3]])
    send_telegram_notification(summary)

    return results


if __name__ == "__main__":
    # 测试运行
    cold = "--cold" in sys.argv
    target = None
    for arg in sys.argv[1:]:
        if arg.isdigit() and len(arg) == 8:
            target = arg

    # 先测试 get_stock_returns
    print("=" * 50)
    print("测试 get_stock_returns")
    print("=" * 50)
    test_result = get_stock_returns('688190', '2026-03-28')
    print(f"688190 从 2026-03-28 开始: {test_result}")
    print()

    results = track_performance(target, cold_start=cold)
    print(f"\n共追踪 {len(results)} 只股票")
    for r in results:
        print(f"  {r['stock_code']} {r['stock_name']}: {r['result']}")
