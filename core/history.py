# core/history.py
import datetime
import os
import time
from ydb import Driver
from ydb.credentials import AccessTokenCredentials


class MessageHistory:
    """
    Работа с историей сообщений в YDB.
    Таблица: messages (
        user_id Text,
        message_id Uint64,        -- автоинкремент в рамках пользователя
        session_id Text,
        role Text,
        content Text,
        timestamp Timestamp,
        PRIMARY KEY (user_id, message_id)
    )
    Индексы:
        - (user_id, session_id)   для быстрого поиска сессий
        - (user_id, timestamp)    для сортировки по времени
    """

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
        self._ensure_table_exists()

    def _get_session(self):
        for attempt in range(3):
            try:
                return self.driver.table_client.session().create()
            except Exception as e:
                if attempt == 2:
                    raise
                time.sleep(0.5)

    def _ensure_table_exists(self):
        session = self._get_session()
        # Таблица
        try:
            session.execute_scheme("""
                CREATE TABLE messages (
                    user_id Text,
                    message_id Uint64,
                    session_id Text,
                    role Text,
                    content Text,
                    timestamp Timestamp,
                    PRIMARY KEY (user_id, message_id)
                )
            """)
        except Exception:
            pass
        # Индексы
        try:
            session.execute_scheme("""
                CREATE INDEX idx_messages_user_session ON messages (user_id, session_id)
            """)
        except Exception:
            pass
        try:
            session.execute_scheme("""
                CREATE INDEX idx_messages_user_timestamp ON messages (user_id, timestamp)
            """)
        except Exception:
            pass

    def _get_next_message_id(self, user_id):
        """Возвращает следующий message_id для пользователя (MAX + 1)."""
        session = self._get_session()
        query = """
            DECLARE $user_id AS Text;
            SELECT MAX(message_id) as max_id FROM messages WHERE user_id = $user_id;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        result = tx.execute(prepared, {"$user_id": user_id})
        max_id = result[0].rows[0]['max_id'] if result[0].rows else 0
        return max_id + 1

    def save_message(self, user_id, session_id, role, content, timestamp=None):
        """Сохраняет одно сообщение, автоматически назначая message_id."""
        if timestamp is None:
            timestamp = datetime.datetime.utcnow()
        elif isinstance(timestamp, str):
            try:
                timestamp = datetime.datetime.fromisoformat(timestamp)
            except ValueError:
                timestamp = datetime.datetime.utcnow()

        message_id = self._get_next_message_id(user_id)

        session = self._get_session()
        query = """
            DECLARE $user_id AS Text;
            DECLARE $message_id AS Uint64;
            DECLARE $session_id AS Text;
            DECLARE $role AS Text;
            DECLARE $content AS Text;
            DECLARE $timestamp AS Timestamp;
            INSERT INTO messages (user_id, message_id, session_id, role, content, timestamp)
            VALUES ($user_id, $message_id, $session_id, $role, $content, $timestamp);
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        tx.execute(prepared, {
            "$user_id": user_id,
            "$message_id": message_id,
            "$session_id": session_id,
            "$role": role,
            "$content": content,
            "$timestamp": timestamp
        })
        tx.commit()

    def save_history(self, user_id, session_id, history):
        """Сохраняет несколько сообщений одной транзакцией."""
        if not history:
            return

        # Получаем начальный message_id
        message_id = self._get_next_message_id(user_id)

        session = self._get_session()
        query = """
            DECLARE $user_id AS Text;
            DECLARE $message_id AS Uint64;
            DECLARE $session_id AS Text;
            DECLARE $role AS Text;
            DECLARE $content AS Text;
            DECLARE $timestamp AS Timestamp;
            INSERT INTO messages (user_id, message_id, session_id, role, content, timestamp)
            VALUES ($user_id, $message_id, $session_id, $role, $content, $timestamp);
        """
        prepared = session.prepare(query)
        tx = session.transaction()

        for msg in history:
            role = msg.get("role")
            content = msg.get("content")
            ts = msg.get("timestamp")
            if ts is None:
                ts = datetime.datetime.utcnow()
            elif isinstance(ts, str):
                try:
                    ts = datetime.datetime.fromisoformat(ts)
                except ValueError:
                    ts = datetime.datetime.utcnow()

            tx.execute(prepared, {
                "$user_id": user_id,
                "$message_id": message_id,
                "$session_id": session_id,
                "$role": role,
                "$content": content,
                "$timestamp": ts
            })
            message_id += 1
        tx.commit()

    def get_markers(self, user_id, session_id):
        """Возвращает первое, среднее (по времени) и последнее сообщение."""
        session = self._get_session()
        tx = session.transaction()

        # Первое
        q1 = """
            DECLARE $user_id AS Text;
            DECLARE $session_id AS Text;
            SELECT role, content FROM messages
            WHERE user_id = $user_id AND session_id = $session_id
            ORDER BY timestamp ASC LIMIT 1;
        """
        p1 = session.prepare(q1)
        r1 = tx.execute(p1, {"$user_id": user_id, "$session_id": session_id})
        first = r1[0].rows[0] if r1[0].rows else None

        # Последнее
        q2 = """
            DECLARE $user_id AS Text;
            DECLARE $session_id AS Text;
            SELECT role, content FROM messages
            WHERE user_id = $user_id AND session_id = $session_id
            ORDER BY timestamp DESC LIMIT 1;
        """
        p2 = session.prepare(q2)
        r2 = tx.execute(p2, {"$user_id": user_id, "$session_id": session_id})
        last = r2[0].rows[0] if r2[0].rows else None

        # Количество и среднее
        q3 = """
            DECLARE $user_id AS Text;
            DECLARE $session_id AS Text;
            SELECT COUNT(*) as cnt FROM messages
            WHERE user_id = $user_id AND session_id = $session_id;
        """
        p3 = session.prepare(q3)
        r3 = tx.execute(p3, {"$user_id": user_id, "$session_id": session_id})
        cnt = r3[0].rows[0]['cnt'] if r3[0].rows else 0

        middle = None
        if cnt > 0:
            offset = cnt // 2
            q4 = """
                DECLARE $user_id AS Text;
                DECLARE $session_id AS Text;
                DECLARE $offset AS Uint64;
                SELECT role, content FROM messages
                WHERE user_id = $user_id AND session_id = $session_id
                ORDER BY timestamp ASC LIMIT 1 OFFSET $offset;
            """
            p4 = session.prepare(q4)
            r4 = tx.execute(
                p4, {"$user_id": user_id, "$session_id": session_id, "$offset": offset})
            middle = r4[0].rows[0] if r4[0].rows else None

        # Собираем, исключая дубли
        markers = []
        if first:
            markers.append(
                {"role": first['role'], "content": first['content']})
        if middle and middle != first:
            markers.append(
                {"role": middle['role'], "content": middle['content']})
        if last and last != first and last != middle:
            markers.append({"role": last['role'], "content": last['content']})
        return markers

    def get_full_history(self, user_id, session_id):
        """Возвращает полную историю (отсортированную по времени)."""
        session = self._get_session()
        query = """
            DECLARE $user_id AS Text;
            DECLARE $session_id AS Text;
            SELECT role, content, timestamp FROM messages
            WHERE user_id = $user_id AND session_id = $session_id
            ORDER BY timestamp ASC;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        result = tx.execute(
            prepared, {"$user_id": user_id, "$session_id": session_id})
        history = []
        for row in result[0].rows:
            history.append({
                "role": row['role'],
                "content": row['content'],
                "timestamp": row['timestamp'].isoformat()
            })
        return history

    def get_last_message(self, user_id, session_id):
        """Возвращает последнее сообщение или None."""
        session = self._get_session()
        query = """
            DECLARE $user_id AS Text;
            DECLARE $session_id AS Text;
            SELECT role, content, timestamp FROM messages
            WHERE user_id = $user_id AND session_id = $session_id
            ORDER BY timestamp DESC LIMIT 1;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        result = tx.execute(
            prepared, {"$user_id": user_id, "$session_id": session_id})
        if result[0].rows:
            row = result[0].rows[0]
            return {"role": row['role'], "content": row['content'], "timestamp": row['timestamp'].isoformat()}
        return None

    def clear_history(self, user_id, session_id):
        """Удаляет все сообщения сессии."""
        session = self._get_session()
        query = """
            DECLARE $user_id AS Text;
            DECLARE $session_id AS Text;
            DELETE FROM messages
            WHERE user_id = $user_id AND session_id = $session_id;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        tx.execute(prepared, {"$user_id": user_id, "$session_id": session_id})
        tx.commit()
