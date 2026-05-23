import json
import os
from collections import Counter

from ..cost.commission import format_action_summary
from .financial_table import build_financial_statement_markdown, build_net_outcome_markdown


def _format_money(value):
    return f"{value:.2f}"


def _build_run_stem(llm_model, initial_cash, frequency):
    return f"{llm_model}-{initial_cash}-{frequency}"


def split_operating_costs(
    commission_total: float,
    token_total: float,
    infra_total: float,
    monthly_total: float,
    uncertain_cost: float,
) -> dict[str, float]:
    """静态成本 = 数据订阅；动态成本 = 与交易/决策执行直接相关的成本。"""
    static_cost = float(monthly_total)
    dynamic_cost = (
        float(commission_total)
        + float(token_total)
        + float(infra_total)
        + float(uncertain_cost)
    )
    total_cost = static_cost + dynamic_cost
    return {
        "static_cost": static_cost,
        "dynamic_cost": dynamic_cost,
        "total_cost": total_cost,
    }


def build_report_text(
    actions_by_date,
    trading_days,
    commission_total,
    token_total,
    infra_total,
    monthly_total,
    uncertain_cost,
    total_cost,
):
    costs = split_operating_costs(
        commission_total, token_total, infra_total, monthly_total, uncertain_cost
    )
    report_lines = [
        "# Actions & Cost Ledger",
        "",
        "## Actions by trading day",
        *format_action_summary(actions_by_date),
        "",
        "## Cost totals",
        f"  trading_days: {trading_days}",
        f"  commission_total: {commission_total:.2f}",
        f"  token_total: {token_total:.2f}",
        f"  infra_total: {infra_total:.2f}",
        f"  monthly_total (static): {monthly_total:.2f}",
        f"  uncertain_cost: {uncertain_cost:.2f}",
        "",
        "## Cost split",
        f"  static_cost (data subscription): {costs['static_cost']:.2f}",
        f"  dynamic_cost (commission + token + infra + uncertain): {costs['dynamic_cost']:.2f}",
        f"  total_cost: {costs['total_cost']:.2f}",
    ]
    return "\n".join(report_lines)


def build_report_payload(
    llm_model,
    initial_cash,
    frequency,
    actions_by_date,
    trading_days,
    commission_total,
    token_total,
    infra_total,
    monthly_total,
    uncertain_cost,
    total_cost,
):
    costs = split_operating_costs(
        commission_total, token_total, infra_total, monthly_total, uncertain_cost
    )
    return {
        "llm_model": llm_model,
        "initial_cash": initial_cash,
        "frequency": frequency,
        "action_summary_by_day": [
            {
                "date": date,
                "actions": dict(Counter(actions_by_date[date])),
            }
            for date in sorted(actions_by_date.keys())
        ],
        "cost_totals": {
            "trading_days": trading_days,
            "commission_total": round(commission_total, 2),
            "token_total": round(token_total, 2),
            "infra_total": round(infra_total, 2),
            "monthly_total": round(monthly_total, 2),
            "uncertain_cost": round(uncertain_cost, 2),
            "static_cost": round(costs["static_cost"], 2),
            "dynamic_cost": round(costs["dynamic_cost"], 2),
            "total_cost": round(costs["total_cost"], 2),
        },
    }


def save_action_ledger(report_text, result_dir, llm_model, initial_cash, frequency):
    filename = f"{_build_run_stem(llm_model, initial_cash, frequency)}-action.txt"
    path = os.path.join(result_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(report_text + "\n")
    print(f"\nSaved action ledger to: {path}")


def save_report_jsonl(report_payload, result_dir, llm_model, initial_cash, frequency):
    jsonl_filename = f"{llm_model}_{initial_cash}_{frequency}.jsonl"
    result_path = os.path.join(result_dir, jsonl_filename)
    with open(result_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(report_payload, ensure_ascii=False) + "\n")
    print(f"\nSaved report to: {result_path}")


def _resolve_trading_period(records, static_config):
    start_time = static_config.get("start_time")
    end_time = static_config.get("end_time")
    if start_time and end_time:
        return str(start_time), str(end_time)

    dates = [str(record.get("date") or "") for record in records if record.get("date")]
    if not dates:
        return "unknown", "unknown"
    return min(dates), max(dates)


def _resolve_strategy_identifier(records, static_config, llm_model):
    identifier = static_config.get("signature") or static_config.get("strategy_id")
    if identifier:
        return str(identifier)
    for record in records:
        signature = record.get("signature")
        if signature:
            return str(signature)
    return str(llm_model)


def _compute_average_daily_llm_metrics(records):
    date_days = set()
    total_latency_ms = 0.0
    total_input_tokens = 0
    total_output_tokens = 0

    for record in records:
        date_raw = record.get("date")
        if not date_raw:
            continue
        date_str = str(date_raw)
        date_part = date_str.split(" ")[0].split("T")[0]
        date_days.add(date_part)

        llm_usage = record.get("llm_usage") or {}
        latency_ms = llm_usage.get("latency_ms")
        if isinstance(latency_ms, (int, float)):
            total_latency_ms += float(latency_ms)
        total_input_tokens += int(llm_usage.get("input_tokens") or 0)
        total_output_tokens += int(llm_usage.get("output_tokens") or 0)

    date_days_count = len(date_days)
    if not date_days_count:
        return 0.0, 0.0, 0.0, 0

    average_daily_latency_ms = total_latency_ms / date_days_count
    average_daily_input_tokens = total_input_tokens / date_days_count
    average_daily_output_tokens = total_output_tokens / date_days_count
    return (
        average_daily_latency_ms,
        average_daily_input_tokens,
        average_daily_output_tokens,
        date_days_count,
    )


_FIGURE_SPECS: tuple[tuple[str, str, str], ...] = (
    ("profit_full", "Figure 1", "Profit Attribution — Full Cash Benchmark"),
    ("profit_invested", "Figure 2", "Profit Attribution — Invested Cash Only"),
    ("cost_pie", "Figure 3", "Operating Cost Composition"),
    ("cost_pie_no_monthly", "Figure 4", "Operating Cost Composition (Excl. Data Subscription)"),
    ("performance", "Figure 5", "Portfolio Value vs Cumulative Dynamic Cost"),
    ("performance_no_monthly", "Figure 6", "Portfolio Value vs Dynamic Cost (Excl. Subscription)"),
)


def _figure_meta(key: str) -> tuple[str, str] | None:
    for figure_key, figure_id, caption in _FIGURE_SPECS:
        if figure_key == key:
            return figure_id, caption
    return None


def _figure_block(chart_paths: dict[str, str] | None, *keys: str) -> list[str]:
    if not chart_paths:
        return []
    lines: list[str] = []
    key_set = set(keys)
    for key, figure_id, caption in _FIGURE_SPECS:
        if key not in key_set:
            continue
        rel = chart_paths.get(key)
        if not rel:
            continue
        lines.extend(
            [
                f"### {figure_id}. {caption}",
                "",
                f"![{figure_id}: {caption}]({rel})",
                "",
            ]
        )
    return lines


def _figure_grid_block(chart_paths: dict[str, str] | None, *keys: str) -> list[str]:
    if not chart_paths:
        return []

    figures: list[str] = []
    for key in keys:
        meta = _figure_meta(key)
        rel = chart_paths.get(key) if chart_paths else None
        if meta is None or not rel:
            continue
        figure_id, caption = meta
        figures.extend(
            [
                '<figure class="report-figure report-figure-compact">',
                f'  <img class="report-chart report-chart-compact" src="{rel}" alt="{figure_id}: {caption}" />',
                f"  <figcaption>{figure_id}. {caption}</figcaption>",
                "</figure>",
            ]
        )

    if not figures:
        return []

    return [
        '<div class="report-figure-grid report-figure-grid-2">',
        *figures,
        "</div>",
        "",
    ]


def build_financial_report_markdown(
    records,
    static_config,
    llm_model,
    initial_cash,
    frequency,
    commission_total,
    token_total,
    infra_total,
    monthly_total,
    uncertain_cost,
    total_cost,
    portfolio_state,
    opportunity_cost,
    average_latency_ms,
    trade_count,
    profit_breakdown=None,
    profit_breakdown_invested=None,
    chart_paths: dict[str, str] | None = None,
):
    start_time, end_time = _resolve_trading_period(records, static_config)
    strategy_id = _resolve_strategy_identifier(records, static_config, llm_model)
    (
        average_daily_latency_ms,
        average_daily_input_tokens,
        average_daily_output_tokens,
        date_days_count,
    ) = _compute_average_daily_llm_metrics(records)

    assets = portfolio_state.get("assets", [])
    assets_text = ", ".join(assets) if assets else "N/A"

    positions = portfolio_state.get("positions", [])
    if positions:
        positions_lines = [f"- {item['ticker']}: {item['quantity']}" for item in positions]
        positions_text = "\n".join(positions_lines)
    else:
        positions_text = "None"

    current_cash = portfolio_state.get("current_cash", 0.0)
    total_position_value = portfolio_state.get("total_position_value", 0.0)
    total_portfolio_value = portfolio_state.get("total_portfolio_value", 0.0)
    return_profit = float(portfolio_state.get("return_profit", 0.0))
    costs = split_operating_costs(
        commission_total, token_total, infra_total, monthly_total, uncertain_cost
    )
    static_cost = costs["static_cost"]
    dynamic_cost = costs["dynamic_cost"]
    total_cost_computed = costs["total_cost"]

    gross_profit = float(return_profit)
    timing_effect = None
    market_effect = None
    selection_effect = None
    if profit_breakdown is not None:
        gross_profit = float(getattr(profit_breakdown, "total_profit", gross_profit) or gross_profit)
        timing_effect = float(getattr(profit_breakdown, "timing_effect", 0.0) or 0.0)
        market_effect = float(getattr(profit_breakdown, "market_effect", 0.0) or 0.0)
        selection_effect = float(getattr(profit_breakdown, "asset_selection_effect", 0.0) or 0.0)

    net_portfolio = gross_profit - total_cost_computed
    net_timing = (timing_effect or 0.0) - dynamic_cost
    action_basename = f"{_build_run_stem(llm_model, initial_cash, frequency)}-action.txt"
    average_latency_text = f"{average_latency_ms:.2f} ms" if trade_count else "N/A"
    average_daily_latency_text = f"{average_daily_latency_ms:.2f} ms" if date_days_count else "N/A"
    average_daily_input_tokens_text = f"{average_daily_input_tokens:.2f}" if date_days_count else "N/A"
    average_daily_output_tokens_text = f"{average_daily_output_tokens:.2f}" if date_days_count else "N/A"

    profit_lines = []
    if profit_breakdown is not None:
        try:
            bench = getattr(profit_breakdown, "benchmark_symbol", "unknown")
            bench_available = bool(getattr(profit_breakdown, "benchmark_available", False))
            bench_ret = getattr(profit_breakdown, "benchmark_return", None)

            def _fmt_pct(v):
                if v is None:
                    return "N/A"
                return f"{float(v) * 100:.2f}%"

            initial_holdings = getattr(profit_breakdown, "initial_holdings", {}) or {}
            holdings_text = ", ".join([f"{k}:{v}" for k, v in sorted(initial_holdings.items())]) or "N/A"

            profit_lines = [
                "## 3.1 Profit Breakdown (market / selection / timing)",
                "",
                f"Benchmark Symbol: {bench}",
                f"Benchmark Available: {bench_available}",
                f"Benchmark Return: {_fmt_pct(bench_ret) if bench_available else 'N/A'}",
                "",
                "v0 (Initial Cash):",
                _format_money(float(getattr(profit_breakdown, 'v0', 0.0))),
                "",
                "v_market (Benchmark Final Value):",
                _format_money(float(getattr(profit_breakdown, 'v_market', 0.0))),
                "",
                "v_static (Initial Holdings Buy&Hold Final Value):",
                _format_money(float(getattr(profit_breakdown, 'v_static', 0.0))),
                "",
                "v_end (Strategy Final Value):",
                _format_money(float(getattr(profit_breakdown, 'v_end', 0.0))),
                "",
                "Market Effect:",
                _format_money(float(getattr(profit_breakdown, "market_effect", 0.0))),
                "",
                "Asset Selection Effect:",
                _format_money(float(getattr(profit_breakdown, "asset_selection_effect", 0.0))),
                "",
                "Timing Effect:",
                _format_money(float(getattr(profit_breakdown, "timing_effect", 0.0))),
                "",
                "Total Profit:",
                _format_money(float(getattr(profit_breakdown, "total_profit", 0.0))),
                "",
                "Initial Holdings (first build day, post-trade):",
                holdings_text,
                "",
            ]
        except Exception:
            profit_lines = [
                "## 3.1 Profit Breakdown (market / selection / timing)",
                "",
                "Profit breakdown calculation is available, but failed to render.",
                "",
            ]

    financial_lines = []
    try:
        financial_lines = build_financial_statement_markdown(
            profit_breakdown,
            profit_breakdown_invested,
            gross_profit=gross_profit,
            static_cost=static_cost,
            dynamic_cost=dynamic_cost,
            total_cost=total_cost_computed,
            net_portfolio=net_portfolio,
            timing_effect=timing_effect or 0.0,
            net_timing=net_timing,
        ).splitlines()
        financial_lines = [line for line in financial_lines]
    except Exception:
        financial_lines = [
            "## 3.2 Financial Statement (Profit & Loss Style)",
            "",
            "Financial tables could not be generated.",
            "",
        ]

    lines = [
        "# Financial Report",
        "",
        "## 1. Trading Configuration",
        "",
        "Trading Period:",
        f"{start_time} - {end_time}",
        "",
        "Trading Model / Strategy:",
        strategy_id,
        "",
        "Assets:",
        assets_text,
        "",
        "## 2. Asset & Portfolio State",
        "",
        "Initial Cash:",
        _format_money(float(initial_cash)),
        "",
        "Current Cash:",
        _format_money(float(current_cash)),
        "",
        "Positions:",
        positions_text,
        "",
        "Total Position Value:",
        _format_money(float(total_position_value)),
        "",
        "Total Portfolio Value:",
        _format_money(float(total_portfolio_value)),
        "",
        "## 3. Performance",
        "",
        "Return / Profit:",
        _format_money(float(return_profit)),
        "",
        *_figure_block(chart_paths, "profit_full", "profit_invested"),
        *profit_lines,
        *financial_lines,
        "",
        "## 4. Cost Summary",
        f"Daily actions and line-item costs: `{action_basename}`.",
        "",
        "| Cost bucket | Amount (USD) |",
        "| --- | ---: |",
        f"| Static (data subscription) | {_format_money(static_cost)} |",
        f"| Dynamic (commission + token + infra + uncertain) | {_format_money(dynamic_cost)} |",
        f"| **Total** | **{_format_money(total_cost_computed)}** |",
        "",
        *_figure_grid_block(chart_paths, "cost_pie", "cost_pie_no_monthly"),
        "## 5. Portfolio Timeline",
        "",
        *_figure_block(chart_paths, "performance", "performance_no_monthly"),
        "## 6. Execution Quality",
        "",
        "Opportunity Cost (Decision Price - Execution Price)",
        _format_money(float(opportunity_cost)),
        "",
        "Average Latency per Trade",
        average_latency_text,
        "",
        "Average Daily LLM Latency",
        average_daily_latency_text,
        "",
        "Average Daily Input Tokens",
        average_daily_input_tokens_text,
        "",
        "Average Daily Output Tokens",
        average_daily_output_tokens_text,
        "",
        *build_net_outcome_markdown(
            gross_profit=gross_profit,
            return_profit=return_profit,
            static_cost=static_cost,
            dynamic_cost=dynamic_cost,
            total_cost=total_cost_computed,
            timing_effect=timing_effect,
            market_effect=market_effect,
            selection_effect=selection_effect,
            action_basename=action_basename,
        ),
    ]
    return "\n".join(lines)


def save_financial_report(report_markdown, result_dir, llm_model, initial_cash, frequency):
    md_filename = f"{_build_run_stem(llm_model, initial_cash, frequency)}-financial-report.md"
    md_path = os.path.join(result_dir, md_filename)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report_markdown + "\n")
    print(f"\nSaved financial report to: {md_path}")
    return md_path

