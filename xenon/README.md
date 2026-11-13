# CALM XENON — Freqtrade integration

This branch connects the upstream Freqtrade engine to the existing owner-private
XENON command center. Upstream trading, exchange and RPC internals are unchanged.
The integration is distributed under the repository's GPLv3 license.

## Current behavior

- Hyperliquid futures, isolated margin; BTC/ETH/SOL/HYPE quoted in USDC.
- A separate 1,000-USDC **virtual** wallet. The 99% allocation leaves 10 USDC
  reserved; the dashboard distinguishes full wallet from bot allocation.
- `XenonFVG` is now the default prospective paper strategy. It uses the
  frozen FVG detector, CE50 Limit entries, an absolute sweep stop and an
  opposing-liquidity target. Planned risk is .5% of virtual equity (~5USDC
  initially), at most2 positions, open risk<=1%, gross notional<=2xequity.
  Full rules, safeguards and execution differences are in `FVG-PORT.md`.
- `XenonObserve` remains a non-trading fallback. Switching back to it
  requires explicitly changing the local dry-run configuration and restarting.
- Existing FVG shadow/backtest results remain separate. No previous +6.33R
  result is attributed to Freqtrade. The newly ported strategy is an
  unvalidated forward-paper pilot, not a claim of profitability.
- API binds only to `127.0.0.1:8091`; generated Basic/JWT credentials remain in
  ignored, mode-0600 runtime files. No wallet/address/private key is required.
- XENON controls are limited to start/resume, pause new entries, and stop the
  trading cycle. Stop keeps the local API process alive. Force-entry, mode
  switching, exchange keys and arbitrary RPC requests are not exposed.
- The adapter checks the actual bot is Hyperliquid dry-run with force-entry
  disabled immediately before every mutation, filters snapshots, and never
  exports API authentication or raw configuration.

## Run

From the repository root, with Python 3.12+:

```bash
python -m venv .venv
.venv/bin/pip install -r xenon/requirements.lock.txt -e .
.venv/bin/python xenon/run.py
```

The launcher rejects `FREQTRADE__*` environment overrides. It uses the inherited
proxy settings and, when available, the OS CA bundle without disabling TLS
verification. The managed runtime has an HTTP proxy; async CCXT trusts that
inherited proxy. Websockets are disabled in this initial integration.

`adapter.collect()` produces bounded telemetry for the private dashboard agent;
`adapter.command()` accepts only `ft_start`, `ft_pause`, `ft_stop`. The dashboard
agent imports this adapter on the same host. Browser commands travel through the
existing authenticated same-origin queue and receive an agent acknowledgement;
the browser never connects directly to the local Freqtrade API.

Runtime ledger, config, authentication and logs are under `xenon/.runtime/` and
must never be committed. Market data is under ignored `xenon/user_data/`.
The current session is not permanent hosting and does not guarantee 24/7 uptime.

## Verify

```bash
.venv/bin/python -m unittest discover -s xenon/tests -v
```

The installed dependency snapshot is in `requirements.lock.txt`; upstream
provenance is in `upstream.json`. Dashboard source is maintained separately in
the existing Sites project. The fork contains the authoritative local adapter.

## Official FreqUI

The private FreqUI Site uses the upstream 3.3.0 release without changes to its
JavaScript/CSS bundles. A connection bootstrap preselects this bot. Its browser
session token is a short-lived gateway token, never the bot's API password.
`native_ui_relay.py` pulls bounded RPC jobs from that owner-private Site and
injects local API authentication only for the loopback call.

Monitoring, charts and start/pause/stop are relayed. Force-entry, configuration
reload, deletions and other mutations are refused. Dry-run is checked against
the actual local API before each job. POST receipts prevent repeating the same
job after an uncertain execution. Responses are bounded and authentication
values are redacted. The gateway advertises HTTP API compatibility 2.19 because
it does not relay WebSocket subscriptions; native FreqUI continues refreshing
through HTTP. The real upstream API version is retained in an extension field.
The trading engine remains Freqtrade 2026.10 and its data is not fabricated.
