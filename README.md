# BlackGate VPN Bot

## Telegram-бот c личным кабинетом через веб-приложение для продажи VPN-подписок.  
## Проект автоматизирует весь процесс: от оплаты через YooKassa до генерации VPN-подключений и учёта пользователей в Google Sheets.

---

## Основные возможности

- 🛒 Оплата подписок через **YooKassa** (поддержка разных тарифов)
- 🎁 Бесплатный **пробный период**
- 👬 **Парная подписка** (вторая ссылка для друга)
- 🔑 Автоматическая генерация **VLESS-ссылок** для подключения
- 📊 Хранение данных о подписках и рефералах в **Google Sheets**
- 🤖 Уведомления пользователям и администратору через **Telegram Bot**
- 🌐 Веб-интерфейс на **FastAPI + Jinja2 + Tailwind**

---

## ⚙️ Стек технологий

- **Backend**: [FastAPI](https://fastapi.tiangolo.com/), [Aiogram](https://docs.aiogram.dev/)
- **Payments**: [YooKassa SDK](https://yookassa.ru/developers/)
- **Database**: Google Sheets API (заколхозил для собственного удобства)
- **VPN Management**: Xray/X3-UI API
- **Frontend**: TailwindCSS + Jinja2 templates
- **Deploy**: Uvicorn + Docker

---

## 📂 Структура проекта

```text
project/
│── bot/                 # Telegram-бот (Aiogram)
│── tgbot/services/      # Работа с Google Sheets
│── templates/           # HTML-шаблоны (личный кабинет, оплата, триал)
│── static/              # Видео и стили для веба
│── vpn_utils.py         # Работа с Xray/X3-UI API
│── payment.py           # Логика платежей и подписок
│── main.py              # FastAPI сервер
│── requirements.txt     # Зависимости
│── README.md            # Документация проекта