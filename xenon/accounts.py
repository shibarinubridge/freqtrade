"""Explicit local dry-run fleet registry. No arbitrary URLs or credentials exported."""
import pathlib
ROOT=pathlib.Path(__file__).resolve().parent
ACCOUNTS={
 'lens':{'id':'lens','name':'AI Agent Lens · Lab','strategy_id':'lens','strategy':'XenonLens','timeframe':'15m','port':8095,'enabled':True,'experimental':True,'risk_per_trade_USDC':200,'runtime':ROOT/'.runtime/accounts/lens','description':'Port Python independent · confluence EMA/RSI/ADX · risc cerut 200 USDC, limitat de marjă și expunere 2×.'},
 'diagnostic':{'id':'diagnostic','name':'Diagnostic · TEST','strategy_id':'diagnostic','strategy':'XenonDiagnostic','timeframe':'1m','port':8094,'enabled':True,'diagnostic':True,'runtime':ROOT/'.runtime/accounts/diagnostic','description':'Test tehnic dry-run; nu este performanță de strategie.'},
 'fvg':{'id':'fvg','name':'FVG Core','strategy_id':'fvg','strategy':'XenonFVG','timeframe':'15m','port':8091,'enabled':True,'runtime':ROOT/'.runtime','description':'Sweep · BOS · FVG · CE 50%'},
 'orderblock':{'id':'orderblock','name':'Order Block Lab','strategy_id':'orderblock','strategy':None,'timeframe':'15m','port':8092,'enabled':False,'runtime':ROOT/'.runtime/accounts/orderblock','description':'Neimplementată în Freqtrade: lipsesc portarea Limit MT și testele native.'},
 'amd':{'id':'amd','name':'AMD Lab','strategy_id':'amd-volume','strategy':None,'timeframe':'30m','port':8093,'enabled':False,'runtime':ROOT/'.runtime/accounts/amd','description':'Neimplementată în Freqtrade: profil M1 proxy și reguli de execuție de portat.'}}
def get(account_id):
 if account_id not in ACCOUNTS:raise ValueError('Unknown account')
 return ACCOUNTS[account_id]
def public():return [{k:v for k,v in a.items() if k not in ('port','runtime')}|{'deployment':'DEPLOYED' if a['enabled'] else 'NOT_DEPLOYED','isolation':'Separate process / database / API / virtual wallet'} for a in ACCOUNTS.values()]
