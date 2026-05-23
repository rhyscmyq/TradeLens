import argparse
import os
import random
from pathlib import Path

from .cost.analysis import (
    calculate_cumulative_cost_series,
    calculate_monthly_cost_series,
    calculate_token_cost_by_date,
    calculate_opportunity_cost_and_latency,
)
from .profit.portfolio import calculate_portfolio_state, calculate_portfolio_series
from .profit.records import load_experiment_records, load_daily_buy_prices
from .profit.profit_breakdown import calculate_profit_breakdown_from_data
from .cost.commission import extract_actions_and_commission
from .config import get_project_root, load_app_config, load_llm_pricing, load_static_config
from .report.plots import plot_cost_pie, plot_performance_lines, plot_profit_breakdown
from .report.agent import run_diagnosis
from .report.report import (
    build_report_payload,
    build_report_text,
    build_financial_report_markdown,
    save_action_ledger,
    save_report_jsonl,
    save_financial_report,
)


def _resolve_path(repo_root: str, raw: str | None) -> str | None:
    if not raw:
        return None
    path = Path(raw).expanduser()
    if path.is_absolute():
        return str(path)
    return str((Path(repo_root) / path).resolve())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FinCost Toolkit entry")
    parser.add_argument("--config", default="config.json", help="config.json path")
    parser.add_argument("--records", default=None, help="experiment_records JSONL path")
    parser.add_argument("--static", default=None, help="static JSON/JSONL path")
    parser.add_argument("--out", default=None, help="output directory path")
    parser.add_argument("--benchmark", default=None, help="benchmark symbol")
    return parser


def main(argv: list[str] | None = None):
    root = get_project_root()
    data_dir = os.path.join(root, "data")
    args = _build_parser().parse_args(argv)

    config_path = _resolve_path(root, args.config) or os.path.join(root, "config.json")
    app_config = load_app_config(config_path)

    records_path = app_config.get("records_path") or os.path.join(data_dir, "experiment_records.jsonl")
    static_path = app_config.get("static_path") or os.path.join(data_dir, "static.jsonl")
    prices_path = app_config.get("prices_path", os.path.join(data_dir, "merged.jsonl"))
    market_base_path = app_config.get("market_base_path", os.path.join(data_dir, "market-base.jsonl"))

    if args.records:
        records_path = _resolve_path(root, args.records)
    if args.static:
        static_path = _resolve_path(root, args.static)

    if not records_path or not os.path.exists(records_path):
        raise FileNotFoundError(
            f"records_path not found: {records_path}. Please pass --records with an explicit path."
        )
    if not static_path or not os.path.exists(static_path):
        raise FileNotFoundError(
            f"static_path not found: {static_path}. Please pass --static with an explicit path."
        )

    records = load_experiment_records(records_path)
    prices_by_date = load_daily_buy_prices(prices_path)
    model_pricing = load_llm_pricing(os.path.join(root, "config_llm.json"))
    static_config = load_static_config(static_path)
    benchmark_symbol = str(args.benchmark or app_config.get("benchmark_symbol", "SPY"))

    actions_by_date, commission_by_date, commission_total = extract_actions_and_commission(records)

    trading_days = len(actions_by_date)
    _, token_cost_by_date = calculate_token_cost_by_date(records, model_pricing)
    token_total = sum(token_cost_by_date.values())
    infra_cost_per_day = 0.2

    monthly_cost = float(static_config.get("data_subscription_monthly", 0.0))
    monthly_additions, monthly_total = calculate_monthly_cost_series(records, monthly_cost)
    uncertain_cost = sum(random.uniform(0.0, 0.5) for _ in range(trading_days))
    infra_total = trading_days * infra_cost_per_day
    total_cost = commission_total + token_total + infra_total + monthly_total + uncertain_cost

    report_text = build_report_text(
        actions_by_date,
        trading_days,
        commission_total,
        token_total,
        infra_total,
        monthly_total,
        uncertain_cost,
        total_cost,
    )
    print(report_text)

    llm_model = str(static_config.get("llm_model", "unknown"))
    initial_cash = str(static_config.get("initial_cash", "unknown"))
    frequency = str(static_config.get("decision_frequency", static_config.get("frequency", "unknown")))

    result_dir = _resolve_path(root, args.out) if args.out else None
    if not result_dir:
        result_dir = os.path.join(root, "result", f"{llm_model}-{initial_cash}-{frequency}")
    os.makedirs(result_dir, exist_ok=True)

    save_action_ledger(report_text, result_dir, llm_model, initial_cash, frequency)
    portfolio_state = calculate_portfolio_state(records, initial_cash, prices_by_date)
    opportunity_cost, average_latency_ms, trade_count = calculate_opportunity_cost_and_latency(
        records
    )
    if market_base_path and os.path.exists(market_base_path):
        try:
            base_prices = load_daily_buy_prices(market_base_path)
            for date, sym_map in base_prices.items():
                prices_by_date[date].update(sym_map)
        except Exception as exc:
            print(f"\n[Warning] Failed to load market base prices: {exc}")

    profit_breakdown = None
    profit_breakdown_invested = None
    start_time = static_config.get("start_time")
    end_time = static_config.get("end_time")
    try:
        profit_breakdown = calculate_profit_breakdown_from_data(
            records,
            static_config,
            prices_by_date,
            benchmark_symbol=benchmark_symbol,
            start_date=str(start_time) if start_time else None,
            end_date=str(end_time) if end_time else None,
            market_mode="full_cash",
        )
        profit_breakdown_invested = calculate_profit_breakdown_from_data(
            records,
            static_config,
            prices_by_date,
            benchmark_symbol=benchmark_symbol,
            start_date=str(start_time) if start_time else None,
            end_date=str(end_time) if end_time else None,
            market_mode="invested_only",
        )
    except Exception as exc:
        print(f"\n[Warning] Failed to calculate profit breakdown: {exc}")

    chart_dir = os.path.join(result_dir, "charts")
    os.makedirs(chart_dir, exist_ok=True)
    chart_paths: dict[str, str] = {}

    if profit_breakdown is not None:
        profit_full_png = os.path.join(chart_dir, "profit_breakdown_full.png")
        plot_profit_breakdown(
            profit_breakdown,
            profit_full_png,
            title="Profit Breakdown (Full Cash)",
        )
        chart_paths["profit_full"] = "charts/profit_breakdown_full.png"
    if profit_breakdown_invested is not None:
        profit_inv_png = os.path.join(chart_dir, "profit_breakdown_invested.png")
        plot_profit_breakdown(
            profit_breakdown_invested,
            profit_inv_png,
            title="Profit Breakdown (Invested Only)",
        )
        chart_paths["profit_invested"] = "charts/profit_breakdown_invested.png"

    pie_dir = os.path.join(result_dir, "pie-chart")
    os.makedirs(pie_dir, exist_ok=True)
    pie_filename = f"{llm_model}_{llm_model}_{initial_cash}_{frequency}_pie_chart.pdf"
    pie_path = os.path.join(pie_dir, pie_filename)
    plot_cost_pie(commission_total, token_total, infra_total, monthly_total, uncertain_cost, pie_path)
    pie_png = os.path.join(chart_dir, "cost_pie.png")
    plot_cost_pie(
        commission_total,
        token_total,
        infra_total,
        monthly_total,
        uncertain_cost,
        pie_png,
    )
    chart_paths["cost_pie"] = "charts/cost_pie.png"

    pie_filename_no_monthly = (
        f"{llm_model}_{llm_model}_{initial_cash}_{frequency}_pie_chart_no_monthly.pdf"
    )
    pie_path_no_monthly = os.path.join(pie_dir, pie_filename_no_monthly)
    plot_cost_pie(
        commission_total,
        token_total,
        infra_total,
        0.0,
        uncertain_cost,
        pie_path_no_monthly,
        include_monthly=False,
    )
    pie_png_nm = os.path.join(chart_dir, "cost_pie_no_monthly.png")
    plot_cost_pie(
        commission_total,
        token_total,
        infra_total,
        0.0,
        uncertain_cost,
        pie_png_nm,
        include_monthly=False,
    )
    chart_paths["cost_pie_no_monthly"] = "charts/cost_pie_no_monthly.png"

    dates, holding_profit_series = calculate_portfolio_series(
        records, initial_cash, prices_by_date
    )
    uncertain_additions = [uncertain_cost] + [0.0 for _ in records[1:]]
    combined_additions = [
        monthly_additions[i] + uncertain_additions[i] for i in range(len(monthly_additions))
    ]
    cumulative_cost_series = calculate_cumulative_cost_series(
        records,
        commission_by_date,
        token_cost_by_date,
        infra_cost_per_day,
        combined_additions,
    )
    real_profit_series = [
        holding_profit_series[i] - cumulative_cost_series[i]
        for i in range(len(holding_profit_series))
    ]
    line_dir = os.path.join(result_dir, "line chart")
    os.makedirs(line_dir, exist_ok=True)
    line_filename = f"{llm_model}_{llm_model}_{initial_cash}_{frequency}_line_chart.pdf"
    line_path = os.path.join(line_dir, line_filename)
    plot_performance_lines(
        dates,
        holding_profit_series,
        cumulative_cost_series,
        real_profit_series,
        line_path,
    )
    line_png = os.path.join(chart_dir, "performance_line.png")
    plot_performance_lines(
        dates,
        holding_profit_series,
        cumulative_cost_series,
        real_profit_series,
        line_png,
    )
    chart_paths["performance"] = "charts/performance_line.png"

    no_monthly_additions = [0.0 for _ in records]
    combined_additions_no_monthly = [
        no_monthly_additions[i] + uncertain_additions[i]
        for i in range(len(no_monthly_additions))
    ]
    cumulative_cost_series_no_monthly = calculate_cumulative_cost_series(
        records,
        commission_by_date,
        token_cost_by_date,
        infra_cost_per_day,
        combined_additions_no_monthly,
    )
    real_profit_series_no_monthly = [
        holding_profit_series[i] - cumulative_cost_series_no_monthly[i]
        for i in range(len(holding_profit_series))
    ]
    line_filename_no_monthly = (
        f"{llm_model}_{llm_model}_{initial_cash}_{frequency}_line_chart_no_monthly.pdf"
    )
    line_path_no_monthly = os.path.join(line_dir, line_filename_no_monthly)
    plot_performance_lines(
        dates,
        holding_profit_series,
        cumulative_cost_series_no_monthly,
        real_profit_series_no_monthly,
        line_path_no_monthly,
    )
    line_png_nm = os.path.join(chart_dir, "performance_line_no_monthly.png")
    plot_performance_lines(
        dates,
        holding_profit_series,
        cumulative_cost_series_no_monthly,
        real_profit_series_no_monthly,
        line_png_nm,
    )
    chart_paths["performance_no_monthly"] = "charts/performance_line_no_monthly.png"

    financial_report_markdown = build_financial_report_markdown(
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
        profit_breakdown=profit_breakdown,
        profit_breakdown_invested=profit_breakdown_invested,
        chart_paths=chart_paths,
    )
    financial_report_path = save_financial_report(
        financial_report_markdown, result_dir, llm_model, initial_cash, frequency
    )

    try:
        from .report.render import render_markdown_to_html

        render_markdown_to_html(financial_report_path)
    except Exception as exc:
        print(f"\n[Warning] Failed to render markdown to HTML: {exc}")
    try:
        llm_analysis_path = os.path.join(
            result_dir,
            f"{llm_model}-{initial_cash}-{frequency}-llm-analysis.md",
        )
        run_diagnosis(
            financial_report_path,
            records_path,
            static_path,
            output_path=llm_analysis_path,
        )
        try:
            from .report.diagnosis_render import render_diagnosis_to_html

            render_diagnosis_to_html(llm_analysis_path)
        except Exception as exc:
            print(f"\n[Warning] Failed to render LLM analysis to HTML: {exc}")
    except Exception as exc:
        print(f"\n[Warning] Failed to run diagnosis agent: {exc}")
    report_payload = build_report_payload(
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
    )
    save_report_jsonl(report_payload, result_dir, llm_model, initial_cash, frequency)


if __name__ == "__main__":
    main()
