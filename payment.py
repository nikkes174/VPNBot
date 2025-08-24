import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any

from aiogram.exceptions import TelegramAPIError
from yookassa import Configuration, Payment
from yookassa.domain.exceptions import (
    ApiError,
    BadRequestError,
    UnauthorizedError,
    NotFoundError,
    TooManyRequestsError,
)

from dotenv import load_dotenv
from bot import bot
from constants import TARIFFS
from tgbot.services.connect_table import (
    upsert_subscription_to_sheet,
    get_user_uuid,
    connect_to_google_sheets,
    parse_date,
)
from vpn_utils import Connection

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class PaymentManager:
    """Класс для управления платежами через YooKassa"""

    def __init__(self):
        self.bot = bot
        self.ip = os.getenv("IP")  # адрес VPN-сервера
        self.shop_id = os.getenv("YOOKASSA_SHOP_ID")
        self.secret_key = os.getenv("YOOKASSA_SECRET_KEY")
        self.return_url = "" #ссылка на бота
        self.tariffs = TARIFFS
        self.sheet = connect_to_google_sheets()

        Configuration.account_id = self.shop_id
        Configuration.secret_key = self.secret_key

    def check_payment_status(self, payment_id: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Проверяет статус платежа"""
        try:
            payment = Payment.find_one(payment_id)
            return payment.status, payment.metadata
        except (ApiError, BadRequestError, UnauthorizedError, NotFoundError, TooManyRequestsError) as e:
            logging.error("Ошибка при проверке платежа: %s", e)
            return None, None

    def get_discount_by_ref_count(self, ref_count: int) -> int:
        """Возвращает скидку в зависимости от количества рефералов"""
        if ref_count >= 21:
            return 100
        if ref_count >= 10:
            return 25
        if ref_count >= 5:
            return 10
        return 0

    def create_payment(self, user_id: int, tariff: str = "solo") -> Tuple[Optional[str], Optional[str]]:
        """Создаёт платёж в YooKassa для пользователя"""
        logging.info("Создание платежа: user_id=%s, tariff=%s", user_id, tariff)

        config = self.tariffs.get(tariff)
        if not config:
            raise ValueError(f"Неизвестный тариф: {tariff}")

        records = self.sheet.get_all_records()
        ref_count = 0
        for record in records:
            if str(record.get("user_id")) == str(user_id):
                ref_count = int(record.get("ref_count", 0))
                break

        discount = self.get_discount_by_ref_count(ref_count)
        base_price = config["price"]
        amount = base_price * (100 - discount) / 100

        if discount == 100:
            logging.info("Пользователь %s получил бесплатную подписку (ref_count=%s)", user_id, ref_count)
            return None, None

        description = f"{config['label']} для пользователя {user_id} (скидка {discount}%)"

        payment = Payment.create({
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": self.return_url},
            "capture": True,
            "description": description,
            "metadata": {"user_id": str(user_id), "tariff": tariff, "ref_count": ref_count, "discount": discount},
            "receipt": {
                "customer": {"full_name": str(user_id), "email": f"user{user_id}@yourvpn.com"},
                "items": [{
                    "description": description,
                    "quantity": "1.00",
                    "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
                    "vat_code": 1,
                    "payment_mode": "full_payment",
                    "payment_subject": "service",
                }],
            },
        })

        logging.info("Платёж создан: %.2f ₽ (скидка: %s%%, рефералов: %s)", amount, discount, ref_count)
        return payment.id, payment.confirmation.confirmation_url

    def apply_referral_bonus_if_needed(self, records, user_id: int, is_paid: bool) -> None:
        """Начисляет бонус владельцу реф.ссылки, если оплата прошла."""
        if not is_paid:
            return

        user_record = next((r for r in records if str(r.get("user_id")) == str(user_id)), None)
        if not user_record:
            return

        referrer_id = user_record.get("referrer_id")
        if not referrer_id:
            return

        referrer_record = next((r for r in records if str(r.get("user_id")) == str(referrer_id)), None)
        if not referrer_record:
            return

        end_str = referrer_record.get("end_date", "")
        end_date = parse_date(end_str)
        today = datetime.today().date()
        if not end_date or end_date < today:
            logging.warning("Не начисляем бонус: подписка у %s не активна", referrer_id)
            return

        new_end = end_date + timedelta(days=5)
        row_index = records.index(referrer_record) + 2
        records.update_cell(row_index, 4, new_end.strftime("%d.%m.%Y"))
        old_count = int(referrer_record.get("ref_count", 0) or 0)
        records.update_cell(row_index, 11, old_count + 1)

        logging.info("Бонус для user_id=%s: +5 дней, +1 к ref_count", referrer_id)

    def generate_vless_link(self, uuid: str, port: int, user_tag: str) -> str:
        """Генерирует ссылку VLESS для клиента."""
        return (
            f"vless://{uuid}@{self.ip}:{port}?type=tcp&security=reality"
            f"&pbk=2UqLjQFhlvLcY7VzaKRotIDQFOgAJe1dYD1njigp9wk"
            f"&fp=chrome&sni=yahoo.com&sid=47595474&spx=%2F#{user_tag}"
        )

    async def check_payment_loop(self, payment_id: str, user_id: int, username: str, days: int = 30) -> None:
        """Проверка статуса оплаты и активации подписки"""
        logging.info("Запущен check_payment_loop: user_id=%s, payment_id=%s", user_id, payment_id)

        for attempt in range(10):
            logging.info("Попытка %s/10 — проверка оплаты...", attempt + 1)
            await asyncio.sleep(30)

            status, metadata = self.check_payment_status(payment_id)
            logging.info("Статус платежа: %s, метаданные: %s", status, metadata)

            if status != "succeeded":
                continue

            logging.info("Оплата прошла успешно: user_id=%s", user_id)
            self.apply_referral_bonus_if_needed(self.sheet.get_all_records(), user_id, is_paid=True)

            tariff = metadata.get("tariff", "solo")
            connect = Connection()
            is_renewal = False

            if tariff == "pair":
                result1 = connect.create_inbound(user_id)
                result2 = connect.create_inbound(f"{user_id}_pair")
                if not result1 or not result2:
                    await self.bot.send_message(user_id, "❌ Не удалось создать парную подписку.")
                    return

                uuid1, port1 = result1["uuid"], result1["port"]
                uuid2, port2 = result2["uuid"], result2["port"]

                upsert_subscription_to_sheet(user_id, username, days=30, client_uuid=uuid1)

                sheet = connect_to_google_sheets()
                records = sheet.get_all_records()
                for i, record in enumerate(records):
                    if str(record.get("user_id")) == str(user_id):
                        row = i + 2
                        sheet.update_cell(row, 9, uuid2)
                        break

                link1 = self.generate_vless_link(uuid1, port1, f"user_{user_id}")
                link2 = self.generate_vless_link(uuid2, port2, f"user_{user_id}_pair")

                text = (
                    "🖤 Парная подписка активирована! 🖤\n\n"
                    f"🔗 Твой ключ:\n<pre>{link1}</pre>\n\n"
                    f"👬 Ключ для друга:\n<pre>{link2}</pre>\n\n"
                    "🔥 Если возникли трудности — напиши @BlackGateSupp"
                )
                await self.bot.send_message(user_id, text, parse_mode="HTML")
                return

            client_uuid = get_user_uuid(user_id)
            if client_uuid:
                logging.info("UUID найден: %s, продление доступа", client_uuid)
                success = connect.update_client(client_uuid, days=days)
                if not success:
                    await self.bot.send_message(user_id, "❌ Не удалось продлить VPN-доступ.")
                    return
                is_renewal = True
            else:
                logging.info("UUID не найден, создаём новое подключение")
                result = connect.create_inbound(user_id)
                if not result:
                    await self.bot.send_message(user_id, "❌ Не удалось создать подключение.")
                    return
                client_uuid = result["uuid"]
                logging.info("Новый клиент создан: %s", client_uuid)

            upsert_subscription_to_sheet(user_id, username, days=days, client_uuid=client_uuid)
            logging.info("Данные о подписке обновлены в Google Sheets")

            inbound = {"uuid": client_uuid, "port": result["port"] if not is_renewal else 0}
            link = self.generate_vless_link(inbound["uuid"], inbound["port"], f"user_{user_id}")
            text = (
                "🔄 Подписка продлена!\n" if is_renewal else "🖤 Подписка активирована! 🖤\n"
            ) + (
                f"🔗 Ваш ключ доступа:\n\n<pre>{link}</pre>\n"
                "🔥 Если возникли трудности — обратитесь к менеджеру @BlackGateSupp"
            )

            try:
                await self.bot.send_message(user_id, text, parse_mode="HTML")
                logging.info("Сообщение Telegram отправлено пользователю %s", user_id)
            except TelegramAPIError as e:
                logging.error("Ошибка при отправке сообщения в Telegram: %s", e)
            return

        logging.warning("Время ожидания истекло для payment_id=%s, user_id=%s", payment_id, user_id)
        await self.bot.send_message(user_id, "⏳ Оплата не завершена.")
