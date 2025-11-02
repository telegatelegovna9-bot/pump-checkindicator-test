import aiohttp
import pandas as pd
from monitor.logger import log
from monitor.settings import load_config

BYBIT_API = "https://api.bybit.com/v5/market"

async def get_all_futures_tickers():
    config = await load_config()
    volume_filter = config.get('volume_filter', 5_000_000.0)
    try:
        async with aiohttp.ClientSession() as session:
            params = {"category": "linear"}
            async with session.get(f"{BYBIT_API}/tickers", params=params) as resp:
                if resp.status != 200:
                    log(f"Ошибка получения тикеров: HTTP {resp.status}", level="error")
                    return []
                data = await resp.json()
                if 'result' not in data or 'list' not in data['result']:
                    log(f"Некорректные данные тикеров", level="error")
                    return []
                tickers = []
                for item in data['result']['list']:
                    symbol = item['symbol']
                    if not (symbol.endswith('USDT') or symbol.endswith('USDTPERP')):
                        continue
                    turnover = float(item.get('turnover24h', 0))
                    if turnover >= volume_filter:
                        tickers.append(symbol)
                log(f"Получено {len(tickers)} тикеров после фильтра", level="info")
                return tickers
    except Exception as e:
        log(f"Ошибка получения тикеров: {str(e)}", level="error")
        return []

async def fetch_ohlcv_bybit(symbol, timeframe='1m', limit=200):
    interval_map = {'1m': '1', '5m': '5', '15m': '15', '1h': '60'}
    interval = interval_map.get(timeframe, '1')
    try:
        async with aiohttp.ClientSession() as session:
            params = {
                "category": "linear",
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            }
            async with session.get(f"{BYBIT_API}/kline", params=params) as resp:
                if resp.status != 200:
                    log(f"Ошибка получения OHLCV для {symbol}: HTTP {resp.status}", level="error")
                    return pd.DataFrame()
                data = await resp.json()
                if 'result' not in data or 'list' not in data['result']:
                    log(f"Некорректные данные OHLCV для {symbol}", level="warning")
                    return pd.DataFrame()
                klines = data['result']['list']
                if not klines:
                    return pd.DataFrame()
                df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms')
                df.set_index('timestamp', inplace=True)
                df = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
                log(f"Получены {len(df)} свечей для {symbol}", level="debug")
                return df[::-1]  # Reverse to ascending time
    except Exception as e:
        log(f"Ошибка получения OHLCV для {symbol}: {str(e)}", level="error")
        return pd.DataFrame()