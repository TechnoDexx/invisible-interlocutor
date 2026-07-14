# core/users.py
import datetime
import hashlib
import os
import time
from dotenv import load_dotenv
from ydb import Driver
from ydb.credentials import AccessTokenCredentials

load_dotenv()


class Users:
    def __init__(self):
        self.token_file = os.getenv("YDB_TOKEN_FILE", "/home/itshark/my_token")
        self.endpoint = os.getenv(
            "YDB_ENDPOINT", "grpcs://ydb.serverless.yandexcloud.net:2135")
        self.database = os.getenv(
            "YDB_DATABASE", "/ru-central1/b1gddu24s17cjrnssgpj/etn4rgl61kgjokonk8pb")

        with open(self.token_file, "r") as f:
            token = f.read().strip()

        self.driver = Driver(
            endpoint=self.endpoint,
            database=self.database,
            credentials=AccessTokenCredentials(token)
        )
        self.driver.wait(timeout=10)
        time.sleep(1)
        self._ensure_table_exists()

    def _get_session(self):
        """Создаёт сессию с .create() и повторными попытками."""
        for attempt in range(3):
            try:
                session = self.driver.table_client.session().create()
                return session
            except Exception as e:
                if attempt == 2:
                    raise
                time.sleep(0.5)
        return None

    def _ensure_table_exists(self):
        session = self._get_session()
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
            pass

    def _hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()

    def create_user(self, username, password):
        session_check = self._get_session()
        if self._user_exists(session_check, username):
            raise Exception("Пользователь с таким именем уже существует")

        session_insert = self._get_session()
        query = """
            DECLARE $user_id AS Text;
            DECLARE $username AS Text;
            DECLARE $password_hash AS Text;
            DECLARE $created_at AS Timestamp;

            UPSERT INTO users (user_id, username, password_hash, created_at)
            VALUES ($user_id, $username, $password_hash, $created_at);
        """
        prepared = session_insert.prepare(query)
        tx = session_insert.transaction()
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
        print(f"✅ Пользователь {username} создан")

    def _user_exists(self, session, username):
        query = """
            DECLARE $username AS Text;
            SELECT user_id FROM users
            WHERE username = $username;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        result = tx.execute(prepared, {"$username": username})
        rows = result[0].rows
        return len(rows) > 0

    def get_user(self, username):
        session = self._get_session()
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
        return rows[0] if rows else None

    def verify_user(self, username, password):
        user = self.get_user(username)
        if user:
            return user["password_hash"] == self._hash_password(password)
        return False

    def close(self):
        self.driver.stop()
