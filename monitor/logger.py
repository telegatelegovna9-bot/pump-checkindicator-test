import logging
from logging.handlers import RotatingFileHandler
import sys
import io

# Настройка логгера
logger = logging.getLogger("TradingBot")
logger.setLevel(logging.INFO)  # Default level, будет изменен в bot.py

handler = RotatingFileHandler("bot.log", maxBytes=10_000_000, backupCount=5, encoding='utf-8')
formatter = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

console_handler = logging.StreamHandler(stream=io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace'))
console_handler.setFormatter(formatter)
console_handler.setLevel(logging.INFO)
logger.addHandler(console_handler)

def log(msg, level="INFO"):
    level = level.upper()
    if level == "ERROR":
        logger.error(msg)
    elif level == "WARNING":
        logger.warning(msg)
    elif level == "DEBUG":
        logger.debug(msg)
    else:
        logger.info(msg)