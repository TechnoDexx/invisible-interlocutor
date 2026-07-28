import sys
import json
from datetime import datetime, timezone


class Session:
    """
    Управляет историей диалога: добавление, сохранение, загрузка, вывод.
    Поддерживает:
    - timestamp для каждого сообщения (ISO 8601, UTC)
    - user_id (может быть None для анонимных сессий)
    - обратную совместимость со старыми файлами (без timestamp и user_id)
    - метод get_context_markers() для «хитрого» восстановления контекста
    - _safe_input для работы в Docker/консоли
    - автоматическую привязку user_id при загрузке, если он установлен в сессии
    - флаг restoring для индикации процесса восстановления контекста
    """

    def __init__(self, filename=None, history=None, user_id=None):
        self.history = history if history is not None else []
        self.filename = filename
        self.user_id = user_id  # храним на уровне сессии
        self.restoring = False   # флаг восстановления контекста

    @staticmethod
    def _safe_input(prompt=""):
        """
        Безопасный ввод из консоли, работающий в Docker и без TTY.
        """
        if prompt:
            sys.stdout.write(prompt)
            sys.stdout.flush()
        raw = sys.stdin.buffer.readline()
        try:
            return raw.decode('utf-8').rstrip('\n')
        except UnicodeDecodeError:
            return raw.decode('utf-8', errors='replace').rstrip('\n')

    def add_user_message(self, text, user_id=None):
        if user_id is None:
            user_id = self.user_id
        self.history.append({
            "role": "user",
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "content": text
        })

    def add_assistant_message(self, text, user_id=None):
        if user_id is None:
            user_id = self.user_id
        self.history.append({
            "role": "assistant",
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "content": text
        })

    def set_user_id(self, user_id):
        self.user_id = user_id

    def set_restoring(self, value):
        self.restoring = bool(value)

    def assign_user_to_history(self, user_id):
        for msg in self.history:
            if msg.get("user_id") is None:
                msg["user_id"] = user_id
        self.user_id = user_id

    def clear(self):
        self.history = []

    def save(self, filename=None):
        if not self.history:
            print("История пуста, сохранять нечего.")
            return
        if filename is None:
            filename = self._safe_input(
                "Введите имя файла (с расширением): ").strip()
            if not filename:
                print("Имя файла не указано. Сохранение отменено.")
                return
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)
        print(f"История сохранена в {filename}")

    def load(self, filename=None):
        if filename is None:
            filename = self._safe_input(
                "Введите имя файла для загрузки: ").strip()
            if not filename:
                print("Имя файла не указано.")
                return
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"Файл '{filename}' не найден.")
            return
        except json.JSONDecodeError:
            print(f"Файл '{filename}' содержит некорректный JSON.")
            return
        if not isinstance(data, list):
            print("Данные в файле не являются списком.")
            return
        for i, msg in enumerate(data):
            if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
                print(
                    f"Сообщение #{i+1} имеет неверную структуру, загрузка прервана.")
                return
        # Добавляем отсутствующие поля для обратной совместимости
        for msg in data:
            if "timestamp" not in msg:
                msg["timestamp"] = None
            if "user_id" not in msg or msg["user_id"] is None:
                msg["user_id"] = self.user_id if self.user_id is not None else None

        if self.history:
            answer = self._safe_input(
                "Текущая история не пуста. Заменить её загруженной? (y/n): ").strip().lower()
            if answer not in ("y", "да", "yes"):
                print("Загрузка отменена.")
                return
        self.history = data
        print(
            f"Загружено {len(self.history)} сообщений из файла '{filename}'.")

    def print(self):
        if not self.history:
            print("История пуста.")
            return
        print("\n=== ИСТОРИЯ ДИАЛОГА ===")
        for i, msg in enumerate(self.history, 1):
            role = "Вы" if msg["role"] == "user" else "Собеседник"
            timestamp = msg.get("timestamp", "")
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    time_str = dt.strftime("%H:%M:%S")
                except:
                    time_str = timestamp
                print(f"{i}. {role} [{time_str}]: {msg['content']}")
            else:
                print(f"{i}. {role}: {msg['content']}")
        print("=== КОНЕЦ ИСТОРИИ ===\n")

    def get_context_markers(self):
        if not self.history:
            return []
        if len(self.history) <= 3:
            return self.history
        mid = len(self.history) // 2
        return [self.history[0], self.history[mid], self.history[-1]]

    def is_empty(self):
        return not self.history

    def __len__(self):
        return len(self.history)

    def __repr__(self):
        return f"<Session history={len(self.history)} user_id={self.user_id} restoring={self.restoring}>"
