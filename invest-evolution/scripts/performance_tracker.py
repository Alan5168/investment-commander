#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
战绩追踪器 - performance_tracker.py
版本: 1.1.0
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
import glob
from datetime import datetime, timedelta
from pathlib import Path

# 路径配置
WORKSPACE = Path.home() / ".openclaw" / "workspace"
SKILL_DIR = WORKSPACE / "skills" / "a-stock-monitor"
DATA_DIR = Path(__file__).parent.parent / "data" / "performance"
REC_DIR = SKILL_DIR / "output" / "recommendations"

# 确保目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_tushare_token():
    """获取 Tushare token"""
    token = os.environ.get("TUSHARE_TOKEN", "")
    if token:
        return token
    token_file = Path.home() / ".tushare_token"
    if token_file.exists():
        return token_file.read_text().strip()
    return ""


def send_telegram_notification(message: str):
    """通过 OpenClaw Telegram session 推送"""
    import subprocess
    # 构造 markdown 格式消息
    cmd = [
        'openclaw', 'message', 'send',
        '--channel', 'telegram',
        '--target', '8710019510',
        message
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=15)
    except Exception as e:
        print(f"[通知] Telegram 推送失败: {e}")


def fetch_price_data_sina_fallback(stock_code: str, trade_date: str):
    """用新浪接口获取单日收盘价"""
    try:
        import requests as req
        symbol = f"sh{stock_code}" if stock_code.startswith(("6", "0")) and len(stock_code) == 6 else f"sz{stock_code}"
        url = f"https://hq.sinajs.cn/list={symbol}"
        headers = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}
        resp = req.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            content = resp.text
            match = re.search(r'"([^"]+)"', content)
            if match:
                parts = match.group(1).split(",")
                if len(parts) > 3:
                    return {"price": float(parts[3]), "date": trade_date}
    except Exception:
        pass
    return None


def fetch_recent_prices(stock_code: str, start_date: str, count: int = 15):
    """获取股票近 count 天的价格数据"""
    prices = []
    today = datetime.now()
    for i in range(1, count + 1):
        d = today - timedelta(days=i)
        trade_date = d.strftime("%Y%m%d")
        data = fetch_price_data_sina_fallback(stock_code, trade_date)
        if data:
            prices.append(data)
    return prices


def parse_recommendation_file(file_path: Path):
    """解析单个推荐文件，返回推荐股票列表"""
    recommendations = []
    try:
        content = file_path.read_text(encoding="utf-8")
        # 提取日期
        date_m = re.search(r'\*\*时间\*\*[：:]?\s*(\d{4}-\d{2}-\d{2})', content)
        rec_date = date_m.group(1).replace("-", "") if date_m else file_path.stem[:8]

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
    """
    获取指定日期的推荐记录
    优先从推荐文件解析，其次用冷启动逻辑
    """
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

    # 过滤出目标日期的记录
    filtered = [r for r in all_recs if r.get("recommend_date") == target_date]
    if filtered:
        print(f"[战绩追踪] 冷启动找到 {len(filtered)} 条目标日期推荐")
    return filtered


def calculate_returns(prices: list, entry_price: float, stop_loss: float = None):
    """计算收益率序列和最大回撤"""
    if not prices or entry_price <= 0:
        return {"return_3d": 0, "return_5d": 0, "return_10d": 0, "max_drawdown": 0}

    returns = []
    for p in prices:
        ret = (p["price"] - entry_price) / entry_price
        returns.append(ret)

    result = {
        "return_3d": round(returns[min(2, len(returns)-1)], 4) if len(returns) >= 3 else 0,
        "return_5d": round(returns[min(4, len(returns)-1)], 4) if len(returns) >= 5 else 0,
        "return_10d": round(returns[min(9, len(returns)-1)], 4) if len(returns) >= 10 else (returns[-1] if returns else 0),
        "max_drawdown": round(min(returns) if returns else 0, 4),
    }

    if stop_loss and entry_price > 0:
        hit_stop = any(p["price"] <= stop_loss for p in prices)
        if hit_stop:
            result["stop_loss_hit"] = True

    return result


def determine_result(returns_data: dict, stop_loss: float = None) -> str:
    """
    判定结果：
    - win: 10天内最高收益 > 5%
    - fail: 10天内最大回撤 > 5% 或触发止损
    - neutral: 其余
    """
    max_return = returns_data.get("return_10d", 0)
    max_drawdown = abs(returns_data.get("max_drawdown", 0))

    if returns_data.get("stop_loss_hit"):
        return "fail"
    if max_return > 0.05:
        return "win"
    if max_drawdown > 0.05:
        return "fail"
    return "neutral"


def track_performance(target_date: str = None, cold_start: bool = False):
    """主函数：追踪指定日期的推荐股票表现"""
    if target_date is None:
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    print(f"[战绩追踪器] 开始追踪 {target_date} 的推荐记录...")

    # 1. 提取推荐记录
    if cold_start:
        recommendations = get_historical_recommendations()
        # 过滤有代码的记录
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
        entry = rec.get("entry_price", 0)
        stop = rec.get("stop_loss", 0)

        if entry <= 0:
            entry = 20.0  # 默认入场价

        prices = fetch_recent_prices(code, target_date, count=15)
        if prices:
            entry = prices[0]["price"] if entry <= 0 else entry

        returns_data = calculate_returns(prices, entry, stop)
        result_status = determine_result(returns_data, stop)

        record = {
            "recommend_date": rec.get("recommend_date", target_date),
            "stock_code": code,
            "stock_name": rec.get("stock_name", ""),
            "recommend_reason": rec.get("recommend_reason", ""),
            "entry_price": entry,
            "stop_loss": stop,
            "industry_score": rec.get("industry_score", 0),
            "quant_score": rec.get("quant_score", 0),
            **returns_data,
            "result": result_status,
            "tracked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        results.append(record)
        print(f"  {code} {rec.get('stock_name', '')}: {result_status} "
              f"(3日{returns_data.get('return_3d', 0):.2%} "
              f"5日{returns_data.get('return_5d', 0):.2%} "
              f"10日{returns_data.get('return_10d', 0):.2%})")

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
    results = track_performance(target, cold_start=cold)
    print(f"\n共追踪 {len(results)} 只股票")
    for r in results:
        print(f"  {r['stock_code']} {r['stock_name']}: {r['result']}")
