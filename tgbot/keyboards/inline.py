from aiogram.types import WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder


def first_start_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔥НАЧАТЬ🔥", web_app=WebAppInfo(url="https://abvgdeikin.ru/")
    )

    builder.button(
        text="⁉️ИНСТРУКЦИЯ ПО ПОДКЛЮЧЕНИЮ⁉️",
        url="https://telegra.ph/Instrukciya-po-podklyucheniyu-07-14",
    )

    builder.button(
        text="⚡️Система скидок⚡️",
        url="https://telegra.ph/Sistema-skidok-07-24",
    )

    builder.button(
        text="🔗Реферальная ссылка🔗", callback_data="our_reff_link"
    )

    builder.adjust(1)
    return builder.as_markup()


def admin_panel():
    builder = InlineKeyboardBuilder()
    builder.button(
        text="💬Сообщение всем пользователям", callback_data="send_all"
    )
    builder.button(text="❗️Сообщение пользователю", callback_data="send_user")
    builder.button(text="🔍Проверка подписок", callback_data="to_check")
    builder.button(text="Назад 🔙️", callback_data="back_to_menu")
    builder.adjust(1, 1)
    return builder.as_markup()


def to_payment():
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🖤ПРИОБРЕСТИ ПОДПИСКУ🖤",
        web_app=WebAppInfo(url="https://127.0.0.1:8000"),
    )
    builder.adjust(1)
    return builder.as_markup()
