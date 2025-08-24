import sys
import os
import logging
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn

from bot import bot
from constants import TARIFFS
from payment import (
    check_payment_loop,
    create_payment as create_tariff_payment,
    get_discount_by_ref_count,
)
from tgbot.services.connect_table import upsert_trial_period, connect_to_google_sheets
from vpn_utils import Connection

BASE_DIR = Path(__file__).resolve().parent


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class TrialRequest(BaseModel):
    user_id: int
    username: str
    key: int

class VPNWebApp:
    def __init__(self):
        self.app = FastAPI(title="VPN Web Backend")
        self.templates = Jinja2Templates(directory=BASE_DIR / "templates")
        self.app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
        self._add_routes()

    def _add_routes(self):
        @self.app.get("/", response_class=HTMLResponse)
        async def index(request: Request, user_id: Optional[int] = None):
            """Личный кабинет пользователя."""
            end_date_str, ref_count, discount = None, 0, 0

            if user_id:
                sheet = connect_to_google_sheets()
                records = sheet.get_all_records()
                for record in records:
                    if str(record.get("user_id")) == str(user_id):
                        end_date_str = record.get("end_date")
                        ref_count = int(record.get("ref_count", 0))
                        discount = get_discount_by_ref_count(ref_count)
                        break

            return self.templates.TemplateResponse("personal_account.html", {
                "request": request,
                "end_date": end_date_str,
                "ref_count": ref_count,
                "discount": discount,
            })

        @self.app.get("/trial", response_class=HTMLResponse)
        async def trial_page(request: Request):
            """Страница пробного периода"""
            return self.templates.TemplateResponse("trail_period.html", {"request": request})

        @self.app.get("/payment", response_class=HTMLResponse)
        async def payment_page(request: Request):
            """Страница оплаты."""
            return self.templates.TemplateResponse("payment.html", {"request": request})

        @self.app.get("/api/create_trial", response_class=HTMLResponse)
        async def create_trial(request: Request, user_id: int, username: str):
            """Создание триальной подписки."""
            logging.info("Запрос на пробный период: user_id=%s, username=%s", user_id, username)

            x3 = Connection()
            result = x3.create_inbound(user_id=user_id, is_trial=True)
            if not result:
                return self.templates.TemplateResponse("trail_link.html", {
                    "request": request,
                    "link": "❌ Не удалось создать подключение. Попробуйте позже."
                })

            uuid, port = result["uuid"], result["port"]
            ip = "82.117.243.199"

            success = upsert_trial_period(user_id, username, days=3, client_uuid=uuid)
            if not success:
                return self.templates.TemplateResponse("trail_link.html", {
                    "request": request,
                    "link": "⛔ Вы уже использовали пробный период."
                })

            link = (
                f"vless://{uuid}@{ip}:{port}?type=tcp&security=reality"
                f"&pbk=2UqLjQFhlvLcY7VzaKRotIDQFOgAJe1dYD1njigp9wk"
                f"&fp=chrome&sni=yahoo.com&sid=47595474&spx=%2F"
                f"#user_{user_id}-{user_id}_prob"
            )

            try:
                await bot.send_message(
                    user_id,
                    "Пробная подписка активирована!\n"
                    f"🔗 Ваша ссылка на подключение (3 дня):\n\n<pre>{link}</pre>\n\n"
                    "Если возникли трудности — @BlackGateSupp",
                    parse_mode="HTML",
                )
                logging.info("Ссылка отправлена в Telegram: user_id=%s", user_id)
            except Exception as e:
                logging.error("Ошибка отправки в Telegram: %s", e)

            return self.templates.TemplateResponse("trail_link.html", {
                "request": request,
                "link": "Ссылка отправлена вам в Telegram."
            })

        @self.app.post("/create_payment", response_class=HTMLResponse)
        async def create_payment(request: Request, data: TrialRequest, background_tasks: BackgroundTasks):
            """Создание платежа."""
            tariff_map = {1: "solo", 2: "long", 3: "pair"}
            tariff = tariff_map.get(data.key)
            if not tariff:
                raise HTTPException(status_code=400, detail="❌ Неверный ключ тарифа")

            days = TARIFFS[tariff]["days"]
            payment_id, payment_url = create_tariff_payment(user_id=data.user_id, tariff=tariff)
            if not payment_id:
                raise HTTPException(status_code=500, detail="❌ Ошибка создания платежа")

            asyncio.create_task(check_payment_loop(payment_id, data.user_id, data.username, bot, days))

            return self.templates.TemplateResponse("payment_redirect.html", {
                "request": request,
                "payment_url": payment_url
            })

        @self.app.get("/payment_redirect", response_class=HTMLResponse)
        async def payment_redirect(request: Request):
            """Редирект после оплаты."""
            try:
                user_id_str = request.query_params.get("user_id")
                username = request.query_params.get("username")
                tariff = request.query_params.get("tariff")

                if not user_id_str or not user_id_str.isdigit():
                    raise ValueError("invalid user_id")
                if not tariff or tariff not in TARIFFS:
                    raise ValueError("invalid tariff")

                user_id = int(user_id_str)
                days = TARIFFS[tariff]["days"]

            except Exception:
                raise HTTPException(status_code=400, detail="❌ Missing or invalid parameters")

            try:
                payment_id, payment_url = create_tariff_payment(user_id=user_id, tariff=tariff)
                asyncio.create_task(check_payment_loop(payment_id, user_id, username, bot, days))
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"❌ Ошибка создания платежа: {str(e)}")

            return self.templates.TemplateResponse("payment_redirect.html", {
                "request": request,
                "payment_url": payment_url
            })

app_instance = VPNWebApp()
app = app_instance.app

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
