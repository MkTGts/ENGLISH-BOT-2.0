from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message, PreCheckoutQuery

from ai_eng_bot.src.config import settings
from ai_eng_bot.src.database.repository import Repository
from ai_eng_bot.src.handlers.menu import is_admin_user, main_menu
from ai_eng_bot.src.services.access import DEFAULT_PLANS

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
        "/my_stats — личная статистика\n"
        "/donate — поддержать развитие бота",
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

    plan = str(stats["plan"])
    limits = DEFAULT_PLANS.get(plan, DEFAULT_PLANS["free"])
    remaining_tokens = max(0, limits.max_tokens_per_day - int(stats["day_tokens"]))

    await message.answer(
        "Ваша статистика:\n"
        f"- дата регистрации: {stats['registered_at']}\n"
        f"- тарифный план: {stats['plan']}\n"
        f"- за всё время сообщений: {stats['total_messages']}\n"
        f"- за всё время токенов: {stats['total_tokens']}\n"
        f"- за день сообщений: {stats['day_messages']}\n"
        f"- за день токенов: {stats['day_tokens']}\n"
        f"- токенов на день осталось: {remaining_tokens}\n",
        reply_markup=main_menu(is_admin=is_admin),
    )


@router.message(Command("donate"))
async def cmd_donate(message: Message):
    is_admin = is_admin_user(int(message.from_user.id)) if message.from_user else False
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Поддержать звёздами (Telegram Stars)", callback_data="donate:stars")],
            [InlineKeyboardButton(text="Что даёт донат?", callback_data="donate:why")],
        ]
    )
    await message.answer(
        "Ты можешь поддержать развитие бота.\n"
        "Сейчас доступен донат через звёзды Telegram (Stars), позже появятся и другие способы.",
        reply_markup=kb,
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


@router.message(F.text.lower() == "my stats")
async def menu_my_stats(message: Message, db_session):
    return await cmd_my_stats(message, db_session)


@router.message(F.text.lower() == "donat")
async def menu_donate(message: Message):
    return await cmd_donate(message)


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


@router.callback_query(F.data == "donate:stars")
async def donate_stars(cb: CallbackQuery):
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return

    # Простое меню с фиксированными суммами Stars
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="50 ⭐", callback_data="donate:stars:50"),
                InlineKeyboardButton(text="100 ⭐", callback_data="donate:stars:100"),
                InlineKeyboardButton(text="300 ⭐", callback_data="donate:stars:300"),
            ],
            [InlineKeyboardButton(text="Назад", callback_data="donate:back")],
        ]
    )
    await cb.message.edit_text("Выбери сумму доната в звёздах:", reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("donate:stars:"))
async def donate_stars_amount(cb: CallbackQuery):
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return

    if not settings.telegram_payment_provider_token:
        await cb.answer("Оплата звёздами ещё не настроена. Обратись к создателю бота.", show_alert=True)
        return

    parts = cb.data.split(":")
    try:
        amount_stars = int(parts[-1])
    except (ValueError, IndexError):
        await cb.answer("Неверный формат суммы.", show_alert=True)
        return

    # Telegram хранит суммы в минимальных единицах (копейках).
    # Для Stars предполагаем 1 Star = 100 единиц.
    amount_units = amount_stars * 100

    prices = [LabeledPrice(label=f"Support {amount_stars} Stars", amount=amount_units)]

    payload = f"donate_stars:{amount_stars}"

    await cb.bot.send_invoice(
        chat_id=cb.message.chat.id,
        title="Поддержка бота звёздами",
        description=f"Донат {amount_stars} Telegram Stars в поддержку развития English Bot 2.0.",
        payload=payload,
        provider_token=settings.telegram_payment_provider_token,
        currency="XTR",
        prices=prices,
    )
    await cb.answer()


@router.callback_query(F.data == "donate:back")
async def donate_back(cb: CallbackQuery):
    if cb.message:
        await cmd_donate(cb.message)
    await cb.answer()


@router.callback_query(F.data == "donate:why")
async def donate_why(cb: CallbackQuery):
    text = (
        "Зачем донатить?\n\n"
        "- Донат помогает покрывать стоимость запросов к AI‑моделям.\n"
        "- Чем стабильнее покрыты расходы, тем больше свобода экспериментировать с качеством ответов и новыми функциями.\n"
        "- Это даёт возможность добавлять новые режимы практики, улучшать подсветку/объяснение ошибок и развивать админку.\n\n"
        "Если бот помогает тебе практиковать английский и снимать страх ошибки — донат это способ сказать «спасибо» и "
        "ускорить его развитие. ❤️"
    )
    if cb.message:
        await cb.message.edit_text(text)
    await cb.answer()


@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    # Здесь можно добавить валидацию payload, лимиты и т.д.
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message, db_session):
    if message.from_user is None or message.successful_payment is None:
        return

    sp = message.successful_payment
    if sp.currency != "XTR":
        return

    user_id = int(message.from_user.id)
    amount_units = int(sp.total_amount)

    repo = Repository(db_session)
    await repo.add_donation(
        user_id=user_id,
        amount_stars=amount_units,
        currency=sp.currency,
        provider="telegram_stars",
        provider_payment_id=sp.telegram_payment_charge_id,
        type_="tip",
    )

    is_admin = is_admin_user(user_id)
    await message.answer(
        "Спасибо за поддержку звёздами! ✨\n"
        "Это помогает покрывать стоимость AI‑запросов и развивать бота дальше.",
        reply_markup=main_menu(is_admin=is_admin),
    )

