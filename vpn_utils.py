import datetime
import json
import logging
import os
import random
import string
import uuid
from typing import Any, Dict, Optional, Union

import requests
from dotenv import load_dotenv

load_dotenv()

LOGIN = os.getenv("LOGIN")

PASSWORD = os.getenv("PASSWORD")

HOST = os.getenv("HOST", "").rstrip("/")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class Connection:
    """Класс для работы с API панели X-ray"""

    def __init__(
        self, login: str = LOGIN, password: str = PASSWORD, host: str = HOST
    ):
        self.login = login
        self.password = password
        self.host = host
        self.ses = requests.Session()
        self.token: Optional[str] = None

    def ensure_login(self) -> bool:
        """Проверка авторизации"""
        if self.token:
            return True
        return self.login_api()

    def login_api(self) -> bool:
        """Авторизация в API. Сохраняет токен в self.token."""
        data = {"username": self.login, "password": self.password}
        try:
            response = self.ses.post(
                f"{self.host}/login", json=data, timeout=10
            )
            response.raise_for_status()
        except requests.RequestException as e:
            logging.error("Ошибка сети при авторизации: %s", e)
            return False

        try:
            res_json = response.json()
        except json.JSONDecodeError:
            logging.error("Ответ от /login не JSON: %s", response.text)
            return False

        if res_json.get("success") is True:
            self.token = res_json.get("token")
            logging.info("Авторизация прошла успешно ✅")
            return True

        logging.error("Ошибка авторизации: %s", res_json)
        return False

    def list_inbounds(self) -> Dict[str, Any]:
        """Возвращает список подключений"""
        if not self.ensure_login():
            return {}
        try:
            response = self.ses.post(
                f"{self.host}/panel/inbound/list", json={}, timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error("Ошибка сети при запросе inbound list: %s", e)
            return {}

    def add_client(self, days: int) -> Optional[str]:
        """Создаёт нового клиента с UUID"""
        if not self.ensure_login():
            logging.error("Авторизация не удалась — клиент не создан")
            return None

        client_uuid = str(uuid.uuid4())
        expiry_time = int(
            (
                datetime.datetime.utcnow() + datetime.timedelta(days=days)
            ).timestamp()
            * 1000
        )
        data = {
            "id": 1,
            "settings": {
                "clients": [
                    {
                        "id": client_uuid,
                        "email": "ignore_this",
                        "enable": True,
                        "expiryTime": expiry_time,
                        "limitIp": 3,
                        "totalGB": 0,
                        "alterId": 0,
                    }
                ]
            },
        }

        logging.info("Добавляется клиент с UUID: %s", client_uuid)
        try:
            response = self.ses.post(
                f"{self.host}/addClient", json=data, timeout=10
            )
            if response.status_code == 200:
                logging.info("Клиент успешно создан ✅")
                return client_uuid
            logging.error("Ошибка при создании клиента: %s", response.text)
        except requests.RequestException as e:
            logging.error("Сетевая ошибка при создании клиента: %s", e)
        return None

    def generate_link(self, client_id: str, user_id: Union[int, str]) -> str:
        """Генерирует ссылку для подключения"""
        if not self.ensure_login():
            return "❌ Ошибка авторизации при генерации ссылки"

        data = self.list_inbounds()
        if not data or "obj" not in data or not data["obj"]:
            return "❌ Не удалось получить inbound"

        inbound = data["obj"][0]
        stream = json.loads(inbound.get("streamSettings", "{}"))
        tcp = stream.get("network", "tcp")
        reality = stream.get("security", "reality")

        link = (
            f"vless://{client_id}@vpn-x3.ru:50888/?type={tcp}"
            f"&security={reality}&fp=chrome"
            f"&pbk=T_95HnSovtH9WNr_XfaJ9iL7xnwp96p8E2A8Q3_t_xk"
            f"&sni=microsoft.com&sid=24705084&spx=%2F#VPN-X3-{user_id}"
        )
        return link

    def print_inbounds(self) -> None:
        """Выводит список подключений"""
        if not self.ensure_login():
            return
        data = self.list_inbounds()
        logging.info(
            "Inbounds:\n%s", json.dumps(data, indent=2, ensure_ascii=False)
        )

    def create_inbound(
        self, user_id: int, is_trial: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Создаёт новое подключение для пользователя"""
        if not self.ensure_login():
            return None

        existing = self.list_inbounds().get("obj", [])
        used_ports = {
            int(inb.get("port"))
            for inb in existing
            if str(inb.get("port", "")).isdigit()
        }

        # Поиск свободного порта
        for _ in range(20):
            port = random.randint(50102, 52999)
            if port not in used_ports:
                break
        else:
            logging.error("Не удалось найти свободный порт после 20 попыток")
            return None

        client_uuid = str(uuid.uuid4())
        sub_id = "".join(
            random.choices(string.ascii_lowercase + string.digits, k=16)
        )
        remark = f"user_{user_id}_prob" if is_trial else f"user_{user_id}"
        email = f"trial_{user_id}" if is_trial else str(user_id)

        settings = {
            "clients": [
                {
                    "id": client_uuid,
                    "flow": "",
                    "email": email,
                    "limitIp": 0,
                    "totalGB": 0,
                    "expiryTime": 0,
                    "enable": True,
                    "tgId": "",
                    "subId": sub_id,
                    "reset": 0,
                }
            ],
            "decryption": "none",
            "fallbacks": [],
        }

        stream_settings = {
            "network": "tcp",
            "security": "reality",
            "externalProxy": [],
            "realitySettings": {
                "show": False,
                "xver": 0,
                "dest": "yahoo.com:443",
                "serverNames": ["yahoo.com", "www.yahoo.com"],
                "privateKey": "wIc7zBUiTXBGxM7S7wl0nCZ663OAvzTDNqS7-bsxV3A",
                "minClient": "",
                "maxClient": "",
                "maxTimediff": 0,
                "shortIds": [
                    "47595474",
                    "7a5e30",
                    "810c1efd750030e8",
                    "99",
                    "9c19c134b8",
                    "35fd",
                    "2409c639a707b4",
                    "c98fc6b39f45",
                ],
                "settings": {
                    "publicKey": "2UqLjQFhlvLcY7VzaKRotIDQFOgAJe1dYD1njigp9wk",
                    "fingerprint": "chrome",
                    "serverName": "",
                    "spiderX": "/",
                },
            },
            "tcpSettings": {
                "acceptProxyProtocol": False,
                "header": {"type": "none"},
            },
        }

        sniffing = {
            "enabled": False,
            "destOverride": ["http", "tls", "quic", "fakedns"],
            "metadataOnly": False,
            "routeOnly": False,
        }

        allocate = {"strategy": "always", "refresh": 5, "concurrency": 3}

        payload = {
            "up": 0,
            "down": 0,
            "total": 0,
            "remark": remark,
            "enable": True,
            "expiryTime": 0,
            "listen": "",
            "port": port,
            "protocol": "vless",
            "settings": json.dumps(settings),
            "streamSettings": json.dumps(stream_settings),
            "sniffing": json.dumps(sniffing),
            "allocate": json.dumps(allocate),
        }

        try:
            response = self.ses.post(
                f"{self.host}/panel/api/inbounds/add", json=payload, timeout=10
            )
            if response.status_code == 200:
                logging.info(
                    "Inbound создан для user_id=%s на порту %s ✅",
                    user_id,
                    port,
                )
                return {"uuid": client_uuid, "port": port}
            logging.error(
                "Ошибка создания inbound: %s — %s",
                response.status_code,
                response.text,
            )
        except requests.RequestException as e:
            logging.error("Сетевая ошибка при создании inbound: %s", e)
        return None

    def update_client(self, client_uuid: str, days: int = 30) -> bool:
        """Продлевает существующего клиента на days дней."""
        if not self.ensure_login():
            return False

        expiry_time = int(
            (
                datetime.datetime.utcnow() + datetime.timedelta(days=days)
            ).timestamp()
            * 1000
        )
        data = {
            "uuid": client_uuid,
            "expiryTime": expiry_time,
            "totalGB": 0,
            "enable": True,
        }
        try:
            response = self.ses.post(
                f"{self.host}/panel/api/client/update", json=data, timeout=10
            )
            if response.status_code == 200:
                logging.info(
                    "Клиент %s продлён до %s ✅", client_uuid, expiry_time
                )
                return True
            logging.error("Ошибка продления клиента: %s", response.text)
        except requests.RequestException as e:
            logging.error("Сетевая ошибка при продлении клиента: %s", e)
        return False


if __name__ == "__main__":
    x3 = Connection()
    x3.print_inbounds()
