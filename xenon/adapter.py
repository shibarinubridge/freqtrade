"""Local API adapter for XENON. No remote URL, raw config or credentials leave it."""
import base64,json,pathlib,time,urllib.request
from accounts import get as account_config
P=pathlib.Path(__file__).resolve().parent
ACTIONS={'ft_start':'start','ft_pause':'pause','ft_stop':'stop'}
class ModeError(RuntimeError):pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
class Client:
    def __init__(self,auth_path=None,account_id='fvg'):
        a=account_config(account_id);self.account_id=account_id;self.api_base=f"http://127.0.0.1:{a['port']}/api/v1/"
        self.auth_path=pathlib.Path(auth_path) if auth_path else a['runtime']/'api-auth.json'
    def request(self,path,method='GET'):
        if path not in {'show_config','health','status','profit','balance','trades?limit=100','start','pause','stop'}:
            raise ValueError('Endpoint not allowlisted')
        auth=json.loads(self.auth_path.read_text())
        token=base64.b64encode((auth['username']+':'+auth['password']).encode()).decode()
        req=urllib.request.Request(self.api_base+path,method=method,headers={'Authorization':'Basic '+token,'Content-Type':'application/json'},data=b'{}' if method=='POST' else None)
        # Only loopback; deliberately ignore remote HTTP proxies for this local hop.
        with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(req,timeout=3) as r:return json.load(r)
    def config(self):
        cfg=self.request('show_config')
        if cfg.get('dry_run') is not True or cfg.get('exchange')!='hyperliquid' or cfg.get('force_entry_enable') is not False:
            raise ModeError('Refused: Hyperliquid dry-run with force-entry disabled is required.')
        return cfg
    def command(self,action):
        if action not in ACTIONS:raise ValueError('Unsupported Freqtrade command')
        self.config()  # Revalidate the ACTUAL bot immediately before every mutation.
        return self.request(ACTIONS[action],'POST')
    def snapshot(self):
        cfg=self.config();health=self.request('health');positions=self.request('status');profit=self.request('profit');balance=self.request('balance');trades=self.request('trades?limit=100')
        fields=('trade_id','pair','is_short','is_open','open_rate','close_rate','current_rate','stop_loss_abs','profit_abs','profit_ratio','open_timestamp','close_timestamp','exit_reason','enter_tag','amount','amount_requested','open_fill_timestamp','leverage')
        order_fields=('order_id','status','remaining','amount','safe_price','cost','filled','ft_order_side','order_type','is_open','order_timestamp','order_filled_timestamp','ft_order_tag')
        def safe(x):return {k:x.get(k) for k in fields}|{'orders':[{k:o.get(k) for k in order_fields} for o in x.get('orders',[])]}
        return {'connected':True,'mode':'DRY_RUN','dry_run':True,'observed_ms':int(time.time()*1000),'state':cfg.get('state'),'version':cfg.get('version'),'exchange':cfg.get('exchange'),'trading_mode':cfg.get('trading_mode'),'margin_mode':cfg.get('margin_mode'),'strategy':cfg.get('strategy'),'observer_only':cfg.get('strategy')=='XenonObserve','timeframe':cfg.get('timeframe'),'max_open_trades':cfg.get('max_open_trades'),'last_process_ms':(health.get('last_process_ts') or 0)*1000 or None,'wallet_USDC':balance.get('total'),'allocated_USDC':balance.get('total_bot'),'starting_allocation_USDC':balance.get('starting_capital'),'profit_closed_USDC':profit.get('profit_closed_coin'),'closed_count':profit.get('closed_trade_count'),'wins':profit.get('winning_trades'),'positions':[safe(x) for x in positions if float(x.get('amount') or 0)>0],'pending_orders':[safe(x) for x in positions if not float(x.get('amount') or 0)>0],'trades':[safe(x) for x in trades.get('trades',[]) if not x.get('is_open')],'repository_url':'https://github.com/shibarinubridge/freqtrade/tree/xenon-command-center'}

_client=Client();_cached=None;_cached_at=0.
_HISTORY=P/'.runtime/fvg-orders-observed.json'
def remember_orders(snapshot,path=None):
    path=pathlib.Path(path) if path else _HISTORY
    try:history=json.loads(path.read_text())
    except (OSError,ValueError):history=[]
    records={str(t['trade_id']):t for t in history}
    current=snapshot.get('positions',[])+snapshot.get('pending_orders',[])+snapshot.get('trades',[])
    reported={str(o['order_id']) for t in current for o in t.get('orders',[])}
    for trade in current:
        key=str(trade['trade_id']);prior=records.get(key,{})
        orders={str(o['order_id']):o for o in prior.get('orders',[])}
        orders.update({str(o['order_id']):o for o in trade.get('orders',[])})
        records[key]=trade|{'orders':list(orders.values())}
    history=list(records.values())[-200:]
    for t in history:
        for o in t.get('orders',[]):o['currently_reported']=str(o['order_id']) in reported
    try:
        path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(history));tmp.replace(path)
    except OSError:pass
    snapshot['observed_order_history']=history
    return snapshot

def collect():
    global _cached,_cached_at
    if _cached is not None and time.monotonic()-_cached_at<5:return _cached
    try:_cached=remember_orders(_client.snapshot())
    except ModeError:_cached={'connected':False,'dry_run':None,'state':'MODE_REJECTED','error':'DRY_RUN_REQUIRED'}
    except Exception:_cached=(_cached or {})|{'connected':False,'state':'OFFLINE','error':'LOCAL_API_UNAVAILABLE'}
    _cached_at=time.monotonic();return _cached

def command(name):return _client.command(name)
