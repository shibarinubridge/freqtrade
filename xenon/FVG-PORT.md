# XenonFVG dry-run v1 — frozen execution contract

The user authorized a prospective FVG strategy in the 1,000-USDC virtual
Freqtrade account. No private exchange key and no real orders are enabled.
This is an unvalidated paper pilot, not a claim of profitable live execution.

## Signal geometry

The portable `fvg_rules.py` retains the audited detector functions exactly,
except that data is passed explicitly and the public size-decimal snapshot is
limited to BTC/ETH/SOL/HYPE. The reference SHA is in `fvg-provenance.json`.
M15, strict 3+3 confirmed pivots, 96-bar liquidity window, prior NY day,
0.1 ATR equal-level tolerance, old FVG <=480 bars, wick sweep and reclaim,
fresh BOS, displacement >=1 ATR with body >=60%, and fresh/new FVG in six
bars are unchanged. CE50, sweep stop and opposing-liquidity target are fixed.
Entry flags live on the confirmation candle, available only at its close.
A 1,000-candle warmup fits Hyperliquid's 5,000-candle API limit.

## Execution and risk

- Entry: fixed CE50 GTC Limit. Confirm uses the book to reject marketable
  orders; this is NOT a guarantee of native post-only execution. A changed
  CE caused by price clamping is rejected, never silently accepted.
- One accepted placement per immutable setup tag, persisted across restarts.
  No pre-start signal is backfilled; new placement must be <=120 seconds old.
- Absolute expiration signal-close+180 minutes, independent of placement age.
  An old-FVG body close or an already-reached target cancels the pending
  order using only closed candles. A pending order retains its original CE.
- Stop is fixed in price and initialized through the after-fill custom stop.
  Initial fill metadata and the 24-hour holding clock use actual fill time.
  Corrupt/missing fill metadata causes a market exit, not an unprotected hold.
- Target uses custom ROI equal to Freqtrade's own fee/funding-adjusted
  `calc_profit_ratio(target)`, with no generic ROI threshold. No TP is
  credited during the entry minute. Standard Freqtrade stop checks precede
  ROI checks. Stop/time exits and target-triggered exits are MARKET simulated.
- Fee override .045% on both sides; estimated risk/reward also reserves1bp
  adverse exit friction. This deliberately differs from maker entry/TP in
  the source replay. Minimum planned net target >=1R is an entry filter,
  not a guarantee of each realized result.
- Risk budget .5% marked virtual equity (~5 USDC initially), at most2 trades,
  reserved open risk <=1%, gross exposure <=2x equity. Isolated leverage2
  funds the required notional; stake is margin, not the risk amount.
  Exchange-minimum adjustments and final submitted quantity are rechecked.
  Pending orders reserve quantity/risk even before trade.amount is populated.
- Day guard: new entries stop at -1.5% from the Europe/Bucharest day's first
  observed equity. Peak drawdown -2.5% suspends entries until reviewed.
  Position exits continue. Guard/consumed-setup state is in ignored runtime.
- Closed trades receive an idempotent JSON review in .runtime/fvg-reviews;
  loss causes remain NOT_ESTABLISHED until supported by evidence.

## Limits

Freqtrade book-based dry-run fills can differ from the research replay's
strict1bp penetration, no-entry-bar TP and ambiguous intrabar rules. Queue
position, market impact and perfect partial fills are not reconstructed.
The callback cannot make native dry-run fills identical to the M1 research
simulator. GTC fill timing can race cancellation between polls. Fees, funding,
slippage and native liquidation modeling can change the resulting PnL.
The historical +6.33R is never assigned to this new forward account.
Historical Freqtrade backtesting of this strategy is intentionally refused;
signal parity and callback invariants are checked separately. This initial
port is for forward paper only, with no claim of live/partial-fill readiness.
