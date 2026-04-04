#!/usr/bin/env python3
"""
每日早报：开盘前30分钟推送
短期：今日需要关注的风险和机会
中期：未来1个月的重要节点
长期：产业动向跟踪
"""

import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

# 设置路径
SCRIPTS_DIR = Path('/Users/alanli/.openclaw/workspace/skills/a-stock-monitor/scripts')
CONFIG_DIR = Path('/Users/alanli/.openclaw/workspace/skills/a-stock-monitor/config')
SHARED_DIR = Path('/Users/alanli/.openclaw/workspace/shared')

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SHARED_DIR))


try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False

from market_filter import get_market_state, get_market_regime
from catalyst_filter import get_stock_industry_context


def get_us_overnight() -> str:
    """美股隔夜情况"""
    if not AKSHARE_AVAILABLE:
        return "🌍 美股数据: akshare 未安装"
    
    try:
        lines = ["🌍 美股隔夜"]
        
        # 美股主要ETF
        etfs = [
            ("QQQ", "纳指100"),
            ("SPY", "标普500"),
            ("YANG", "做空中国3X")
        ]
        
        yang_chg = None
        any_success = False
        
        for symbol, name in etfs:
            try:
                df = ak.stock_us_daily(symbol=symbol, adjust="qfq")
                if df is None or len(df) < 2:
                    continue
                
                df = df.sort_values("date").tail(2)
                chg = (df.iloc[-1]["close"] - df.iloc[-2]["close"]) / df.iloc[-2]["close"] * 100
                
                if symbol == "YANG":
                    yang_chg = chg
                
                emoji = "🔴" if chg < -1 else "🟢" if chg > 1 else "⚪"
                lines.append(f"  {emoji} {name}: {chg:+.2f}%")
                any_success = True
            except Exception as e:
                lines.append(f"  ⚠️ {name}: 获取失败")
        
        # YANG 信号解读
        if yang_chg is not None:
            if yang_chg > 5:
                lines.append("  🚨 YANG暴涨超5%，强烈建议减仓观望")
            elif yang_chg > 3:
                lines.append("  ⚠️ YANG大涨超3%，今日A股注意回避风险")
            elif yang_chg < -3:
                lines.append("  ✅ YANG大跌超3%，今日A股可能偏强")
        
        if not any_success:
            lines.append("  美股数据获取失败，请检查网络或akshare版本")
        
        return "\n".join(lines)
    except Exception as e:
        return f"🌍 美股数据获取失败: {e}"


def get_market_state_report() -> str:
    """大盘状态判断"""
    try:
        today = datetime.now().strftime("%Y%m%d")
        state = get_market_state(today)
        regime = get_market_regime()
        
        lines = ["📊 大盘状态"]
        lines.append(f"  沪深300: {state['state']} — {state['reason']}")
        lines.append(f"  二八轮动: {regime['advice']}")
        
        if not state['can_select']:
            lines.append("  🚫 今日建议空仓观望")
        else:
            lines.append("  ✅ 大盘正常，可正常选股")
        
        return "\n".join(lines)
    except Exception as e:
        return f"📊 大盘状态获取失败: {e}"


def get_short_term_news() -> str:
    """短期：今日重要新闻（影响今天交易）"""
    if not AKSHARE_AVAILABLE:
        return "📰 新闻: akshare 未安装"
    
    try:
        # 用 AKShare 获取财新主要新闻
        news_df = ak.stock_news_main_cx()
        
        if news_df is None or len(news_df) == 0:
            return "📰 今日重点新闻（短期）\n  暂无重大新闻"
        
        # 关键词过滤（高影响关键词）
        high_impact_keywords = [
            "美联储", "关税", "降息", "加息", "暴跌", "熔断",
            "央行", "降准", "MLF", "LPR", "政策", "制裁",
            "贸易战", "黑天鹅", "灰犀牛", "系统性风险", "危机"
        ]
        
        medium_impact_keywords = [
            "IPO", "重组", "并购", "业绩", "财报",
            "分红", "回购", "增持", "减持", "监管"
        ]
        
        important_high = []
        important_medium = []
        
        for _, row in news_df.head(30).iterrows():
            summary = str(row.get("summary", ""))
            tag = str(row.get("tag", ""))
            
            if any(kw in summary for kw in high_impact_keywords):
                important_high.append(f"  🔴 [{tag}] {summary[:50]}...")
            elif any(kw in summary for kw in medium_impact_keywords):
                important_medium.append(f"  🟡 [{tag}] {summary[:50]}...")
        
        lines = ["📰 今日重点新闻（短期）"]
        
        if important_high:
            lines.append("  【高影响】")
            lines.extend(important_high[:3])
        
        if important_medium:
            lines.append("  【中影响】")
            lines.extend(important_medium[:3])
        
        if not important_high and not important_medium:
            lines.append("  暂无重大政策/市场新闻")
        
        return "\n".join(lines)
    except Exception as e:
        return f"📰 新闻获取失败: {e}"


def get_medium_term_calendar() -> str:
    """中期：未来1个月重要节点"""
    calendar_file = CONFIG_DIR / "event_calendar.json"
    
    if not calendar_file.exists():
        # 初始化默认日历
        default_calendar = {
            "events": [
                {
                    "date": "2026-04-30",
                    "type": "政策",
                    "title": "美联储FOMC会议",
                    "impact": "high",
                    "note": "关注降息信号"
                },
                {
                    "date": "2026-04-15",
                    "type": "财报",
                    "title": "美股科技股Q1财报季开始",
                    "impact": "medium",
                    "note": "关注AI算力需求指引"
                },
                {
                    "date": "2026-04-10",
                    "type": "数据",
                    "title": "中国3月CPI/PPI数据",
                    "impact": "medium",
                    "note": "关注通胀走势"
                }
            ]
        }
        calendar_file.parent.mkdir(parents=True, exist_ok=True)
        calendar_file.write_text(
            json.dumps(default_calendar, ensure_ascii=False, indent=2)
        )
    
    data = json.loads(calendar_file.read_text())
    today = datetime.now()
    
    lines = ["📅 中期重要节点（1个月内）"]
    
    upcoming = []
    for event in data.get("events", []):
        event_date = datetime.strptime(event["date"], "%Y-%m-%d")
        days_away = (event_date - today).days
        if 0 <= days_away <= 30:
            impact_emoji = "🔴" if event["impact"] == "high" else "🟡"
            upcoming.append((
                days_away, 
                f"  {impact_emoji} {event['date']} ({days_away}天后) "
                f"[{event['type']}] {event['title']}"
            ))
    
    if upcoming:
        upcoming.sort(key=lambda x: x[0])
        lines.extend([u[1] for u in upcoming])
    else:
        lines.append("  本月暂无重大节点")
    
    return "\n".join(lines)


def get_long_term_tracking() -> str:
    """长期：产业动向跟踪"""
    tracking_file = CONFIG_DIR / "long_term_tracking.json"
    
    if not tracking_file.exists():
        default = {
            "themes": [
                {
                    "name": "商业航天",
                    "milestone": "SpaceX IPO预期",
                    "timeline": "2026年内",
                    "status": "观察中",
                    "related_stocks": ["688568", "600118"]
                },
                {
                    "name": "固态变压器SST",
                    "milestone": "国内商业化落地",
                    "timeline": "2026-2027",
                    "status": "布局期",
                    "related_stocks": ["601126", "688676", "002479"]
                },
                {
                    "name": "AI算力",
                    "milestone": "英伟达GTC大会",
                    "timeline": "2026-03已过",
                    "status": "持续跟踪",
                    "related_stocks": ["688041", "688256"]
                },
                {
                    "name": "固态电池",
                    "milestone": "量产时间表",
                    "timeline": "2026-2027",
                    "status": "观察中",
                    "related_stocks": ["300750", "002594"]
                },
                {
                    "name": "人形机器人",
                    "milestone": "Tesla Optimus量产",
                    "timeline": "2027-2028",
                    "status": "观察中",
                    "related_stocks": ["002747", "688169"]
                }
            ]
        }
        tracking_file.parent.mkdir(parents=True, exist_ok=True)
        tracking_file.write_text(
            json.dumps(default, ensure_ascii=False, indent=2)
        )
    
    data = json.loads(tracking_file.read_text())
    lines = ["🔭 长期产业跟踪"]
    
    status_emoji_map = {
        "观察中": "👀", 
        "布局期": "📌",
        "持续跟踪": "🔄", 
        "已兑现": "✅"
    }
    
    for theme in data.get("themes", []):
        status_emoji = status_emoji_map.get(theme["status"], "📌")
        lines.append(
            f"  {status_emoji} {theme['name']}: {theme['milestone']} "
            f"({theme['timeline']})"
        )
    
    return "\n".join(lines)




def get_last30days_briefing() -> str:
    """整合 last30days-engine 简报：市场情绪 + 系统健康"""
    try:
        import subprocess
        import re
        
        # 先生成简报（用 subprocess 避免 numpy/pandas 版本冲突）
        result = subprocess.run([
            'python3', 
            '/Users/alanli/.openclaw/workspace/skills/last30days-engine/scripts/briefing.py',
            'daily'
        ], capture_output=True, timeout=30, text=True)
        
        # 读取生成的简报
        today = datetime.now().strftime("%Y-%m-%d")
        briefing_file = BRIEFING_DIR / f"daily_{today}.md"
        
        if not briefing_file.exists():
            return ""
        
        md_content = briefing_file.read_text()
        
        # 提取关键部分（市场概览 + 系统健康）
        lines_out = ["📊 last30days 简报"]
        
        # 提取市场情绪
        market_match = re.search(r'市场情绪\s*\|\s*(\w+)\s*\|', md_content)
        if market_match:
            sentiment = market_match.group(1)
            lines_out.append(f"  市场情绪: {sentiment}")
        
        # 提取恐惧贪婪指数
        fear_match = re.search(r'恐惧贪婪指数\s*\|\s*(\d+)\s*\|', md_content)
        if fear_match:
            fear_index = int(fear_match.group(1))
            if fear_index < 25:
                lines_out.append(f"  恐惧贪婪指数: {fear_index} (极度恐惧)")
            elif fear_index > 75:
                lines_out.append(f"  恐惧贪婪指数: {fear_index} (极度贪婪)")
            else:
                lines_out.append(f"  恐惧贪婪指数: {fear_index}")
        
        # 提取系统健康状态
        health_match = re.search(r'状态\*\*:\s*(🟢|🟡|🔴)\s*(\w+)', md_content)
        if health_match:
            lines_out.append(f"  系统健康: {health_match.group(1)} {health_match.group(2)}")
        
        # 提取故障数
        failure_match = re.search(r'最近24小时故障\*\*:\s*(\d+)\s*次', md_content)
        if failure_match:
            failures = int(failure_match.group(1))
            if failures > 0:
                lines_out.append(f"  ⚠️ 最近24小时故障: {failures} 次")
        
        return "\n".join(lines_out)
    except Exception as e:
        return ""

def get_portfolio_status() -> str:
    """持仓状态快速检查"""
    try:
        from stock_client import get_daily
        
        portfolio_file = Path('/Users/alanli/.openclaw/workspace/data/portfolio.json')
        if not portfolio_file.exists():
            return ""
        
        portfolio = json.loads(portfolio_file.read_text())
        holdings = portfolio.get("holdings", [])
        
        if not holdings:
            return ""
        
        lines = ["💼 持仓概览"]
        
        for h in holdings[:5]:  # 最多显示5只
            code = h.get("code", "").split(".")[0]
            name = h.get("name", code)
            industry = get_stock_industry_context(code)
            cost = h.get("cost", 0)
            
            if not cost:
                continue
            
            try:
                df = get_daily(code, days=2)
                if df is not None and len(df) >= 1:
                    current = df.iloc[-1]["收盘"]
                    pnl_pct = (current - cost) / cost * 100
                    emoji = "🔴" if pnl_pct < -5 else "🟡" if pnl_pct < 0 else "🟢"
                    industry_short = industry[:8] if industry != '待补充' else ''
                    ind_str = f' [{industry_short}]' if industry_short else ''
                    lines.append(
                        f"  {emoji} {name}{ind_str}: "
                        f"现价{current:.2f} 成本{cost:.2f} "
                        f"({pnl_pct:+.1f}%)"
                    )
            except:
                pass
        
        return "\n".join(lines)
    except Exception as e:
        return ""


def generate_morning_briefing() -> str:
    """生成完整早报"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    sections = [
        f"🌅 Investment Commander 早报 {now}",
        "=" * 40,
        get_us_overnight(),
        "",
        get_market_state_report(),
        "",
        "",
        get_short_term_news(),
        "",
        get_medium_term_calendar(),
        "",
        get_long_term_tracking(),
    ]
    
    portfolio = get_portfolio_status()
    if portfolio:
        sections.extend(["", portfolio])
    
    sections.extend([
        "",
        "=" * 40,
        "📌 今日行动建议",
    ])
    
    # 根据大盘状态给出行动建议
    try:
        today = datetime.now().strftime("%Y%m%d")
        state = get_market_state(today)
        
        if not state["can_select"]:
            sections.append("  🚫 大盘偏弱，建议今日空仓观望，不做新仓")
        else:
            sections.append("  ✅ 大盘正常，可正常参考今日选股推荐")
            sections.append(
                "  运行: python3 scripts/commander_final.py --auto"
            )
    except:
        pass
    
    return "\n".join(sections)


if __name__ == "__main__":
    print(generate_morning_briefing())
