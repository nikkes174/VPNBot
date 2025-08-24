FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY miniapp ./miniapp
COPY tgbot ./tgbot
COPY vpn_utils.py ./vpn_utils.py
COPY payment.py ./payment.py
COPY for_connect_table.json ./for_connect_table.json
COPY bot.py ./bot.py


CMD ["uvicorn", "miniapp.main:app", "--host", "0.0.0.0", "--port", "8000"]
