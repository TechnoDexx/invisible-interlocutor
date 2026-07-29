# core/users.py
import datetime
import hashlib
import os
import time
import uuid
from dotenv import load_dotenv
from ydb import Driver
from ydb.credentials import AccessTokenCredentials
from flask_login import UserMixin

load_dotenv()

debug = os.getenv('DEBUG', '').lower() in ('true', '1', 'yes')


class User(UserMixin):
    def __init__(self, user_id, username, password_hash, created_at, email=None):
        self.id = user_id
        self.user_id = user_id
        self.username = username
        self.password_hash = password_hash
        self.created_at = created_at
        self.email = email

    def get_id(self):
        return str(self.user_id)

    @property
    def is_active(self):
        return True


class Users:
    def __init__(self):
        self.token_file = os.getenv("YDB_TOKEN_FILE", "/home/itshark/my_token")
        self.endpoint = os.getenv(
            "YDB_ENDPOINT", "grpcs://ydb.serverless.yandexcloud.net:2135")
        self.database = os.getenv(
            "YDB_DATABASE", "/ru-central1/b1gddu24s17cjrnssgpj/etn4rgl61kgjokonk8pb")

        if debug:
            print(
                f"🔧 Users init: endpoint={self.endpoint}, database={self.database}")

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
        for attempt in range(3):
            try:
                session = self.driver.table_client.session().create()
                if debug:
                    print("✅ Сессия YDB создана")
                return session
            except Exception as e:
                if debug:
                    print(
                        f"⚠️ Попытка {attempt+1} создания сессии не удалась: {e}")
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
            if debug:
                print("✅ Таблица users создана")
        except Exception as e:
            if debug:
                print("ℹ️ Таблица уже существует (или ошибка):", e)
        try:
            session.execute_scheme(
                "CREATE INDEX username_idx ON users (username);")
            if debug:
                print("✅ Индекс на username создан")
        except Exception as e:
            if debug:
                print("ℹ️ Индекс уже существует (или ошибка):", e)
        # Добавляем колонку email, если её нет
        try:
            session.execute_scheme("ALTER TABLE users ADD COLUMN email Text")
            if debug:
                print("✅ Колонка email добавлена в таблицу users")
        except Exception as e:
            if debug:
                print("ℹ️ Колонка email уже существует или ошибка:", e)

    def _hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()

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
        exists = len(rows) > 0
        if debug:
            print(
                f"🔍 Проверка существования пользователя {username}: {'найден' if exists else 'не найден'}")
        return exists

    def create_user(self, username, password, email=None):
        session_check = self._get_session()
        if self._user_exists(session_check, username):
            if debug:
                print(
                    f"❌ Попытка создать существующего пользователя {username}")
            raise Exception("Пользователь с таким именем уже существует")

        user_id = str(uuid.uuid4())
        session_insert = self._get_session()
        query = """
            DECLARE $user_id AS Text;
            DECLARE $username AS Text;
            DECLARE $password_hash AS Text;
            DECLARE $created_at AS Timestamp;
            DECLARE $email AS Text;

            UPSERT INTO users (user_id, username, password_hash, created_at, email)
            VALUES ($user_id, $username, $password_hash, $created_at, $email);
        """
        prepared = session_insert.prepare(query)
        tx = session_insert.transaction()
        tx.execute(
            prepared,
            {
                "$user_id": user_id,
                "$username": username,
                "$password_hash": self._hash_password(password),
                "$created_at": datetime.datetime.now(),
                "$email": email
            }
        )
        tx.commit()
        if debug:
            print(f"✅ Пользователь {username} создан с ID {user_id}")
        return user_id

    def get_user(self, username):
        if debug:
            print(f"🔍 Поиск пользователя по username: {username}")
        session = self._get_session()
        query = """
            DECLARE $username AS Text;
            SELECT user_id, username, password_hash, created_at, email
            FROM users
            WHERE username = $username;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        result = tx.execute(prepared, {"$username": username})
        rows = result[0].rows
        if rows:
            row = rows[0]
            if debug:
                print(f"✅ Пользователь {username} найден")
            return User(
                user_id=row['user_id'],
                username=row['username'],
                password_hash=row['password_hash'],
                created_at=row['created_at'],
                email=row.get('email')
            )
        if debug:
            print(f"❌ Пользователь {username} не найден")
        return None

    def get_user_by_id(self, user_id):
        if debug:
            print(f"🔍 Поиск пользователя по user_id: {user_id}")
        session = self._get_session()
        query = """
            DECLARE $user_id AS Text;
            SELECT user_id, username, password_hash, created_at, email
            FROM users
            WHERE user_id = $user_id;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        result = tx.execute(prepared, {"$user_id": user_id})
        rows = result[0].rows
        if rows:
            row = rows[0]
            if debug:
                print(
                    f"✅ Пользователь с ID {user_id} найден: {row['username']}")
            return User(
                user_id=row['user_id'],
                username=row['username'],
                password_hash=row['password_hash'],
                created_at=row['created_at'],
                email=row.get('email')
            )
        if debug:
            print(f"❌ Пользователь с ID {user_id} не найден")
        return None

    def verify_user(self, username, password):
        user = self.get_user(username)
        if user:
            valid = user.password_hash == self._hash_password(password)
            if debug:
                print(
                    f"🔐 Проверка пароля для {username}: {'успешно' if valid else 'неверный пароль'}")
            return valid
        return False

    def update_user_email(self, user_id, email):
        session = self._get_session()
        query = """
            DECLARE $user_id AS Text;
            DECLARE $email AS Text;
            UPDATE users SET email = $email WHERE user_id = $user_id;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        tx.execute(prepared, {"$user_id": user_id, "$email": email})
        tx.commit()
        if debug:
            print(f"✅ Email обновлён для пользователя {user_id}")

    def close(self):
        self.driver.stop()
