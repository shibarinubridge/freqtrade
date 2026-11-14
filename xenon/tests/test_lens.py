import datetime as dt
import json
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from freqtrade.enums import RunMode
from freqtrade.persistence import Trade

P=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P));sys.path.insert(0,str(P/'strategies'))
from lens_rules import calculate, packet, pattern, rma, known_higher, STEP
from lens_context import save_packet, collect, CACHE
from XenonLens import XenonLens, encode, decode, unit_risk, FEE


def candles(n=1152):
    rng=np.random.default_rng(825)
    close=100+np.cumsum(rng.normal(0,.4,n))
    opening=np.r_[close[0],close[:-1]]
    return pd.DataFrame({'date':pd.date_range('2026-08-01',periods=n,freq='15min',tz='UTC'),'open':opening,'high':np.maximum(opening,close)+rng.uniform(.1,.7,n),'low':np.minimum(opening,close)-rng.uniform(.1,.7,n),'close':close,'volume':rng.uniform(1,50,n)})


class LensRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=candles();cls.result=calculate(cls.data)

    def test_wilder_seed_and_recursion_have_known_values(self):
        a=rma(pd.Series([np.nan,1.,2.,3.,6.]),3)
        self.assertTrue(a.iloc[:3].isna().all());self.assertEqual(a.iloc[3],2);self.assertAlmostEqual(a.iloc[4],10/3)

    def test_full_prefix_outputs_never_change_when_future_arrives(self):
        for n in [804,809,816,900,1011]:
            prefix=calculate(self.data.iloc[:n])
            pd.testing.assert_frame_equal(prefix,self.result.iloc[:n])

    def test_feather_millisecond_and_microsecond_dates_match_nanoseconds(self):
        for unit in ['ms','us']:
            f=self.data.iloc[:100].copy();f['date']=f.date.astype(f'datetime64[{unit}, UTC]')
            pd.testing.assert_frame_equal(calculate(f),self.result.iloc[:100])

    def test_higher_timeframe_is_known_at_bar_open_not_bar_close(self):
        f=self.data.iloc[:33].copy();higher=known_higher(f,240,50)
        self.assertTrue(pd.isna(higher.iloc[15].known_close))
        self.assertEqual(higher.iloc[16].known_close,f.iloc[15].close)
        self.assertEqual(higher.iloc[31].known_close,f.iloc[15].close)
        self.assertEqual(higher.iloc[32].known_close,f.iloc[31].close)

    def test_incomplete_higher_day_and_missing_bucket_are_not_invented(self):
        f=self.data.iloc[:48].drop(index=[17]).reset_index(drop=True)
        higher=known_higher(f,240)
        # The missing 04:15 candle invalidates the 04:00–08:00 aggregate.
        row=f.index[f.date.eq(pd.Timestamp('2026-08-01T08:00Z'))][0]
        self.assertTrue(pd.isna(higher.iloc[row].known_close))
        self.assertTrue(known_higher(f,1440).known_high.isna().all())

    def test_pivots_become_known_five_bars_later(self):
        r=self.result
        for name in ['high','low']:
            available=r[f'swing_{name}_known_ms'].dropna()
            origin=r.loc[available.index,f'swing_{name}_origin_ms']
            self.assertTrue((available-origin).eq(6*STEP).all())
            for i in available.index:
                self.assertLessEqual(available.loc[i],int((r.loc[i,'date']+pd.Timedelta(minutes=15)).timestamp()*1000))

    def test_scores_are_explained_and_reference_signals_are_crossings(self):
        r=self.result
        for side in ['long','short']:
            total=r[[side+'_'+k for k in ['trend','momentum','strength','volume','htf']]].sum(axis=1)
            pd.testing.assert_series_equal(total,r[side+'_score'],check_names=False)
            self.assertTrue(total.between(0,100).all())
        for i in r.index[r.signal.ne(0)]:
            side='long' if r.at[i,'signal']==1 else 'short'
            self.assertTrue(r.at[i,side+'_condition'])
            self.assertGreaterEqual(r.at[i,side+'_score'],70)
            self.assertLess(r.at[i-1,side+'_score'],70)

    def test_anatomy_priority_and_known_shape(self):
        self.assertEqual(pattern(10,10,10,10,None,1),'FLAT')
        self.assertEqual(pattern(9,12,8,11,(11,12,8,9),1),'BULLISH_ENGULFING')
        self.assertEqual(pattern(10,12,8,10.1,None,1),'DOJI')

    def test_packet_is_finite_schema_compatible_and_marks_reference(self):
        q=packet(self.result)
        json.dumps(q,allow_nan=False)
        self.assertEqual(q['schema'],'ai-agent-lens/v1')
        self.assertEqual(q['xenon']['execution'],'REFERENCE_ONLY_NOT_BROKER')
        self.assertEqual(len(q['recent_candles']),5)
        self.assertEqual(q['scores']['long'],sum(q['scores']['long_factors'].values()))
        self.assertEqual(q['recent_candles'][-1]['c'],q['candle']['close'])

    def test_missing_volume_matches_code_fallback_and_partial_session_is_marked(self):
        f=self.data.iloc[:200].copy();f['volume']=np.nan
        r=calculate(f)
        self.assertEqual(r.iloc[-1].long_volume,6 if r.iloc[-1].close>r.iloc[-1].open else 0)
        q=packet(r);self.assertIsNone(q['candle']['volume']);self.assertIsNone(q['levels']['vwap'])
        partial=calculate(self.data.iloc[1:100]);self.assertFalse(partial.iloc[0].vwap_complete_session)
        gap=calculate(self.data.iloc[:100].drop(index=[5]));self.assertFalse(gap.iloc[5].vwap_complete_session)

    def test_rejects_duplicate_unsorted_and_inconsistent_ohlc(self):
        for f in [self.data.iloc[::-1],pd.concat([self.data.iloc[:2],self.data.iloc[:2]])]:
            with self.assertRaises(ValueError):calculate(f)
        f=self.data.iloc[:20].copy();f.loc[0,'high']=1
        with self.assertRaises(ValueError):calculate(f)

    def test_packet_journal_is_restart_idempotent_and_collector_excludes_forming_bar(self):
        with tempfile.TemporaryDirectory() as d:
            q=packet(self.result)
            self.assertTrue(save_packet(d,'BTC',q));self.assertFalse(save_packet(d,'BTC',q))
            self.assertEqual(len((pathlib.Path(d)/'history/BTC_15.jsonl').read_text().splitlines()),1)
            updated=json.loads(json.dumps(q));updated['xenon']['version']='next-test-version'
            self.assertTrue(save_packet(d,'BTC',updated))
            latest=json.loads((pathlib.Path(d)/'latest/BTC_15.json').read_text())
            self.assertEqual(latest['xenon']['version'],'next-test-version')
            self.assertEqual(latest['xenon']['reanalysis_of_version'],q['xenon']['version'])
            frame=self.data.iloc[-25:]
            rows=[{'t':int(b.date.timestamp()*1000),'o':b.open,'h':b.high,'l':b.low,'c':b.close,'v':b.volume} for b in frame.itertuples()]
            now=rows[-1]['t']+1;CACHE.clear()
            out=collect('BTC',rows,now,d)
            self.assertEqual(out['packet']['xenon']['closed_ms'],rows[-1]['t'])
            self.assertEqual(out['packet']['candle']['close'],rows[-2]['c'])


NOW=dt.datetime(2026,11,14,0,0,30,tzinfo=dt.timezone.utc)
T=int(NOW.timestamp()*1000)-30000
PAIR='BTC/USDC:USDC'


class LensNativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.s=XenonLens({'runmode':RunMode.BACKTEST,'dry_run':True,'force_entry_enable':False,'fee':FEE,'stake_currency':'USDC','exchange':{'name':'hyperliquid'},'xenon_lens_risk_USDC':200})
        self.s.bot_start();self.s._account=lambda:(1000.,[],0.,0.)
        self.tag=encode('BTC',1,T,100,99,103)
        self.s.dp=types.SimpleNamespace(get_analyzed_dataframe=lambda *args:(pd.DataFrame({'date':pd.to_datetime([T-STEP],unit='ms',utc=True),'lens_ready':[True],'lens_signal':[0]}),None))

    def tearDown(self):self.tmp.cleanup()

    def confirm(self,tag=None,amount=1,rate=100):
        return self.s.confirm_trade_entry(PAIR,'market',amount,rate,'GTC',NOW,tag or self.tag,'long')

    def test_live_forceentry_other_exchange_and_shared_runtime_are_refused(self):
        for update in [{'dry_run':False},{'force_entry_enable':True},{'runmode':RunMode.LIVE},{'exchange':{'name':'binance'}},{'runmode':RunMode.DRY_RUN,'xenon_runtime_dir':str(pathlib.Path(self.tmp.name)/'fvg')}]:
            with self.subTest(update=update):
                bad=XenonLens(self.s.config|update)
                with self.assertRaises(RuntimeError):bad.bot_start()

    def test_fixed_risk_200_refuses_insufficient_margin_without_downsizing(self):
        stake=self.s.custom_stake_amount(PAIR,NOW,100,100,5,990,2,self.tag,'long')
        self.assertEqual(stake,0);self.assertEqual(self.s._audit[-1]['reason'],'margin_or_2x_exposure')
        self.assertAlmostEqual(self.s._audit[-1]['risk_USDC'],200,places=3)

    def test_sizing_and_final_guard_use_actual_entry_and_frozen_stop(self):
        self.s._account=lambda:(100000.,[],0.,0.)
        stake=self.s.custom_stake_amount(PAIR,NOW,100.1,100,5,99000,2,self.tag,'long')
        q=stake*2/100.1
        self.assertGreater(stake,0);self.assertLessEqual(q*unit_risk(decode(self.tag),100.1),200)
        self.assertTrue(self.confirm(amount=q,rate=100.1));self.assertFalse(self.confirm(amount=q,rate=100.1))

    def test_stale_wrong_pair_stop_gap_and_target_gap_do_not_place(self):
        for tag,rate in [(encode('BTC',1,T-180000,100,99,103),100),(encode('ETH',1,T,100,99,103),100),(self.tag,98),(self.tag,104)]:
            self.assertFalse(self.confirm(tag=tag,rate=rate))

    def test_fill_metadata_roi_and_absolute_stop_and_opposite_exit(self):
        data={}
        t=types.SimpleNamespace(enter_tag=self.tag,is_short=False,leverage=2.,entry_side='buy',amount=1.,open_rate=100.,is_open=True,stop_loss=99.,get_custom_data=lambda k:data.get(k),set_custom_data=lambda k,v:data.__setitem__(k,v),calc_profit_ratio=lambda rate:(rate-100)/50-.0018)
        order=types.SimpleNamespace(ft_order_side='buy',filled=1.,order_filled_date=NOW)
        self.s.order_filled(PAIR,t,order,NOW);self.s.order_filled(PAIR,t,order,NOW+dt.timedelta(seconds=20))
        self.assertEqual(data['lens_fill_ms'],int(NOW.timestamp()*1000))
        self.assertIsNone(self.s.custom_roi(PAIR,t,NOW,0,self.tag,'long'))
        self.assertAlmostEqual(self.s.custom_roi(PAIR,t,NOW+dt.timedelta(minutes=1),1,self.tag,'long'),t.calc_profit_ratio(103))
        self.assertAlmostEqual(self.s.custom_stoploss(PAIR,t,NOW,100,0,True),.02)
        self.s.dp.get_analyzed_dataframe=lambda *args:(pd.DataFrame({'date':pd.to_datetime([T-STEP],unit='ms',utc=True),'lens_ready':[True],'lens_signal':[-1]}),None)
        self.assertEqual(self.s.custom_exit(PAIR,t,NOW,100,0),'lens_opposite_setup')

    def test_real_framework_prioritizes_stop_over_target(self):
        t=Trade(pair=PAIR,open_rate=100.,amount=1.,stake_amount=50.,leverage=2.,is_short=False,fee_open=FEE,fee_close=FEE,open_date=NOW-dt.timedelta(minutes=30),enter_tag=self.tag)
        t.get_custom_data=lambda key:T-60000;t.stop_loss=99.;t.initial_stop_loss=99.;self.s._ft_stop_uses_after_fill=True
        reasons=[x.exit_type.value for x in self.s.should_exit(t,103.2,NOW,enter=False,exit_=False,low=98.,high=104.)]
        self.assertLess(reasons.index('stop_loss'),reasons.index('roi'))

    def test_native_restart_preserves_consumed_tags_without_fvg_files(self):
        runtime=pathlib.Path(self.tmp.name)/'accounts/lens'
        config=self.s.config|{'runmode':RunMode.DRY_RUN,'xenon_runtime_dir':str(runtime)}
        a=XenonLens(config);a.bot_start();a._state['consumed']=[self.tag];a._write()
        b=XenonLens(config);b.bot_start();self.assertEqual(b._state['consumed'],[self.tag])
        self.assertFalse((runtime/'fvg-risk.json').exists())

    def test_historical_stop_is_independent_of_future_monthly_precision(self):
        from ccxt import TICK_SIZE
        tag=encode('SOL',1,T,119.41,119.095597748,120.353206755)
        o=decode(tag);self.assertAlmostEqual(o['stop'],119.1);self.assertAlmostEqual(o['target'],120.35)
        for inferred in [.001,.01]:
            data={};trade=Trade(pair='SOL/USDC:USDC',open_rate=119.41,amount=2,stake_amount=119.41,leverage=2,is_short=False,fee_open=FEE,fee_close=FEE,open_date=NOW,enter_tag=tag,price_precision=inferred,precision_mode_price=TICK_SIZE)
            trade.get_custom_data=lambda key:data.get(key);trade.set_custom_data=lambda k,v:data.__setitem__(k,v)
            order=types.SimpleNamespace(ft_order_side='buy',filled=2,order_filled_date=NOW)
            self.s.order_filled(trade.pair,trade,order,NOW);self.s._ft_stop_uses_after_fill=True
            self.s.ft_stoploss_adjust(119.41,trade,NOW,0,0,after_fill=True)
            self.assertEqual(trade.price_precision,.01);self.assertAlmostEqual(trade.stop_loss,119.1)

    def test_drawdown_guards_are_not_relaxed_for_200_risk(self):
        self.assertTrue(self.s._gate(1000,NOW));self.assertFalse(self.s._gate(800,NOW));self.assertTrue(self.s._state['suspended'])

    def test_launcher_scopes_lens_config_and_starts_paused_at_requested_risk(self):
        import run as launcher
        from accounts import get
        runtime=pathlib.Path(self.tmp.name)/'accounts/lens'
        account=get('lens')|{'runtime':runtime}
        with patch('accounts.get',return_value=account),patch.dict('os.environ',{},clear=True):
            config=json.loads(launcher.prepare('lens').read_text())
        self.assertEqual(config['strategy'],'XenonLens');self.assertEqual(config['initial_state'],'paused')
        self.assertEqual(config['xenon_lens_risk_USDC'],200);self.assertEqual(config['api_server']['listen_port'],8095)
        self.assertEqual(config['order_types']['entry'],'market');self.assertIn(str(runtime),config['db_url'])
        self.assertEqual(config['xenon_lens_margin_USDC'],900);self.assertEqual(config['xenon_lens_leverage'],5);self.assertEqual(config['max_open_trades'],1)

    def fixed_margin_profile(self):
        config=self.s.config|{'xenon_lens_margin_USDC':900,'xenon_lens_leverage':5}
        self.s=XenonLens(config);self.s.bot_start();self.s._account=lambda:(1000.,[],0.,0.)

    def test_900_margin_5x_is_4500_notional_and_risk_is_not_900(self):
        self.fixed_margin_profile()
        self.assertEqual(self.s.leverage(PAIR,NOW,100,1,20,self.tag,'long'),5)
        stake=self.s.custom_stake_amount(PAIR,NOW,100,100,5,990,5,self.tag,'long')
        self.assertAlmostEqual(stake,900);q=stake*5/100
        self.assertAlmostEqual(q*100,4500);self.assertLess(q*unit_risk(decode(self.tag),100),200)
        self.assertTrue(self.confirm(amount=q));self.assertFalse(self.confirm(amount=q+1))

    def test_fixed_margin_refuses_wide_stop_or_missing_margin_instead_of_reducing_order(self):
        self.fixed_margin_profile()
        wide=encode('BTC',1,T,100,95,115)
        self.assertEqual(self.s.custom_stake_amount(PAIR,NOW,100,100,5,990,5,wide,'long'),0)
        self.assertEqual(self.s._audit[-1]['reason'],'fixed_margin_exceeds_risk_cap')
        self.assertEqual(self.s.custom_stake_amount(PAIR,NOW,100,100,5,899,5,self.tag,'long'),0)
        self.assertEqual(self.s._audit[-1]['reason'],'margin_or_exposure_limit')

    def test_fixed_margin_allows_only_one_position_and_requires_requested_leverage(self):
        self.fixed_margin_profile()
        self.assertEqual(self.s.custom_stake_amount(PAIR,NOW,100,100,5,990,3,self.tag,'long'),0)
        self.assertEqual(self.s._audit[-1]['reason'],'requested_leverage_unavailable')
        self.s._account=lambda:(1000.,[object()],0.,0.)
        self.assertEqual(self.s.custom_stake_amount(PAIR,NOW,100,100,5,990,5,self.tag,'long'),0)

    def test_900_margin_profile_can_authorize_a_short(self):
        self.fixed_margin_profile();tag=encode('BTC',-1,T,100,101,97)
        stake=self.s.custom_stake_amount(PAIR,NOW,100,100,5,990,5,tag,'short')
        self.assertAlmostEqual(stake,900)
        self.assertTrue(self.s.confirm_trade_entry(PAIR,'market',stake*5/100,100,'GTC',NOW,tag,'short'))


if __name__=='__main__':unittest.main()
