import json
import openai
import time
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

client = openai.OpenAI(
    api_key="",
    base_url="https://ai.api.cloud.yandex.net/v1",
    project="b1g0mvagt30sttlfi76u"
)

PROMPT_ID = "fvtfrhldlipm16uqtdb9"
history = []

def ask(prompt_text: str, retries: int = 3) -> str:
    """
    Отправляет запрос к модели с автоматическими повторными попытками
    при сбоях соединения или временных ошибках.
    """
    history.append({"role": "user", "content": prompt_text})
    
    for attempt in range(retries):
        try:
            response = client.responses.create(
                prompt={"id": PROMPT_ID},
                input=history
            )
            answer = response.output_text
            history.append({"role": "assistant", "content": answer})
            return "[[ {0} ]]".format(answer)
        
        except Exception as e:
            # Если это последняя попытка — поднимаем исключение дальше
            if attempt == retries - 1:
                raise
            # Иначе ждём и повторяем
            time.sleep(1)  # пауза перед повторной попыткой
            continue

def print_history():
    if not history:
        print("История пуста.")
        return
    print("\n=== ИСТОРИЯ ДИАЛОГА ===")
    for i, msg in enumerate(history, 1):
        role = "Вы" if msg["role"] == "user" else "Собеседник"
        print(f"{i}. {role}: {msg['content']}")
    print("=== КОНЕЦ ИСТОРИИ ===\n")

def save_history(filename=None):
    if not history:
        print("История пуста, сохранять нечего.")
        return
    if filename is None:
        filename = input("Введите имя файла (c расширением): ")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"История сохранена в {filename}")

def load_history(filename=None):
    global history
    if filename is None:
        filename = input("Введите имя файла для загрузки: ").strip()
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
            print(f"Сообщение #{i+1} имеет неверную структуру, загрузка прервана.")
            return

    if history:
        print("Текущая история не пуста.")
        answer = input("Заменить текущую историю загруженной? (y/n): ").strip().lower()
        if answer not in ("y", "да", "yes"):
            print("Загрузка отменена.")
            return

    history = data
    print(f"Загружено {len(history)} сообщений из файла '{filename}'.")

if __name__ == "__main__":
    print("Незримый собеседник (консоль).")
    print("Команды: /history - показать историю, /save - сохранить в файл, "
          "/load - загрузить из файла, /clear - очистить историю, выход - завершить.")
    while True:
        user_input = input("> ")
        if user_input.lower() in ("выход", "exit", "quit"):
            break
        if not user_input.strip():
            continue

        if user_input.startswith("/"):
            cmd = user_input.lower()
            if cmd == "/history":
                print_history()
            elif cmd == "/save":
                save_history()
            elif cmd == "/clear":
                history.clear()
                print("История очищена.")
            elif cmd == "/load":
                load_history()
            else:
                print("Неизвестная команда.")
            continue

        try:
            reply = ask(user_input)
            print(reply)
        except Exception as e:
            print(f"Ошибка: {e}")