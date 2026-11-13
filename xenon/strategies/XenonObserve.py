"""Connection/observation strategy, deliberately no trading edge asserted.

Existing FVG shadow is independent. Porting a strategy requires a separate
execution equivalence audit before its results can be attributed to Freqtrade.
"""
from pandas import DataFrame
from freqtrade.strategy import IStrategy

class XenonObserve(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = '15m'
    can_short = True
    startup_candle_count = 50
    process_only_new_candles = True
    minimal_roi = {'0': 0.015}
    stoploss = -0.01
    order_types = {'entry': 'limit', 'exit': 'limit', 'stoploss': 'market', 'stoploss_on_exchange': False}

    def version(self):
        return 'xenon-observe-1'

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['xenon_ema20'] = dataframe['close'].ewm(span=20, adjust=False).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        return dataframe

    def confirm_trade_entry(self, **kwargs) -> bool:
        return False
