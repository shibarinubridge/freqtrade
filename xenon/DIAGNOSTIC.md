Diagnostic integration account

XenonDiagnostic is a bounded technical dry-run fixture, not an alpha strategy.
It uses its own loopback API, database, auth and 1000-USDC virtual wallet. The
normal strategy and its force-entry-disabled setting are unchanged. No private
wallet key is accepted. Entries use the standard Freqtrade signal lifecycle.

The diagnostic account starts stopped. An explicit .runtime/accounts/diagnostic/
arm.json specifies count (1–2), baseline_closed and a deadline_ms. Each test uses
~20 USDC at 1x; entries above25 USDC are rejected. Long and short alternate. A
custom exit requests closure after45 seconds; the stop remains a fallback.
When the bounded count or deadline is reached, there are no further entries.
Pause/stop should be used after verifying the account is flat. Trading profit
or loss here is execution-test output, not evidence about a strategy's edge.

Official FreqUI uses its existing multi-bot store. The diagnostic connection has
apiUrl /bots/diagnostic and distinct selected-bot ID. The private gateway carries
an explicit diagnostic scope in the RPC queue; local relay revalidates dry-run
and injects only that account's local authentication. Force entry and destructive
mutations remain unavailable. XENON uses its account-scoped snapshot and controls.

An end-to-end test arms the account, starts via hosted FreqUI RPC, observes native
orders/fills and XENON snapshots, compares closed trade IDs across both gateways,
and stops the diagnostic account flat. Results are retained in the ignored
.runtime/accounts/diagnostic/e2e-report.json. No browser screenshot verification
is implied by API tests; the managed desktop control tool was unavailable.
