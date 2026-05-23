def _try_import_pyplot():
    try:
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            import matplotlib.pyplot as plt  # type: ignore

        return plt
    except Exception as exc:  # pragma: no cover
        print(f"[Warning] matplotlib unavailable, skip plotting: {exc}")
        return None


def plot_cost_pie(
    commission_total,
    token_total,
    infra_total,
    monthly_total,
    uncertain_total,
    output_path,
    include_monthly=True,
):
    plt = _try_import_pyplot()
    if plt is None:
        return
    labels = ["commission", "token", "infra", "monthly", "uncertain"]
    values = [commission_total, token_total, infra_total, monthly_total, uncertain_total]
    colors = ["#809bce", "#eac4d5", "#b8e0d4", "#95b8d1", "#f5e2ea"]
    if not include_monthly:
        filtered = [(l, v, c) for l, v, c in zip(labels, values, colors) if l != "monthly"]
        labels, values, colors = zip(*filtered) if filtered else ([], [], [])

    total = sum(values)
    if total <= 0:
        print("No costs to plot.")
        return
    formatted_labels = [f"{label} (${value:.2f})" for label, value in zip(labels, values)]

    def make_autopct(vals):
        def _autopct(pct):
            value = pct * sum(vals) / 100.0
            return f"{pct:.1f}%\n${value:.2f}"

        return _autopct

    title = (
        "Operating Cost Composition"
        if include_monthly
        else "Operating Cost Composition (Excl. Data Subscription)"
    )
    plt.figure(figsize=(5.2, 4.4))
    plt.pie(
        values,
        labels=formatted_labels,
        autopct=make_autopct(values),
        startangle=90,
        colors=colors,
    )
    plt.title(title, fontsize=10, pad=10)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"Saved pie chart to: {output_path}")


def plot_profit_breakdown(breakdown, output_path, *, title: str = "Profit Breakdown"):
    """按 profit-breakdown 口径绘制 market / selection / timing 瀑布图。"""
    plt = _try_import_pyplot()
    if plt is None or breakdown is None:
        return

    market = float(getattr(breakdown, "market_effect", 0.0) or 0.0)
    selection = float(getattr(breakdown, "asset_selection_effect", 0.0) or 0.0)
    timing = float(getattr(breakdown, "timing_effect", 0.0) or 0.0)
    v0 = float(getattr(breakdown, "v0", 0.0) or 0.0)
    v_end = float(getattr(breakdown, "v_end", 0.0) or 0.0)

    labels = ["Market", "Selection", "Timing"]
    values = [market, selection, timing]
    colors = ["#809bce", "#b8e0d4", "#ff8531"]

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    axes[0].bar(labels, values, color=colors)
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].set_ylabel("USD")
    axes[0].set_title(f"{title} — Effects")
    for idx, val in enumerate(values):
        axes[0].text(idx, val, f"{val:,.0f}", ha="center", va="bottom" if val >= 0 else "top", fontsize=9)

    cumulative = [v0]
    for val in values:
        cumulative.append(cumulative[-1] + val)
    # v₀ + 三效应 = v_end，共 4 个点；标签数须与点数一致
    step_labels = ["v₀", "+Market", "+Selection", "v_end"]
    x = range(len(cumulative))
    axes[1].plot(x, cumulative, marker="o", color="#4a6fa5", linewidth=2)
    axes[1].set_xticks(list(x))
    axes[1].set_xticklabels(step_labels, rotation=20, ha="right")
    axes[1].set_ylabel("Portfolio value (USD)")
    axes[1].set_title(f"{title} — Waterfall")
    axes[1].axhline(v0, color="#999", linestyle="--", linewidth=0.8)
    axes[1].text(
        len(cumulative) - 1,
        cumulative[-1],
        f"{v_end:,.0f}",
        ha="center",
        va="bottom",
        fontsize=9,
    )

    bench = getattr(breakdown, "benchmark_symbol", "")
    mode = getattr(breakdown, "market_mode", "")
    fig.suptitle(f"{title} ({bench}, mode={mode})", fontsize=11)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved profit breakdown chart to: {output_path}")


def plot_performance_lines(dates, holding_profit_series, cumulative_cost_series, real_profit_series, output_path):
    plt = _try_import_pyplot()
    if plt is None:
        return
    if "no_monthly" in output_path:
        chart_title = "Portfolio Value vs Dynamic Cost (Excl. Subscription)"
    else:
        chart_title = "Portfolio Value vs Cumulative Dynamic Cost"
    plt.figure(figsize=(9, 4.5))
    plt.plot(
        dates,
        holding_profit_series,
        label="Portfolio value − initial cash",
        color="#88a4c9",
    )
    plt.plot(
        dates,
        cumulative_cost_series,
        label="Cumulative dynamic cost",
        color="#ff8696",
    )
    plt.plot(
        dates,
        real_profit_series,
        label="Net profit (portfolio − cost)",
        color="#ff8531",
    )
    plt.title(chart_title, fontsize=11, pad=10)
    plt.ylabel("USD")
    plt.axhline(0, color="black", linewidth=2.5, linestyle="--")
    plt.legend(loc="best", fontsize=8)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"Saved performance chart to: {output_path}")

