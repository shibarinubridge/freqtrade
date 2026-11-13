Live strategy drawings for XENON

Observation only; the frozen strategy version, risk limits and fill rules remain
unchanged. detect(trace=True) returns a third presentation value without mutating
the order dictionaries. Each event has an ID based on coin, sweep and candle
close timestamps, a candle anchor and an availability time. Swing confirmations
respect their right-hand bars; forming candles are excluded from native output.

fvg_visual.py writes bounded files under .runtime/fvg-visual, only when enabled by
an actual dry_run bot_start. Errors in observation export do not affect execution.
Initial history is labelled historical_reconstruction; subsequent confirmed
candle events retain the first observed_ms. Callback logs distinguish approval
and cancellation requests from broker acknowledgement.

adapter.py exports only allowlisted order/trade fields. A broker order needs an
order ID; fill quantity must be positive. A missing fill timestamp cannot be
replaced by trade creation time. Previously observed orders are retained in a
bounded .runtime history. A missing order in a later API response means only
currently_reported=false; cancellation is never inferred from absence.

dashboard_visuals.py supplies the private bridge with actual native trace files,
up to 600 candles, and Hyperliquid public current candle OHLC. The separate shadow
plan stays labelled as shadow. The public forming candle is display-only, never
an input to native stage confirmation. The hosted chart polls the existing
private snapshot transport and has no order mutation endpoint.

Validation: 24 local adapter/relay/FVG/telemetry tests; 160 reference detector and
indicator checks; trace-on/off equality for all four historical datasets and 16
prefix checks; isolated real Freqtrade database persistence/fill/SL/ROI/review
verification. No production trade ledger or risk settings were modified.
