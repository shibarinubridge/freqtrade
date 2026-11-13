"""Read-only public order-book preflight using the bot's actual CCXT settings."""
import datetime as dt,json,pathlib,time
import ccxt

def verify(path):
    cfg=json.loads(pathlib.Path(path).read_text())
    if cfg['dry_run'] is not True or cfg['exchange']['name']!='hyperliquid':raise RuntimeError('Dry-run Hyperliquid configuration required')
    options=cfg['exchange']['ccxt_config']
    if options.get('requests_trust_env') is not True:raise RuntimeError('Synchronous CCXT must honor managed proxy and CA settings')
    exchange=ccxt.hyperliquid(options);proof={'checked_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'mode':'public_read_only','pairs':{}}
    for pair in cfg['exchange']['pair_whitelist']:
        start=time.monotonic()
        try:
            book=exchange.fetch_order_book(pair,limit=20)
            if not book['bids'] or not book['asks']:raise ValueError('Empty order book')
            proof['pairs'][pair]={'status':'PASS','bid_levels':len(book['bids']),'ask_levels':len(book['asks']),'seconds':round(time.monotonic()-start,2)}
        except Exception as error:raise RuntimeError(f'Public order-book preflight failed for {pair}: {type(error).__name__}') from None
    (pathlib.Path(path).parent/'connection-check.json').write_text(json.dumps(proof,indent=2))
    print('Public order-book preflight passed for all configured pairs.',flush=True)
    return proof
