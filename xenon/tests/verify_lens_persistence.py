"""Real isolated Freqtrade SQL/order lifecycle; no exchange/order submission."""
import datetime as dt
import json
import pathlib
import sys
import tempfile

sys.path.insert(0,'xenon/strategies')
from XenonLens import XenonLens,encode,unit_risk,decode,FEE
from freqtrade.persistence import init_db,Trade,Order
from freqtrade.enums import TradingMode,RunMode

now=dt.datetime.now(dt.timezone.utc)
tag=encode('BTC',1,int(now.timestamp()*1000),100,99,103)
with tempfile.TemporaryDirectory() as folder:
    root=pathlib.Path(folder)/'accounts/lens';root.mkdir(parents=True)
    init_db('sqlite:///'+str(root/'test.sqlite'))
    config={'runmode':RunMode.DRY_RUN,'dry_run':True,'force_entry_enable':False,'fee':FEE,'exchange':{'name':'hyperliquid'},'stake_currency':'USDC','xenon_runtime_dir':str(root)}
    s=XenonLens(config);s.bot_start();s._ft_stop_uses_after_fill=True
    t=Trade(pair='BTC/USDC:USDC',open_rate=100,amount=2,stake_amount=100,leverage=2,is_short=False,is_open=True,open_date=now,fee_open=FEE,fee_close=FEE,enter_tag=tag,trading_mode=TradingMode.FUTURES,exchange='hyperliquid',amount_precision=5,price_precision=1,precision_mode=2,contract_size=1)
    Trade.session.add(t);Trade.commit()
    entry=Order(order_id='isolated-lens-entry',ft_order_side='buy',status='closed',filled=2,amount=2,ft_pair=t.pair,ft_is_open=False,order_filled_date=now,order_date=now,average=100,price=100,order_type='market',ft_amount=2,ft_price=100,cost=200)
    t.orders.append(entry);t.update_trade(entry);Trade.commit();s.order_filled(t.pair,t,entry,now);Trade.commit();Trade.session.expire_all()
    restarted=XenonLens(config);restarted.bot_start();restarted._ft_stop_uses_after_fill=True
    assert t.get_custom_data('lens_fill_ms')==int(now.timestamp()*1000)
    assert abs(t.get_custom_data('lens_risk_USDC')-2*unit_risk(decode(tag),100))<1e-9
    restarted.ft_stoploss_adjust(100,t,now,0,0,after_fill=True)
    assert abs(t.stop_loss-99)<1e-9
    assert abs(restarted.custom_roi(t.pair,t,now+dt.timedelta(minutes=1),1,tag,'long')-t.calc_profit_ratio(103))<1e-9
    t.exit_reason='stop_loss'
    exit_order=Order(order_id='isolated-lens-exit',ft_order_side='sell',status='closed',filled=2,amount=2,ft_pair=t.pair,ft_is_open=False,order_filled_date=now+dt.timedelta(minutes=15),order_date=now,average=99,price=99,order_type='market',ft_amount=2,ft_price=99,cost=198)
    t.orders.append(exit_order);t.update_trade(exit_order);Trade.commit();restarted.order_filled(t.pair,t,exit_order,now+dt.timedelta(minutes=15))
    review=json.loads((root/'lens-reviews'/f'{t.id}.json').read_text())
    assert review['net_USDC']<0 and review['source']=='NATIVE_LENS_DRY_RUN'
    print('PASS: SQL restart retains Lens fill/geometry/risk, fixed stop and target, and native losing exit review. No production ledger or exchange was used.')
    Trade.session.remove()
