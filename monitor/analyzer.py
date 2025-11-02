import pandas as pd
import numpy as np
import talib
from monitor.logger import log

def analyze(df, config, symbol="Unknown"):
    info = {}
    if len(df) < 50:
        info['debug'] = f"Внимание: для анализа {symbol} доступно только {len(df)} свечей (менее 50)"
        return False, info
    elif len(df) < 200:
        info['debug'] = f"Внимание: для анализа {symbol} доступно {len(df)} свечей (менее 200, требуется для обычных монет)"

    df = df.copy() if any(config.get('indicators_enabled', {}).values()) else df
    df['close'] = df['close'].astype(float)
    df['volume'] = df['volume'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)

    # Проверка данных на NaN
    if df['close'].isna().any() or df['high'].isna().any() or df['low'].isna().any() or df['volume'].isna().any():
        log(f"Ошибка: DataFrame для {symbol} содержит NaN значения", level="error")
        info['debug'] = f"Ошибка: DataFrame содержит NaN значения"
        return False, info

    indicators = config.get('indicators_enabled', {
        "price_change": True,
        "rsi": True,
        "macd": True,
        "volume_surge": True,
        "bollinger": True,
        "adx": True,
        "rsi_macd_divergence": True,
        "candle_patterns": True,
        "volume_pre_surge": True,
        "ema_crossover": True,
        "obv": True
    })

    # Инициализация переменных
    rsi = np.nan
    macd = np.nan
    macd_cross = False
    macd_bear = False
    sma20 = np.nan
    upper = np.nan
    lower = np.nan
    vol_surge = np.nan
    adx = np.nan
    bullish_divergence = False
    bearish_divergence = False
    bullish_candle = False
    bearish_candle = False
    volume_pre_surge = False
    ema_cross_up = False
    ema_cross_down = False
    obv_trend = np.nan
    obv_rising = False
    obv_falling = False

    price_change = (df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100 if len(df) > 1 else 0

    # RSI (14)
    if indicators.get('rsi', True) or indicators.get('rsi_macd_divergence', True):
        try:
            df['rsi'] = talib.RSI(df['close'], timeperiod=14)
            rsi = df['rsi'].iloc[-1]
            info['rsi'] = rsi
        except Exception as e:
            log(f"Ошибка расчёта RSI для {symbol}: {e}", level="error")

    # MACD
    if indicators.get('macd', True) or indicators.get('rsi_macd_divergence', True):
        try:
            df['macd'], df['signal'], df['macd_hist'] = talib.MACD(df['close'], fastperiod=12, slowperiod=26, signalperiod=9)
            macd = df['macd'].iloc[-1]
            macd_prev = df['macd'].iloc[-2]
            signal = df['signal'].iloc[-1]
            signal_prev = df['signal'].iloc[-2]
            macd_cross = (macd > signal) and (macd_prev <= signal_prev)
            macd_bear = (macd < signal) and (macd_prev >= signal_prev)
            info['macd'] = macd
        except Exception as e:
            log(f"Ошибка расчёта MACD для {symbol}: {e}", level="error")

    # Bollinger Bands
    if indicators.get('bollinger', True):
        try:
            if len(df) >= 20:  # Проверяем, достаточно ли данных для Bollinger Bands
                df['upper'], df['sma20'], df['lower'] = talib.BBANDS(df['close'], timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
                sma20 = df['sma20'].iloc[-1]
                upper = df['upper'].iloc[-1]
                lower = df['lower'].iloc[-1]
                info['bollinger'] = 'upper' if df['close'].iloc[-1] > upper else 'lower' if df['close'].iloc[-1] < lower else 'inside'
            else:
                log(f"Недостаточно данных для Bollinger Bands для {symbol}: {len(df)} свечей", level="warning")
        except Exception as e:
            log(f"Ошибка расчёта Bollinger Bands для {symbol}: {e}", level="error")

    # Volume Surge
    if indicators.get('volume_surge', True):
        try:
            vol_avg = df['volume'].rolling(window=20).mean().iloc[-1]
            vol_surge = df['volume'].iloc[-1] / vol_avg if vol_avg != 0 else np.nan
            info['volume_surge'] = vol_surge
        except Exception as e:
            log(f"Ошибка расчёта Volume Surge для {symbol}: {e}", level="error")

    # ADX
    if indicators.get('adx', True):
        try:
            df['adx'] = talib.ADX(df['high'], df['low'], df['close'], timeperiod=14)
            adx = df['adx'].iloc[-1]
            info['adx'] = adx
        except Exception as e:
            log(f"Ошибка расчёта ADX для {symbol}: {e}", level="error")

    # RSI-MACD Divergence
    if indicators.get('rsi_macd_divergence', True):
        try:
            last_close = df['close'].iloc[-1]
            prev_close = df['close'].iloc[-2]
            last_rsi = rsi
            prev_rsi = df['rsi'].iloc[-2]
            # ... (оставшаяся часть кода для дивергенции)
            # (здесь код обрезан в исходном файле, предполагается, что он остался без изменений)
        except Exception as e:
            log(f"Ошибка расчёта дивергенции RSI-MACD для {symbol}: {e}", level="error")

    # ... (оставшаяся часть кода для других индикаторов, предполагается, что она осталась без изменений)

    # Подсчёт сработавших индикаторов
    triggered = []
    if indicators.get('price_change', True) and abs(price_change) > config['price_change_threshold']:
        triggered.append('price_change')
    if indicators.get('rsi', True) and not pd.isna(rsi) and (rsi > 70 or rsi < 30):
        triggered.append('rsi')
    if indicators.get('macd', True) and (macd_cross or macd_bear):
        triggered.append('macd')
    if indicators.get('volume_surge', True) and not pd.isna(vol_surge) and vol_surge > 2:
        triggered.append('volume_surge')
    if indicators.get('bollinger', True) and info.get('bollinger') != 'inside':
        triggered.append('bollinger')
    if indicators.get('adx', True) and not pd.isna(adx) and adx > 25:
        triggered.append('adx')
    if indicators.get('rsi_macd_divergence', True) and info.get('rsi_macd_divergence') != 'none':
        triggered.append('rsi_macd_divergence')
    if indicators.get('candle_patterns', True) and (bullish_candle or bearish_candle):
        triggered.append('candle_patterns')
    if indicators.get('volume_pre_surge', True) and volume_pre_surge:
        triggered.append('volume_pre_surge')
    if indicators.get('ema_crossover', True) and (ema_cross_up or ema_cross_down):
        triggered.append('ema_crossover')
    if indicators.get('obv', True) and (obv_rising or obv_falling):
        triggered.append('obv')

    count_triggered = len(triggered)
    total_indicators = sum(indicators.values())
    info['count_triggered'] = count_triggered
    info['total_indicators'] = total_indicators

    # Проверка минимального количества и обязательных индикаторов
    required = config.get('required_indicators', [])
    min_ind = config.get('min_indicators', 1)
    all_required = all(r in triggered for r in required)
    is_signal = all_required and count_triggered >= min_ind

    # Определение типа сигнала (pump/dump)
    signal_type = ""
    if is_signal:
        if price_change > config['price_change_threshold']:
            signal_type = "pump"
        elif price_change < -config['price_change_threshold']:
            signal_type = "dump"
    info['type'] = signal_type

    # Комментарий
    comment_parts = []
    if indicators.get('rsi', True):
        comment_parts.append(f"RSI={rsi:.1f}" if not pd.isna(rsi) else "RSI=NaN")
    if indicators.get('macd', True):
        comment_parts.append(f"MACD={'бычий' if macd_cross else 'медвежий' if macd_bear else 'нейтральный'}")
    if indicators.get('volume_surge', True):
        comment_parts.append(f"объём x{vol_surge:.2f}" if not pd.isna(vol_surge) else "объём=NaN")
    if indicators.get('adx', True):
        comment_parts.append(f"ADX={adx:.1f}" if not pd.isna(adx) else "ADX=NaN")
    if indicators.get('rsi_macd_divergence', True):
        comment_parts.append(f"Дивергенция={'бычья' if bullish_divergence else 'медвежья' if bearish_divergence else 'нет'}")
    if indicators.get('candle_patterns', True):
        comment_parts.append(f"Свечной паттерн={'Hammer' if bullish_candle else 'Shooting Star' if bearish_candle else 'нет'}")
    if indicators.get('volume_pre_surge', True):
        comment_parts.append(f"Рост объёма={'да' if volume_pre_surge else 'нет'}")
    if indicators.get('ema_crossover', True):
        comment_parts.append(f"EMA Crossover={'бычий' if ema_cross_up else 'медвежий' if ema_cross_down else 'нет'}")
    if indicators.get('obv', True):
        comment_parts.append(f"OBV={'растёт' if obv_rising else 'падает' if obv_falling else 'стабилен'}")
    info["comment"] = ", ".join(comment_parts) if comment_parts else "Нет активных индикаторов"

    # Детали для логов
    if not signal_type:
        if 'debug' not in info:
            info['debug'] = f"Нет сигнала для {symbol}"
    else:
        info['debug'] = f"Сигнал сгенерирован для {symbol}: {signal_type}, сработало {count_triggered} из {total_indicators}"

    return bool(signal_type), info