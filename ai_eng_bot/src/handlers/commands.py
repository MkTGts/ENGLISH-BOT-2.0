from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ai_eng_bot.src.config import settings
from ai_eng_bot.src.database.repository import Repository

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я помогу тебе практиковать английский.\n"
        "Пиши сообщение — я отвечу по-английски и дам исправления ошибок отдельно.\n\n"
        "Команды: /help, /privacy"
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "Как пользоваться:\n"
        "- Просто пиши мне на русском/английском.\n"
        "- Я отвечу по-английски.\n"
        "- Исправления (если есть) дам отдельным блоком.\n\n"
        "Команды:\n"
        "/privacy — политика хранения и очистка истории\n"
        "/settings — настройки (заготовка)"
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    await message.answer("Настройки будут добавлены позже. Сейчас можно пользоваться чатом и /privacy.")


def _privacy_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Очистить историю", callback_data="privacy:clear_history")],
            [InlineKeyboardButton(text="Закрыть", callback_data="privacy:close")],
        ]
    )


@router.message(Command("privacy"))
async def cmd_privacy(message: Message):
    await message.answer(
        "Политика хранения:\n"
        f"- История сообщений хранится не дольше {settings.history_ttl_days} дней.\n"
        "- Вы можете очистить историю диалога по кнопке ниже.\n"
        "- В модель отправляется только ограниченный контекст последних сообщений.\n",
        reply_markup=_privacy_kb(),
    )


@router.callback_query(F.data == "privacy:close")
async def privacy_close(cb: CallbackQuery):
    if cb.message:
        await cb.message.delete()
    await cb.answer()


@router.callback_query(F.data == "privacy:clear_history")
async def privacy_clear_history(cb: CallbackQuery, db_session):
    if cb.from_user is None:
        await cb.answer()
        return
    repo = Repository(db_session)
    deleted = await repo.delete_user_history(user_id=int(cb.from_user.id))
    if cb.message:
        await cb.message.edit_text(f"История очищена. Удалено сообщений: {deleted}.")
    await cb.answer()

