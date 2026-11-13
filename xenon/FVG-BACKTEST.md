# XenonFVGBacktest v1

Historical-only strategy for the official Freqtrade 2026.10 engine. The forward
XenonFVG class, account registry, live risk ledger and running process are not
changed. Backtest and explicitly flagged lookahead utility modes only are
accepted. Forward trading refuses this class. No wallet key/API server is used.

## Reproduction

Use the existing user-held snapshots (they are not redistributed in Git):

```
.venv/bin/python xenon/prepare_backtest.py
.venv/bin/python xenon/verify_backtest_parity.py
.venv/bin/python xenon/run_backtest.py --dataset native_m15
.venv/bin/python xenon/run_backtest.py --dataset native_m15 --stress
.venv/bin/python xenon/run_backtest.py --dataset august_m1
.venv/bin/python xenon/run_backtest.py --dataset august_m1 --stress
.venv/bin/python xenon/verify_backtest_fills.py
.venv/bin/python xenon/report_backtest.py
.venv/bin/python -m unittest discover -s xenon/tests -q
```

All generated data, configs, funding data, logs, audits and official result ZIPs
are isolated in xenon/.runtime/backtest. Each run has a distinct audit file to
avoid concurrent-write contamination. See data-manifest.json for source hashes.
The same frozen detector is inherited; exact entry tags, direction, CE, stop and
target match the forward class on both datasets, including truncated prefixes.

## Execution differences

Historical OHLCV open at or before the simulated clock replaces a real bid/ask
book. Data after the decision time is never used for this quote proxy. The CE
Limit must remain nonmarketable relative to that open. Native price clamping is
refused, pending invalidation/expiry and immutable entry tags are preserved.
Funding uses historical hourly rates (timestamps floored to hour) and futures
H1 candles as the available mark/oracle proxy. No exact historical book exists.

Sizing, maximum 2 trades, 0.5% planned risk, 1% reserved open risk, 2x gross exposure,
2x maximum leverage, daily guard and peak drawdown gate are inherited. The risk
state is fresh per backtest and writes only that run's audit. Equity marks use
observed candle opens; reserved gross notional uses current historical marks.
The initial planned reward filter and risk-unit calculation retain base fees;
the stress experiment doubles actual fees only and may trigger different guards.

Freqtrade fills at an in-range candle price; no queue/partial-fill reconstruction
or 1 bp penetration rule is introduced. Actual adverse exit slippage is not added,
although 1 bp is reserved in the original risk calculation. M15-only fills cannot
resolve entry-minute chronology. M1 detail suppresses target credit in the fill
minute via inherited metadata. Stop checks precede ROI in the native engine.
An export label trailing_stop_loss can reflect custom stop handling; it does not
mean the strategy enabled a price-following trailing stop. Effective stops are
audited against the immutable level within one native tick.

The native export's open_date is order-placement time; the holding clock is
based on entry order_filled_timestamp. Export initial_stop_loss_abs can reflect
the generic pre-fill placeholder; effective post-fill stop is stop_loss_abs.
Native M15 has no gaps. The August source has 12–15 missing M1 bars per asset and
missing M15 aggregates; synthetic aggregate bars are excluded from the detector.
No exported position in these four runs spans missing M1 data. Native engine
filling/rounding assumptions remain limitations rather than production evidence.

## Causality and interpretation

The default lookahead CLI can force market orders unless
lookahead_allow_limit_orders=true is explicitly set in its config. Preserve the
original official output: it flags 5 of 8 entry comparisons, zero exit/indicator
biases. All five flagged orders filled 30–150 minutes after placement, beyond the
tool's placement+one-candle entry slice. verify_backtest_fills.py reruns the full
portfolio with a cutoff after each actual fill and compares tag, fill time,
quantity and price. This diagnoses those flags; it is not a universal guarantee.

Both historical periods were examined previously. They are exploratory, not a
fresh holdout. native_m15 is 2026-10-02 to 2026-11-12 UTC (1000-bar warmup retained);
august_m1 is 2026-08-12 to 2026-08-31 23:45 UTC. Since periods differ, PnL differences
cannot be attributed solely to M1 versus M15 resolution. Do not run Hyperopt on
the same verification period to claim new out-of-sample evidence. No strategy
promotion or real-money deployment follows from these results.

## Same-period review and requested fixed risk

The execution comparison uses the same August source, M15 signals, timerange,
fees, starting wallet and portfolio rules, changing only the detail timeframe:

```
.venv/bin/python xenon/run_backtest.py --dataset august_m1 --coarse
.venv/bin/python xenon/run_backtest.py --dataset august_m1 --coarse --fixed-risk 200
.venv/bin/python xenon/run_backtest.py --dataset august_m1 --fixed-risk 200
.venv/bin/python xenon/run_backtest.py --dataset native_m15 --fixed-risk 200
.venv/bin/python xenon/compare_backtests.py
```

Fixed risk is a separate historical sizing scenario, not a detector variant or
an active-account change. It sizes to at most 200 USDC of planned stop loss
including frozen estimated costs, after downward quantity rounding. The scenario
uses a two-order aggregate budget of 400 USDC; it retains the 2x leverage and
gross exposure cap, available margin, daily loss and peak drawdown guards. It
does not silently downsize to a different risk when the requested order cannot
fit. With the 1000 USDC wallet all tested 200 USDC orders are rejected for margin
or exposure. Raw sizing attempts include retries of the same tag.

The default, without --fixed-risk, continues to use the original 0.5% per-order
and 1% aggregate risk rules. None of these flags affect the forward class.

The same-period baseline has seven identical entry tags: M15 net -8.2639 USDC,
M1-detail net -8.2563 USDC. The review directory includes a per-trade comparison,
fourteen SVG execution charts and conditional exit-slippage sensitivities. The
slippage calculation applies an extra exit cost to fixed observed trades; it
does not rerun portfolio sizing, risk guards or order matching. It is not a
native slippage simulation. Outputs: .runtime/backtest/same-period-review/.
No new holdout or profitability qualification is claimed.
