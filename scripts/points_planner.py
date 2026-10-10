#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦享会积分止损方案计算器 —— Mc-Use-It-or-Lose-It（麦麦积分末班车）.

输入 mcd-mcp 四个只读工具的原始返回，输出「本月将过期积分」的止损方案对比。

输入（stdin 或 --input 指定 JSON 文件）:
{
  "now":      "2026-10-10 11:12:21",          // now-time-info.data.formatted
  "account":  {...},                          // query-my-account.data
  "lottery":  {...},                          // query-lottery-info.data
  "products": [ {...}, ... ]                  // mall-points-products.data
}

输出：JSON（--format json）或可读文本（默认）。

设计约束：本脚本只做计算，不做任何网络调用，不发起抽奖或兑换。
真实消耗动作由 Skill 编排层在用户明确确认后调用 mcd-mcp 完成。
"""

import argparse
import json
import math
import sys
from datetime import datetime

# 商品状态码 -> 文案
STATUS_TEXT = {1: "仓库中", 2: "上架", 3: "售罄", 4: "下架", 5: "预热"}

# 时间解析候选格式，按优先级尝试
DT_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")


def to_float(value, default=0.0):
    """把 '9.9' / 9.9 / None 统一成 float。"""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def parse_time(value):
    """解析接口返回的时间字符串，失败返回 None。"""
    if not value:
        return None
    text = str(value).strip().replace("T", " ")[:19]
    for fmt in DT_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def fmt_points(value):
    """积分展示：整数不显示 .0。"""
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def is_on_shelf(product, now):
    """判断商品是否在当前时段可兑换。

    注意：接口的 status 字段存在滞后，下架时间已过仍可能返回 2(上架)，
    因此时间窗口是主判据，status 仅作辅助。
    """
    if int(to_float(product.get("status"), 0)) != 2:
        return False, "非上架状态"
    up = parse_time(product.get("upTime"))
    down = parse_time(product.get("downTime"))
    if now is None:
        return True, "未提供当前时间，跳过时效校验"
    if down is not None and now > down:
        return False, "兑换已截止"
    if up is not None and now < up:
        return False, "尚未开始兑换"
    return True, "在售"


def lottery_unit_cost(lottery):
    """从 drawDecision 取本次实际消耗积分；无法确定时返回 None。

    严格遵守 mcd-mcp 约束：抽奖资格与消耗以 drawDecision 为准，
    不得根据 availableTimes 或 drawTypeText 自行推断。
    """
    decision = (lottery or {}).get("drawDecision") or {}
    if decision.get("resourceEligible") is False:
        return None
    consumption = decision.get("nextConsumption") or {}
    if consumption.get("type") == "POINTS":
        cost = to_float(consumption.get("points"), 0.0)
        return cost if cost > 0 else None
    return None


def build_plan(payload):
    now = parse_time(payload.get("now"))
    account = payload.get("account") or {}
    lottery = payload.get("lottery") or {}
    products = payload.get("products") or []

    available = to_float(account.get("availablePoint"))
    expiring = to_float(account.get("currentMouthExpirePoint"))
    expiring_next = to_float(account.get("nextMouthExpirePoint"))
    expired = to_float(account.get("expiredPoint"))

    result = {
        "snapshotTime": payload.get("now"),
        "account": {
            "availablePoint": available,
            "thisMonthExpire": expiring,
            "nextMonthExpire": expiring_next,
            "alreadyExpired": expired,
        },
        "needToBurn": expiring,
        "lottery": None,
        "redeem": [],
        "recommendation": None,
        "warnings": [],
    }

    # ---------- 抽奖方案 ----------
    status = (lottery or {}).get("status") or {}
    unit_cost = lottery_unit_cost(lottery)
    lottery_plan = {
        "activityName": lottery.get("activityName"),
        "activityStatus": lottery.get("activityStatusText"),
        "endTime": lottery.get("endTime"),
        "drawTypeText": lottery.get("drawTypeText"),
        "unitCost": unit_cost,
        "prizeCount": len(lottery.get("prizes") or []),
        "prizes": [p.get("name") for p in (lottery.get("prizes") or [])],
        "feasible": False,
        "drawsNeeded": None,
        "pointsBurned": None,
        "remainingAfter": None,
        "reason": None,
    }

    if status.get("code") not in (None, "SUCCESS"):
        lottery_plan["reason"] = status.get("message") or "抽奖活动不可用"
    elif unit_cost is None:
        lottery_plan["reason"] = "当前无可用积分抽奖消耗（活动不存在或规则非消耗积分）"
    elif unit_cost > available:
        lottery_plan["reason"] = f"可用积分 {fmt_points(available)} 不足单次消耗 {fmt_points(unit_cost)}"
    elif expiring <= 0:
        lottery_plan["reason"] = "本月无将过期积分，无需抽奖止损"
    else:
        draws = int(math.ceil((expiring - 1e-9) / unit_cost))
        burned = draws * unit_cost
        lottery_plan.update(
            feasible=burned <= available + 1e-9,
            drawsNeeded=draws,
            pointsBurned=burned,
            remainingAfter=available - burned,
        )
        if not lottery_plan["feasible"]:
            lottery_plan["reason"] = (
                f"止损需抽 {draws} 次共消耗 {fmt_points(burned)} 分，超出可用积分 {fmt_points(available)}"
            )
    result["lottery"] = lottery_plan

    # ---------- 兑换方案 ----------
    on_shelf, skipped = [], []
    for product in products:
        ok, reason = is_on_shelf(product, now)
        point = to_float(product.get("point"))
        item = {
            "spuId": product.get("spuId"),
            "spuName": product.get("spuName"),
            "point": point,
            "catName": product.get("catName"),
            "shopId": product.get("shopId"),
            "downTime": product.get("downTime"),
            "affordable": point <= available + 1e-9,
            "coversExpiring": point >= expiring - 1e-9,
        }
        item["statusText"] = reason if not ok else STATUS_TEXT.get(int(to_float(product.get("status"), 0)), "未知")
        (on_shelf if ok else skipped).append(item)

    on_shelf.sort(key=lambda x: x["point"])
    result["redeem"] = on_shelf

    # 一次兑换即可覆盖本月过期积分的最省商品
    covers = [p for p in on_shelf if p["affordable"] and p["coversExpiring"]]
    cheapest_cover = covers[0] if covers else None

    # 积分不够但最接近的，作为攒分提示
    unaffordable = [p for p in on_shelf if not p["affordable"]]

    result["redeemSkippedCount"] = len(skipped)
    result["cheapestSingleCover"] = cheapest_cover
    result["cheapestAny"] = on_shelf[0] if on_shelf else None
    result["gapToCheapest"] = (
        max(0.0, unaffordable[0]["point"] - available) if unaffordable else 0.0
    )

    # ---------- 推荐 ----------
    candidates = []
    if lottery_plan.get("feasible"):
        candidates.append(
            {
                "type": "lottery",
                "label": f"积分抽奖 × {lottery_plan['drawsNeeded']}",
                "burn": lottery_plan["pointsBurned"],
                "remaining": lottery_plan["remainingAfter"],
                "note": f"单次 {fmt_points(unit_cost)} 分，共 {lottery_plan['prizeCount']} 种奖品",
            }
        )
    if cheapest_cover:
        candidates.append(
            {
                "type": "redeem",
                "label": f"兑换《{cheapest_cover['spuName']}》",
                "burn": cheapest_cover["point"],
                "remaining": available - cheapest_cover["point"],
                "note": f"spuId={cheapest_cover['spuId']}，有效期至 {cheapest_cover['downTime']}",
            }
        )

    if expiring <= 0:
        result["recommendation"] = {
            "action": "none",
            "text": f"本月无将过期积分（可用 {fmt_points(available)} 分）。"
            + (f"下月将过期 {fmt_points(expiring_next)} 分，建议留意。" if expiring_next > 0 else ""),
        }
    elif candidates:
        best = min(candidates, key=lambda c: (c["burn"], -c["remaining"]))
        result["recommendation"] = {
            "action": best["type"],
            "text": (
                f"本月将过期 {fmt_points(expiring)} 分，建议{best['label']}，"
                f"消耗 {fmt_points(best['burn'])} 分，剩余可用 {fmt_points(best['remaining'])} 分。"
            ),
            "candidates": candidates,
        }
    else:
        gap = result["gapToCheapest"]
        result["recommendation"] = {
            "action": "accumulate",
            "text": (
                f"本月将过期 {fmt_points(expiring)} 分，但现有 {len(on_shelf)} 个在售商品与"
                f"抽奖方案均无法覆盖（门槛最低 {fmt_points(result['cheapestAny']['point'])} 分，"
                f"还差 {fmt_points(gap)} 分）。建议先点餐攒积分，或等待新一期活动。"
            )
            if result["cheapestAny"]
            else f"本月将过期 {fmt_points(expiring)} 分，当前无在售兑换商品，且抽奖不可用，建议持续关注活动更新。",
        }

    # ---------- 风险提示 ----------
    if expired > 0:
        result["warnings"].append(
            f"历史已过期积分 {fmt_points(expired)} 分（含上月 {fmt_points(to_float(account.get('lastMouthExpirePoint')))} 分），"
            "本工具只能止损未来过期部分，已过期的无法找回。"
        )
    if expiring_next > 0:
        result["warnings"].append(f"下月还将过期 {fmt_points(expiring_next)} 分，建议提前规划。")
    if result["redeemSkippedCount"] > 0:
        result["warnings"].append(
            f"接口返回的 {result['redeemSkippedCount']} 个商品已过兑换截止时间（status 仍显示上架），已自动剔除。"
        )
    frozen = to_float(account.get("frozenPoint"))
    if frozen > 0:
        result["warnings"].append(f"存在冻结积分 {fmt_points(frozen)} 分，未计入可用积分。")

    return result


def render_text(plan):
    """把方案渲染成适合直接回复用户的中文文本。"""
    lines = []
    acc = plan["account"]
    lines.append("积分止损体检")
    lines.append(f"  快照时间：{plan['snapshotTime']}")
    lines.append(
        f"  可用积分 {fmt_points(acc['availablePoint'])}｜本月将过期 {fmt_points(acc['thisMonthExpire'])}"
        f"｜下月将过期 {fmt_points(acc['nextMonthExpire'])}｜累计已过期 {fmt_points(acc['alreadyExpired'])}"
    )
    lines.append("")

    lot = plan["lottery"]
    lines.append(f"抽奖方案：{lot['activityName']}（{lot['activityStatus']}）")
    if lot["feasible"]:
        lines.append(
            f"  可行 → 抽 {lot['drawsNeeded']} 次，消耗 {fmt_points(lot['pointsBurned'])} 分，"
            f"剩余 {fmt_points(lot['remainingAfter'])} 分"
        )
    else:
        lines.append(f"  不可行 → {lot['reason']}")
    lines.append("")

    lines.append(f"兑换方案：当前在售 {len(plan['redeem'])} 个商品")
    for item in plan["redeem"][:10]:
        flag = "可兑" if item["affordable"] else f"差 {fmt_points(item['point'] - acc['availablePoint'])} 分"
        lines.append(
            f"  [{flag}] {item['spuName']}｜{fmt_points(item['point'])} 分｜"
            f"截止 {item['downTime']}｜spuId={item['spuId']}"
        )
    if len(plan["redeem"]) > 10:
        lines.append(f"  ...另有 {len(plan['redeem']) - 10} 个")
    lines.append("")

    lines.append(f"建议：{plan['recommendation']['text']}")
    if plan["warnings"]:
        lines.append("")
        lines.append("提示：")
        for warning in plan["warnings"]:
            lines.append(f"  - {warning}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="麦享会积分止损方案计算器")
    parser.add_argument("--input", "-i", help="输入 JSON 文件路径，默认从 stdin 读取")
    parser.add_argument("--format", "-f", choices=("text", "json"), default="text")
    args = parser.parse_args()

    if args.input:
        with open(args.input, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        payload = json.load(sys.stdin)

    plan = build_plan(payload)
    if args.format == "json":
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        print(render_text(plan))


if __name__ == "__main__":
    main()
