"""Real-data prefix causality for context AND native indicator/tag outputs."""
import json
import pathlib
import sys

import pandas as pd
from freqtrade.enums import RunMode

P=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(P/'strategies'))
from XenonLens import XenonLens
from lens_rules import packet

checks=[]
for dataset in ['native_m15','august_m1']:
    root=P/'.runtime/backtest'/dataset
    cfg=json.loads((root/'config.json').read_text());cfg.update(runmode=RunMode.BACKTEST,xenon_lens_risk_USDC=200)
    s=XenonLens(cfg);s.bot_start()
    for coin in ['BTC','ETH','SOL','HYPE']:
        pair=coin+'/USDC:USDC'
        f=pd.read_feather(root/'data/futures'/f'{coin}_USDC_USDC-15m-futures.feather')
        full=s.populate_indicators(f.copy(),{'pair':pair})
        for n in [len(f)//2,len(f)-7]:
            prefix=s.populate_indicators(f.iloc[:n].copy(),{'pair':pair})
            pd.testing.assert_frame_equal(prefix,full.iloc[:n])
        checks.append({'dataset':dataset,'coin':coin,'bars':len(f),'prefix_checks':2,'native_tags_and_levels':'PASS'})
out={'status':'PASS','scope':'Same-start native indicator/tag/level causality; not a Pine numeric comparison','checks':checks}
(P/'.runtime/lens-backtest/prefix-parity.json').write_text(json.dumps(out,indent=2))
print('PASS: 16 native indicator/tag/level prefix comparisons across all four markets and both datasets.')
