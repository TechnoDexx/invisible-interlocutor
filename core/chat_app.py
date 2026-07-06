# chat_app.py

class ChatApp:
    """
    Основной класс приложения.
    Объединяет AI-клиента и сессию, организует интерактивный диалог.
    """

    def __init__(self, ai_client, session):
        """
        ai_client: экземпляр AIClient (или любого класса с методом ask(history))
        session: экземпляр Session (с методами add_user_message, add_assistant_message, save, load, print, clear)
        """
        self.ai_client = ai_client
        self.session = session
        self.running = False

    def run(self):
        """Запускает основной цикл диалога."""
        self.running = True
        print("Добро пожаловать в 'Незримого собеседника'.")
        print("Введите сообщение или команду (начинается с /):")
        print("Доступные команды: /save, /load, /print, /clear, /exit")
        print()

        while self.running:
            # Получаем ввод пользователя
            user_input = self.session._safe_input("> ").strip()

            # Если ввод пустой — просто продолжаем
            if not user_input:
                continue

            # Обработка команд (начинаются с "/")
            if user_input.startswith("/"):
                self._handle_command(user_input[1:].strip())
                continue

            # Обычное сообщение пользователя
            self.session.add_user_message(user_input)

            # Получаем ответ от AI
            try:
                response = self.ai_client.ask(self.session.history)
            except Exception as e:
                print(f"Ошибка при обращении к AI: {e}")
                # В случае ошибки мы всё равно сохранили сообщение пользователя,
                # но не добавляем ответ. Можно продолжить или прервать.
                continue

            # Добавляем ответ в историю
            self.session.add_assistant_message(response)

            # Выводим ответ
            print(f"Собеседник: {response}")

    def _handle_command(self, command):
        """Обрабатывает команды пользователя."""
        if command == "exit":
            print("До свидания.")
            self.running = False
            return

        if command == "save":
            # Если у сессии есть filename, используем его, иначе запросим
            if self.session.filename:
                self.session.save(self.session.filename)
            else:
                self.session.save()  # вызовет запрос имени файла
            return

        if command == "load":
            if self.session.filename:
                self.session.load(self.session.filename)
            else:
                self.session.load()  # запросит имя файла
            return

        if command == "print":
            self.session.print()
            return

        if command == "clear":
            self.session.clear()
            print("История очищена.")
            return

        # Неизвестная команда
        print(f"Неизвестная команда: /{command}")
        print("Доступные команды: /save, /load, /print, /clear, /exit")

    # Дополнительный метод для пакетного импорта/экспорта (опционально)
    def export_history_to_json(self, filepath):
        """Экспортирует историю сессии в отдельный JSON-файл (вне сессии)."""
        import json
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.session.history, f, ensure_ascii=False, indent=2)
        print(f"История экспортирована в {filepath}")

    def import_history_from_json(self, filepath):
        """Импортирует историю из JSON-файла и добавляет к текущей."""
        import json
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"Файл {filepath} не найден.")
            return
        except json.JSONDecodeError:
            print(f"Файл {filepath} содержит некорректный JSON.")
            return
        if not isinstance(data, list):
            print("Данные не являются списком.")
            return
        # Проверяем структуру
        for msg in data:
            if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
                print("Неверная структура сообщений в файле.")
                return
        self.session.history.extend(data)
        print(f"Импортировано {len(data)} сообщений из {filepath}")
