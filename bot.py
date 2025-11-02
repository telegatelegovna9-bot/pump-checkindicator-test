import asyncio
import sys
import traceback
import telegram
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
from monitor.fetcher import get_all_futures_tickers, fetch_ohlcv_bybit
from monitor.analyzer import analyze
from monitor.logger import log, logger
from monitor.settings import load_config
from monitor.signals import send_signal
from monitor.handlers import start, test_telegram, handle_message, toggle_indicator
import time
import logging

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

config = asyncio.run(load_config())  # Load config synchronously at startup
logger.setLevel(getattr(logging, config.get('log_level', 'INFO').upper(), logging.INFO))
for handler in logger.handlers:
    handler.setLevel(getattr(logging, config.get('log_level', 'INFO').upper(), logging.INFO))

scheduler = AsyncIOScheduler(timezone=pytz.UTC)
semaphore = asyncio.Semaphore(25)

EXCLUDED_KEYWORDS = ["ALPHA", "WEB3", "AI", "BOT"]

previous_signals = {}  # {symbol: {'count': count_triggered, 'time': time.time()}}

cached_tickers = None
cache_time = 0

async def run_monitor():
    global config, cached_tickers, cache_time
    config = await load_config()
    if not config.get('bot_status', False):
        log("Мониторинг отключен по конфигу.", level="WARNING")
        return

    try:
        log("Запуск мониторинга...")
        start_time = asyncio.get_event_loop().time()

        # Cache tickers
        current_time = time.time()
        if config.get('cache_tickers', True) and cached_tickers and (current_time - cache_time < config.get('cache_duration', 300)):
            tickers = cached_tickers
            log("Использование кэшированных тикеров", level="INFO")
        else:
            tickers = await get_all_futures_tickers()
            tickers = [t for t in tickers if not any(k in t.upper() for k in EXCLUDED_KEYWORDS)]
            cached_tickers = tickers
            cache_time = current_time
        log(f"Получено {len(tickers)} тикеров для обработки", level="INFO")

        if not tickers:
            log("Тикеры не найдены, проверка остановлена.", level="WARNING")
            return

        # Cleanup previous_signals
        ttl = 3600  # 1 hour
        to_remove = [sym for sym, data in previous_signals.items() if current_time - data['time'] > ttl]
        for sym in to_remove:
            del previous_signals[sym]
        log(f"Очищено {len(to_remove)} старых сигналов", level="DEBUG")

        total, signals = 0, 0

        async def process_symbol(symbol):
            nonlocal total, signals
            async with semaphore:
                symbol_start_time = asyncio.get_event_loop().time()
                try:
                    log(f"Начало обработки {symbol}", level="DEBUG")
                    df = await fetch_ohlcv_bybit(symbol, config['timeframe'])
                    if df.empty:
                        log(f"{symbol} - пустой DataFrame после fetch_ohlcv_bybit", level="WARNING")
                        return
                    is_signal, info = analyze(df, config, symbol=symbol)
                    total += 1
                    if is_signal:
                        signals += 1
                        count_triggered = info.get('count_triggered', 0)
                        prev_data = previous_signals.get(symbol, {'count': 0, 'time': 0})
                        if symbol not in previous_signals or count_triggered > prev_data['count']:
                            log(f"Начало отправки сигнала для {symbol}", level="INFO")
                            await send_signal(symbol, df, info, config)
                            previous_signals[symbol] = {'count': count_triggered, 'time': time.time()}
                        else:
                            # === ПОДТВЕРЖДЕНИЯ ОТКЛЮЧЕНЫ ===
                            # await send_confirmation(symbol, info, config, count_triggered, prev_data['count'])
                            pass
                    else:
                        log(f"[{symbol}] Нет сигнала. {info.get('debug', 'Нет дополнительной информации')}", level="DEBUG")
                    symbol_end_time = asyncio.get_event_loop().time()
                    log(f"Обработка {symbol} завершена за {symbol_end_time - symbol_start_time:.2f} сек", level="DEBUG")
                except Exception as e:
                    log(f"Ошибка обработки {symbol}: {str(e)}", level="ERROR")

        tasks = [process_symbol(symbol) for symbol in tickers]
        await asyncio.gather(*tasks, return_exceptions=True)
        end_time = asyncio.get_event_loop().time()
        log(f"Обработано {total} тикеров, сигналов: {signals}, время обработки: {end_time - start_time:.2f} сек", level="INFO")
    except Exception as e:
        log(f"Ошибка в run_monitor: {str(e)} | Traceback: {traceback.format_exc()}", level="ERROR")


# === ФУНКЦИЯ ОСТАВЛЕНА, НО НЕ ИСПОЛЬЗУЕТСЯ ===
# async def send_confirmation(symbol, info, config, count_triggered, prev_count):
#     try:
#         bot = telegram.Bot(token=config['telegram_token'])
#         signal_type = info.get("type", "")
#         if signal_type == "pump":
#             icon, label = "Подтверждение пампа", "ПАМП"
#         elif signal_type == "dump":
#             icon, label = "Подтверждение дампа", "ДАМП"
#         else:
#             icon, label = "СИГНАЛ", "СИГНАЛ"
#
#         html = (
#             f"<b>{icon} Подтверждение {label.lower()}</b>\n"
#             f"Монета: <code>{symbol}</code>\n"
#             f"Теперь сработало {count_triggered} из {info['total_indicators']} индикаторов (ранее {prev_count})\n"
#             f"{info['comment']}"
#         )
#
#         await bot.send_message(chat_id=config['chat_id'], text=html, parse_mode="HTML")
#         log(f"[{symbol}] Отправлено подтверждение: {label}, сработало {count_triggered}")
#     except Exception as e:
#         log(f"Ошибка отправки подтверждения для {symbol}: {e}")


async def reload_bot(app):
    """Reload config and reschedule jobs"""
    global config
    log("Перезагрузка бота...")
    scheduler.remove_all_jobs()
    config = await load_config()
    # Update log level
    logger.setLevel(getattr(logging, config.get('log_level', 'INFO').upper(), logging.INFO))
    for handler in logger.handlers:
        handler.setLevel(getattr(logging, config.get('log_level', 'INFO').upper(), logging.INFO))
    scheduler.add_job(run_monitor, 'interval', seconds=60, misfire_grace_time=30)
    scheduler.start()
    log("Бот перезапущен")


async def main():
    app = ApplicationBuilder().token(config['telegram_token']).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('test', test_telegram))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(toggle_indicator))

    scheduler.add_job(run_monitor, 'interval', seconds=60, misfire_grace_time=30)
    scheduler.start()
    log("Бот запущен. Используй /start или /test в Telegram.")

    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=['message', 'callback_query'])
    await asyncio.Event().wait()


if __name__ == '__main__':
    asyncio.run(main())