"""Launch only the isolated XENON dry-run configuration. No wallet key required."""
import json,os,pathlib,secrets,sys
P=pathlib.Path(__file__).resolve().parent
ROOT=P.parent
RUNTIME=P/'.runtime'

def prepare():
    if any(k.startswith('FREQTRADE__') for k in os.environ):
        raise RuntimeError('Remove FREQTRADE__ overrides; this launcher uses a fixed dry-run configuration.')
    cfg=json.loads((P/'dry-run.example.json').read_text())
    if cfg['dry_run'] is not True or cfg['force_entry_enable'] is not False:raise RuntimeError('Dry-run only; force entry must remain disabled')
    if cfg['exchange']['name']!='hyperliquid' or cfg['strategy'] not in {'XenonObserve','XenonFVG'}:raise RuntimeError('Unapproved exchange/strategy')
    if cfg['strategy']=='XenonFVG' and cfg.get('fee')!=.00045:raise RuntimeError('FVG conservative fee override required')
    if cfg['api_server']['listen_ip_address']!='127.0.0.1':raise RuntimeError('API must remain on loopback')
    if any(cfg['exchange'].get(k) for k in ('key','secret','api_key','privateKey','walletAddress')):raise RuntimeError('Wallet authentication is not accepted by this dry-run launcher')
    RUNTIME.mkdir(exist_ok=True,mode=0o700)
    os.chmod(RUNTIME,0o700)
    auth_path=RUNTIME/'api-auth.json'
    if auth_path.exists():auth=json.loads(auth_path.read_text())
    else:
        auth={'username':'xenon','password':secrets.token_urlsafe(48),'jwt_secret_key':secrets.token_hex(48),'ws_token':secrets.token_urlsafe(48)}
        fd=os.open(auth_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:json.dump(auth,f)
    cfg['api_server'].update(auth)
    cfg['db_url']='sqlite:///'+str(RUNTIME/'trades.dryrun.sqlite')
    # This host supplies a managed CA bundle; keep TLS verification enabled.
    if pathlib.Path('/etc/ssl/certs/ca-certificates.crt').exists():
        cfg['exchange']['ccxt_config']['verify']=True
        cfg['exchange']['ccxt_config']['cafile']='/etc/ssl/certs/ca-certificates.crt'
    path=RUNTIME/'config.runtime.json'
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:json.dump(cfg,f)
    (P/'user_data').mkdir(exist_ok=True)
    return path

if __name__=='__main__':
    path=prepare()
    os.execv(sys.executable,[sys.executable,'-m','freqtrade','trade','--config',str(path),'--userdir',str(P/'user_data'),'--strategy-path',str(P/'strategies'),'--logfile',str(RUNTIME/'freqtrade.log')])
