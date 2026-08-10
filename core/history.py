# core/history.py
import datetime
import os
import time
from ydb import Driver
from ydb.credentials import AccessTokenCredentials
from dotenv import load_dotenv

load_dotenv()
debug = os.getenv('DEBUG', '').lower() in ('true', '1', 'yes')


class MessageHistory:
    """
    Работа с историей сообщений в YDB.
    Таблица: messages (
        user_id Text,
        message_id Uint64,
        session_id Text,
        role Text,
        content Text,
        timestamp Timestamp,
        PRIMARY KEY (user_id, message_id)
    )
    Индексы: (user_id, session_id), (user_id, timestamp)
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

    @staticmethod
    def _parse_timestamp(ts):
        if ts is None:
            return None
        if isinstance(ts, datetime.datetime):
            return ts
        if isinstance(ts, int):
            return datetime.datetime.fromtimestamp(ts / 1_000_000)
        if isinstance(ts, str):
            try:
                return datetime.datetime.fromisoformat(ts)
            except ValueError:
                return datetime.datetime.utcnow()
        return datetime.datetime.utcnow()

    def _get_next_message_id(self, user_id):
        session = self._get_session()
        query = """
            DECLARE $user_id AS Text;
            SELECT MAX(message_id) as max_id FROM messages WHERE user_id = $user_id;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        result = tx.execute(prepared, {"$user_id": user_id})
        max_id = None
        if result[0].rows:
            max_id = result[0].rows[0]['max_id']
        if max_id is None:
            return 1
        return max_id + 1

    def save_message(self, user_id, session_id, role, content, timestamp=None):
        if timestamp is None:
            timestamp = datetime.datetime.utcnow()
        elif isinstance(timestamp, str):
            try:
                timestamp = datetime.datetime.fromisoformat(timestamp)
            except ValueError:
                timestamp = datetime.datetime.utcnow()
        elif isinstance(timestamp, int):
            timestamp = datetime.datetime.fromtimestamp(timestamp / 1_000_000)

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
        if not history:
            return

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
            elif isinstance(ts, int):
                ts = datetime.datetime.fromtimestamp(ts / 1_000_000)

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
        session = self._get_session()
        tx = session.transaction()

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

    # ========== ИЗМЕНЁННЫЙ МЕТОД get_full_history (добавлен user_id) ==========
    def get_full_history(self, user_id, session_id=None):
        """
        Возвращает полную историю сообщений с полем user_id.
        Если session_id=None — возвращает все сообщения пользователя.
        Если session_id указан — только для этой сессии.
        """
        session = self._get_session()
        tx = session.transaction()

        if session_id is None:
            query = """
                DECLARE $user_id AS Text;
                SELECT user_id, role, content, timestamp FROM messages
                WHERE user_id = $user_id
                ORDER BY timestamp ASC;
            """
            prepared = session.prepare(query)
            result = tx.execute(prepared, {"$user_id": user_id})
        else:
            query = """
                DECLARE $user_id AS Text;
                DECLARE $session_id AS Text;
                SELECT user_id, role, content, timestamp FROM messages
                WHERE user_id = $user_id AND session_id = $session_id
                ORDER BY timestamp ASC;
            """
            prepared = session.prepare(query)
            result = tx.execute(
                prepared, {"$user_id": user_id, "$session_id": session_id})

        history = []
        for row in result[0].rows:
            ts = self._parse_timestamp(row['timestamp'])
            history.append({
                "user_id": row['user_id'],          # добавлено поле user_id
                "role": row['role'],
                "content": row['content'],
                "timestamp": ts.isoformat() if ts else None
            })
        return history
    # ====================================================================

    def get_last_message(self, user_id, session_id):
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
            ts = self._parse_timestamp(row['timestamp'])
            return {
                "role": row['role'],
                "content": row['content'],
                "timestamp": ts.isoformat() if ts else None
            }
        return None

    def clear_history(self, user_id, session_id):
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

    # ========== МЕТОД ДЛЯ УДАЛЕНИЯ ВСЕХ СООБЩЕНИЙ ПОЛЬЗОВАТЕЛЯ ==========
    def delete_user_history(self, user_id: str) -> bool:
        """Удаляет все сообщения пользователя из таблицы messages."""
        session = self._get_session()
        query = """
            DECLARE $user_id AS Text;
            DELETE FROM messages WHERE user_id = $user_id;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        tx.execute(prepared, {"$user_id": user_id})
        tx.commit()
        if debug:
            print(f"✅ История сообщений для пользователя {user_id} удалена")
        return True

    def close(self):
        self.driver.stop()


class PendingQuestions:
    """
    Работа с неотвеченными вопросами в YDB.
    Таблица: pending_questions (
        id Text,
        session_id Text,
        user_id Text,
        question_text Text,
        timestamp Timestamp,
        status Text,
        error_reason Text,
        PRIMARY KEY (session_id, id)
    )
    Индексы: (status), (session_id, status)
    """

    def __init__(self):
        self.token_file = os.getenv("YDB_TOKEN_FILE", "/home/itshark/my_token")
        self.endpoint = os.getenv(
            "YDB_ENDPOINT", "grpcs://ydb.serverless.yandexcloud.net:2135")
        self.database = os.getenv(
            "YDB_DATABASE", "/ru-central1/b1gddu24s17cjrnssgpj/etn4rgl61kgjokonk8pb")

        with open(self.token_file, "r") as f:
            token = f.read().strip()

        self._last_cleanup = None  # троттлинг ленивой очистки

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
        try:
            session.execute_scheme("""
                CREATE TABLE pending_questions (
                    id Text,
                    session_id Text,
                    user_id Text,
                    question_text Text,
                    timestamp Timestamp,
                    status Text,
                    error_reason Text,
                    PRIMARY KEY (session_id, id)
                )
            """)
        except Exception:
            pass
        try:
            session.execute_scheme("""
                CREATE INDEX idx_pending_status ON pending_questions (status)
            """)
        except Exception:
            pass
        try:
            session.execute_scheme("""
                CREATE INDEX idx_session_status ON pending_questions (session_id, status)
            """)
        except Exception:
            pass

    @staticmethod
    def _parse_timestamp(ts):
        if ts is None:
            return None
        if isinstance(ts, datetime.datetime):
            return ts
        if isinstance(ts, int):
            return datetime.datetime.fromtimestamp(ts / 1_000_000)
        if isinstance(ts, str):
            try:
                return datetime.datetime.fromisoformat(ts)
            except ValueError:
                pass
        return datetime.datetime.utcnow()

    def _lazy_cleanup(self, hours=24):
        """Ленивая очистка старых записей: не чаще раза в час."""
        now = time.time()
        if self._last_cleanup is not None and (now - self._last_cleanup) < 3600:
            return
        try:
            self.cleanup_old_pending(hours)
        except Exception as e:
            print(f"[PENDING] cleanup пропущен: {e}")
        finally:
            self._last_cleanup = now

    def _record_exists(self, session_id, qid):
        session = self._get_session()
        query = """
            DECLARE $session_id AS Optional<Text>;
            DECLARE $id AS Optional<Text>;
            SELECT id FROM pending_questions
            WHERE session_id = $session_id AND id = $id LIMIT 1;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        result = tx.execute(
            prepared, {"$session_id": session_id, "$id": qid})
        return bool(result[0].rows)

    def save_pending_question(self, session_id, user_id, question_text, qid,
                              timestamp=None, status="pending", error_reason=None):
        """Вставляет запись в YDB. Если id уже существует — пропускает (INSERT не перезаписывает).
        Возвращает True, если запись вставлена, False если уже существовала."""
        if timestamp is None:
            timestamp = datetime.datetime.utcnow()
        else:
            timestamp = self._parse_timestamp(timestamp)

        if self._record_exists(session_id, qid):
            return False

        session = self._get_session()
        query = """
            DECLARE $id AS Optional<Text>;
            DECLARE $session_id AS Optional<Text>;
            DECLARE $user_id AS Optional<Text>;
            DECLARE $question_text AS Optional<Text>;
            DECLARE $timestamp AS Optional<Timestamp>;
            DECLARE $status AS Optional<Text>;
            DECLARE $error_reason AS Optional<Text>;
            INSERT INTO pending_questions
                (id, session_id, user_id, question_text, timestamp, status, error_reason)
            VALUES
                ($id, $session_id, $user_id, $question_text, $timestamp, $status, $error_reason);
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        tx.execute(prepared, {
            "$id": qid,
            "$session_id": session_id,
            "$user_id": user_id,
            "$question_text": question_text,
            "$timestamp": timestamp,
            "$status": status,
            "$error_reason": error_reason,
        })
        tx.commit()
        return True

    def get_pending_question(self, session_id):
        """Последний неотвеченный вопрос сессии (status='pending')."""
        self._lazy_cleanup()
        session = self._get_session()
        query = """
            DECLARE $session_id AS Optional<Text>;
            SELECT id, session_id, user_id, question_text, timestamp, status, error_reason
            FROM pending_questions
            WHERE session_id = $session_id AND status = 'pending'
            ORDER BY timestamp DESC LIMIT 1;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        result = tx.execute(prepared, {"$session_id": session_id})
        if result[0].rows:
            row = result[0].rows[0]
            return {
                "id": row['id'],
                "session_id": row['session_id'],
                "user_id": row['user_id'],
                "question_text": row['question_text'],
                "timestamp": self._parse_timestamp(row['timestamp']).isoformat()
                if row['timestamp'] else None,
                "status": row['status'],
                "error_reason": row['error_reason'],
            }
        return None

    def resolve_pending_question(self, session_id, qid, reason=None):
        """Помечает конкретную запись как resolved. reason=... дополнительно пишет причину."""
        session = self._get_session()
        query = """
            DECLARE $session_id AS Optional<Text>;
            DECLARE $id AS Optional<Text>;
            DECLARE $reason AS Optional<Text>;
            UPDATE pending_questions
            SET status = 'resolved', error_reason = $reason
            WHERE session_id = $session_id AND id = $id;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        tx.execute(prepared, {
            "$session_id": session_id,
            "$id": qid,
            "$reason": reason,
        })
        tx.commit()

    def set_error_reason(self, session_id, qid, reason):
        session = self._get_session()
        query = """
            DECLARE $session_id AS Optional<Text>;
            DECLARE $id AS Optional<Text>;
            DECLARE $reason AS Optional<Text>;
            UPDATE pending_questions
            SET error_reason = $reason
            WHERE session_id = $session_id AND id = $id;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        tx.execute(prepared, {
            "$session_id": session_id,
            "$id": qid,
            "$reason": reason,
        })
        tx.commit()

    def cleanup_old_pending(self, hours=24):
        """Удаляет старые записи: и resolved, и зависшие pending старше hours часов."""
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
        session = self._get_session()
        query = """
            DECLARE $cutoff AS Optional<Timestamp>;
            DELETE FROM pending_questions
            WHERE timestamp < $cutoff;
        """
        prepared = session.prepare(query)
        tx = session.transaction()
        tx.execute(prepared, {"$cutoff": cutoff})
        tx.commit()

    def close(self):
        self.driver.stop()
