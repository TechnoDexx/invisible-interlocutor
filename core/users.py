# core/users.py
import datetime
import hashlib
import os
from dotenv import load_dotenv
from ydb import Driver
from ydb.credentials import AccessTokenCredentials

load_dotenv()

class Users:
    def __init__(self):
        """Инициализация: загружает параметры из .env и подключается к YDB."""
        self.token_file = os.getenv("YDB_TOKEN_FILE", "/home/itshark/my_token")
        self.endpoint = os.getenv("YDB_ENDPOINT", "grpcs://ydb.serverless.yandexcloud.net:2135")
        self.database = os.getenv("YDB_DATABASE", "/ru-central1/b1gddu24s17cjrnssgpj/etn4rgl61kgjokonk8pb")

        with open(self.token_file, "r") as f:
            token = f.read().strip()

        self.driver = Driver(
            endpoint=self.endpoint,
            database=self.database,
            credentials=AccessTokenCredentials(token)
        )
        self.driver.wait(timeout=10)
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        session = self.driver.table_client.session().create()
        try:
            session.execute_scheme("""
                CREATE TABLE users (
                    user_id Text,
                    username Text,
                    password_hash Text,
                    created_at Timestamp,
                    PRIMARY KEY (user_id)
                )
            """)
            print("✅ Таблица users создана")
        except Exception:
            pass  # таблица уже существует
        finally:
            session.close()

    def _hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()

    def create_user(self, username, password):
        session = self.driver.table_client.session().create()
        query = """
            DECLARE $user_id AS Text;
            DECLARE $username AS Text;
            DECLARE $password_hash AS Text;
            DECLARE $created_at AS Timestamp;

            UPSERT INTO users (user_id, username, password_hash, created_at)
            VALUES ($user_id, $username, $password_hash, $created_at);
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        tx.execute(
            prepared,
            {
                "$user_id": username,
                "$username": username,
                "$password_hash": self._hash_password(password),
                "$created_at": datetime.datetime.now()
            }
        )
        tx.commit()
        session.close()
        print(f"✅ Пользователь {username} создан")

    def get_user(self, username):
        session = self.driver.table_client.session().create()
        query = """
            DECLARE $username AS Text;
            SELECT user_id, username, password_hash, created_at
            FROM users
            WHERE username = $username;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        result = tx.execute(prepared, {"$username": username})
        rows = result[0].rows
        session.close()
        return rows[0] if rows else None

    def verify_user(self, username, password):
        user = self.get_user(username)
        if user:
            return user["password_hash"] == self._hash_password(password)
        return False

    def close(self):
        self.driver.stop()