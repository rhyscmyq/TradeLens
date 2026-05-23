from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from ..config import get_project_root, load_app_config, load_static_config
from .portfolio import calculate_portfolio_value
from .records import load_daily_buy_prices, load_experiment_records


@dataclass(frozen=True)
class ProfitBreakdownResult:
    """收益分解结果（类似 Brinson 的 market/selection/timing 拆分）。"""

    start_date: str
    end_date: str
    benchmark_symbol: str
    benchmark_available: bool
    benchmark_return: float | None

    v0: float
    v_market: float
    v_static: float
    v_end: float

    market_effect: float
    asset_selection_effect: float
    timing_effect: float
    total_profit: float

    initial_holdings: dict[str, int]
    market_mode: str = "full_cash"
    invested_cash: float | None = None
    cash_after_first_day: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "benchmark_symbol": self.benchmark_symbol,
            "benchmark_available": self.benchmark_available,
            "benchmark_return": self.benchmark_return,
            "market_mode": self.market_mode,
            "invested_cash": self.invested_cash,
            "cash_after_first_day": self.cash_after_first_day,
            "v0": self.v0,
            "v_market": self.v_market,
            "v_static": self.v_static,
            "v_end": self.v_end,
            "market_effect": self.market_effect,
            "asset_selection_effect": self.asset_selection_effect,
            "timing_effect": self.timing_effect,
            "total_profit": self.total_profit,
            "initial_holdings": dict(self.initial_holdings),
        }

    def to_rows(self) -> list[dict[str, Any]]:
        return [
            {"component": "market_effect", "value": self.market_effect},
            {"component": "asset_selection_effect", "value": self.asset_selection_effect},
            {"component": "timing_effect", "value": self.timing_effect},
            {"component": "total_profit", "value": self.total_profit},
        ]

    def to_frame(self):
        """
        可选：转成 pandas.DataFrame。
        环境若缺少可用 pandas（例如 numpy/pandas 二进制不匹配），会抛异常；上层可改用 `to_rows()`。
        """

        import pandas as pd  # 仅在需要 DataFrame 时才导入

        return pd.DataFrame(self.to_rows())


def _as_date_str(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    # 支持 "YYYY-MM-DD" / "YYYY-MM-DD HH:MM:SS" / ISO8601
    date_part = text.split(" ")[0].split("T")[0]
    parts = date_part.split("-")
    if len(parts) == 3 and parts[0] and parts[1] and parts[2]:
        y, m, d = parts[0], parts[1], parts[2]
        if len(m) == 1:
            m = f"0{m}"
        if len(d) == 1:
            d = f"0{d}"
        if len(y) == 4:
            return f"{y}-{m}-{d}"
    return date_part


def _price_on_or_before(prices_by_date: dict[str, dict[str, float]], date_str: str, symbol: str) -> float | None:
    """拿到指定日期当日价格；若缺失则向前回溯最多 10 天（处理周末/节假日）。"""

    symbol = str(symbol)
    date_part = _as_date_str(date_str)
    if not date_part:
        return None

    if date_part in prices_by_date and symbol in prices_by_date[date_part]:
        return float(prices_by_date[date_part][symbol])

    # 轻量回溯，避免对所有日期排序（merged.jsonl 每个 symbol 会覆盖很多天）
    try:
        from datetime import datetime, timedelta

        dt = datetime.strptime(date_part, "%Y-%m-%d")
    except Exception:
        return None
    for _ in range(10):
        dt = dt - timedelta(days=1)
        key = dt.strftime("%Y-%m-%d")
        if key in prices_by_date and symbol in prices_by_date[key]:
            return float(prices_by_date[key][symbol])
    return None


def _resolve_first_build_holdings(records: list[dict[str, Any]]) -> tuple[str | None, dict[str, int]]:
    """找到第一次有 BUY/SELL 的日期，并返回当日交易后持仓（用于 static buy&hold）。"""

    holdings: dict[str, int] = {}
    for record in records:
        date = _as_date_str(record.get("date"))
        trades = record.get("trades") or []
        if not trades:
            continue
        # 判断是否有有效交易（BUY/SELL 且 quantity>0）
        has_trade = False
        for trade in trades:
            decision_type = str(trade.get("decision_type") or "").upper()
            ticker = str(trade.get("ticker") or "")
            quantity = int(trade.get("quantity") or 0)
            if decision_type in {"BUY", "SELL"} and ticker and quantity > 0:
                has_trade = True
                break
        if not has_trade:
            continue

        # 计算当日交易后的净持仓
        day_holdings: dict[str, int] = {}
        for trade in trades:
            decision_type = str(trade.get("decision_type") or "").upper()
            ticker = str(trade.get("ticker") or "")
            quantity = int(trade.get("quantity") or 0)
            if decision_type not in {"BUY", "SELL"} or not ticker or quantity <= 0:
                continue
            if decision_type == "BUY":
                day_holdings[ticker] = day_holdings.get(ticker, 0) + quantity
            else:
                day_holdings[ticker] = day_holdings.get(ticker, 0) - quantity

        holdings = {k: v for k, v in day_holdings.items() if v != 0}
        return date, holdings

    return None, {}


def _resolve_first_build_day_cash_holdings(
    records: list[dict[str, Any]], initial_cash: float
) -> tuple[str | None, float, dict[str, int]]:
    """
    找到第一天发生 BUY/SELL 的日期，并返回：
    - build_date（YYYY-MM-DD）
    - cash_after_day（按 execution_price/analysis_price 模拟交易后的现金）
    - holdings_after_day（当日交易后的净持仓）
    """

    cash = float(initial_cash)
    holdings: dict[str, int] = {}
    for record in records:
        date = _as_date_str(record.get("date"))
        trades = record.get("trades") or []
        if not trades:
            continue
        # 当天是否有 BUY/SELL
        has_trade = False
        for trade in trades:
            decision_type = str(trade.get("decision_type") or "").upper()
            ticker = str(trade.get("ticker") or "")
            quantity = int(trade.get("quantity") or 0)
            if decision_type in {"BUY", "SELL"} and ticker and quantity > 0:
                has_trade = True
                break
        if not has_trade:
            continue

        for trade in trades:
            decision_type = str(trade.get("decision_type") or "").upper()
            ticker = str(trade.get("ticker") or "")
            quantity = int(trade.get("quantity") or 0)
            if decision_type not in {"BUY", "SELL"} or not ticker or quantity <= 0:
                continue
            price = trade.get("execution_price")
            if price is None:
                price = trade.get("analysis_price")
            if price is None:
                price = 0.0
            price = float(price)
            if decision_type == "BUY":
                cash -= price * quantity
                holdings[ticker] = holdings.get(ticker, 0) + quantity
            else:
                cash += price * quantity
                holdings[ticker] = holdings.get(ticker, 0) - quantity

        holdings = {k: v for k, v in holdings.items() if v != 0}
        return date, float(cash), holdings

    return None, float(initial_cash), {}


def calculate_profit_breakdown(
    records_path: str | None = None,
    static_path: str | None = None,
    prices_path: str | None = None,
    market_base_path: str | None = None,
    *,
    benchmark_symbol: str = "SPY",
    start_date: str | None = None,
    end_date: str | None = None,
) -> ProfitBreakdownResult:
    """
    将最终收益拆为三部分：
    - market_effect：市场基准从 start->end 的变化带来的收益（把 v0 乘以基准收益率）
    - asset_selection_effect：如果只做“初始选股 buy&hold”相对于 market 的超额
    - timing_effect：实际交易（择时/调仓）相对于 buy&hold 的增量

    定义（与草稿一致）：
    - v0：初始资金（static config 的 initial_cash）
    - v_market：v0 * (1 + benchmark_return)
    - v_static：初始建仓持仓 buy&hold 到 end 的期末资产（含未投资现金）
    - v_end：实际策略期末资产（根据 records + end prices 复盘计算）

    则：
    - market_effect = v_market - v0
    - asset_selection_effect = v_static - v_market
    - timing_effect = v_end - v_static
    - total_profit = v_end - v0
    """

    root = get_project_root()
    data_dir = os.path.join(root, "data")
    app_config = load_app_config(os.path.join(root, "config.json"))

    resolved_records_path = records_path or app_config.get("records_path") or os.path.join(
        data_dir, "experiment_records.jsonl"
    )
    resolved_static_path = static_path or app_config.get("static_path") or os.path.join(
        data_dir, "static.jsonl"
    )
    resolved_prices_path = prices_path or app_config.get("prices_path") or os.path.join(
        data_dir, "merged.jsonl"
    )
    resolved_market_base_path = (
        market_base_path
        or app_config.get("market_base_path")
        or os.path.join(data_dir, "market-base.jsonl")
    )

    records = load_experiment_records(resolved_records_path)
    if not records:
        raise ValueError(f"No records loaded from: {resolved_records_path}")

    prices_by_date = load_daily_buy_prices(resolved_prices_path)
    if resolved_market_base_path and os.path.exists(resolved_market_base_path):
        try:
            base_prices = load_daily_buy_prices(resolved_market_base_path)
            for date, sym_map in base_prices.items():
                prices_by_date[date].update(sym_map)
        except Exception as exc:
            print(f"[Warning] Failed to load market base prices: {exc}")

    static_config = load_static_config(resolved_static_path)
    return calculate_profit_breakdown_from_data(
        records,
        static_config,
        prices_by_date,
        benchmark_symbol=benchmark_symbol,
        start_date=start_date,
        end_date=end_date,
    )


def calculate_profit_breakdown_from_data(
    records: list[dict[str, Any]],
    static_config: dict[str, Any],
    prices_by_date: dict[str, dict[str, float]],
    *,
    benchmark_symbol: str = "SPY",
    start_date: str | None = None,
    end_date: str | None = None,
    market_mode: str = "full_cash",
) -> ProfitBreakdownResult:
    """同 `calculate_profit_breakdown`，但复用已加载的 records/static/prices（用于批量实验统计）。"""

    v0 = float(static_config.get("initial_cash") or 0.0)
    if v0 <= 0:
        raise ValueError("static config missing/invalid initial_cash")

    resolved_start = _as_date_str(start_date) or _as_date_str(static_config.get("start_time"))
    resolved_end = _as_date_str(end_date) or _as_date_str(static_config.get("end_time"))
    if not resolved_start:
        resolved_start = _as_date_str(records[0].get("date")) or "unknown"
    if not resolved_end:
        resolved_end = _as_date_str(records[-1].get("date")) or "unknown"

    build_date, initial_holdings = _resolve_first_build_holdings(records)
    if not initial_holdings:
        raise ValueError("Cannot resolve initial holdings: no BUY/SELL trades found in records")

    first_trade_date, cash_after_first_day, _ = _resolve_first_build_day_cash_holdings(records, v0)
    invested_cash = max(0.0, v0 - float(cash_after_first_day))

    initial_position_value = 0.0
    for ticker, qty in initial_holdings.items():
        initial_price = _price_on_or_before(prices_by_date, resolved_start, ticker)
        if initial_price is None and build_date:
            initial_price = _price_on_or_before(prices_by_date, build_date, ticker)
        if initial_price is None:
            fallback = None
            for record in records:
                if _as_date_str(record.get("date")) != build_date:
                    continue
                for trade in record.get("trades") or []:
                    if str(trade.get("ticker") or "") != ticker:
                        continue
                    p = trade.get("execution_price")
                    if p is None:
                        p = trade.get("analysis_price")
                    if p is not None:
                        fallback = float(p)
                        break
                if fallback is not None:
                    break
            if fallback is None:
                raise ValueError(f"Missing initial price for {ticker} on {resolved_start} (and no fallback)")
            initial_price = fallback
        initial_position_value += float(qty) * float(initial_price)

    cash_hold = v0 - initial_position_value
    static_final_value = float(cash_hold)
    for ticker, qty in initial_holdings.items():
        end_price = _price_on_or_before(prices_by_date, resolved_end, ticker)
        if end_price is None:
            raise ValueError(f"Missing end price for {ticker} on {resolved_end}")
        static_final_value += float(qty) * float(end_price)

    bench_start_price = _price_on_or_before(prices_by_date, resolved_start, benchmark_symbol)
    bench_end_price = _price_on_or_before(prices_by_date, resolved_end, benchmark_symbol)
    benchmark_available = bench_start_price is not None and bench_end_price is not None
    if benchmark_available:
        benchmark_return = (float(bench_end_price) / float(bench_start_price)) - 1.0
        if str(market_mode).lower() in {"invested_only", "invested", "exclude_cash"}:
            # 剔除“首日未投资现金”对 market 的影响：只对 invested_cash 部分应用 benchmark_return
            v_market = v0 + invested_cash * benchmark_return
        else:
            v_market = v0 * (1.0 + benchmark_return)
    else:
        benchmark_return = None
        v_market = v0

    v_end = calculate_portfolio_value(records, v0, prices_by_date, resolved_end)

    market_effect = v_market - v0
    asset_selection_effect = static_final_value - v_market
    timing_effect = v_end - static_final_value
    total_profit = v_end - v0

    return ProfitBreakdownResult(
        start_date=resolved_start,
        end_date=resolved_end,
        benchmark_symbol=str(benchmark_symbol),
        benchmark_available=bool(benchmark_available),
        benchmark_return=benchmark_return,
        market_mode=str(market_mode),
        invested_cash=float(invested_cash),
        cash_after_first_day=float(cash_after_first_day),
        v0=v0,
        v_market=float(v_market),
        v_static=float(static_final_value),
        v_end=float(v_end),
        market_effect=float(market_effect),
        asset_selection_effect=float(asset_selection_effect),
        timing_effect=float(timing_effect),
        total_profit=float(total_profit),
        initial_holdings=initial_holdings,
    )

