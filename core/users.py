# core/users.py
import datetime
import hashlib
import os
import time
<<<<<<< HEAD
from dotenv import load_dotenv
from ydb import Driver
from ydb.credentials import AccessTokenCredentials
=======
import uuid
from dotenv import load_dotenv
from ydb import Driver
from ydb.credentials import AccessTokenCredentials
from flask_login import UserMixin
>>>>>>> 153e734 (Add auth)

load_dotenv()

# ===== КЛАСС ПОЛЬЗОВАТЕЛЯ ДЛЯ FLASK-LOGIN =====

<<<<<<< HEAD
=======

class User(UserMixin):
    def __init__(self, user_id, username, password_hash, created_at, email=None):
        self.id = user_id
        self.user_id = user_id
        self.username = username
        self.password_hash = password_hash
        self.created_at = created_at
        self.email = email  # пока не используем, но для будущего

    def get_id(self):
        return str(self.user_id)

    @property
    def is_active(self):
        return True


>>>>>>> 153e734 (Add auth)
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
<<<<<<< HEAD
        """Создаёт сессию с .create() и повторными попытками."""
=======
>>>>>>> 153e734 (Add auth)
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
<<<<<<< HEAD
=======
        try:
            session.execute_scheme(
                "CREATE INDEX username_idx ON users (username);")
            print("✅ Индекс на username создан")
        except Exception:
            pass
>>>>>>> 153e734 (Add auth)

    def _hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()

<<<<<<< HEAD
    def create_user(self, username, password):
=======
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

    def create_user(self, username, password, email=None):
>>>>>>> 153e734 (Add auth)
        session_check = self._get_session()
        if self._user_exists(session_check, username):
            raise Exception("Пользователь с таким именем уже существует")

<<<<<<< HEAD
        session_insert = self._get_session()
=======
        user_id = str(uuid.uuid4())
        session_insert = self._get_session()
        # Пока email не используем, но поле зарезервируем
>>>>>>> 153e734 (Add auth)
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
                "$user_id": user_id,
                "$username": username,
                "$password_hash": self._hash_password(password),
                "$created_at": datetime.datetime.now()
            }
        )
        tx.commit()
<<<<<<< HEAD
        print(f"✅ Пользователь {username} создан")
=======
        print(f"✅ Пользователь {username} создан с ID {user_id}")
        return user_id
>>>>>>> 153e734 (Add auth)

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
<<<<<<< HEAD
        return rows[0] if rows else None
=======
        if rows:
            row = rows[0]
            return User(
                user_id=row['user_id'],
                username=row['username'],
                password_hash=row['password_hash'],
                created_at=row['created_at']
            )
        return None

    def get_user_by_id(self, user_id):
        session = self._get_session()
        query = """
            DECLARE $user_id AS Text;
            SELECT user_id, username, password_hash, created_at
            FROM users
            WHERE user_id = $user_id;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        result = tx.execute(prepared, {"$user_id": user_id})
        rows = result[0].rows
        if rows:
            row = rows[0]
            return User(
                user_id=row['user_id'],
                username=row['username'],
                password_hash=row['password_hash'],
                created_at=row['created_at']
            )
        return None
>>>>>>> 153e734 (Add auth)

    def verify_user(self, username, password):
        user = self.get_user(username)
        if user:
            return user.password_hash == self._hash_password(password)
        return False

    def close(self):
        self.driver.stop()
