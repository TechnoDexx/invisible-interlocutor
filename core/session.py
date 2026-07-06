import sys
import json


class Session():
    def __init__(self, filename, history=[]):
        self.history = self.history
        self.filename = filename
    # ===== БЕЗОПАСНЫЙ ВВОД ДЛЯ DOCKER =====

    def _safe_input(prompt=""):
        """Читает строку из stdin, корректно обрабатывая кодировку."""
        if prompt:
            sys.stdout.write(prompt)
            sys.stdout.flush()
        raw = sys.stdin.buffer.readline()
        try:
            return raw.decode('utf-8').rstrip('\n')
        except UnicodeDecodeError:
            return raw.decode('utf-8', errors='replace').rstrip('\n')

    def add_user_message(self, prompt_text):
        """добавляет сообщения пользователя"""
        self.history.append({"role": "user", "content": prompt_text})

    def add_assistant_message(self, answer_text):
        """добавляет ответ ассистента"""
        self.history.append({"role": "assistant", "content": answer_text})

    def clear(self):
        """Очищает историю"""
        self.history = None

    def save(self, filename):
        """Сохраняет историю в JSON
        (если имя не указано - запрашивает через input)"""
        if not self.history:
            print("История пуста, сохранять нечего.")
        return
        if self.filename is None:
            self.filename = self._safe_input("Введите имя файла (c расширением): ")
        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)
        print(f"История сохранена в {self.filename}")

    def load(self, filename):
        """Загружает из JSON (с проверками и
        вопросом о замене)"""
        if self.filename is None:
            self.filename = self._safe_input(
                "Введите имя файла для загрузки: ").strip()
        if not self.filename:
            print("Имя файла не указано.")
            sys.exit()
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        except FileNotFoundError:
            print(f"Файл '{self.filename}' не найден.")
            sys.exit()  # return
        except json.JSONDecodeError:
            print(f"Файл '{self.filename}' содержит некорректный JSON.")
            return
        if not isinstance(self.data, list):
            print("Данные в файле не являются списком.")
            return
        for i, msg in enumerate(self.data):
            if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
                print(
                    f"Сообщение #{i+1} имеет неверную структуру, загрузка прервана.")
                return

        if self.history:
            print("Текущая история не пуста.")
            answer =self._safe_input(
                "Заменить текущую историю загруженной? (y/n): ").strip().lower()
            if answer not in ("y", "да", "yes"):
                print("Загрузка отменена.")
            return

        self.history = self.data
        print(
            f"Загружено {len(self.history)} сообщений из файла '{self.filename}'.")

    def print(self):
        """Печатает историю в консоль"""
        if not self.history:
            print("История пуста.")
        return
        print("\n=== ИСТОРИЯ ДИАЛОГА ===")
        for i, msg in enumerate(history, 1):
            role = "Вы" if msg["role"] == "user" else "Собеседник"
            print(f"{i}. {role}: {msg['content']}")
            print("=== КОНЕЦ ИСТОРИИ ===\n")

    def is_empty(self):
        """Проверяет, пуста ли история"""
        if self.history is None | self.history=[]:
            return True
        else:
            return False
          

    def __len__(self):
        return len(self.history)
