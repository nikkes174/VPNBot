import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import gspread
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from oauth2client.service_account import ServiceAccountCredentials

from tgbot.keyboards.inline import to_payment


class SubscriptionManager:
    """Класс для управления подписками и интеграцией с Google Sheets."""

    def __init__(self, json_path: str, sheet_key: str):
        self.scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        self.json_path = json_path
        self.sheet_key = sheet_key
        self.sheet = self._connect_to_google_sheets()

    def _connect_to_google_sheets(self):
        """Подключение к Google Sheets."""
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            self.json_path, self.scope
        )
        client = gspread.authorize(creds)
        return client.open_by_key(self.sheet_key).sheet1

    def _get_records(self):
        """Возвращает все записи из таблицы."""
        return self.sheet.get_all_records()

    @staticmethod
    def parse_date(date_value) -> Optional[datetime.date]:
        """Пытается распарсить дату из строки или объекта datetime."""
        if not date_value:
            return None

        if isinstance(date_value, datetime):
            return date_value.date()

        try:
            date_str = str(date_value).strip()
            for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
            return None
        except Exception:
            return None

    def upsert_subscription(
        self,
        user_id: int,
        username: str,
        days: int = 30,
        client_uuid: str = "",
        referrer_id: int = None,
    ) -> None:
        """Создать или обновить подписку пользователя."""
        records = self._get_records()
        today = datetime.now().date()
        start = today.strftime("%d.%m.%Y")
        end = (today + timedelta(days=days + 1)).strftime("%d.%m.%Y")

        for i, record in enumerate(records):
            if str(record.get("user_id")) == str(user_id):
                row = i + 2
                self.sheet.update_cell(row, 3, start)
                self.sheet.update_cell(row, 4, end)
                if client_uuid:
                    self.sheet.update_cell(row, 8, client_uuid)
                return

        self.sheet.append_row(
            [
                user_id,
                username,
                "",
                "",
                "",
                "",
                "",  # C–G
                client_uuid,
                "",
                referrer_id,
                0,
            ]
        )

    def get_user_uuid(self, user_id: int) -> Optional[str]:
        """Возвращает UUID клиента по user_id."""
        records = self._get_records()
        for record in reversed(records):
            if str(record.get("user_id")) == str(user_id):
                uuid_val = record.get("client_uuid")
                if uuid_val:
                    return uuid_val.strip()
        return None

    def upsert_trial(
        self,
        user_id: int,
        username: str,
        days: int = 3,
        client_uuid: str = "",
        referrer_id: int = None,
    ) -> bool:
        """Создать или обновить пробный период для пользователя."""
        records = self._get_records()
        today = datetime.now().date()
        start = today.strftime("%d.%m.%Y")
        end = (today + timedelta(days=days + 1)).strftime("%d.%m.%Y")

        for i, record in enumerate(records):
            if str(record.get("user_id")) == str(user_id):
                row = i + 2
                last_trial = record.get("last_trial_used")
                if last_trial:
                    try:
                        last_trial_date = self.parse_date(last_trial)
                        if (
                            last_trial_date
                            and (today - last_trial_date).days < 180
                        ):
                            return False
                    except Exception:
                        pass
                self.sheet.update_cell(row, 5, start)
                self.sheet.update_cell(row, 6, end)
                self.sheet.update_cell(row, 7, start)
                if client_uuid:
                    self.sheet.update_cell(row, 8, client_uuid)
                return True

        self.sheet.append_row(
            [
                user_id,
                username,
                "",
                "",
                "",
                "",
                "",  # C–G
                client_uuid,
                "",
                referrer_id,
                0,
            ]
        )
        return True

    def increment_ref_count(self, referrer_id: int) -> None:
        """Увеличивает счетчик рефералов у пользователя."""
        records = self._get_records()
        for i, record in enumerate(records):
            if str(record.get("user_id")) == str(referrer_id):
                row = i + 2
                current_count = record.get("ref_count", 0)
                try:
                    current_count = int(current_count)
                except Exception:
                    current_count = 0
                self.sheet.update_cell(row, 10, current_count + 1)
                return

    async def send_payment_notification(self, bot: Bot, user_id: int) -> None:
        """Отправить уведомление о завершении подписки."""
        await bot.send_message(
            user_id,
            "Здравствуйте, сегодня заканчивается подписка на VPN🖤",
            reply_markup=to_payment(),
        )

    async def check_expiration_dates(
        self, bot: Bot, admin_id: int = None
    ) -> None:
        """Проверяет подписки и отправляет уведомления об окончании."""
        try:
            records = self._get_records()
            today = datetime.today().date()
            logging.info("📅 Проверка подписок на %s", today)

            for record in records:
                user_id = record.get("user_id")
                if not user_id:
                    continue

                end_date = record.get("end_date")
                if end_date and self.parse_date(end_date) == today:
                    try:
                        await self.send_payment_notification(bot, int(user_id))
                        logging.info(
                            "✅ Уведомление: окончание подписки — user %s",
                            user_id,
                        )
                    except TelegramForbiddenError:
                        logging.warning(
                            "🚫 Бот заблокирован у пользователя %s (подписка)",
                            user_id,
                        )

                trial_end = record.get("end_trial_period")
                if trial_end and self.parse_date(trial_end) == today:
                    try:
                        await bot.send_message(
                            int(user_id),
                            "⚠️ Сегодня заканчивается пробный период. Чтобы продолжить пользоваться VPN, оплатите подписку.",
                            reply_markup=to_payment(),
                        )
                        if admin_id:
                            await bot.send_message(
                                admin_id,
                                f"📛 У пользователя {user_id} заканчивается пробный период.",
                            )
                        logging.info(
                            "✅ Уведомление: окончание триала — user %s",
                            user_id,
                        )
                    except TelegramForbiddenError:
                        logging.warning(
                            "🚫 Бот заблокирован у пользователя %s (триал)",
                            user_id,
                        )

        except Exception as e:
            logging.exception("💥 Ошибка при проверке подписок: %s", e)

    def schedule_daily_check(self, bot: Bot, admin_id: int = None) -> None:
        """Запускает асинхронную проверку подписок."""
        logging.info("✅ Запуск проверки подписок вручную")
        asyncio.create_task(self.check_expiration_dates(bot, admin_id))
