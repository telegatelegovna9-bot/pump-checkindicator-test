import io
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import mplfinance as mpf
from monitor.logger import log
import talib


def create_chart(df_plot, symbol, timeframe):
    """
    Создаёт график: свечи + MACD + Volume + Фибо слева.
    Исправлено: панели синхронизированы, нет ошибок missing panels.
    """
    try:
        log(f"Колонки в df_plot для {symbol}: {list(df_plot.columns)}", level="debug")
        if len(df_plot) < 2:
            log(f"Недостаточно данных для графика {symbol}", level="warning")
            return None

        df_plot = df_plot.copy()

        # === РАСЧЁТ MACD (всегда) ===
        try:
            macd_line, signal_line, macd_hist = talib.MACD(
                df_plot['close'], fastperiod=12, slowperiod=26, signalperiod=9
            )
            df_plot['macd'] = macd_line
            df_plot['signal'] = signal_line
            df_plot['macd_hist'] = macd_hist
        except Exception as e:
            log(f"Ошибка MACD для {symbol}: {e}", level="warning")
            df_plot['macd'] = df_plot['signal'] = df_plot['macd_hist'] = np.nan

        add_plots = []

        # === ДОБＡВЛЕНИЕ ИНДИКАТОРОВ С ПРОВЕРКОЙ NaN ===
        # Bollinger
        if all(col in df_plot for col in ['sma20', 'upper', 'lower']):
            if not (df_plot['sma20'].isna().all() or df_plot['upper'].isna().all() or df_plot['lower'].isna().all()):
                add_plots.extend([
                    mpf.make_addplot(df_plot['sma20'], color='orange', linestyle='--', width=1),
                    mpf.make_addplot(df_plot['upper'], color='purple', linestyle=':', width=0.8),
                    mpf.make_addplot(df_plot['lower'], color='purple', linestyle=':', width=0.8)
                ])

        # RSI → панель 1
        if 'rsi' in df_plot and not df_plot['rsi'].isna().all():
            add_plots.append(mpf.make_addplot(df_plot['rsi'], panel=1, color='blue', ylabel='RSI'))

        # ADX → панель 3
        if 'adx' in df_plot and not df_plot['adx'].isna().all():
            add_plots.append(mpf.make_addplot(df_plot['adx'], panel=3, color='green', ylabel='ADX'))

        # MACD → панель 2 (всегда)
        if not df_plot[['macd', 'signal', 'macd_hist']].isna().all().all():
            add_plots.extend([
                mpf.make_addplot(df_plot['macd'], panel=2, color='#1f77b4', width=1.0),
                mpf.make_addplot(df_plot['signal'], panel=2, color='#ff7f0e', linestyle='--', width=1.0),
                mpf.make_addplot(df_plot['macd_hist'], type='bar', panel=2, color='gray', alpha=0.6, width=0.7)
            ])

        # === УРОВНИ ФИБОНАЧЧИ ===
        fib_high = df_plot['high'].max()
        fib_low = df_plot['low'].min()
        fib_diff = max(fib_high - fib_low, 1e-8)

        fib_ratios = [0.0, 0.236, 0.382, 0.5, 0.618, 1.0]
        fib_levels = [fib_high - r * fib_diff for r in fib_ratios]
        fib_labels = ['0%', '23.6%', '38.2%', '50%', '61.8%', '100%']

        price_decimals = max(4, -int(np.log10(abs(fib_high) or 1)) + 2) if fib_high > 0 else 8
        fib_prices = [f"{lvl:.{price_decimals}f}" for lvl in fib_levels]

        # === ОПРЕДЕЛЕНИЕ ПАНЕЛЕЙ (ГАРАНТИРОВАННАЯ СИНХРОНИЗАЦИЯ) ===
        has_rsi = any(getattr(ap, 'panel', None) == 1 for ap in add_plots)
        has_macd = any(getattr(ap, 'panel', None) == 2 for ap in add_plots)
        has_adx = any(getattr(ap, 'panel', None) == 3 for ap in add_plots)

        panel_ratios = [5]  # 0: свечи
        volume_panel = 0

        if has_rsi:
            panel_ratios.append(1)  # 1: RSI
            volume_panel += 1
        if has_macd:
            panel_ratios.append(1)  # 2: MACD
            volume_panel += 1
        if has_adx:
            panel_ratios.append(1)  # 3: ADX
            volume_panel += 1
        panel_ratios.append(1.5)  # Volume
        volume_panel += 1

        # === ПАРАМЕТРЫ ГРАФИКА ===
        plot_kwargs = {
            'type': 'candle',
            'style': 'yahoo',
            'title': f"{symbol} ({timeframe})",
            'ylabel': 'Price (USDT)',
            'volume': True,
            'volume_panel': volume_panel,
            'panel_ratios': tuple(panel_ratios),
            'figsize': (13, 8),
            'returnfig': True,
            'hlines': {
                'hlines': fib_levels,
                'colors': ['purple'] * 6,
                'linestyle': '--',
                'linewidths': [1.2] * 6,
                'alpha': 0.85
            }
        }

        if add_plots:
            plot_kwargs['addplot'] = add_plots

        fig, axes = mpf.plot(df_plot, **plot_kwargs)

        # === МЕТКИ ФИБОНАЧЧИ СЛЕВА ===
        ax = axes[0]
        x_left = -0.02
        y_offset = fib_diff * 0.001

        for level, perc, price in zip(fib_levels, fib_labels, fib_prices):
            ax.text(
                x_left, level + y_offset,
                f"{perc} — {price}",
                fontsize=8.5,
                color='purple',
                fontweight='bold',
                va='center',
                ha='right',
                transform=ax.get_yaxis_transform(),
                bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.85,
                          edgecolor='purple', linewidth=0.5)
            )

        ax.margins(x=0.02)

        # === СОХРАНЕНИЕ ===
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', dpi=110)
        plt.close(fig)
        buf.seek(0)
        return buf

    except Exception as e:
        log(f"КРИТИЧЕСКАЯ ОШИБКА в create_chart({symbol}): {e}", level="error")
        log(f"Traceback: {__import__('traceback').format_exc()}", level="error")
        return None