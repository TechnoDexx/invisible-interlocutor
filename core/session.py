import json
from datetime import datetime


class Session:
    """
    Управляет историей диалога: добавление, сохранение, загрузка.
    Поддерживает:
    - timestamp для каждого сообщения (ISO 8601, UTC)
    - user_id (может быть None для анонимных сессий)
    - обратную совместимость со старыми файлами (без timestamp и user_id)
    - автоматическую привязку user_id при загрузке, если он установлен в сессии
    - флаг restoring для индикации процесса восстановления контекста
    """

    def __init__(self, filename=None, history=None, user_id=None):
        self.history = history if history is not None else []
        self.filename = filename
        self.user_id = user_id  # храним на уровне сессии
        self.restoring = False   # флаг восстановления контекста

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
            return
        if filename is None:
            return
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)

    def load(self, filename=None):
        if filename is None:
            return
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            raise
        except json.JSONDecodeError:
            raise
        if not isinstance(data, list):
            raise ValueError("Данные в файле не являются списком.")
        for i, msg in enumerate(data):
            if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
                raise ValueError(
                    f"Сообщение #{i+1} имеет неверную структуру")
        # Добавляем отсутствующие поля для обратной совместимости
        for msg in data:
            if "timestamp" not in msg:
                msg["timestamp"] = None
            if "user_id" not in msg or msg["user_id"] is None:
                msg["user_id"] = self.user_id if self.user_id is not None else None

        self.history = data

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
