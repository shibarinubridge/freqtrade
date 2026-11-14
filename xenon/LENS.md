# AI Agent Lens without TradingView

Independent experimental Python port of [AI Agent Lens](https://github.com/roan-maverick/tradingview-indicator-for-ai-agents).
The MIT source snapshot and attribution are in `vendor/ai-agent-lens/`; its Pine
blob is `cd5a2b56b93e2e79107606269587d79fa4c96341`. No TradingView account,
webhook, paid subscription or TradingView data session is required. XENON's
existing charting-library attribution stays intact.

## Current requested execution profile (14 November 2026)

The paper account now uses **900 USDC margin at 5x**, approximately 4,500 USDC
notional after downward quantity rounding, on its existing 1,000-USDC wallet.
At most one position is allowed. The earlier 200-USDC fixed-risk sizing is
replaced by a **200-USDC maximum planned loss at the stop**, not a loss target.
A 1% stop on 4,500 USDC notional is approximately 45 USDC price risk plus costs.
Unavailable margin, unavailable requested leverage, invalid geometry or a planned
loss above 200 USDC refuses the order without silently resizing it. Stop/target,
confirmed-signal, daily-loss and peak-drawdown rules remain unchanged.

This profile has version suffix `-fixed-margin`; the earlier `xenon-lens-2`
execution evidence below is a separate legacy profile. It is not pooled with the
new forward evaluation. Historical reproduction:

```
.venv/bin/python xenon/run_lens_backtest.py --dataset august_m1 --risk 200 --margin 900 --leverage 5
.venv/bin/python xenon/run_lens_backtest.py --dataset native_m15 --risk 200 --margin 900 --leverage 5
```

These exploratory runs executed 2 trades / +18.3073 USDC (August, M1 detail) and
1 trade / -35.9326 USDC (October–November, M15). Margin was 899.78–899.97 USDC,
leverage 5x. The existing peak drawdown protection suspended later entries in
both runs. This proves sizing/native order flow, not profitability. The previous
lookahead report is not relabelled as validation of the new execution profile.
The default launcher still starts paused; active state is controlled through the
verified local API/XENON. FVG configuration and process remain separate.

## Architecture

Hyperliquid OHLCV → `strategies/lens_rules.py` → `ai-agent-lens/v1` JSON packets
→ observation layers in XENON. Independently, `strategies/XenonLens.py` produces
native Freqtrade paper/backtest orders, with its own risk and SQL ledger. The
source's reference tracker is never presented as proof of a broker position.

This is deterministic signal/context computation. There is no newly connected
LLM service, autonomous model training or claim that confluence scores predict
win probability. Existing scheduled video research remains separate.

## Frozen source rules

- M15, EMA 20/50/200, slow slope over 5 bars; RSI 14 with 75/25 extremes;
  MACD 12/26/9; DMI/ADX 14/14, trend threshold 20; ATR 14, percentile over 100;
  relative volume over 20; previous UTC day high/low and session VWAP.
- Previous completed H4 close versus EMA50. Available at the M15 bar's OPEN,
  not its close; the final M15 of an H4 still uses the earlier H4.
- Regime priority: HIGH_VOLATILITY (ATR percentile ≥90), TREND_UP/TREND_DOWN,
  then RANGE. Five transparent factors of up to 20 points on each side.
- Setup only when score crosses from below 70 to ≥70. Opposing trend and high
  volatility block it. Simultaneous long/short is ignored. Same direction is
  ignored while the reference tracker is active; opposite replaces it.
- Confirmed swing pivots use 5 bars each side. Store both pivot origin and
  confirmation time; XENON marks confirmation rather than backdating a signal.
- Reference entry at signal close; stop 1.5×ATR, T1 1.5R, T2 3R. Stop has
  priority if stop and target touch the same reference bar. T1 is informational.

Tests cover these causal rules and the published factor arithmetic. We cannot
certify numerical Pine parity without a Pine runtime/reference export. EMA/RMA
seeding, percentile/tie behavior and pivot equality remain explicit parity
limits. The code awards six volume points on directional bars when relative
volume is missing; the port follows code over the contradictory prose spec.

## Data and packet handling

Only actually observed closed M15 bars enter calculations. Missing bars are not
fabricated. H4/daily aggregates require all 16/96 constituent bars. A missing
aggregate is unavailable rather than silently carried across a missing bucket.
VWAP starts at UTC midnight; partial-session coverage is flagged. Warmup needs
at least 200 M15 bars, 50 complete H4 bars and nonmissing indicator inputs.

The source schema is preserved with a `xenon` extension containing implementation
version, closed timestamp, readiness, provenance and parity/coverage flags.
No native trade IDs are fabricated. Input correction invalidates the in-memory
calculation cache; historical observed packets are not retroactively rewritten.

- Observation: `.runtime/lens/observation/latest/<COIN>_15.json`.
- Native analysis: `.runtime/accounts/lens/lens-packets/latest/<COIN>_15.json`.
- Per-symbol close journal: corresponding `history/<COIN>_15.jsonl`, last 2,000
  observed closes. Timestamp/version-based restart deduplication (version
  upgrades are explicitly labelled reanalysis); missed closes during
  downtime are not fabricated as live observations.
- XENON uses fresh native analysis when available, otherwise labels public
  context as reference only. It sends only the chosen 600-bar trace to keep
  snapshots bounded. A correction or different rolling warmup may alter public
  context versus native analysis; their provenance remains separate.

## Independent paper account and shared safeguards

```
.venv/bin/python xenon/run.py --account lens
```

This creates only the Lens runtime/config/auth and SQL database. It starts
`paused`, on the existing 1,000-USDC virtual wallet, with 900 USDC requested
margin at 5x, maximum one position and a 200-USDC planned-stop-loss cap. Gross
exposure is capped at 5x equity. Quantity rounds down to exchange precision;
insufficient margin or excess planned loss refuses the order instead of silently
reducing the requested margin. Stop budgets include frozen 0.045% fees each side
and a 1 bp adverse-stop reserve; realized losses can still differ under gaps,
slippage and funding.

Legacy backtest configs without `xenon_lens_margin_USDC` retain fixed-risk sizing,
default 2x exposure/leverage and two positions. They are separate experiments,
not the current launcher profile.

Daily loss gate 1.5% (Bucharest date) and peak drawdown gate 2.5% remain active.
Peak drawdown suspension persists through restart. A large planned-risk trade
can trip those guards alone; no guard is loosened to force more entries.

The account uses port 8095 on loopback, separate credentials and
`.runtime/accounts/lens/trades.dryrun.sqlite`. Live mode, force-entry, exchange
credentials through the launcher and shared forward runtime directories are
refused. Market entries occur AFTER candle confirmation at the available price;
geometry stays anchored to the signal. Invalid gap/stop/target or net planned
reward below 1R refuses entry. Stop and T2 exit all remaining quantity; no T1
partial exit. An opposite confirmed setup requests an exit; instant reference
replacement is not a guaranteed native same-bar reversal.

Version 2 fixes a demonstrated native backtester precision issue. Upstream
`freqtrade/data/btanalysis/historic_precision.py` infers tick size from the entire
month's maximum decimal count, including future bars. A SOL stop was 119.096
in the long run versus 119.10 in its prefix, changing an exit. The port now
rounds native stop/T2 toward entry to valid known Hyperliquid ticks, then freezes
historical trade precision in the entry-fill callback before stop/ROI evaluation.
An epsilon below/above the fixed long/short stop prevents floating-point
reconstruction from crossing a tick. The raw reference map remains unchanged.
No upstream engine code was modified. Original results and the failed audit
are retained under `.runtime/lens-backtest/pre-causal-precision/`.

Native execution differs from the indicator's zero-cost reference tracker.
Historical equity marks use last closed main-bar prices; forward marks use the
available book. Initial risk sizing and final confirmation reserve existing
positions and pending quantities. Broker fill/risk metadata survives SQL
restart; ROI target credit is suppressed in the entry minute. On M15-only
simulation this is a conservative whole-bar delay. Funding uses native engine
handling and the available historical H1 mark-price proxy.

XENON start/pause/stop controls are scoped to `lens`; FreqUI opens it using
`https://calm-frequi.lexnerg.chatgpt.site/trade?bot=lens`. Existing FVG process,
configuration, wallet and risk state are untouched. No real-money orders are
authorized by this implementation.
The FreqUI transport can use any verified deployed paper account for health;
Lens monitoring does not depend on FVG being online. Each RPC still verifies
its own target account immediately before execution.

## Reproduce verification

Use the existing research data prepared by `prepare_backtest.py`:

```
.venv/bin/python -m unittest discover -s xenon/tests -q
.venv/bin/python xenon/tests/verify_lens_persistence.py
.venv/bin/python xenon/run_lens_backtest.py --dataset august_m1 --risk 200
.venv/bin/python xenon/run_lens_backtest.py --dataset native_m15 --risk 200
# Separate technical comparison; does not change the requested paper risk:
.venv/bin/python xenon/run_lens_backtest.py --dataset august_m1 --risk 5
.venv/bin/python xenon/run_lens_backtest.py --dataset august_m1 --risk 5 --coarse
.venv/bin/python xenon/run_lens_backtest.py --dataset august_m1 --risk 5 --stress
.venv/bin/python xenon/run_lens_backtest.py --dataset native_m15 --risk 5
.venv/bin/python xenon/audit_lens.py
.venv/bin/python xenon/verify_lens_prefix.py
.venv/bin/python xenon/verify_lens_precision.py
.venv/bin/python xenon/verify_lens_lookahead.py
.venv/bin/python xenon/report_lens.py
```

Each dataset/risk/cost case has its own config, output, audit and user directory
under `.runtime/lens-backtest`. The final official lookahead audit has no flags
in 10 checked trades; the earlier flagged exit is preserved separately.
The native precision regression reproduces 14 closed trades identically in
the long and truncated portfolio. `verify_lens_lookahead.py` retains the official analysis object
via an observation-only hook, then tests flagged exits with full portfolio
prefixes. It never changes the engine, indicators, original comparisons or risk
limits to force a pass. Diagnostic results do not replace the official CSV.
Unique audit CSV names avoid an upstream Pandas CSV-upsert dtype error on reruns.

These historical periods were previously examined. They are exploratory, not
fresh holdout validation. No Hyperopt, threshold search or strategy selection
uses these runs. Raw negative, suspended and margin-blocked outcomes are kept.
Source and data hashes, commands, official archives and limitations are retained
in the generated report/review package. No profitability qualification follows.
