from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from ai_eng_bot.src.config import settings


USER_MENU = ("Chat", "Help", "Privacy", "My stats", "Donat")
ADMIN_MENU = ("Admin",)


def main_menu(*, is_admin: bool) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text="Chat"), KeyboardButton(text="Help")],
        [KeyboardButton(text="Privacy"), KeyboardButton(text="My stats")]
        #[KeyboardButton(text="Donat")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text="Admin")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, input_field_placeholder="Напиши сообщение…")


def is_admin_user(user_id: int) -> bool:
    return user_id in settings.admin_id_set()

