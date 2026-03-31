from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ai_eng_bot.src.config import settings
from ai_eng_bot.src.database.repository import Repository
from ai_eng_bot.src.handlers.menu import is_admin_user, main_menu

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    is_admin = is_admin_user(int(message.from_user.id)) if message.from_user else False
    await message.answer(
        "Привет! Я помогу тебе практиковать английский.\n"
        "Бот общается с тобой как живой собеседник и аккуратно исправляет ошибки.\n\n"
        "Пиши по‑английски, как в обычном чате — я отвечу по‑английски и покажу исправления отдельным блоком.\n"
        "Напиши своё первое сообщение на английском прямо сейчас.\n\n"
        "Открой меню кнопками ниже, если хочешь посмотреть команды.",
        reply_markup=main_menu(is_admin=is_admin),
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    is_admin = is_admin_user(int(message.from_user.id)) if message.from_user else False
    await message.answer(
        "Как пользоваться:\n"
        "- Просто пиши мне на русском/английском.\n"
        "- Я отвечу по-английски.\n"
        "- Исправления (если есть) дам отдельным блоком.\n\n"
        "Команды:\n"
        "/privacy — политика хранения и очистка истории\n"
        "/settings — настройки (заготовка)",
        reply_markup=main_menu(is_admin=is_admin),
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    is_admin = is_admin_user(int(message.from_user.id)) if message.from_user else False
    await message.answer(
        "Настройки будут добавлены позже. Сейчас можно пользоваться чатом и /privacy.",
        reply_markup=main_menu(is_admin=is_admin),
    )


@router.message(Command("my_stats"))
async def cmd_my_stats(message: Message, db_session):
    if message.from_user is None:
        return
    is_admin = is_admin_user(int(message.from_user.id))
    repo = Repository(db_session)
    stats = await repo.user_personal_stats(user_id=int(message.from_user.id))
    if stats is None:
        return await message.answer("Не смог найти ваш профиль в базе.", reply_markup=main_menu(is_admin=is_admin))

    await message.answer(
        "Ваша статистика:\n"
        f"- дата регистрации: {stats['registered_at']}\n"
        f"- тарифный план: {stats['plan']}\n"
        f"- за всё время сообщений: {stats['total_messages']}\n"
        f"- за всё время токенов: {stats['total_tokens']}\n"
        f"- за день сообщений: {stats['day_messages']}\n"
        f"- за день токенов: {stats['day_tokens']}\n",
        reply_markup=main_menu(is_admin=is_admin),
    )


def _privacy_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Очистить историю", callback_data="privacy:clear_history")],
            [InlineKeyboardButton(text="Закрыть", callback_data="privacy:close")],
        ]
    )


@router.message(Command("privacy"))
async def cmd_privacy(message: Message):
    is_admin = is_admin_user(int(message.from_user.id)) if message.from_user else False
    await message.answer(
        "Политика хранения:\n"
        f"- История сообщений хранится не дольше {settings.history_ttl_days} дней.\n"
        "- Вы можете очистить историю диалога по кнопке ниже.\n"
        "- В модель отправляется только ограниченный контекст последних сообщений.\n",
        reply_markup=_privacy_kb(),
    )


@router.message(F.text.lower() == "help")
async def menu_help(message: Message):
    return await cmd_help(message)


@router.message(F.text.lower() == "privacy")
async def menu_privacy(message: Message):
    return await cmd_privacy(message)


@router.message(F.text.lower() == "settings")
async def menu_settings(message: Message):
    return await cmd_settings(message)


@router.message(F.text.lower() == "chat")
async def menu_chat(message: Message):
    is_admin = is_admin_user(int(message.from_user.id)) if message.from_user else False
    return await message.answer("Ок. Напиши сообщение — я отвечу по‑английски.", reply_markup=main_menu(is_admin=is_admin))


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

