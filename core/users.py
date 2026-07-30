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
    def __init__(self, user_id, username, password_hash, created_at, email=None, email_verified=False):
        self.id = user_id
        self.user_id = user_id
        self.username = username
        self.password_hash = password_hash
        self.created_at = created_at
        self.email = email
        self.email_verified = email_verified

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
        # Создание таблицы, если её нет
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

        # Индекс по username
        try:
            session.execute_scheme(
                "CREATE INDEX username_idx ON users (username);")
            if debug:
                print("✅ Индекс на username создан")
        except Exception as e:
            if debug:
                print("ℹ️ Индекс уже существует (или ошибка):", e)

        # Добавляем колонки, если их нет
        for col_name, col_type in [
            ("email", "Text"),
            ("email_verified", "Bool"),
            ("verification_token", "Text"),
            ("verification_token_expires", "Timestamp"),
            ("reset_token", "Text"),
            ("reset_token_expires", "Timestamp"),
        ]:
            try:
                session.execute_scheme(
                    f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                if debug:
                    print(f"✅ Колонка {col_name} добавлена")
            except Exception as e:
                if debug:
                    print(
                        f"ℹ️ Колонка {col_name} уже существует или ошибка:", e)

    def _hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()

    def _user_exists(self, session, username):
        query = """
            DECLARE $username AS Text;
            SELECT user_id FROM users WHERE username = $username;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        result = tx.execute(prepared, {"$username": username})
        exists = len(result[0].rows) > 0
        if debug:
            print(
                f"🔍 Проверка существования пользователя {username}: {'найден' if exists else 'не найден'}")
        return exists

    def create_user(self, username, password, email=None):
        session_check = self._get_session()
        if self._user_exists(session_check, username):
            raise Exception("Пользователь с таким именем уже существует")

        user_id = str(uuid.uuid4())
        session_insert = self._get_session()
        query = """
            DECLARE $user_id AS Text;
            DECLARE $username AS Text;
            DECLARE $password_hash AS Text;
            DECLARE $created_at AS Timestamp;
            DECLARE $email AS Text;
            DECLARE $email_verified AS Bool;
            UPSERT INTO users (user_id, username, password_hash, created_at, email, email_verified)
            VALUES ($user_id, $username, $password_hash, $created_at, $email, $email_verified);
        """
        prepared = session_insert.prepare(query)
        tx = session_insert.transaction()
        tx.execute(prepared, {
            "$user_id": user_id,
            "$username": username,
            "$password_hash": self._hash_password(password),
            "$created_at": datetime.datetime.now(),
            "$email": email,
            "$email_verified": False
        })
        tx.commit()
        if debug:
            print(f"✅ Пользователь {username} создан с ID {user_id}")
        return user_id

    def get_user(self, username):
        session = self._get_session()
        query = """
            DECLARE $username AS Text;
            SELECT user_id, username, password_hash, created_at, email, email_verified
            FROM users WHERE username = $username;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        result = tx.execute(prepared, {"$username": username})
        if result[0].rows:
            row = result[0].rows[0]
            if debug:
                print(f"✅ Пользователь {username} найден")
            return User(
                user_id=row['user_id'],
                username=row['username'],
                password_hash=row['password_hash'],
                created_at=row['created_at'],
                email=row.get('email'),
                email_verified=row.get('email_verified', False)
            )
        if debug:
            print(f"❌ Пользователь {username} не найден")
        return None

    def get_user_by_id(self, user_id):
        session = self._get_session()
        query = """
            DECLARE $user_id AS Text;
            SELECT user_id, username, password_hash, created_at, email, email_verified
            FROM users WHERE user_id = $user_id;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        result = tx.execute(prepared, {"$user_id": user_id})
        if result[0].rows:
            row = result[0].rows[0]
            if debug:
                print(
                    f"✅ Пользователь с ID {user_id} найден: {row['username']}")
            return User(
                user_id=row['user_id'],
                username=row['username'],
                password_hash=row['password_hash'],
                created_at=row['created_at'],
                email=row.get('email'),
                email_verified=row.get('email_verified', False)
            )
        if debug:
            print(f"❌ Пользователь с ID {user_id} не найден")
        return None

    def get_user_by_email(self, email):
        """Возвращает пользователя по email."""
        session = self._get_session()
        query = """
            DECLARE $email AS Text;
            SELECT user_id, username, password_hash, created_at, email, email_verified
            FROM users WHERE email = $email;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        result = tx.execute(prepared, {"$email": email})
        if result[0].rows:
            row = result[0].rows[0]
            if debug:
                print(
                    f"✅ Пользователь с email {email} найден: {row['username']}")
            return User(
                user_id=row['user_id'],
                username=row['username'],
                password_hash=row['password_hash'],
                created_at=row['created_at'],
                email=row.get('email'),
                email_verified=row.get('email_verified', False)
            )
        if debug:
            print(f"❌ Пользователь с email {email} не найден")
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

    # ---------- МЕТОДЫ ДЛЯ ПОДТВЕРЖДЕНИЯ EMAIL И ВОССТАНОВЛЕНИЯ ПАРОЛЯ ----------

    def set_verification_token(self, user_id, token, expires_hours=24):
        """Сохраняет токен подтверждения email и время его истечения."""
        expires_at = datetime.datetime.now() + datetime.timedelta(hours=expires_hours)
        session = self._get_session()
        query = """
            DECLARE $user_id AS Text;
            DECLARE $token AS Text;
            DECLARE $expires_at AS Timestamp;
            UPDATE users SET verification_token = $token, verification_token_expires = $expires_at
            WHERE user_id = $user_id;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        tx.execute(prepared, {"$user_id": user_id,
                   "$token": token, "$expires_at": expires_at})
        tx.commit()
        if debug:
            print(f"✅ Токен подтверждения сохранён для пользователя {user_id}")

    def verify_email_by_token(self, token):
        """Проверяет токен подтверждения и, если он действителен, подтверждает email."""
        session = self._get_session()
        # Находим пользователя по токену
        query_find = """
            DECLARE $token AS Text;
            SELECT user_id, email, verification_token_expires FROM users
            WHERE verification_token = $token;
        """
        prepared_find = session.prepare(query_find)
        tx = session.transaction()
        result = tx.execute(prepared_find, {"$token": token})
        if not result[0].rows:
            if debug:
                print("❌ Токен подтверждения не найден")
            return False, "Токен не найден"

        row = result[0].rows[0]
        user_id = row['user_id']
        expires_at = row.get('verification_token_expires')

        # Проверяем срок действия
        if expires_at and expires_at < datetime.datetime.now():
            if debug:
                print("❌ Токен подтверждения истёк")
            return False, "Срок действия токена истёк"

        # Подтверждаем email
        query_update = """
            DECLARE $user_id AS Text;
            UPDATE users SET email_verified = True, verification_token = NULL, verification_token_expires = NULL
            WHERE user_id = $user_id;
        """
        prepared_update = session.prepare(query_update)
        tx_update = session.transaction()
        tx_update.execute(prepared_update, {"$user_id": user_id})
        tx_update.commit()

        if debug:
            print(f"✅ Email подтверждён для пользователя {user_id}")
        return True, "Email успешно подтверждён"

    def set_reset_token(self, email, token, expires_hours=1):
        """Сохраняет токен сброса пароля для пользователя по email."""
        user = self.get_user_by_email(email)
        if not user:
            if debug:
                print(f"❌ Пользователь с email {email} не найден")
            return False, "Пользователь с таким email не найден"

        expires_at = datetime.datetime.now() + datetime.timedelta(hours=expires_hours)
        session = self._get_session()
        query = """
            DECLARE $user_id AS Text;
            DECLARE $token AS Text;
            DECLARE $expires_at AS Timestamp;
            UPDATE users SET reset_token = $token, reset_token_expires = $expires_at
            WHERE user_id = $user_id;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        tx.execute(prepared, {"$user_id": user.user_id,
                   "$token": token, "$expires_at": expires_at})
        tx.commit()
        if debug:
            print(f"✅ Токен сброса сохранён для пользователя {user.user_id}")
        return True, "Токен сброса отправлен на email"

    def reset_password_by_token(self, token, new_password):
        """Проверяет токен сброса и, если он действителен, меняет пароль."""
        session = self._get_session()
        # Находим пользователя по токену
        query_find = """
            DECLARE $token AS Text;
            SELECT user_id, reset_token_expires FROM users
            WHERE reset_token = $token;
        """
        prepared_find = session.prepare(query_find)
        tx = session.transaction()
        result = tx.execute(prepared_find, {"$token": token})
        if not result[0].rows:
            if debug:
                print("❌ Токен сброса не найден")
            return False, "Токен не найден"

        row = result[0].rows[0]
        user_id = row['user_id']
        expires_at = row.get('reset_token_expires')

        # Проверяем срок действия
        if expires_at and expires_at < datetime.datetime.now():
            if debug:
                print("❌ Токен сброса истёк")
            return False, "Срок действия токена истёк"

        # Обновляем пароль
        new_hash = self._hash_password(new_password)
        query_update = """
            DECLARE $user_id AS Text;
            DECLARE $new_hash AS Text;
            UPDATE users SET password_hash = $new_hash, reset_token = NULL, reset_token_expires = NULL
            WHERE user_id = $user_id;
        """
        prepared_update = session.prepare(query_update)
        tx_update = session.transaction()
        tx_update.execute(prepared_update, {
                          "$user_id": user_id, "$new_hash": new_hash})
        tx_update.commit()

        if debug:
            print(f"✅ Пароль обновлён для пользователя {user_id}")
        return True, "Пароль успешно изменён"

    def get_user_by_reset_token(self, token):
        """Возвращает пользователя по токену сброса пароля, если токен действителен."""
        session = self._get_session()
        query = """
            DECLARE $token AS Text;
            SELECT user_id, username, email FROM users
            WHERE reset_token = $token AND reset_token_expires > CURRENT_TIMESTAMP();
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        result = tx.execute(prepared, {"$token": token})
        if result[0].rows:
            row = result[0].rows[0]
            return self.get_user_by_id(row['user_id'])
        return None

    def close(self):
        self.driver.stop()
