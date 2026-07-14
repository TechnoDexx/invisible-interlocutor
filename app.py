# app.py
from flask import Flask, make_response, render_template, request, jsonify
from core import AIClient
from core import Session
import os
from dotenv import load_dotenv
import uuid

load_dotenv()

app = Flask(__name__)

# Инициализация AI-клиента
ai_client = AIClient(
    api_key=os.getenv('API_KEY'),
    base_url=os.getenv('BASE_URL'),
    project=os.getenv('PROJECT'),
    prompt_id=os.getenv('PROMPT_ID')
)

# Хранилище сессий (пока в памяти)
# Ключ — session_id, значение — экземпляр Session
sessions = {}

@app.route('/')
def index():
    """Главная страница — чат."""
    # Генерируем или берём session_id из cookies
    session_id = request.cookies.get('session_id')
    if not session_id or session_id not in sessions:
        session_id = str(uuid.uuid4())
        sessions[session_id] = Session()

    # Загружаем историю из сессии
    history = sessions[session_id].history
    response = make_response(render_template('index.html', history=history))
    response.set_cookie('session_id', session_id, max_age=60*60*24*30)  # 30 дней
    return response

@app.route('/send', methods=['POST'])
def send():
    """Обрабатывает сообщение пользователя и возвращает ответ AI."""
    session_id = request.cookies.get('session_id')
    if not session_id or session_id not in sessions:
        return jsonify({'error': 'Сессия не найдена'}), 400

    user_message = request.form.get('user_message', '').strip()
    if not user_message:
        return jsonify({'error': 'Сообщение пустое'}), 400

    session = sessions[session_id]

    # Добавляем сообщение пользователя в историю
    session.add_user_message(user_message)

    try:
        # Получаем ответ от AI
        response_text = ai_client.ask(session.history)
        session.add_assistant_message(response_text)
        return jsonify({'reply': response_text})
    except Exception as e:
        # В случае ошибки не добавляем ответ AI в историю, но сообщение пользователя остаётся
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)