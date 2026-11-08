"""Локализация интерфейса.

Язык задаётся переменной BOT_LANG (ru — по умолчанию, en — английский) и действует на весь процесс:
для английской версии запускается отдельный экземпляр бота со своим токеном.
Тексты в коде пишутся по-русски и оборачиваются в _(); переводы лежат в bot/locales/en.py.
"""
import os

from dotenv import load_dotenv

load_dotenv()
LANG = (os.getenv("BOT_LANG") or "ru").strip().lower()
if LANG not in ("ru", "en"):
    raise RuntimeError(f"BOT_LANG={LANG!r}: допустимы ru и en")

if LANG == "en":
    from bot.locales.en import EN as _TABLE
else:
    _TABLE: dict[str, str] = {}


def _(text: str, /, **kwargs) -> str:
    """Переводит строку и подставляет именованные параметры: _("Запись #{id}", id=5)."""
    result = _TABLE.get(text, text)
    return result.format(**kwargs) if kwargs else result
