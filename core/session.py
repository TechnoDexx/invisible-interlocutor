import sys
import json
import datetime
from datetime import timezone
class Session:
    def __init__(self, filename=None, history=None):
        self.history = history if history is not None else []
        self.filename = filename

    @staticmethod
    def _safe_input(prompt=""):
        if prompt:
            sys.stdout.write(prompt)
            sys.stdout.flush()
        raw = sys.stdin.buffer.readline()
        try:
            return raw.decode('utf-8').rstrip('\n')
        except UnicodeDecodeError:
            return raw.decode('utf-8', errors='replace').rstrip('\n')

    def add_user_message(self, text,user_id=None):
        self.history.append({"role": "user","timestamp": datetime.utcnow().isoformat(),"user_id": user_id, "content": text})

    def add_assistant_message(self, text):
        self.history.append({"role": "assistant", "timestamp": datetime.utcnow().isoformat(), "content": text})

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
        if self.history:
            answer = self._safe_input(
                "Текущая история не пуста. Заменить её загруженной? (y/n): "
            ).strip().lower()
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
            print(f"{i}. {role}: {msg['content']}")
        print("=== КОНЕЦ ИСТОРИИ ===\n")

    def is_empty(self):
        return not self.history

    def __len__(self):
        return len(self.history)
