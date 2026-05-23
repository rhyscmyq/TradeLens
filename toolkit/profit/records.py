import json
from collections import defaultdict


def load_experiment_records(records_path: str):
    records = []
    with open(records_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def load_daily_buy_prices(prices_path: str):
    """
 Reads `data/merged*.jsonl` files and organizes buy prices by date:
 prices_by_date[date][symbol] -> float(buy_price)
    """

    prices_by_date = defaultdict(dict)
    with open(prices_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            meta = payload.get("Meta Data", {})
            symbol = meta.get("2. Symbol") or meta.get("symbol")
            if not symbol:
                continue
            series = payload.get("Time Series (Daily)", {})
            for date, day_data in series.items():
                if not isinstance(day_data, dict):
                    continue
                price_text = day_data.get("1. buy price") or day_data.get("buy_price")
                if price_text is None:
                    continue
                try:
                    price_value = float(price_text)
                except (TypeError, ValueError):
                    continue
                prices_by_date[str(date)][str(symbol)] = price_value
    return prices_by_date

