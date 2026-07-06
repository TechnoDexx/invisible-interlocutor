# main.py
import os
from dotenv import load_dotenv
from core import AIClient
from core import Session
from core import ChatApp

if __name__ == "__main__":
    # Загружаем переменные окружения из .env
    load_dotenv()

    # Создаём AI-клиента с параметрами из окружения
    client = AIClient(
        api_key=os.getenv('API_KEY'),
        base_url=os.getenv('BASE_URL'),
        project=os.getenv('PROJECT'),
        prompt_id=os.getenv('PROMPT_ID')
    )

    # Создаём сессию с указанием файла для автоматического сохранения/загрузки
    # Если файл не нужен — можно не передавать filename
    session = Session(filename="history.json")

    # Запускаем приложение
    app = ChatApp(client, session)
    app.run()