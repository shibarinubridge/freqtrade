"""Launch only the isolated XENON dry-run configuration. No wallet key required."""
import json,os,pathlib,secrets,sys
P=pathlib.Path(__file__).resolve().parent
ROOT=P.parent
RUNTIME=P/'.runtime'

def prepare(account_id='fvg'):
    from accounts import get
    account=get(account_id)
    if not account['enabled'] or not account['strategy']:raise RuntimeError('Account strategy has no tested native implementation')
    runtime=RUNTIME if account_id=='fvg' else account['runtime']
    if any(k.startswith('FREQTRADE__') for k in os.environ):
        raise RuntimeError('Remove FREQTRADE__ overrides; this launcher uses a fixed dry-run configuration.')
    cfg=json.loads((P/'dry-run.example.json').read_text())
    if cfg['dry_run'] is not True or cfg['force_entry_enable'] is not False:raise RuntimeError('Dry-run only; force entry must remain disabled')
    if cfg['exchange']['name']!='hyperliquid' or cfg['strategy'] not in {'XenonObserve','XenonFVG'}:raise RuntimeError('Unapproved exchange/strategy')
    if cfg['strategy']=='XenonFVG' and cfg.get('fee')!=.00045:raise RuntimeError('FVG conservative fee override required')
    if cfg['api_server']['listen_ip_address']!='127.0.0.1':raise RuntimeError('API must remain on loopback')
    if any(cfg['exchange'].get(k) for k in ('key','secret','api_key','privateKey','walletAddress')):raise RuntimeError('Wallet authentication is not accepted by this dry-run launcher')
    runtime.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(runtime,0o700)
    auth_path=runtime/'api-auth.json'
    if auth_path.exists():auth=json.loads(auth_path.read_text())
    else:
        auth={'username':'xenon','password':secrets.token_urlsafe(48),'jwt_secret_key':secrets.token_hex(48),'ws_token':secrets.token_urlsafe(48)}
        fd=os.open(auth_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:json.dump(auth,f)
    cfg['api_server'].update(auth);cfg['api_server']['listen_port']=account['port'];cfg['strategy']=account['strategy'];cfg['xenon_account_id']=account_id;cfg['xenon_runtime_dir']=str(runtime)
    if account_id=='diagnostic':
        cfg.update(bot_name='XENON Diagnostic / TEST ONLY',timeframe='1m',stake_amount=20,max_open_trades=1,initial_state='stopped')
        cfg['entry_pricing']['price_side']='other';cfg['exchange']['pair_whitelist']=['BTC/USDC:USDC']
    if account_id=='lens':
        cfg.update(bot_name='XENON Lens / EXPERIMENTAL DRY-RUN',initial_state='paused',xenon_lens_risk_USDC=200,stake_amount='unlimited')
        cfg['order_types']={'entry':'market','exit':'market','stoploss':'market','stoploss_on_exchange':False}
        cfg['entry_pricing']['price_side']='other'
    cfg['db_url']='sqlite:///'+str(runtime/'trades.dryrun.sqlite')
    # This host supplies a managed CA bundle; keep TLS verification enabled.
    if pathlib.Path('/etc/ssl/certs/ca-certificates.crt').exists():
        cfg['exchange']['ccxt_config']['verify']=True
        cfg['exchange']['ccxt_config']['cafile']='/etc/ssl/certs/ca-certificates.crt'
    path=runtime/'config.runtime.json'
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:json.dump(cfg,f)
    (P/'user_data').mkdir(exist_ok=True)
    return path

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--account',default='fvg');args=parser.parse_args()
    path=prepare(args.account)
    from check_connection import verify
    verify(path)
    os.execv(sys.executable,[sys.executable,'-m','freqtrade','trade','--config',str(path),'--userdir',str(P/'user_data'),'--strategy-path',str(P/'strategies'),'--logfile',str(path.parent/'freqtrade.log')])
