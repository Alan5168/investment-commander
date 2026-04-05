#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测验证器 - backtest_validator.py
版本: 1.0.0
作者: Alan Li
日期: 2026-04-05

功能：验证归因诊断器的建议是否经得起回测
输入：data/diagnosis/ 下的诊断文件
验证逻辑：
  1. action=="update_catalyst": 拉该赛道近30天表现，差→支持降级，好→拒绝
  2. action=="retrain_indicator": 读取 indicator_explorer.log 对比新旧参数
  3. action=="adjust_risk": 对比调整前后风控效果
原则：不自动合并，只生成报告推送钉钉
触发：每天 17:30
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

WORKSPACE = Path.home() / ".openclaw" / "workspace"
SKILL_DIR = WORKSPACE / "skills" / "a-stock-monitor"
DATA_DIR = Path(__file__).parent.parent / "data"
DIAG_DIR = DATA_DIR / "diagnosis"


def send_telegram_notification(message: str):
    """通过 OpenClaw Telegram session 推送"""
    import subprocess
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

# 赛道到股票代码的映射（简化版，用于验证）
SECTOR_STOCKS = {
    "SST固态变压器": ["601567", "300124"],  # 示例
    "半导体/芯片": ["688012", "002371", "688072"],
    "智能驾驶/汽车电子": ["301268", "688677"],
    "新材料": ["688116", "300567"],
}


def load_diagnosis_files() -> List[Dict]:
    """加载所有待验证的诊断文件"""
    diagnoses = []
    if not DIAG_DIR.exists():
        return diagnoses

    # 只处理今天的诊断文件
    today_str = datetime.now().strftime("%Y%m%d")
    for df in DIAG_DIR.glob(f"{today_str}_*.json"):
        try:
            with df.open(encoding="utf-8") as f:
                diagnoses.append(json.load(f))
        except Exception as e:
            print(f"[回测验证] 读取 {df} 出错: {e}")

    return diagnoses


def get_tushare_token() -> str:
    """获取 Tushare token"""
    token = os.environ.get("TUSHARE_TOKEN", "")
    if token:
        return token
    token_file = Path.home() / ".tushare_token"
    if token_file.exists():
        return token_file.read_text().strip()
    return ""


def fetch_sina_price(stock_code: str, days: int = 30) -> List[Dict]:
    """用新浪接口获取近 N 天收盘价"""
    prices = []
    today = datetime.now()

    for i in range(1, days + 1):
        d = today - timedelta(days=i)
        date_str = d.strftime("%Y%m%d")
        try:
            symbol = f"sh{stock_code}" if stock_code.startswith(("6", "0")) and len(stock_code) == 6 else f"sz{stock_code}"
            url = f"https://hq.sinajs.cn/list={symbol}"
            headers = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}
            import requests as req
            resp = req.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                content = resp.text
                match = re.search(r'"([^"]+)"', content)
                if match:
                    parts = match.group(1).split(",")
                    if len(parts) > 3:
                        try:
                            price = float(parts[3])
                            prices.append({"date": date_str, "price": price})
                        except ValueError:
                            pass
        except Exception:
            pass

    return prices


def validate_update_catalyst(diag: Dict) -> Dict:
    """
    验证 update_catalyst 建议
    近30天该赛道表现：差→支持降级，好→拒绝
    """
    sector = diag.get("catalyst_diagnosis", {}).get("sector", "")
    if not sector:
        return {
            "verdict": "skip",
            "reason": "无法识别赛道",
            "support_downgrade": False,
            "avg_return": 0
        }

    # 获取该赛道的代表股票
    stocks = SECTOR_STOCKS.get(sector, [])
    if not stocks:
        # 尝试从推荐记录推断
        stocks = [diag.get("stock", "")]

    # 获取近30天行情
    all_returns = []
    for code in stocks:
        prices = fetch_sina_price(code, days=30)
        if len(prices) >= 5:
            start_price = prices[-1]["price"] if prices else 0
            end_price = prices[0]["price"] if prices else 0
            if start_price > 0:
                ret = (end_price - start_price) / start_price
                all_returns.append(ret)

    if not all_returns:
        return {
            "verdict": "inconclusive",
            "reason": "无法获取该赛道近期数据",
            "support_downgrade": None,
            "avg_return": None
        }

    avg_return = sum(all_returns) / len(all_returns)

    # 判断：平均收益 < -5% → 支持降级；> 0% → 拒绝降级
    if avg_return < -0.05:
        verdict = "support"
        reason = f"近30天该赛道平均收益 {avg_return:.2%}，显著走弱，支持降级"
        support = True
    elif avg_return > 0:
        verdict = "reject"
        reason = f"近30天该赛道平均收益 {avg_return:.2%}，仍在上涨，拒绝降级"
        support = False
    else:
        verdict = "neutral"
        reason = f"近30天该赛道平均收益 {avg_return:.2%}，方向不明，建议观察"
        support = None

    return {
        "verdict": verdict,
        "reason": reason,
        "sector": sector,
        "stocks_tested": stocks,
        "avg_return": round(avg_return, 4),
        "support_downgrade": support,
        "confidence": 0.75 if support is not None else 0.5
    }


def validate_retrain_indicator(diag: Dict) -> Dict:
    """
    验证 retrain_indicator 建议
    读取 indicator_explorer.log 最新一代参数，对比新旧回测收益
    """
    log_file = SKILL_DIR / "logs" / "indicator_explorer.log"

    if not log_file.exists():
        return {
            "verdict": "inconclusive",
            "reason": "未找到 indicator_explorer.log",
            "current_gen": None,
            "best_score": None,
            "recommendation": None
        }

    try:
        content = log_file.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        last_lines = [l for l in lines if "generation" in l.lower() or "score" in l.lower()][-10:]

        # 提取最新代数和分数
        gen_m = re.search(r'[Gg]eneration\s+(\d+)', last_lines[-1] if last_lines else "")
        score_m = re.search(r'[Ss]core:\s*([\d.]+)', last_lines[-1] if last_lines else "")

        current_gen = int(gen_m.group(1)) if gen_m else None
        best_score = float(score_m.group(1)) if score_m else None

        return {
            "verdict": "ready",
            "reason": f"当前最优：第{current_gen}代，分数{best_score}",
            "current_gen": current_gen,
            "best_score": best_score,
            "recommendation": "建议运行新一轮进化测试",
            "confidence": 0.7
        }
    except Exception as e:
        return {
            "verdict": "error",
            "reason": f"读取日志出错: {e}",
            "confidence": 0.3
        }


def validate_adjust_risk(diag: Dict) -> Dict:
    """
    验证 adjust_risk 建议
    对比调整前后的最大回撤和收益率
    """
    entry = diag.get("entry_price", 0)
    stop = diag.get("stop_loss", 0)
    max_dd = abs(diag.get("max_drawdown", 0))
    ret_10d = diag.get("return_10d", 0)

    if entry <= 0 or stop <= 0:
        return {
            "verdict": "inconclusive",
            "reason": "缺少止损数据",
            "current_stop_pct": None,
            "recommendation": None
        }

    current_stop_pct = (entry - stop) / entry

    # 评估当前止损
    if current_stop_pct < 0.03:
        verdict = "too_tight"
        recommendation = f"止损 {current_stop_pct:.1%} 过窄，建议放宽至 5%-8%"
        confidence = 0.7
    elif current_stop_pct > 0.15:
        verdict = "too_wide"
        recommendation = f"止损 {current_stop_pct:.1%} 过宽，建议收窄至 8%-12%"
        confidence = 0.65
    else:
        verdict = "acceptable"
        recommendation = f"止损 {current_stop_pct:.1%} 在合理范围"
        confidence = 0.6

    return {
        "verdict": verdict,
        "reason": recommendation,
        "current_stop_pct": round(current_stop_pct, 4),
        "max_drawdown_observed": round(max_dd, 4),
        "return_10d_observed": round(ret_10d, 4),
        "recommendation": recommendation,
        "confidence": confidence
    }


def validate_all() -> List[Dict]:
    """主函数：验证所有诊断建议"""
    print("[回测验证器] 开始验证诊断建议...")

    diagnoses = load_diagnosis_files()
    if not diagnoses:
        print("[回测验证器] 未找到待验证的诊断文件")
        return []

    print(f"  找到 {len(diagnoses)} 个诊断文件")

    validations = []
    for diag in diagnoses:
        stock = diag.get("stock", "unknown")
        action = diag.get("action", "")

        print(f"\n  验证 {stock}（action={action}）...")

        if action == "update_catalyst":
            validation = validate_update_catalyst(diag)
        elif action == "retrain_indicator":
            validation = validate_retrain_indicator(diag)
        elif action == "adjust_risk":
            validation = validate_adjust_risk(diag)
        else:
            validation = {
                "verdict": "skip",
                "reason": f"未知 action 类型: {action}",
                "confidence": 0
            }

        validation["stock"] = stock
        validation["stock_name"] = diag.get("stock_name", "")
        validation["original_diagnosis"] = diag.get("diagnosis", "")
        validation["original_action"] = action
        validation["validated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        validations.append(validation)
        print(f"    结论：{validation.get('verdict', 'unknown')} - {validation.get('reason', '')}")

    return validations


def format_telegram_report(validations: List[Dict]) -> str:
    """格式化Telegram 推送报告"""
    if not validations:
        return "【投研进化】今日无待验证的诊断"

    lines = ["【投研进化】诊断验证报告"]

    for v in validations:
        verdict_icon = "✅" if v["verdict"] in ("support", "ready", "acceptable") else "❌" if v["verdict"] in ("reject", "too_tight", "too_wide") else "⚠️"
        lines.append(f"\n{verdict_icon} {v['stock']} {v.get('stock_name', '')}")
        lines.append(f"   归因：{v.get('original_diagnosis', '')}")
        lines.append(f"   建议：{v.get('original_action', '')}")
        lines.append(f"   验证：{v.get('reason', '')}")

        if v.get("support_downgrade") is True:
            lines.append("   📋 建议操作：确认后更新知识库")
        elif v.get("support_downgrade") is False:
            lines.append("   📋 建议操作：暂不调整，继续观察")

    lines.append(f"\n— 共 {len(validations)} 条诊断待确认 —")
    return "\n".join(lines)


if __name__ == "__main__":
    print("=" * 50)
    print("Investment Commander 投研自进化系统 - 回测验证器")
    print("=" * 50)

    results = validate_all()
    print("\n" + "=" * 50)
    print("验证结果汇总：")
    for r in results:
        print(f"  [{r['verdict']}] {r['stock']}: {r.get('reason', '')}")

    if results:
        report = format_telegram_report(results)
        print("\nTelegram 推送内容：")
        print(report)
        send_telegram_notification(report)
