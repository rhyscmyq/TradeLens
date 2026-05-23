import argparse
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from ..config import get_project_root, load_app_config, load_static_config


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _resolve_records_path_for_tool(records_path: str | None) -> str | None:
    root = get_project_root()
    app_config = load_app_config(os.path.join(root, "config.json"))
    candidates: list[str] = []
    if records_path:
        candidates.append(str(records_path))
    env_override = os.getenv("TRADELENS_RECORDS_PATH")
    if env_override:
        candidates.append(str(env_override))
    config_path = app_config.get("records_path")
    if config_path:
        candidates.append(str(config_path))

    for raw in candidates:
        path = raw
        if not os.path.isabs(path):
            path = os.path.join(root, path)
        if os.path.exists(path):
            return path
    return None


def _load_jsonl(path: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw:
                continue
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return records


def _relaxed_json_loads(raw: str) -> dict[str, Any]:
    cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
    return json.loads(cleaned)


def _load_static_any(path: str) -> dict[str, Any]:
    raw = _read_text(path).strip()
    if not raw:
        return {}

    try:
        data = _relaxed_json_loads(raw)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, dict):
        if "structure" in data:
            try:
                return load_static_config(path)
            except (json.JSONDecodeError, ValueError):
                return data
        return data

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return {}


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _compute_average_daily_latency(records: list[dict[str, Any]]) -> dict[str, Any]:
    daily_latency_ms = defaultdict(float)
    trade_days = set()
    total_latency_ms = 0.0

    for record in records:
        date_raw = record.get("date")
        if not date_raw:
            continue
        date_str = str(date_raw)
        date_part = date_str.split(" ")[0].split("T")[0]
        llm_usage = record.get("llm_usage") or {}
        latency_ms = llm_usage.get("latency_ms")
        if isinstance(latency_ms, (int, float)):
            daily_latency_ms[date_part] += float(latency_ms)
            total_latency_ms += float(latency_ms)

        trades = record.get("trades", []) or []
        if trades:
            trade_days.add(date_part)

    trade_days_count = len(trade_days)
    average_daily_latency_ms = total_latency_ms / trade_days_count if trade_days_count else 0.0

    return {
        "average_daily_latency_ms": average_daily_latency_ms,
        "daily_latency_ms": dict(sorted(daily_latency_ms.items())),
        "trade_days_count": trade_days_count,
        "latency_total_ms": total_latency_ms,
    }


def _compute_average_daily_tokens(records: list[dict[str, Any]]) -> dict[str, Any]:
    daily_tokens = defaultdict(lambda: {"input_tokens": 0, "output_tokens": 0})
    trade_days = set()
    total_input = 0
    total_output = 0

    for record in records:
        date_raw = record.get("date")
        if not date_raw:
            continue
        date_str = str(date_raw)
        date_part = date_str.split(" ")[0].split("T")[0]
        llm_usage = record.get("llm_usage") or {}
        input_tokens = int(llm_usage.get("input_tokens") or 0)
        output_tokens = int(llm_usage.get("output_tokens") or 0)
        daily_tokens[date_part]["input_tokens"] += input_tokens
        daily_tokens[date_part]["output_tokens"] += output_tokens
        total_input += input_tokens
        total_output += output_tokens
        trades = record.get("trades", []) or []
        if trades:
            trade_days.add(date_part)

    trade_days_count = len(trade_days)
    average_daily_input_tokens = total_input / trade_days_count if trade_days_count else 0.0
    average_daily_output_tokens = total_output / trade_days_count if trade_days_count else 0.0

    return {
        "average_daily_input_tokens": average_daily_input_tokens,
        "average_daily_output_tokens": average_daily_output_tokens,
        "daily_tokens": dict(sorted(daily_tokens.items())),
        "trade_days_count": trade_days_count,
        "input_tokens_total": total_input,
        "output_tokens_total": total_output,
    }


@tool("average_daily_trade_latency")
def average_daily_trade_latency_tool(records_path: str | None = None) -> str:
    """Compute average daily trade latency from experiment_records JSONL."""
    resolved_path = _resolve_records_path_for_tool(records_path)
    if not resolved_path:
        return json.dumps(
            {
                "error": "records_path_not_found",
                "hint": "Pass a valid experiment_records JSONL path, or set TRADELENS_RECORDS_PATH.",
                "requested_records_path": records_path,
            },
            ensure_ascii=False,
        )
    records = _load_jsonl(resolved_path)
    result = _compute_average_daily_latency(records)
    return json.dumps(result, ensure_ascii=False)


@tool("average_daily_tokens")
def average_daily_tokens_tool(records_path: str | None = None) -> str:
    """Compute average daily input/output tokens from experiment_records JSONL."""
    print("Computing average daily tokens...")
    resolved_path = _resolve_records_path_for_tool(records_path)
    if not resolved_path:
        return json.dumps(
            {
                "error": "records_path_not_found",
                "hint": "Pass a valid experiment_records JSONL path, or set TRADELENS_RECORDS_PATH.",
                "requested_records_path": records_path,
            },
            ensure_ascii=False,
        )
    records = _load_jsonl(resolved_path)
    result = _compute_average_daily_tokens(records)
    return json.dumps(result, ensure_ascii=False)


def _summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "record_count": len(records),
        "date_range": None,
        "models": [],
        "decision_counts": {},
        "trade_count": 0,
        "hold_ratio": None,
        "token_total": 0,
        "token_average": None,
        "latency_average_ms": None,
        "tool_counts": {},
        "tool_latency_total_ms": 0,
        "slippage_avg": None,
        "slippage_pct_avg": None,
        "analysis_to_decision_latency_ms": None,
    }
    if not records:
        return summary

    dates = [str(r.get("date")) for r in records if r.get("date")]
    if dates:
        summary["date_range"] = (min(dates), max(dates))

    models = {r.get("model") or r.get("signature") for r in records if r.get("model") or r.get("signature")}
    summary["models"] = sorted(models)

    decision_counter = Counter()
    token_total = 0
    latencies = []
    tool_counter = Counter()
    tool_latency_total = 0
    slippages = []
    slippage_pcts = []
    decision_latencies = []
    trade_total = 0

    for record in records:
        llm_usage = record.get("llm_usage") or {}
        token_total += int(llm_usage.get("input_tokens", 0)) + int(llm_usage.get("output_tokens", 0))
        latency_ms = llm_usage.get("latency_ms")
        if isinstance(latency_ms, (int, float)):
            latencies.append(float(latency_ms))

        tool_usage = record.get("tool_usage") or {}
        for call in tool_usage.get("calls", []) or []:
            tool_name = call.get("tool_name")
            if tool_name:
                tool_counter[tool_name] += int(call.get("call_count", 0) or 0)
                tool_latency_total += int(call.get("total_latency_ms", 0) or 0)

        trades = record.get("trades") or []
        trade_total += len(trades)
        for trade in trades:
            decision_type = trade.get("decision_type") or "UNKNOWN"
            decision_counter[decision_type] += 1
            analysis_price = trade.get("analysis_price")
            execution_price = trade.get("execution_price")
            if isinstance(analysis_price, (int, float)) and isinstance(execution_price, (int, float)):
                slippage = float(execution_price) - float(analysis_price)
                slippages.append(slippage)
                if analysis_price:
                    slippage_pcts.append(slippage / float(analysis_price))
            timestamp = trade.get("timestamp") or {}
            analysis_ts = _parse_ts(timestamp.get("analysis_time"))
            decision_ts = _parse_ts(timestamp.get("decision_time"))
            if analysis_ts and decision_ts:
                decision_latencies.append((decision_ts - analysis_ts).total_seconds() * 1000)

    summary["decision_counts"] = dict(decision_counter)
    summary["trade_count"] = trade_total
    hold_count = decision_counter.get("HOLD", 0)
    if trade_total:
        summary["hold_ratio"] = hold_count / trade_total

    summary["token_total"] = token_total
    if records:
        summary["token_average"] = token_total / len(records)
    if latencies:
        summary["latency_average_ms"] = sum(latencies) / len(latencies)
    summary["tool_counts"] = dict(tool_counter)
    summary["tool_latency_total_ms"] = tool_latency_total
    if slippages:
        summary["slippage_avg"] = sum(slippages) / len(slippages)
    if slippage_pcts:
        summary["slippage_pct_avg"] = sum(slippage_pcts) / len(slippage_pcts)
    if decision_latencies:
        summary["analysis_to_decision_latency_ms"] = sum(decision_latencies) / len(decision_latencies)

    return summary


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head = text[: max_chars - 200]
    return head + "\n\n[...truncated...]\n"


def _format_summary(summary: dict[str, Any]) -> str:
    lines = [
        f"record_count: {summary.get('record_count')}",
        f"date_range: {summary.get('date_range')}",
        f"models: {summary.get('models')}",
        f"decision_counts: {summary.get('decision_counts')}",
        f"trade_count: {summary.get('trade_count')}",
        f"hold_ratio: {summary.get('hold_ratio')}",
        f"token_total: {summary.get('token_total')}",
        f"token_average: {summary.get('token_average')}",
        f"latency_average_ms: {summary.get('latency_average_ms')}",
        f"tool_counts: {summary.get('tool_counts')}",
        f"tool_latency_total_ms: {summary.get('tool_latency_total_ms')}",
        f"slippage_avg: {summary.get('slippage_avg')}",
        f"slippage_pct_avg: {summary.get('slippage_pct_avg')}",
        f"analysis_to_decision_latency_ms: {summary.get('analysis_to_decision_latency_ms')}",
    ]
    return "\n".join(lines)


def _line_after_label(text: str, label: str) -> str | None:
    match = re.search(rf"{re.escape(label)}\n([^\n]+)", text)
    if not match:
        return None
    return match.group(1).strip()


def _table_value(text: str, row_label: str) -> str | None:
    match = re.search(rf"\|\s*{re.escape(row_label)}\s*\|\s*([^|]+?)\s*\|", text)
    if not match:
        return None
    return match.group(1).strip()


def _safe_float(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.replace(",", "").replace("%", "").replace("*", "").replace("`", "").strip()
    if not cleaned or cleaned.upper() == "N/A":
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _extract_report_context(md_text: str) -> dict[str, Any]:
    context = {
        "trading_period": _line_after_label(md_text, "Trading Period:"),
        "strategy": _line_after_label(md_text, "Trading Model / Strategy:"),
        "assets": _line_after_label(md_text, "Assets:"),
        "initial_cash": _safe_float(_line_after_label(md_text, "Initial Cash:")),
        "current_cash": _safe_float(_line_after_label(md_text, "Current Cash:")),
        "total_position_value": _safe_float(_line_after_label(md_text, "Total Position Value:")),
        "total_portfolio_value": _safe_float(_line_after_label(md_text, "Total Portfolio Value:")),
        "return_profit": _safe_float(_line_after_label(md_text, "Return / Profit:")),
        "benchmark_symbol": _line_after_label(md_text, "Benchmark Symbol:"),
        "benchmark_return_pct": _safe_float(_line_after_label(md_text, "Benchmark Return:")),
        "market_effect": _safe_float(_line_after_label(md_text, "Market Effect:")),
        "selection_effect": _safe_float(_line_after_label(md_text, "Asset Selection Effect:")),
        "timing_effect": _safe_float(_line_after_label(md_text, "Timing Effect:")),
        "gross_profit": _safe_float(_line_after_label(md_text, "Total Profit:")),
        "static_cost": _safe_float(_table_value(md_text, "Static (data subscription)")),
        "dynamic_cost": _safe_float(_table_value(md_text, "Dynamic (commission + token + infra + uncertain)")),
        "total_cost": _safe_float(_table_value(md_text, "**Total**")),
        "opportunity_cost": _safe_float(_line_after_label(md_text, "Opportunity Cost (Decision Price - Execution Price)")),
        "avg_latency_per_trade_ms": _safe_float(_line_after_label(md_text, "Average Latency per Trade")),
        "avg_daily_llm_latency_ms": _safe_float(_line_after_label(md_text, "Average Daily LLM Latency")),
        "avg_daily_input_tokens": _safe_float(_line_after_label(md_text, "Average Daily Input Tokens")),
        "avg_daily_output_tokens": _safe_float(_line_after_label(md_text, "Average Daily Output Tokens")),
        "net_outcome": _safe_float(_table_value(md_text, "**Net outcome (gross − total cost)**")),
        "net_timing_outcome": _safe_float(_table_value(md_text, "**Net timing outcome (timing − dynamic cost)**")),
    }
    gross_profit = context.get("gross_profit")
    total_cost = context.get("total_cost")
    static_cost = context.get("static_cost")
    dynamic_cost = context.get("dynamic_cost")
    timing_effect = context.get("timing_effect")
    if gross_profit not in (None, 0) and total_cost is not None:
        context["cost_to_gross_profit_ratio"] = total_cost / abs(gross_profit)
    if total_cost not in (None, 0):
        if static_cost is not None:
            context["static_cost_share"] = static_cost / total_cost
        if dynamic_cost is not None:
            context["dynamic_cost_share"] = dynamic_cost / total_cost
    if timing_effect not in (None, 0) and dynamic_cost is not None:
        context["dynamic_cost_to_timing_ratio"] = dynamic_cost / abs(timing_effect)
    return context


def _extract_figure_inventory(md_text: str) -> list[dict[str, str]]:
    inventory: list[dict[str, str]] = []
    for alt, src in re.findall(r"!\[([^\]]+)\]\(([^)]+)\)", md_text):
        inventory.append({"caption": alt.strip(), "path": src.strip()})
    return inventory


def _summarize_static_config_for_prompt(static_config: dict[str, Any]) -> dict[str, Any]:
    keys_of_interest = [
        "frequency",
        "start_time",
        "end_time",
        "benchmark_symbol",
        "signature",
        "initial_cash",
        "cash",
        "model",
        "llm_model",
        "top_k",
        "rebalance",
        "trade_frequency",
        "agent_model",
    ]
    summary: dict[str, Any] = {}
    for key in keys_of_interest:
        if key in static_config:
            summary[key] = static_config[key]
    structure = static_config.get("structure")
    if isinstance(structure, dict):
        summary["structure_keys"] = sorted(structure.keys())
    assets = static_config.get("assets")
    if isinstance(assets, list):
        summary["asset_count"] = len(assets)
        summary["assets_preview"] = assets[:10]
    return summary or static_config


def _build_analysis_prompt(
    md_text: str,
    records_summary: dict[str, Any],
    static_config: dict[str, Any],
) -> str:
    report_context = _extract_report_context(md_text)
    figure_inventory = _extract_figure_inventory(md_text)
    static_focus = _summarize_static_config_for_prompt(static_config)
    output_contract = """
# LLM Analysis

## Executive Summary
- 3-5 bullets only.

## Part 1. Trading Performance Analysis
### 1.1 Outcome Snapshot
- Summarize return, net outcome, cost burden, and whether the run created real economic value.

### 1.2 Profit Attribution Analysis
- Use Figure 1 and Figure 2 explicitly.
- Explain market, selection, and timing contributions separately.
- State whether the strategy outperformed buy-and-hold because of timing, selection, both, or neither.

### 1.3 Cost Structure Analysis
- Use Figure 3 and Figure 4 explicitly.
- Explain static vs dynamic cost burden and whether current cost structure is acceptable for this profit level.
- Identify the most actionable cost driver.

### 1.4 Portfolio Timeline and Risk Signals
- Use Figure 5 and Figure 6 explicitly.
- Comment on the shape of cumulative profit vs cumulative cost, path dependency, and whether profitability is fragile.

### 1.5 Execution Quality and LLM Efficiency
- Evaluate opportunity cost, latency, token intensity, and trade efficiency.
- Distinguish issues caused by market exposure from issues caused by system design.

## Part 2. Trading System Diagnosis
### 2.1 System Diagnosis
- Diagnose whether the current system is mainly limited by model quality, portfolio construction, trading cadence, execution overhead, or workflow design.

### 2.2 Root Causes
- Provide 3-6 root causes with evidence.

### 2.3 Top Recommended Actions
1. Highest-priority action with expected impact and implementation idea.
2. Second-priority action with expected impact and implementation idea.
3. Third-priority action with expected impact and implementation idea.

### 2.4 Quick Wins vs Structural Changes
#### Quick Wins
- 2-4 bullets.
#### Structural Changes
- 2-4 bullets.

## Appendix. Key Metrics Snapshot
| Metric | Value | Why it matters |
| --- | --- | --- |
| ... | ... | ... |
""".strip()

    return "\n".join(
        [
            "You are a senior trading-system reviewer writing a high-quality financial analysis note.",
            "Write polished Markdown only.",
            "Part 1 must read like a trading performance report built directly on the financial report figures and tables.",
            "Part 2 must read like a trading system diagnosis memo for the research team.",
            "Ground every conclusion in the supplied report, figures, experiment summary, and static config.",
            "Do not invent unavailable evidence. If evidence is weak, say so clearly.",
            "Recommendations should remain actionable and should map back to one or more of these levers:",
            "(1) starting capital, (2) model choice, (3) trading frequency, (4) system / agent / tool architecture.",
            "Top Recommended Actions must appear under Part 2, not in the executive summary.",
            "Use the tools `average_daily_trade_latency` and `average_daily_tokens` if you need extra numeric support.",
            "",
            "Style requirements:",
            "- Be concise but analytical.",
            "- Prefer decision-useful interpretation over generic praise/blame.",
            "- Explicitly cite Figure numbers when discussing chart-based evidence.",
            "- Separate gross trading skill from cost-adjusted economic value.",
            "- Distinguish market effect, asset selection effect, timing effect, and system overhead.",
            "",
            "Output must follow the exact section structure below and contain no extra preamble.",
            output_contract,
            "",
            "## Financial report structured context",
            json.dumps(report_context, ensure_ascii=False, indent=2),
            "",
            "## Figure inventory from financial report",
            json.dumps(figure_inventory, ensure_ascii=False, indent=2),
            "",
            "## Financial report excerpt",
            _truncate(md_text, 10000),
            "",
            "## Experiment records summary",
            _format_summary(records_summary),
            "",
            "## Static config summary",
            json.dumps(static_focus, ensure_ascii=False, indent=2),
        ]
    )


def _is_usable_api_key(key: str | None) -> bool:
    if not key or not str(key).strip():
        return False
    lowered = str(key).strip().lower()
    if lowered in {
        "sk-your-openai-api-key-here",
        "your-aihubmix-api-key-here",
        "your-api-key-here",
        "changeme",
    }:
        return False
    if "your-openai" in lowered or "your-aihubmix" in lowered or "example.com" in lowered:
        return False
    return True


def _resolve_llm(model: str) -> ChatOpenAI:
    openai_key = os.getenv("OPENAI_API_KEY")
    if _is_usable_api_key(openai_key):
        return ChatOpenAI(
            model=model,
            api_key=openai_key,
            base_url=os.getenv("OPENAI_BASE_URL"),
            temperature=0.2,
        )

    aihubmix_key = os.getenv("AIHUBMIX_API_KEY")
    if _is_usable_api_key(aihubmix_key):
        base_url = (os.getenv("AIHUBMIX_BASE_URL") or "").strip()
        if not base_url or "example.com" in base_url.lower():
            raise ValueError("AIHUBMIX_BASE_URL is required when using AIHUBMIX_API_KEY")
        return ChatOpenAI(
            model=model,
            api_key=aihubmix_key,
            base_url=base_url,
            temperature=0.2,
        )

    raise ValueError("Missing API key: set OPENAI_API_KEY or AIHUBMIX_API_KEY in env")


def _default_output_path(md_path: str) -> str:
    md_dir = os.path.dirname(os.path.abspath(md_path))
    base = os.path.basename(md_path)
    stem = base[:-3] if base.endswith(".md") else base
    for suffix in ("-financial-report", "-bill"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return os.path.join(md_dir, f"{stem}-llm-analysis.md")


def run_diagnosis(md_path: str, records_path: str | None, static_path: str, output_path: str | None = None) -> str:
    root = get_project_root()
    load_dotenv(os.path.join(root, ".env"))
    app_config = load_app_config(os.path.join(root, "config.json"))
    model = str(app_config.get("agent_model", "gpt-4o-mini"))
    if not records_path:
        records_path = app_config.get("records_path")
    if not records_path:
        raise ValueError("Missing records_path in config.json")
    if not os.path.isabs(records_path):
        records_path = os.path.join(root, records_path)
    os.environ["TRADELENS_RECORDS_PATH"] = str(records_path)
    if not os.path.isabs(static_path):
        static_path = os.path.join(root, static_path)

    md_text = _read_text(md_path)
    records = _load_jsonl(records_path)
    static_config = _load_static_any(static_path)

    summary = _summarize_records(records)
    prompt = _build_analysis_prompt(md_text, summary, static_config)

    llm = _resolve_llm(model).bind_tools([average_daily_trade_latency_tool, average_daily_tokens_tool])
    messages = [
        SystemMessage(
            content=(
                "You are a meticulous trading-system performance diagnostician and "
                "financial report writer. Produce precise, evidence-backed Markdown."
            )
        ),
        HumanMessage(content=prompt),
    ]
    response = llm.invoke(messages)
    if getattr(response, "tool_calls", None):
        tool_outputs = []
        for call in response.tool_calls:
            tool_name = call.get("name")
            if tool_name == "average_daily_trade_latency":
                tool_result = average_daily_trade_latency_tool.invoke(call.get("args") or {})
                tool_outputs.append(ToolMessage(content=tool_result, tool_call_id=call.get("id")))
            elif tool_name == "average_daily_tokens":
                tool_result = average_daily_tokens_tool.invoke(call.get("args") or {})
                tool_outputs.append(ToolMessage(content=tool_result, tool_call_id=call.get("id")))
        messages.extend([response, *tool_outputs])
        response = llm.invoke(messages)
    diagnosis = response.content.strip()

    output_path = output_path or _default_output_path(md_path)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(diagnosis + "\n")

    return diagnosis


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FinCost model diagnosis agent")
    parser.add_argument("--md", required=True, help="Path to report markdown file")
    parser.add_argument(
        "--records",
        help="Path to experiment_records JSONL (default: records_path in config.json)",
    )
    parser.add_argument("--static", required=True, help="Path to static config JSON/JSONL")
    parser.add_argument("--output", help="Optional path to save diagnosis markdown")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    diagnosis = run_diagnosis(args.md, args.records, args.static, args.output)
    print(diagnosis)


if __name__ == "__main__":
    main()

