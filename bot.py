"""Personal habit tracker Telegram bot."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from dotenv import load_dotenv

import storage
from storage import (
    DayState,
    HistoryRow,
    PROTEIN_TARGET,
    WATER_TARGET,
    bump_protein,
    bump_water,
    compute_streaks,
    get_day,
    get_history,
    init_db,
    reset_protein,
    set_binary,
)

load_dotenv()

TG_BOT_TOKEN: Final = os.environ["TG_BOT_TOKEN"]
AUTHOR_TG_ID: Final = int(os.environ["AUTHOR_TG_ID"])
TZ_NAME: Final = os.environ.get("TZ", "Europe/Moscow")
DB_PATH: Final = os.environ.get("DB_PATH", "habits.db")

TZ: Final = ZoneInfo(TZ_NAME)

logger = logging.getLogger(__name__)


def today_iso() -> str:
    """Single source of truth for 'today' in configured TZ."""
    return datetime.now(TZ).date().isoformat()


def water_bar(count: int, target: int = WATER_TARGET) -> str:
    filled = "▰" * count
    empty = "▱" * (target - count)
    return f"{filled}{empty}"


def check(b: bool) -> str:
    return "✅" if b else "⬜"


def render_today_text(state: DayState, current: int, best: int) -> str:
    closed = state.is_closed()
    header_status = "🎯 Закрыт" if closed else f"{state.checked_count()}/9"
    lines = [
        f"📅 *{state.date}*  {header_status}",
        "",
        f"{check(state.morning_shower)} Утренний душ",
        f"{check(state.morning_walk)} Ходьба с утра (25-30 мин)",
        "",
        f"💧 Вода: {water_bar(state.water_count)} {state.water_count}/{WATER_TARGET}",
        (
            f"🥩 Белок: {state.protein_g}г / {PROTEIN_TARGET}г "
            f"{'✅' if state.protein_g >= PROTEIN_TARGET else ''}"
        ).rstrip(),
        "",
        f"{check(state.evening_walk)} Вечерняя прогулка",
        "",
        f"{check(state.no_porn)} Без порно",
        f"{check(state.no_masturbation)} Без мастурбации",
        f"{check(state.no_shorts)} Без коротких видео",
        "",
        f"{check(state.sleep)} Здоровый сон",
        "",
        f"Стрик: текущий *{current}* / лучший *{best}*",
    ]
    return "\n".join(lines)


def render_today_keyboard(state: DayState) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(
            text=f"{check(state.morning_shower)} Душ",
            callback_data="t:shower",
        )],
        [InlineKeyboardButton(
            text=f"{check(state.morning_walk)} Ходьба утром",
            callback_data="t:walk_am",
        )],
        [
            InlineKeyboardButton(text="💧 −1", callback_data="w:-"),
            InlineKeyboardButton(text="💧 +1", callback_data="w:+"),
        ],
        [
            InlineKeyboardButton(text="🥩 +10", callback_data="p:10"),
            InlineKeyboardButton(text="🥩 +20", callback_data="p:20"),
            InlineKeyboardButton(text="🥩 +50", callback_data="p:50"),
            InlineKeyboardButton(text="🥩 ↺", callback_data="p:r"),
        ],
        [InlineKeyboardButton(
            text=f"{check(state.evening_walk)} Прогулка вечером",
            callback_data="t:walk_pm",
        )],
        [InlineKeyboardButton(
            text=f"{check(state.no_porn)} Без порно",
            callback_data="t:porn",
        )],
        [InlineKeyboardButton(
            text=f"{check(state.no_masturbation)} Без мастурбации",
            callback_data="t:mast",
        )],
        [InlineKeyboardButton(
            text=f"{check(state.no_shorts)} Без коротких видео",
            callback_data="t:shorts",
        )],
        [InlineKeyboardButton(
            text=f"{check(state.sleep)} Здоровый сон",
            callback_data="t:sleep",
        )],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def render_history_text(rows: list[HistoryRow]) -> str:
    lines = ["📜 *Последние 7 дней:*", ""]
    for r in rows:
        status = "✅" if r.is_closed else f"{r.checked_count}/9"
        lines.append(f"`{r.date}`  {status}")
    return "\n".join(lines)


# Map short callback toggle keys to DB field names.
TOGGLE_KEYS: Final = {
    "shower": "morning_shower",
    "walk_am": "morning_walk",
    "walk_pm": "evening_walk",
    "porn": "no_porn",
    "mast": "no_masturbation",
    "shorts": "no_shorts",
    "sleep": "sleep",
}


def is_author(user_id: int | None) -> bool:
    return user_id == AUTHOR_TG_ID


async def send_today(message: Message) -> None:
    state = get_day(today_iso())
    current, best = compute_streaks(today_iso())
    await message.answer(
        render_today_text(state, current, best),
        reply_markup=render_today_keyboard(state),
        parse_mode="Markdown",
    )


def make_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def on_start(message: Message):
        if not is_author(message.from_user.id if message.from_user else None):
            return
        await send_today(message)

    @dp.message(Command("today"))
    async def on_today(message: Message):
        if not is_author(message.from_user.id if message.from_user else None):
            return
        await send_today(message)

    @dp.message(Command("history"))
    async def on_history(message: Message):
        if not is_author(message.from_user.id if message.from_user else None):
            return
        rows = get_history(7, today_iso())
        await message.answer(render_history_text(rows), parse_mode="Markdown")

    @dp.message(F.text)
    async def on_text(message: Message):
        if not is_author(message.from_user.id if message.from_user else None):
            return
        await send_today(message)

    @dp.callback_query()
    async def on_callback(cq: CallbackQuery):
        if not is_author(cq.from_user.id if cq.from_user else None):
            await cq.answer()
            return
        data = cq.data or ""
        d = today_iso()

        if data.startswith("t:"):
            key = data[2:]
            field = TOGGLE_KEYS.get(key)
            if field is None:
                await cq.answer("неизвестная кнопка")
                return
            state = get_day(d)
            current_val = getattr(state, field)
            set_binary(d, field, not current_val)
        elif data == "w:+":
            bump_water(d, 1)
        elif data == "w:-":
            bump_water(d, -1)
        elif data == "p:10":
            bump_protein(d, 10)
        elif data == "p:20":
            bump_protein(d, 20)
        elif data == "p:50":
            bump_protein(d, 50)
        elif data == "p:r":
            reset_protein(d)
        else:
            await cq.answer("неизвестная кнопка")
            return

        state = get_day(d)
        current, best = compute_streaks(d)
        try:
            if cq.message:
                await cq.message.edit_text(
                    render_today_text(state, current, best),
                    reply_markup=render_today_keyboard(state),
                    parse_mode="Markdown",
                )
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                pass
            else:
                raise
        await cq.answer()

    return dp


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    init_db(DB_PATH)
    bot = Bot(token=TG_BOT_TOKEN)
    dp = make_dispatcher()
    logger.info(
        "bot starting: author=%s tz=%s db=%s", AUTHOR_TG_ID, TZ_NAME, DB_PATH
    )
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
