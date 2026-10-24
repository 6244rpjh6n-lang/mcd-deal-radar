#!/usr/bin/env python3
"""麦麦优惠雷达 —— 一条命令看清今天麦当劳有什么活动、有什么券能领。

用法：
    python scripts/deal_radar.py             # 今日活动 + 未来活动 + 券
    python scripts/deal_radar.py --all       # 连往期活动一起看
    python scripts/deal_radar.py --claim     # 顺便一键领券（会改动账户）
    python scripts/deal_radar.py --json      # 输出结构化 JSON，便于二次处理
    python scripts/deal_radar.py --tools     # 列出服务端可用工具，排查问题

依赖：仅 Python 3.9+ 标准库；需要环境变量 MCD_MCP_TOKEN。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime

for _stream in (sys.stdout, sys.stderr):
    # Windows 控制台默认可能是 GBK，中文与 emoji 会报 UnicodeEncodeError
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcd_mcp import McpClient, McpError  # noqa: E402

RULE = "─" * 60
IMG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
PAST_LABEL = "往期回顾"


@dataclass
class Event:
    date: str
    label: str
    title: str
    body: str

    @property
    def is_today(self):
        return self.label == "今日"

    @property
    def is_past(self):
        return self.label == PAST_LABEL


@dataclass
class Coupon:
    title: str
    status: str


# --------------------------------------------------------------------- 解析
def strip_markup(text):
    """去掉图片标签与 Markdown 续行反斜杠，保留可读文本。"""
    text = IMG_RE.sub("", text)
    text = re.sub(r"[ \t]*\\[ \t]*\r?\n", "\n", text)  # 行尾 \ 续行
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def clip(text, limit):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def parse_server_time(raw):
    """now-time-info 返回的是一段说明文档 + Original Response JSON。"""
    if not isinstance(raw, str):
        return ""
    marker = raw.rfind("## Original Response")
    blob = raw[marker + len("## Original Response"):] if marker >= 0 else raw
    try:
        start, end = blob.index("{"), blob.rindex("}") + 1
        data = json.loads(blob[start:end]).get("data", {})
        return data.get("formatted") or data.get("datetime") or ""
    except (ValueError, json.JSONDecodeError, AttributeError):
        match = re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", raw)
        return match.group(0) if match else ""


def parse_calendar(raw):
    """campaign-calendar 返回 Markdown：#### 日期 标签 + 活动标题/介绍。"""
    if not isinstance(raw, str):
        return []
    text = strip_markup(raw)
    events = []
    for block in re.split(r"^####\s+", text, flags=re.MULTILINE)[1:]:
        lines = block.splitlines()
        if not lines:
            continue
        header = lines[0].strip()
        match = re.match(r"^(\S+?日)\s*(.*)$", header)
        date, label = (match.group(1), match.group(2).strip()) if match else (header, "")
        rest = "\n".join(lines[1:])

        title = ""
        found = re.search(r"\*\*活动标题\*\*[：:]\s*(.+)", rest)
        if found:
            title = found.group(1).strip()

        body = ""
        found = re.search(
            r"\*\*活动内容介绍\*\*[：:]\s*(.+?)(?=\n\s*\*\*|\Z)", rest, re.DOTALL
        )
        if found:
            body = " ".join(part.strip() for part in found.group(1).splitlines() if part.strip())

        if title or body:
            events.append(Event(date=date, label=label, title=title, body=body))
    return events


def parse_coupons(raw):
    """available-coupons 返回 Markdown 列表：优惠券标题 / 状态 / 图片。"""
    if not isinstance(raw, str):
        return []
    text = strip_markup(raw)
    coupons = []
    for block in re.split(r"^-\s+", text, flags=re.MULTILINE)[1:]:
        title = re.search(r"优惠券标题[：:]\s*(.+)", block)
        status = re.search(r"状态[：:]\s*(.+)", block)
        if title:
            coupons.append(
                Coupon(
                    title=title.group(1).strip(),
                    status=status.group(1).strip() if status else "未知",
                )
            )
    return coupons


# --------------------------------------------------------------------- 输出
def render_event(event, indent="  "):
    tag = f"[{event.label}] " if event.label else ""
    print(f"{indent}· {tag}{event.title or '（未命名活动）'}")
    if event.body:
        print(f"{indent}    {clip(event.body, 78)}")


def show_events(title, events, limit, empty):
    print(f"\n{title}")
    if not events:
        print(f"  （{empty}）")
        return
    for event in events[:limit]:
        render_event(event)
    if len(events) > limit:
        print(f"  … 还有 {len(events) - limit} 场，用 --all 查看")


def main(argv=None):
    parser = argparse.ArgumentParser(description="麦麦优惠雷达：今日活动与优惠券速查")
    parser.add_argument("--claim", action="store_true", help="一键领取麦麦省可用优惠券（会改动账户）")
    parser.add_argument("--all", action="store_true", help="同时列出往期活动")
    parser.add_argument("--json", action="store_true", help="输出结构化 JSON")
    parser.add_argument("--tools", action="store_true", help="列出服务端可用工具")
    parser.add_argument("--limit", type=int, default=5, help="每个板块最多显示条数，默认 5")
    parser.add_argument("--timeout", type=int, default=30, help="单次请求超时秒数，默认 30")
    args = parser.parse_args(argv)

    try:
        client = McpClient(timeout=args.timeout)
        info = client.initialize()
    except McpError as exc:
        print(f"✗ 连接麦当劳 MCP 失败：{exc}", file=sys.stderr)
        return 2

    if args.tools:
        for tool in client.list_tools():
            first_line = (tool.get("description") or "").strip().splitlines()
            summary = first_line[0][:70] if first_line else ""
            print(f"{tool.get('name', ''):<24} {summary}")
        return 0

    def call(tool, arguments=None):
        try:
            return client.call_tool(tool, arguments or {}), None
        except McpError as exc:
            return None, str(exc)

    time_raw, time_err = call("now-time-info")
    calendar_raw, calendar_err = call("campaign-calendar")
    coupons_raw, coupons_err = call("available-coupons")
    claimed, claim_err = call("auto-bind-coupons") if args.claim else (None, None)

    server_time = parse_server_time(time_raw) or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    events = parse_calendar(calendar_raw)
    coupons = parse_coupons(coupons_raw)

    today = [e for e in events if e.is_today]
    upcoming = [e for e in events if not e.is_today and not e.is_past]
    past = [e for e in events if e.is_past]

    if args.json:
        print(json.dumps(
            {
                "server_time": server_time,
                "today": [asdict(e) for e in today],
                "upcoming": [asdict(e) for e in upcoming],
                "past": [asdict(e) for e in past],
                "coupons": [asdict(c) for c in coupons],
                "claimed": strip_markup(claimed) if isinstance(claimed, str) else claimed,
                "errors": {
                    "time": time_err, "calendar": calendar_err,
                    "coupons": coupons_err, "claim": claim_err,
                },
            },
            ensure_ascii=False, indent=2,
        ))
        return 0 if not (calendar_err and coupons_err) else 1

    print(f"🍟 麦麦优惠雷达 · {server_time[:16]}")
    print(RULE)
    print(f"服务端：{client.url} · 协议版本：{info.get('protocolVersion', '未知')} · 时间为北京时间")
    print(RULE)

    if calendar_err:
        print(f"\n📅 活动\n  ⚠ 查询失败：{calendar_err}")
    else:
        show_events("📅 今日活动", today, args.limit, "今天没有单独标注的活动，见下方未来活动")
        show_events("📅 即将到来", upcoming, args.limit, "暂无未来活动")
        if args.all:
            show_events("📅 往期回顾", past, args.limit, "暂无往期活动")
        elif past:
            print(f"\n📅 往期回顾\n  共 {len(past)} 场，用 --all 查看")

    print(f"\n🎟 麦麦省优惠券（{len(coupons)} 张）" if coupons else "\n🎟 麦麦省优惠券")
    if coupons_err:
        print(f"  ⚠ 查询失败：{coupons_err}")
    elif not coupons:
        print("  （暂无可领的券）")
    else:
        claimable = sum(1 for c in coupons if "已领取" not in c.status)
        for coupon in coupons[: args.limit]:
            print(f"  · {coupon.title}  [{coupon.status}]")
        if len(coupons) > args.limit:
            print(f"  … 还有 {len(coupons) - args.limit} 张")
        print(f"  → 其中 {claimable} 张待领取")

    if args.claim:
        print("\n🎁 一键领券")
        if claim_err:
            print(f"  ⚠ 领券失败：{claim_err}")
        else:
            print(f"  ✓ {clip(strip_markup(claimed) if isinstance(claimed, str) else str(claimed), 200)}")

    print(f"\n{RULE}")
    print("提示：券的可用范围、有效期与活动规则以麦当劳官方渠道为准。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
