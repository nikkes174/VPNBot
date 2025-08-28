import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message
from dotenv import load_dotenv

from tgbot.keyboards.inline import (admin_panel, first_start_keyboard,
                                    to_payment)
from tgbot.services.connect_table import (connect_to_google_sheets, parse_date,
                                          schedule_daily_check)

load_dotenv()

user_router = Router()

dp = Dispatcher()


class BroadcastStates(StatesGroup):
    waiting_for_message = State()


class SendMessageStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_message = State()


@user_router.message(CommandStart())
async def user_start(message: Message, command: CommandObject):
    try:
        await message.delete()
    except TelegramAPIError as e:
        print(f"⚠️ Ошибка удаления сообщения: {e}")

    user_id = message.from_user.id
    username = message.from_user.username or ""
    args = command.args
    referrer_id = None
    if args and args.startswith("ref_"):
        try:
            referrer_id = int(args.replace("ref_", ""))
        except ValueError:
            referrer_id = None

    sheet = connect_to_google_sheets()
    records = sheet.get_all_records()
    user_row = None
    for i, record in enumerate(records):
        if str(record.get("user_id")) == str(user_id):
            user_row = i + 2
            break
    if user_row:
        sheet.update_cell(user_row, 2, username)
        if referrer_id and not records[user_row - 2].get("referrer_id"):
            sheet.update_cell(user_row, 6, referrer_id)
    else:
        sheet.append_row(
            [user_id, username, "", "", "", "", "", "", "", referrer_id, 0]
        )
    print(f"🌀 Новый запуск: user_id={user_id}, referrer_id={referrer_id}")

    video_path = "/root/vpnbot/TestNew/Files/1.mp4"
    video = FSInputFile(video_path)
    await message.answer_video(
        video=video,
        caption=(
            "🔥 Добро пожаловать в BlackGate 🔥\n"
            "Забудьте про блокировки. Теперь всё работает — всегда и везде.\n"
            "Что умеет BlackGate:\n"
            " 💳  Все банки открываются как часы\n"
            " 📺  YouTube и стримы — без тормозов, рекламы и ограничений\n"
            " 🧾  Госуслуги? Без проблем\n"
            " 😮  Никаких ручных включений — работает фоном 24/7\n"
            " ❗️ Неважно где вы — интернет всегда как дома"
        ),
        reply_markup=first_start_keyboard(),
    )


@user_router.message(Command("admin_panel"))
async def admin_panel_handler(message: types.Message):
    if message.from_user.id != 7792300158:
        await message.answer("У вас нет прав на использование этой команды.")
        return
    await message.answer(
        "Панель админа",
        reply_markup=admin_panel()
    )


@user_router.callback_query(F.data == "send_all")
async def send_all(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != 7792300158:
        await call.message.edit_text("Вы не администратор")
        return
    await call.message.edit_text("Введите сообщение для всех пользователей:")
    await state.set_state(BroadcastStates.waiting_for_message)


@user_router.message(BroadcastStates.waiting_for_message)
async def process_broadcast_message(
    message: types.Message, state: FSMContext, bot: Bot
):
    text = message.text
    sheet = connect_to_google_sheets()
    users = sheet.get_all_records()
    count = 0
    for record in users:
        user_id = record.get("user_id")
        if user_id:
            try:
                await bot.send_message(int(user_id), text)
                count += 1
            except TelegramAPIError as e:
                print(f"❌ Не удалось отправить {user_id}: {e}")
    await message.answer("✅ Рассылка завершена.")
    await state.clear()


@user_router.callback_query(F.data == "to_check")
async def o_daily_check(call: CallbackQuery, bot: Bot):
    await call.answer()  # Убираем "часики"
    await call.message.answer(
        "📅 Запуск планировщика для проверки подписок..."
    )
    schedule_daily_check(bot)
    await call.message.answer("✅ Проверка подписок была успешно запущена.")


@user_router.callback_query(F.data == "send_user")
async def send_message_to_user_handler(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer(
        "Введите ID пользователя," " которому хотите отправить сообщение:"
    )
    await state.set_state(SendMessageStates.waiting_for_user_id)


@user_router.message(SendMessageStates.waiting_for_user_id)
async def process_user_id(message: types.Message, state: FSMContext):
    user_id = message.text.strip()
    if not user_id.isdigit():
        await message.answer("❌ Введите корректный user_id (число).")
        return
    await state.update_data(user_id=user_id)
    await message.answer(f"Напишите сообщение пользователю с ID {user_id}:")
    await state.set_state(SendMessageStates.waiting_for_message)


@user_router.message(SendMessageStates.waiting_for_message)
async def process_message_text(
    message: types.Message, state: FSMContext, bot: Bot
):
    user_data = await state.get_data()
    user_id = user_data.get("user_id")
    text = message.text
    try:
        await bot.send_message(user_id, text)
        await message.answer("✅ Сообщение успешно отправлено!")
    except Exception as e:
        await message.answer(f"❌ Ошибка при отправке сообщения: {e}")
    await state.clear()


@user_router.callback_query(F.data == "our_reff_link")
async def get_reff_link(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    sheet = connect_to_google_sheets()
    records = sheet.get_all_records()
    user_record = next(
        (r for r in records if str(r.get("user_id")) == str(user_id)), None
    )
    if user_record:
        end_date_str = user_record.get("end_date")
        end_date = parse_date(end_date_str)
        if end_date and end_date >= datetime.today().date():
            ref_link = (
                f"https://t.me/mainfuckinghelper_bot?start=ref_{user_id}"
            )
            await bot.send_message(
                user_id,
                f"🔗 Твоя реферальная ссылка:\n{ref_link}\n\n"
                f"🧠 За каждую покупку по ссылке  +5 дней к твоей подписке!",
            )
        else:
            await bot.send_message(
                user_id,
                "⚠️ Реферальная ссылка доступна "
                "только при активной подписке.\n",
            )
    else:
        await bot.send_message(user_id, "😔 У вас нет активной подписки.")


async def send_payment_notification(bot: Bot, user_id: int):
    await bot.send_message(
        user_id,
        "Здравствуйте, сегодня заканчивается подписка на VPN🖤",
        reply_markup=to_payment(),
    )


async def check_expiration_dates(bot: Bot):
    try:
        sheet = connect_to_google_sheets()
        records = sheet.get_all_records()
        today = datetime.today().date()
        logging.info(f"📅 Проверка подписок на {today}")
        admin_id = "ADMIN_ID"
        for record in records:
            user_id = record.get("user_id")
            if not user_id:
                continue
            end_date = record.get("end_date")
            if end_date and parse_date(end_date) == today:
                try:
                    await send_payment_notification(bot, int(user_id))
                    logging.info(f"✅Окончание подписки {user_id}")
                except TelegramForbiddenError:
                    logging.warning(f"🚫 Бот заблокирован у {user_id}")

            trial_end = record.get("end_trial_period")
            if trial_end and parse_date(trial_end) == today:
                try:
                    await bot.send_message(
                        int(user_id),
                        "⚠️ Здравствуйте,сегодня заканчивается пробный период."
                        " Чтобы продолжить пользоваться VPN,"
                        " оплатите подписку.",
                        reply_markup=to_payment(),
                    )
                    await bot.send_message(
                        admin_id,
                        f"📛 У пользователя {user_id}"
                        f" заканчивается пробный период.",
                    )
                    logging.info(f"✅ Уведомление: окончание  {user_id}")
                except TelegramForbiddenError:
                    logging.warning(f"🚫 Бот заблокирован у {user_id}")
    except Exception as e:
        logging.exception(f"💥 Ошибка при проверке подписок: {e}")
