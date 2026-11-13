import importlib.util,json,pathlib,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import adapter
import run as launcher

class FakeClient(adapter.Client):
    def __init__(self,cfg=None):
        self.cfg={'dry_run':True,'force_entry_enable':False,'exchange':'hyperliquid','strategy':'XenonObserve','state':'running','password':'MUST_NOT_LEAVE_ADAPTER'}| (cfg or {})
        self.calls=[]
    def request(self,path,method='GET'):
        self.calls.append((path,method))
        if path=='show_config':return self.cfg
        if path=='health':return {'last_process_ts':123}
        if path=='status':return []
        if path=='profit':return {'closed_trade_count':0,'profit_closed_coin':0,'winning_trades':0}
        if path=='balance':return {'total':1000,'total_bot':990,'starting_capital':990}
        if path=='trades?limit=100':return {'trades':[]}
        return {'status':'confirmed'}

class AdapterTests(unittest.TestCase):
    def test_commands_revalidate_actual_dry_run_before_every_post(self):
        c=FakeClient();self.assertEqual(c.command('ft_pause'),{'status':'confirmed'})
        self.assertEqual(c.calls,[('show_config','GET'),('pause','POST')])
        c.cfg['dry_run']=False
        with self.assertRaises(adapter.ModeError):c.command('ft_start')
        self.assertEqual(sum(m=='POST' for _,m in c.calls),1)
    def test_live_wrong_exchange_forceentry_and_unknown_commands_are_rejected(self):
        for cfg in [{'dry_run':False},{'exchange':'binance'},{'force_entry_enable':True}]:
            c=FakeClient(cfg)
            with self.assertRaises(adapter.ModeError):c.command('ft_stop')
            self.assertFalse(any(m=='POST' for _,m in c.calls))
        c=FakeClient()
        with self.assertRaises(ValueError):c.command('forceentry')
        self.assertEqual(c.calls,[])
    def test_snapshot_distinguishes_wallet_from_allocation_and_never_exports_config(self):
        s=FakeClient().snapshot();self.assertEqual(s['wallet_USDC'],1000);self.assertEqual(s['allocated_USDC'],990)
        self.assertNotIn('MUST_NOT_LEAVE_ADAPTER',json.dumps(s));self.assertTrue(s['observer_only']);self.assertEqual(s['closed_count'],0)
    def test_order_observations_preserve_absence_as_unknown_not_cancelled(self):
        with tempfile.TemporaryDirectory() as d:
            path=pathlib.Path(d)/'history.json';trade={'trade_id':7,'pair':'BTC/USDC:USDC','is_open':True,'orders':[{'order_id':'dry_7','status':'open','filled':0}]}
            s=adapter.remember_orders({'pending_orders':[trade]},path);self.assertTrue(s['observed_order_history'][0]['orders'][0]['currently_reported'])
            s=adapter.remember_orders({'pending_orders':[]},path);o=s['observed_order_history'][0]['orders'][0];self.assertFalse(o['currently_reported']);self.assertEqual(o['status'],'open');self.assertEqual(o['filled'],0)
    def test_launcher_creates_private_local_auth_and_rejects_environment_override(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td);(p/'dry-run.example.json').write_text((launcher.P/'dry-run.example.json').read_text())
            with patch.object(launcher,'P',p),patch.object(launcher,'RUNTIME',p/'.runtime'),patch.dict('os.environ',{},clear=True):
                path=launcher.prepare();cfg=json.loads(path.read_text());self.assertTrue(cfg['dry_run']);self.assertEqual(path.stat().st_mode & 0o777,0o600)
                self.assertEqual((p/'.runtime/api-auth.json').stat().st_mode & 0o777,0o600);self.assertEqual(cfg['api_server']['listen_ip_address'],'127.0.0.1');self.assertIs(cfg['exchange']['ccxt_config']['requests_trust_env'],True)
            with patch.dict('os.environ',{'FREQTRADE__DRY_RUN':'false'}):
                with self.assertRaises(RuntimeError):launcher.prepare()
    def test_observer_never_signals_or_confirms_an_entry(self):
        from pandas import DataFrame
        from strategies.XenonObserve import XenonObserve
        s=XenonObserve({});d=DataFrame({'close':[100,101,99]});d=s.populate_indicators(d,{})
        d=s.populate_entry_trend(d,{});self.assertEqual(d.enter_long.sum(),0);self.assertEqual(d.enter_short.sum(),0);self.assertFalse(s.confirm_trade_entry(pair='BTC/USDC:USDC'))

if __name__=='__main__':unittest.main()
