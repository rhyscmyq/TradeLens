from collections import defaultdict
from datetime import datetime


def _parse_iso_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def calculate_portfolio_series(records, initial_cash, prices_by_date=None):
    cash = float(initial_cash)
    holdings = defaultdict(int)
    last_price = {}
    dates = []
    holding_profit_series = []
    prices_by_date = prices_by_date or {}

    for record in records:
        date = record.get("date")
        trades = record.get("trades", [])
        for trade in trades:
            decision_type = trade.get("decision_type", "").upper()
            ticker = trade.get("ticker") or ""
            quantity = int(trade.get("quantity") or 0)
            price = trade.get("execution_price")
            if price is None:
                price = trade.get("analysis_price")
            if price is None:
                price = 0.0
            price = float(price)

            if ticker:
                last_price[ticker] = price

            if decision_type == "BUY":
                cash -= price * quantity
                holdings[ticker] += quantity
            elif decision_type == "SELL":
                cash += price * quantity
                holdings[ticker] -= quantity

        daily_prices = prices_by_date.get(str(date), {})
        holdings_value = 0.0
        for ticker, qty in holdings.items():
            if qty == 0:
                continue
            if ticker in daily_prices:
                last_price[ticker] = daily_prices[ticker]
            holdings_value += qty * last_price.get(ticker, 0.0)
        portfolio_value = cash + holdings_value
        holding_profit = portfolio_value - float(initial_cash)

        dates.append(date)
        holding_profit_series.append(holding_profit)

    return dates, holding_profit_series


def calculate_portfolio_state(records, initial_cash, prices_by_date=None):
    cash = float(initial_cash)
    holdings = defaultdict(int)
    last_price = {}
    traded_assets = set()
    prices_by_date = prices_by_date or {}

    for record in records:
        trades = record.get("trades", [])
        for trade in trades:
            decision_type = str(trade.get("decision_type") or "").upper()
            ticker = trade.get("ticker") or ""
            quantity = int(trade.get("quantity") or 0)
            price = trade.get("execution_price")
            if price is None:
                price = trade.get("analysis_price")
            if price is None:
                price = 0.0
            price = float(price)

            if ticker:
                traded_assets.add(ticker)
                last_price[ticker] = price

            if decision_type == "BUY":
                cash -= price * quantity
                holdings[ticker] += quantity
            elif decision_type == "SELL":
                cash += price * quantity
                holdings[ticker] -= quantity

    last_record_date = None
    for record in reversed(records):
        if record.get("date"):
            last_record_date = str(record.get("date"))
            break

    daily_prices = prices_by_date.get(last_record_date, {}) if last_record_date else {}

    positions = []
    total_position_value = 0.0
    for ticker, qty in holdings.items():
        if qty == 0:
            continue
        if ticker in daily_prices:
            last_price[ticker] = daily_prices[ticker]
        price = last_price.get(ticker, 0.0)
        value = qty * price
        total_position_value += value
        positions.append(
            {
                "ticker": ticker,
                "quantity": qty,
                "price": price,
                "value": value,
            }
        )
    positions.sort(key=lambda item: item["ticker"])

    total_portfolio_value = cash + total_position_value
    return {
        "current_cash": cash,
        "positions": positions,
        "total_position_value": total_position_value,
        "total_portfolio_value": total_portfolio_value,
        "return_profit": total_portfolio_value - float(initial_cash),
        "assets": sorted(traded_assets),
    }


def calculate_portfolio_value(records, initial_cash, prices_by_date=None, end_date: str | None = None) -> float:
    """
    复盘到 end_date 的期末总资产（cash + holdings value）。
    - 若 end_date=None，使用最后一个 record 的 date
    - 估值价格使用 prices_by_date[date][symbol]，若缺失则用最后一次交易价兜底
    """

    prices_by_date = prices_by_date or {}
    cash = float(initial_cash)
    holdings = defaultdict(int)
    last_price = {}

    resolved_end_date = None
    if end_date:
        resolved_end_date = str(end_date).split(" ")[0].split("T")[0]

    for record in records:
        record_date = record.get("date")
        record_date_str = str(record_date).split(" ")[0].split("T")[0] if record_date else None
        if resolved_end_date and record_date_str and record_date_str > resolved_end_date:
            break

        for trade in record.get("trades", []) or []:
            decision_type = str(trade.get("decision_type") or "").upper()
            ticker = trade.get("ticker") or ""
            quantity = int(trade.get("quantity") or 0)
            price = trade.get("execution_price")
            if price is None:
                price = trade.get("analysis_price")
            if price is None:
                price = 0.0
            price = float(price)

            if ticker:
                last_price[ticker] = price

            if decision_type == "BUY":
                cash -= price * quantity
                holdings[ticker] += quantity
            elif decision_type == "SELL":
                cash += price * quantity
                holdings[ticker] -= quantity

        resolved_end_date = resolved_end_date or record_date_str

    if not resolved_end_date:
        return float(initial_cash)

    daily_prices = prices_by_date.get(resolved_end_date, {})
    holdings_value = 0.0
    for ticker, qty in holdings.items():
        if qty == 0:
            continue
        if ticker in daily_prices:
            last_price[ticker] = daily_prices[ticker]
        holdings_value += qty * float(last_price.get(ticker, 0.0))
    return cash + holdings_value

