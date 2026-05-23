from collections import Counter, defaultdict


COMMISSION_PER_SHARE = 0.005
COMMISSION_MINIMUM = 1.0
COMMISSION_MAXIMUM_RATE = 0.01


def calculate_commission(shares: int, trade_value: float | None) -> float:
    if shares <= 0:
        return 0.0
    base_commission = shares * COMMISSION_PER_SHARE
    commission = max(base_commission, COMMISSION_MINIMUM)
    if trade_value is None:
        return commission
    if trade_value <= 0:
        return 0.0
    max_commission = trade_value * COMMISSION_MAXIMUM_RATE
    return min(commission, max_commission)


def extract_actions_and_commission(records):
    actions_by_date = {}
    commission_by_date = defaultdict(float)
    commission_total = 0.0

    for record in records:
        date = record.get("date")
        trades = record.get("trades", [])
        actions = []

        for trade in trades:
            decision_type = str(trade.get("decision_type", "UNKNOWN")).upper()
            actions.append(decision_type)

            if decision_type not in {"BUY", "SELL"}:
                continue

            quantity = int(trade.get("quantity") or 0)
            price = trade.get("execution_price")
            if price is None:
                price = trade.get("analysis_price")
            trade_value = None if price is None else float(price) * quantity

            trade_commission = calculate_commission(quantity, trade_value)
            commission_by_date[date] += trade_commission
            commission_total += trade_commission

        actions_by_date[date] = actions

    return actions_by_date, commission_by_date, commission_total


def format_action_summary(actions_by_date):
    lines = ["Action summary by trading day:"]
    for date in sorted(actions_by_date.keys()):
        counts = Counter(actions_by_date[date])
        counts_str = ", ".join([f"{k}={v}" for k, v in counts.items()])
        lines.append(f"  {date}: {counts_str}")
    return lines
