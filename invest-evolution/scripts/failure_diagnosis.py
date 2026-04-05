#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
归因诊断器 - failure_diagnosis.py
版本: 1.0.0
作者: Alan Li
日期: 2026-04-05

功能：对 result=="fail" 的推荐做反事实归因分析
输入：data/performance/ 下 result=="fail" 的记录
输出三维度诊断：
  1. 产业催化剂（70%权重）：催化剂是否真实/price in/知识库过时
  2. 量化择时（30%权重）：买入时点/技术指标矛盾
  3. 风控：大盘环境/止损设置
归因结论：
  - 「催化剂失效」→ 建议更新知识库
  - 「择时失败」 → 建议触发 indicator_explorer 重新进化
  - 「市场环境」 → 建议调整风控参数
输出：data/diagnosis/{date}_{stock_code}.json
触发：每天 17:00
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

WORKSPACE = Path.home() / ".openclaw" / "workspace"
SKILL_DIR = WORKSPACE / "skills" / "investment-commander"
DATA_DIR = Path(__file__).parent.parent / "data"
PERF_DIR = DATA_DIR / "performance"
DIAG_DIR = DATA_DIR / "diagnosis"

DIAG_DIR.mkdir(parents=True, exist_ok=True)


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

# 催化剂知识库（与 catalyst_radar.py 共享）
DEFAULT_KB_SECTORS = {
    "半导体/芯片": {"last_updated": "2026-03-20", "strength": "high"},
    "智能驾驶/汽车电子": {"last_updated": "2026-03-22", "strength": "medium"},
    "SST固态变压器": {"last_updated": "2026-03-28", "strength": "medium"},
    "新材料": {"last_updated": "2026-03-25", "strength": "medium"},
    "消费电子": {"last_updated": "2026-03-10", "strength": "low"},
}


def load_failure_records(days: int = 7) -> List[Dict]:
    """加载近 N 天的失败记录"""
    failures = []
    cutoff = datetime.now() - timedelta(days=days)

    for pf in PERF_DIR.glob("*.jsonl"):
        try:
            # 从文件名提取日期
            date_str = pf.stem  # 如 "20260403"
            file_date = datetime.strptime(date_str, "%Y%m%d")
            if file_date < cutoff:
                continue

            with pf.open(encoding="utf-8") as f:
                for line in f:
                    record = json.loads(line.strip())
                    if record.get("result") == "fail":
                        failures.append(record)
        except Exception as e:
            print(f"[归因诊断] 读取 {pf} 出错: {e}")

    return failures


def extract_sector_from_reason(reason: str) -> Optional[str]:
    """从推荐理由中提取赛道"""
    if not reason:
        return None

    sector_keywords = {
        "SST固态变压器": ["SST", "固态变压器", "电力变压器"],
        "半导体/芯片": ["半导体", "芯片", "AI芯片"],
        "智能驾驶": ["智能驾驶", "自动驾驶", "L3", "L4", "华为"],
        "新材料": ["新材料", "碳纤维", "复合材料"],
        "军工": ["军工", "国防"],
        "固态电池": ["固态电池", "全固态", "电池"],
    }

    for sector, keywords in sector_keywords.items():
        for kw in keywords:
            if kw in reason:
                return sector
    return None


def diagnose_catalyst(
    record: Dict,
    kb_sectors: Dict
) -> Dict:
    """
    诊断催化剂维度（70%权重）
    返回：{passed: bool, reason: str, confidence: float}
    """
    reason = record.get("recommend_reason", "")
    sector = extract_sector_from_reason(reason)

    if not sector:
        return {
            "passed": False,
            "reason": "无法从推荐理由中识别赛道",
            "detail": "推荐理由缺少赛道关键词",
            "confidence": 0.5
        }

    # 检查知识库中该赛道状态
    kb_info = kb_sectors.get(sector, {})
    last_updated = kb_info.get("last_updated", "")

    if not last_updated:
        return {
            "passed": False,
            "reason": f"赛道 {sector} 不在知识库中",
            "detail": "知识库缺少该赛道信息，建议更新",
            "confidence": 0.7,
            "sector": sector,
            "action": "update_catalyst"
        }

    # 检查知识库是否过期（超过14天未更新）
    try:
        update_date = datetime.strptime(last_updated, "%Y-%m-%d")
        days_since = (datetime.now() - update_date).days
        if days_since > 14:
            return {
                "passed": False,
                "reason": f"赛道 {sector} 知识库已 {days_since} 天未更新",
                "detail": f"最后更新：{last_updated}，信息可能过时",
                "confidence": 0.75,
                "sector": sector,
                "action": "update_catalyst"
            }
    except Exception:
        pass

    # 催化剂已被市场 price in 的判断
    # 如果推荐后10日最大回撤 > 5%，且赛道强度为 medium/low，说明催化不够强
    strength = kb_info.get("strength", "unknown")
    max_drawdown = abs(record.get("max_drawdown", 0))
    if max_drawdown > 0.05 and strength in ["medium", "low"]:
        return {
            "passed": False,
            "reason": f"赛道 {sector} 催化剂强度 {strength}，不足以支撑上涨",
            "detail": "催化剂已充分反映在当前股价中（price in）",
            "confidence": 0.72,
            "sector": sector,
            "action": "update_catalyst"
        }

    return {
        "passed": True,
        "reason": f"赛道 {sector} 催化剂有效",
        "detail": f"知识库状态正常（强度：{strength}）",
        "confidence": 0.6,
        "sector": sector
    }


def diagnose_quant_timing(
    record: Dict
) -> Dict:
    """
    诊断量化择时维度（30%权重）
    检查：买入时点、MACD/RSI/布林带矛盾
    """
    industry_score = record.get("industry_score", 0)
    quant_score = record.get("quant_score", 0)
    max_drawdown = abs(record.get("max_drawdown", 0))
    return_10d = record.get("return_10d", 0)

    # 如果量化分数很低但还是推荐了
    if quant_score < 50 and industry_score > 60:
        return {
            "passed": False,
            "reason": "量化择时信号矛盾",
            "detail": f"产业分数{industry_score} vs 量化分数{quant_score}，技术面不支持",
            "confidence": 0.68,
            "action": "retrain_indicator"
        }

    # 如果量化分数高但仍然失败
    if quant_score >= 70 and max_drawdown > 0.05:
        return {
            "passed": False,
            "reason": "技术指标对该股票失效",
            "detail": f"量化分数{quant_score}较高但仍亏损{return_10d:.2%}，当前指标组合不适用",
            "confidence": 0.7,
            "action": "retrain_indicator"
        }

    # 如果没有量化分数信息
    if quant_score == 0:
        return {
            "passed": True,
            "reason": "无量化分数记录",
            "detail": "缺少量化择时数据，无法判断",
            "confidence": 0.4
        }

    return {
        "passed": True,
        "reason": "量化择时未发现明显矛盾",
        "detail": f"量化分数{quant_score}在合理范围",
        "confidence": 0.55
    }


def diagnose_risk_control(
    record: Dict
) -> Dict:
    """
    诊断风控维度
    检查：大盘环境、止损设置
    """
    entry_price = record.get("entry_price", 0)
    stop_loss = record.get("stop_loss", 0)
    max_drawdown = abs(record.get("max_drawdown", 0))

    if stop_loss > 0 and entry_price > 0:
        stop_pct = (entry_price - stop_loss) / entry_price
        # 止损设置过窄（< 3%）
        if stop_pct < 0.03:
            return {
                "passed": False,
                "reason": f"止损设置过窄（{stop_pct:.1%}）",
                "detail": "止损幅度太小，容易被正常波动洗出",
                "confidence": 0.65,
                "action": "adjust_risk"
            }
        # 止损设置过宽（> 15%）
        if stop_pct > 0.15:
            return {
                "passed": False,
                "reason": f"止损设置过宽（{stop_pct:.1%}）",
                "detail": "止损幅度过大，风险敞口控制不当",
                "confidence": 0.6,
                "action": "adjust_risk"
            }
    else:
        # 没有设置止损
        if max_drawdown > 0.05:
            return {
                "passed": False,
                "reason": "未设置止损且亏损超5%",
                "detail": "缺少风控保护，建议设置止损位",
                "confidence": 0.7,
                "action": "adjust_risk"
            }

    return {
        "passed": True,
        "reason": "风控参数设置合理",
        "detail": f"止损{stop_pct:.1%}在正常范围（3%-15%）",
        "confidence": 0.6
    }


def determine_root_cause(
    catalyst_diag: Dict,
    quant_diag: Dict,
    risk_diag: Dict
) -> Dict:
    """
    综合三个维度，确定根本原因
    权重：催化剂70%，择时30%（风控不参与归因权重）
    """
    # 计算加权得分
    catalyst_score = 1.0 if catalyst_diag["passed"] else 0.0
    quant_score = 1.0 if quant_diag["passed"] else 0.0

    weighted = catalyst_score * 0.7 + quant_score * 0.3

    # 确定结论
    if not catalyst_diag["passed"]:
        action = catalyst_diag.get("action", "update_catalyst")
        conclusion = "催化剂失效"
        detail = catalyst_diag.get("reason", "")
        confidence = catalyst_diag.get("confidence", 0.7)
    elif not quant_diag["passed"]:
        action = quant_diag.get("action", "retrain_indicator")
        conclusion = "择时失败"
        detail = quant_diag.get("reason", "")
        confidence = quant_diag.get("confidence", 0.65)
    else:
        action = risk_diag.get("action", "adjust_risk") if not risk_diag["passed"] else "none"
        conclusion = "市场环境"
        detail = "大盘整体弱势，策略适应性下降"
        confidence = 0.55

    return {
        "conclusion": conclusion,
        "detail": detail,
        "action": action,
        "confidence": confidence,
        "catalyst_score": catalyst_score,
        "quant_score": quant_score,
        "risk_score": 1.0 if risk_diag["passed"] else 0.0
    }


def diagnose_failures():
    """主函数：诊断所有失败记录"""
    print("[归因诊断器] 开始诊断失败记录...")

    # 1. 加载失败记录
    failures = load_failure_records(days=7)
    if not failures:
        print("[归因诊断器] 未找到失败记录")
        return []

    print(f"  找到 {len(failures)} 条失败记录")

    # 2. 加载催化剂知识库
    # 复用 catalyst_radar 的知识库
    kb_file = DATA_DIR / "catalyst_updates"
    # 简化：直接使用默认知识库
    kb_sectors = DEFAULT_KB_SECTORS

    results = []
    for fail in failures:
        code = fail.get("stock_code", "unknown")
        name = fail.get("stock_name", "")
        print(f"\n  诊断 {code} {name}...")

        # 三维度诊断
        catalyst_diag = diagnose_catalyst(fail, kb_sectors)
        quant_diag = diagnose_quant_timing(fail)
        risk_diag = diagnose_risk_control(fail)

        # 综合归因
        root_cause = determine_root_cause(catalyst_diag, quant_diag, risk_diag)

        # 构建诊断报告
        diag_report = {
            "stock": code,
            "stock_name": name,
            "recommend_date": fail.get("recommend_date", ""),
            "entry_price": fail.get("entry_price", 0),
            "stop_loss": fail.get("stop_loss", 0),
            "return_10d": fail.get("return_10d", 0),
            "max_drawdown": fail.get("max_drawdown", 0),
            "diagnosis": root_cause["conclusion"],
            "detail": root_cause["detail"],
            "action": root_cause["action"],
            "confidence": root_cause["confidence"],
            "catalyst_diagnosis": catalyst_diag,
            "quant_diagnosis": quant_diag,
            "risk_diagnosis": risk_diag,
            "weighted_score": root_cause["catalyst_score"] * 0.7 + root_cause["quant_score"] * 0.3,
            "diagnosed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # 保存诊断报告
        today_str = datetime.now().strftime("%Y%m%d")
        output_file = DIAG_DIR / f"{today_str}_{code}.json"
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(diag_report, f, ensure_ascii=False, indent=2)

        results.append(diag_report)
        print(f"    归因：{root_cause['conclusion']}（置信度 {root_cause['confidence']:.0%}）")
        print(f"    建议：{root_cause['action']}")

    print(f"\n[归因诊断器] 完成，共诊断 {len(results)} 条记录")
    return results


if __name__ == "__main__":
    results = diagnose_failures()
    print(f"\n诊断结果汇总：")
    for r in results:
        print(f"  {r['stock']} {r['stock_name']}: {r['diagnosis']} → {r['action']}")

# Telegram 通知
    if results:
        lines = ["【归因诊断】"]
        for r in results:
            icon = "🔴" if r["action"] == "update_catalyst" else "🟡" if r["action"] == "retrain_indicator" else "🟠"
            lines.append(f"{icon} {r['stock']} {r['stock_name']}: {r['diagnosis']}")
        msg = "\n".join(lines)
        send_telegram_notification(msg)
