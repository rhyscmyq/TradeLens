from __future__ import annotations

from typing import Any


def _money(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):,.2f}"


def _pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{float(value) * 100:.2f}%"


def _single_attribution_table(breakdown: Any, *, title: str) -> list[str]:
    if breakdown is None:
        return [f"### {title}", "", "_Profit breakdown unavailable._", ""]

    bench = getattr(breakdown, "benchmark_symbol", "N/A")
    bench_ret = getattr(breakdown, "benchmark_return", None)
    bench_ok = bool(getattr(breakdown, "benchmark_available", False))
    mode = getattr(breakdown, "market_mode", "full_cash")

    v0 = float(getattr(breakdown, "v0", 0.0) or 0.0)
    v_market = float(getattr(breakdown, "v_market", 0.0) or 0.0)
    v_static = float(getattr(breakdown, "v_static", 0.0) or 0.0)
    v_end = float(getattr(breakdown, "v_end", 0.0) or 0.0)
    market_effect = float(getattr(breakdown, "market_effect", 0.0) or 0.0)
    selection_effect = float(getattr(breakdown, "asset_selection_effect", 0.0) or 0.0)
    timing_effect = float(getattr(breakdown, "timing_effect", 0.0) or 0.0)
    total_profit = float(getattr(breakdown, "total_profit", 0.0) or 0.0)

    invested = getattr(breakdown, "invested_cash", None)
    cash_after = getattr(breakdown, "cash_after_first_day", None)

    lines = [
        f"### {title}",
        "",
        f"Benchmark: **{bench}** | Mode: `{mode}` | Benchmark return: {_pct(bench_ret) if bench_ok else 'N/A'}",
        "",
        "| Line item | Amount (USD) |",
        "| --- | ---: |",
        f"| Initial capital (v₀) | {_money(v0)} |",
        f"| Benchmark portfolio at end (v_market) | {_money(v_market)} |",
        f"| Buy & hold portfolio at end (v_static) | {_money(v_static)} |",
        f"| Strategy portfolio at end (v_end) | {_money(v_end)} |",
        "| | |",
        "| **Profit attribution** | |",
        f"| Market effect | {_money(market_effect)} |",
        f"| Asset selection effect | {_money(selection_effect)} |",
        f"| Timing effect | {_money(timing_effect)} |",
        f"| **Total profit (gross)** | **{_money(total_profit)}** |",
    ]
    if invested is not None or cash_after is not None:
        lines.extend(
            [
                "| | |",
                "| Invested cash (excl. idle cash after day 1) | "
                f"{_money(float(invested) if invested is not None else None)} |",
                f"| Cash after first build day | {_money(float(cash_after) if cash_after is not None else None)} |",
            ]
        )
    lines.append("")
    return lines


def build_financial_statement_markdown(
    breakdown_full: Any,
    breakdown_invested: Any,
    *,
    gross_profit: float,
    static_cost: float,
    dynamic_cost: float,
    total_cost: float,
    net_portfolio: float,
    timing_effect: float,
    net_timing: float,
) -> str:
    """生成两张类 P&L 结构的财务表（全本金基准 vs 按投资金额比例基准）。"""
    sections = [
        "## 3.2 Financial Statement (Profit & Loss Style)",
        "",
        "Two attribution views: **full initial cash** tracks the whole portfolio against the benchmark; "
        "**invested-only** removes idle cash after the first build day when applying market moves.",
        "",
        *_single_attribution_table(
            breakdown_full,
            title="Table A — Full Cash / Market Benchmark",
        ),
        *_single_attribution_table(
            breakdown_invested,
            title="Table B — Invested Cash Only (Proportional to Deployed Capital)",
        ),
        "### Consolidated Net Outcome (two views)",
        "",
        "| Line item | Amount (USD) |",
        "| --- | ---: |",
        "| **Portfolio level** | |",
        f"| Gross profit (v_end − v₀) | {_money(gross_profit)} |",
        f"| Static cost (data subscription) | {_money(-static_cost)} |",
        f"| Dynamic cost (commission + token + infra + uncertain) | {_money(-dynamic_cost)} |",
        f"| Total operating cost | {_money(-total_cost)} |",
        f"| **Net economic outcome (gross − total cost)** | **{_money(net_portfolio)}** |",
        "| | |",
        "| **Execution / timing layer** | |",
        f"| Timing effect (vs initial buy&hold) | {_money(timing_effect)} |",
        f"| Dynamic cost (same as above) | {_money(-dynamic_cost)} |",
        f"| **Net timing outcome (timing − dynamic cost)** | **{_money(net_timing)}** |",
        "",
    ]
    return "\n".join(sections)


def build_net_outcome_markdown(
    *,
    gross_profit: float,
    return_profit: float,
    static_cost: float,
    dynamic_cost: float,
    total_cost: float,
    timing_effect: float | None,
    market_effect: float | None = None,
    selection_effect: float | None = None,
    action_basename: str,
) -> list[str]:
    net_portfolio = float(gross_profit) - float(total_cost)
    net_timing = float(timing_effect or 0.0) - float(dynamic_cost)
    lines = [
        "## 7. Net Economic Outcome",
        "",
        f"Daily actions and detailed cost lines: see `{action_basename}`.",
        "",
        "### 7.1 Portfolio level — gross profit vs total cost",
        "",
        "Uses profit-breakdown **total profit** (v_end − v₀), i.e. market + selection + timing.",
        "",
        "| Line item | Amount (USD) |",
        "| --- | ---: |",
        f"| Gross profit (attribution total) | {_money(gross_profit)} |",
        f"| Return / profit (portfolio replay) | {_money(return_profit)} |",
        f"| Static cost | {_money(-static_cost)} |",
        f"| Dynamic cost | {_money(-dynamic_cost)} |",
        f"| Total cost | {_money(-total_cost)} |",
        f"| **Net outcome (gross − total cost)** | **{_money(net_portfolio)}** |",
        "",
        "### 7.2 Execution layer — timing effect vs dynamic cost",
        "",
        "Isolates **timing** (actual strategy vs buy&hold) against costs that scale with trading/decisions.",
        "",
        "| Line item | Amount (USD) |",
        "| --- | ---: |",
    ]
    if market_effect is not None:
        lines.append(f"| Market effect (context) | {_money(market_effect)} |")
    if selection_effect is not None:
        lines.append(f"| Asset selection effect (context) | {_money(selection_effect)} |")
    lines.extend(
        [
            f"| Timing effect | {_money(timing_effect)} |",
            f"| Dynamic cost | {_money(-dynamic_cost)} |",
            f"| **Net timing outcome (timing − dynamic cost)** | **{_money(net_timing)}** |",
            "",
        ]
    )
    return lines
