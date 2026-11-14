"""Diagnose official single-pair flags using unchanged native portfolio replays.

The observation hook retains the official analysis object; it never changes an
indicator, trade result, configuration or comparison during the official audit.
"""
import json
import pathlib
import sys
import time
from datetime import timedelta

from freqtrade.main import main
from freqtrade.optimize.analysis.lookahead import LookaheadAnalysis
from freqtrade.optimize.analysis.base_analysis import VarHolder

P=pathlib.Path(__file__).resolve().parent
OUT=P/'.runtime/lens-backtest/lookahead'
captured=[]
original=LookaheadAnalysis.start


def observe(self,progress):
    result=original(self,progress)
    captured.append(self)
    return result


LookaheadAnalysis.start=observe
args=json.loads((OUT/'command.json').read_text())[3:]
args[args.index('--lookahead-analysis-exportfilename')+1]=str(OUT/f'diagnostic-lookahead-{time.time_ns()}.csv')
try:
    main(args)
except SystemExit as exit:
    if exit.code not in (None,0):raise
finally:
    LookaheadAnalysis.start=original
checks=[]
for analysis in captured:
    results=analysis.full_varHolder.result['results']
    for i,row in results.iterrows():
        if i>=len(analysis.exit_varHolders):continue
        cut=analysis.exit_varHolders[i]
        if not hasattr(cut,'compared_dt'):continue
        if analysis.report_signal(cut.result,'close_date',cut.compared_dt):continue
        holder=VarHolder();holder.from_dt=analysis.full_varHolder.from_dt;holder.to_dt=row['close_date']+timedelta(minutes=30)
        analysis.prepare_data(holder,analysis.local_config['pairs'])
        replay=holder.result['results'];same=replay.loc[replay.enter_tag.eq(row['enter_tag'])]
        exact=len(same)==1 and all(same.iloc[0][k]==row[k] for k in ['open_date','close_date','open_rate','close_rate','amount','exit_reason'])
        isolated=cut.result['results'];isolated=isolated.loc[isolated.enter_tag.eq(row['enter_tag'])]
        fields=['pair','enter_tag','open_date','close_date','open_rate','close_rate','amount','exit_reason']
        def record(frame):return json.loads(frame[fields].to_json(orient='records',date_format='iso'))
        checks.append({'index':int(i),'pair':row['pair'],'tag':row['enter_tag'],'full_portfolio_cutoff':holder.to_dt.isoformat(),'same_portfolio_prefix_exact':exact,'baseline':record(results.loc[[i]]),'single_pair_replay':record(isolated),'full_portfolio_replay':record(same),'interpretation':'Same full portfolio retains exit without future data; official audit changes portfolio membership.' if exact else 'Unresolved: full portfolio cutoff changed the trade; do not claim lookahead clearance.'})
report={'official_has_bias':any(a.current_analysis.has_bias for a in captured),'flagged_exit_checks':checks,'status':'DIAGNOSED_PORTFOLIO_DEPENDENCE' if checks and all(x['same_portfolio_prefix_exact'] for x in checks) else 'UNRESOLVED' if checks else 'NO_FLAGGED_EXITS','scope':'Diagnostic only. Preserve official CSV; no universal absence-of-bias certification.'}
(OUT/'portfolio-prefix-diagnosis.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
