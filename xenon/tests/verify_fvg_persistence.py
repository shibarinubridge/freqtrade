import sys,pathlib,tempfile,datetime as dt
sys.path.insert(0,'xenon/strategies')
from XenonFVG import XenonFVG,encode,risk_unit,FEE
from freqtrade.persistence import init_db,Trade,Order
from freqtrade.enums import TradingMode
now=dt.datetime.now(dt.timezone.utc);setup={'coin':'BTC','direction':1,'signal_time':int(now.timestamp()*1000),'entry_limit':100.,'stop':99.,'target':103.,'old_gap':{'lo':98.,'hi':98.5}}
with tempfile.TemporaryDirectory() as folder:
 init_db('sqlite:///'+str(pathlib.Path(folder)/'ledger.sqlite'))
 s=XenonFVG({'dry_run':True,'force_entry_enable':False,'fee':FEE,'stake_currency':'USDC'});s._risk_path=pathlib.Path(folder)/'risk.json';s._ft_stop_uses_after_fill=True
 t=Trade(pair='BTC/USDC:USDC',open_rate=100,amount=2,stake_amount=100,leverage=2,is_short=False,is_open=True,open_date=now,fee_open=FEE,fee_close=FEE,enter_tag=encode(setup),trading_mode=TradingMode.FUTURES,exchange='hyperliquid',amount_precision=5,price_precision=1,precision_mode=2,contract_size=1)
 Trade.session.add(t);Trade.commit()
 order=Order(order_id='isolated-test-entry',ft_order_side='buy',status='closed',filled=2,amount=2,ft_pair=t.pair,ft_is_open=False,order_filled_date=now,order_date=now,average=100,price=100,order_type='limit',ft_amount=2,ft_price=100,cost=200)
 t.orders.append(order);t.update_trade(order);Trade.commit()
 s.order_filled(t.pair,t,order,now);Trade.commit();Trade.session.expire_all()
 assert t.get_custom_data('fvg_fill_ms')==int(now.timestamp()*1000)
 assert abs(t.get_custom_data('fvg_initial_risk_USDC')-2*risk_unit(setup))<1e-9
 s.ft_stoploss_adjust(100,t,now,0,0,after_fill=True);assert abs(t.stop_loss-99)<1e-9
 assert abs(s.custom_roi(t.pair,t,now+dt.timedelta(minutes=1),1,t.enter_tag,'long')-t.calc_profit_ratio(103))<1e-9
 t.exit_reason='stop_loss';out=Order(order_id='isolated-test-exit',ft_order_side='sell',status='closed',filled=2,amount=2,ft_pair=t.pair,ft_is_open=False,order_filled_date=now+dt.timedelta(minutes=15),order_date=now,average=99,price=99,order_type='market',ft_amount=2,ft_price=99,cost=198);t.orders.append(out);t.update_trade(out);Trade.commit();s.order_filled(t.pair,t,out,now+dt.timedelta(minutes=15))
 import json
 review=json.loads((pathlib.Path(folder)/'fvg-reviews'/f'{t.id}.json').read_text());print({k:review[k] for k in ['net_USDC','risk_USDC','net_R']});assert review['net_R']<0 and review['cause_status']=='NOT_ESTABLISHED'
 print('PASS: real isolated Freqtrade database retains fill/risk metadata, absolute stop, native ROI and loss review. No production ledger was modified.')
 Trade.session.remove()
