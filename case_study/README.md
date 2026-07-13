# End-to-End Case Study: Profitable but Agentically Non-Viable

This directory provides a **complete, inspectable walkthrough** of TradeLens on a GPT-5.2-based agentic trading system ($500,000 initial capital, daily decisions, two-month window: 2025-12-01 – 2026-01-30).


**This case study is that walkthrough.** Every stage—from raw system artifacts to the final recommended actions—is preserved in this folder, and the generated reports are included under `diagonosis/`.

---

## What This Case Demonstrates

| Question | Answer in this case |
|----------|---------------------|
| Is the system profitable? | **Yes, at portfolio level:** gross profit **+$2,022.49**, net outcome **+$1,782.48** after $240.01 operating cost. |
| Is it agentically viable? | **No:** timing effect **−$5,662.80**; net timing outcome (timing − dynamic cost) **−$5,702.82**. Dynamic reallocation destroyed value relative to buy-and-hold. |
| Where is the loss localized? | Not in API/token spend ($40.01 dynamic cost), but in the **agentic trading loop** (timing) and **execution path** ($3,982.68 opportunity cost). |
| What does TradeLens output? | A financial report, cost ledger, charts, structured metrics JSON, and an LLM-grounded diagnosis with prioritized revision steps. |

This is exactly the *profitable overall but agentically non-viable* pattern discussed in the paper—here shown through a single concrete run rather than aggregate tables alone.

---

## Case Setting

| Parameter | Value |
|-----------|-------|
| Backbone model | GPT-5.2 |
| Initial capital | $500,000 |
| Trading frequency | Daily |
| Evaluation window | 2025-12-01 – 2026-01-30 (41 trading days) |
| Universe | AMZN, AVGO, GOOG, META, MSFT, NVDA |
| Benchmark | SPY (+1.72% over the window) |
| Trading system | AI-trader (external agentic stack) |

---

## Directory Layout

```text
case_study/
├── config/                          # Deployment configuration (LLM pricing, etc.)
│   └── config_llm.json
├── runtime_traces/                    # Stage 1 — raw agent runtime logs (per day)
│   └── log/YYYY-MM-DD/
│       ├── log.jsonl                  # LLM messages, tool calls, reasoning trace
│       ├── log_response.jsonl
│       ├── telemetry.jsonl
│       └── trade.jsonl
├── trading_records/                   # Stage 1 — portfolio snapshots from the trading system
│   └── position.jsonl
├── tradelens_input/                   # Stage 2 — normalized TradeLens input (runnable entry point)
│   ├── experiment_records_gpt-5.2_500000_2025-12-01_2026-01-30.jsonl
│   ├── static-gpt-5.2_500000.0-daily_2025-12-01_2026-01-30.jsonl
│   └── price_data.jsonl
└── diagonosis/                        # Stage 3 — TradeLens outputs (pre-generated)
    ├── gpt-5.2-500000-daily-financial-report.md
    ├── gpt-5.2-500000-daily-financial-report.md.html
    ├── gpt-5.2-500000-daily-llm-analysis.md
    ├── gpt-5.2-500000-daily-llm-analysis.md.html
    ├── gpt-5.2-500000-daily-action.txt
    ├── gpt-5.2_500000_daily.jsonl
    ├── charts/                        # Profit breakdown, cost pie, performance line
    ├── line chart/
    └── pie-chart/
```

> **Note:** The released TradeLens pipeline starts from `tradelens_input/`. The upstream conversion from `runtime_traces/` and `trading_records/` to normalized records is part of the trading-system data collection pipeline; we ship both raw artifacts and normalized inputs so reviewers can inspect provenance.

---

## End-to-End Pipeline (Three Stages)

```text
┌─────────────────────────────────────────────────────────────────┐
│  Stage 1: Agentic trading system (AI-trader)                    │
│  config/  +  runtime_traces/  +  trading_records/               │
└────────────────────────────┬────────────────────────────────────┘
                             │ normalize & merge
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 2: TradeLens input                                       │
│  tradelens_input/experiment_records_*.jsonl                     │
│  tradelens_input/static-*.jsonl                                 │
│  tradelens_input/price_data.jsonl                               │
└────────────────────────────┬────────────────────────────────────┘
                             │ python main.py
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 3: TradeLens analysis → diagonosis/                      │
│  • Financial report (profit/cost attribution + risk metrics)    │
│  • Action & cost ledger                                         │
│  • Charts (profit breakdown, cost composition, timeline)        │
│  • LLM diagnosis (evidence-grounded root cause + actions)       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Stage 1 → Stage 2: What Gets Transformed

### 1. Deployment configuration (`config/config_llm.json`)

Token pricing for cost attribution. TradeLens uses this to convert per-day `llm_usage` token counts into dollar costs.

### 2. Runtime traces (`runtime_traces/log/YYYY-MM-DD/`)

Raw agent execution evidence. Example from `2025-12-02/log.jsonl`:

- **System prompt** — trading objective, position state, price feeds
- **LLM messages** — reasoning about portfolio construction
- **Tool calls** — market data lookups, position updates
- **`llm` block** — `input_tokens`, `output_tokens`, `latency_ms` per decision

This is the *trace* layer: it explains **why** the agent acted and **how expensive** each decision was in latency and tokens.

### 3. Trading records → normalized experiment records (`tradelens_input/experiment_records_*.jsonl`)

Each line is one trading day, merging trades with runtime telemetry:

```json
{
  "date": "2025-12-02",
  "model": "gpt-5.2",
  "llm_usage": {
    "input_tokens": 15076,
    "output_tokens": 1886,
    "latency_ms": 47281
  },
  "trades": [
    {
      "decision_type": "BUY",
      "ticker": "NVDA",
      "analysis_price": 179.92,
      "execution_price": 181.76,
      "quantity": 500
    }
  ]
}
```

Key fields used downstream:

| Field | Used for |
|-------|----------|
| `trades[].decision_type` | Action ledger, turnover, hold ratio |
| `trades[].analysis_price` vs `execution_price` | Opportunity cost |
| `llm_usage.*` | Token cost, latency, workflow overhead |
| `date` | Portfolio replay, daily cost accumulation |

### 4. Static baseline (`tradelens_input/static-*.jsonl`)

Defines the **buy-and-hold counterfactual** (initial basket held unchanged). Required for market / selection / timing decomposition.

---

## Stage 2 → Stage 3: Report Walkthrough

Open the pre-generated outputs in `diagonosis/` in this order to follow the diagnostic narrative.

### Step 1 — Financial Report (`gpt-5.2-500000-daily-financial-report.md`)

**Section 1–2: Configuration & portfolio state**
- Trading period, model, asset universe
- Final positions and portfolio value ($502,022.49)

**Section 3: Performance & profit attribution**

| Component | Full cash | Invested-only |
|-----------|----------:|--------------:|
| Market effect | +$8,599.53 | +$8,130.57 |
| Asset selection | −$914.23 | −$445.27 |
| Timing effect | **−$5,662.80** | **−$5,662.80** |
| **Gross profit** | **+$2,022.49** | **+$2,022.49** |

See `charts/profit_breakdown_full.png` and `charts/profit_breakdown_invested.png`.

**Section 3.2: Consolidated net outcome (the viability split)**

| View | Amount |
|------|-------:|
| Gross profit | +$2,022.49 |
| Total operating cost | −$240.01 |
| **Net economic outcome** | **+$1,782.48** ← portfolio looks fine |
| Timing effect | −$5,662.80 |
| Dynamic cost | −$40.01 |
| **Net timing outcome** | **−$5,702.82** ← agentic layer is not viable |

**Section 3.3: Risk & trading metrics**

| Metric | Value |
|--------|------:|
| Total return | +0.40% |
| Sharpe ratio | −0.02 |
| Max drawdown | 5.39% |
| Turnover | 1.13× |
| Excess vs SPY | −1.32 pp |

**Section 4: Cost summary**

| Bucket | Amount |
|--------|-------:|
| Static (data subscription) | $200.00 |
| Dynamic (commission + token + infra + uncertain) | $40.01 |
| **Total** | **$240.01** |

See `charts/cost_pie.png` and `charts/cost_pie_no_monthly.png`.

**Section 5: Portfolio timeline**

`charts/performance_line.png` — portfolio value vs cumulative dynamic cost over the window.

**Section 6: Execution quality**

Opportunity cost **$3,982.68**, average trade latency **25.3 s**, average daily LLM latency **~50 s**.

---

### Step 2 — Action & Cost Ledger (`gpt-5.2-500000-daily-action.txt`)

Day-by-day action summary linked from the financial report:

```text
2025-12-02: BUY=6          ← initial build (6 tickers)
2025-12-03 … 2026-01-04: HOLD (mostly)
2026-01-05: SELL=2
2026-01-16: SELL=1, BUY=1
2026-01-29: SELL=2, BUY=1
```

Only **5 active trade days** out of 41, yet timing destroyed **$5,662.80** — the ledger makes this activity–impact mismatch visible.

Structured cost totals are also in `gpt-5.2_500000_daily.jsonl`.

---

### Step 3 — LLM Diagnosis (`gpt-5.2-500000-daily-llm-analysis.md`)

TradeLens feeds the financial report + runtime evidence into an LLM agent that produces:

1. **Executive summary** — profitable net outcome but negative timing; opportunity cost exceeds dynamic cost
2. **Performance analysis** — attribution interpretation with figure references
3. **System diagnosis** — localizes failure to trading cadence / portfolio adjustment, not API spend
4. **Root causes** — evidence bullets (timing −$5,662.80, opportunity cost $3,982.68, 67,980 input tokens/day)
5. **Recommended actions** — staged, falsifiable revisions:
   - Gate trading frequency unless expected value exceeds hurdle
   - Add benchmark-aware portfolio construction layer
   - Simplify LLM workflow / test alternative models
6. **Quick wins vs structural changes**

HTML-rendered versions: `*.md.html` for browser viewing.

---

## The Core Diagnostic Insight (Rebuttal Summary)

```text
Portfolio level:     +$1,782 net  →  "system is profitable"
Agentic layer:       −$5,703 net timing  →  "dynamic decisions are not viable"

Market exposure:     +$8,599  (helped)
Stock selection:       −$914    (mild drag)
Timing/rebalancing:  −$5,663  (dominant loss)
API/token cost:      −$40     (negligible vs timing loss)
Opportunity cost:    $3,983   (execution path — separate economic signal)
```

**Without TradeLens**, a practitioner might stop at "+$1,782 net profit" and conclude the agent works.
**With TradeLens**, the same run is diagnosed as: *market beta carried the portfolio; the agentic loop subtracted value; fix timing/execution before scaling the model or capital.*

This is the practical diagnostic value the paper claims: **localize loss → rank mechanisms → propose testable revisions.**

---

## Reproduce the Analysis

From the repository root:

```bash
python main.py \
  --records case_study/tradelens_input/experiment_records_gpt-5.2_500000_2025-12-01_2026-01-30.jsonl \
  --static  case_study/tradelens_input/static-gpt-5.2_500000.0-daily_2025-12-01_2026-01-30.jsonl \
  --out     case_study/diagonosis/repro \
  --benchmark SPY
```

Pre-generated outputs in `diagonosis/` match this pipeline. LLM diagnosis (`gpt-5.2-500000-daily-llm-analysis.md`) requires API keys in `.env` (see `env.example`); the financial report and charts are produced without LLM calls.

Point `prices_path` in `config.json` to `case_study/tradelens_input/price_data.jsonl` (or `data/merged.jsonl`) when running locally.

---

## Artifact Index (Quick Reference)

| File | Role |
|------|------|
| `diagonosis/gpt-5.2-500000-daily-financial-report.md` | **Primary user-facing report** — profit/cost attribution, viability split, risk metrics |
| `diagonosis/gpt-5.2-500000-daily-action.txt` | Daily actions + cost ledger |
| `diagonosis/gpt-5.2-500000-daily-llm-analysis.md` | Evidence-grounded diagnosis + recommended actions |
| `diagonosis/gpt-5.2_500000_daily.jsonl` | Machine-readable cost/action summary |
| `diagonosis/charts/profit_breakdown_*.png` | Market / selection / timing waterfall |
| `diagonosis/charts/cost_pie*.png` | Operating cost composition |
| `diagonosis/charts/performance_line*.png` | Portfolio value vs cumulative cost |
| `tradelens_input/experiment_records_*.jsonl` | Normalized per-day records (trades + telemetry) |
| `runtime_traces/log/2025-12-02/log.jsonl` | Example raw agent trace for provenance inspection |

---

## Case Takeaway

The value of this diagnosis is not merely that timing is negative. TradeLens:

1. **Separates portfolio profitability from agentic viability** — net outcome +$1,782 vs net timing −$5,703
2. **Localizes the loss** — timing layer, not token/API spend
3. **Grounds the diagnosis in traces** — latency, opportunity cost, sparse trade days with large impact
4. **Produces a staged revision path** — test execution-corrected replay before rewriting the backbone model

This supports an iterative workflow: **localize → rank mechanisms → test highest-priority fix → re-run TradeLens.**
