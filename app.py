# app.py
from flask import Flask, render_template, request, jsonify, make_response, redirect
from core.ai_client import AIClient
from core.session import Session
import os
import uuid
from dotenv import load_dotenv
from flask_wtf import CSRFProtect
load_dotenv()

debug = os.getenv('DEBUG', '').lower() in ('true', '1', 'yes')
app = Flask(__name__)
csrf=CSRFProtect(app)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Инициализация AI-клиента
ai_client = AIClient(
    api_key=os.getenv('API_KEY'),
    base_url=os.getenv('BASE_URL'),
    project=os.getenv('PROJECT'),
    prompt_id=os.getenv('PROMPT_ID')
)

# Хранилище сессий (в памяти)
sessions = {}

def get_session(session_id):
    """Возвращает сессию по ID, создаёт новую при необходимости."""
    if session_id not in sessions:
        sessions[session_id] = Session()
    return sessions[session_id]

@app.route('/')
def index():
    """Главная страница чата."""
    session_id = request.cookies.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())
        sessions[session_id] = Session()

    session = get_session(session_id)
    history = session.history

    response = make_response(render_template('index.html', history=history))
    response.set_cookie('session_id', session_id, max_age=60*60*24*30)  # 30 дней
    return response

@app.route('/send', methods=['POST'])
def send():
    if debug:
        print("=== REQUEST ===")
        print("METHOD:", request.method)
        print("HEADERS:", request.headers)
    """Обрабатывает сообщение пользователя и возвращает ответ AI."""
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify({'error': 'Сессия не найдена'}), 400

    session = get_session(session_id)
    user_message = request.form.get('user_message', '').strip()
    if debug:
        print("=== FORM DATA ===")
        print(request.form)
        print("KEYS:", list(request.form.keys()))
    if not user_message:
        return jsonify({'error': 'Сообщение пустое'}), 400

    session.add_user_message(user_message)

    try:
        response_text = ai_client.ask(session.history)
        session.add_assistant_message(response_text)
        return jsonify({'reply': response_text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/save', methods=['POST'])
def save_history():
    """Сохраняет историю текущей сессии в файл."""
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify({'error': 'Сессия не найдена'}), 400

    session = get_session(session_id)
    if not session.history:
        return jsonify({'error': 'История пуста, сохранять нечего'}), 400

    filename = request.form.get('filename', '').strip()
    if not filename:
        # Генерируем имя по умолчанию
        filename = f'history_{session_id[:8]}.json'

    try:
        session.save(filename)
        return jsonify({'message': f'История сохранена в {filename}'})
    except Exception as e:
        return jsonify({'error': f'Ошибка при сохранении: {str(e)}'}), 500

@app.route('/load', methods=['POST'])
def load_history():
    """Загружает историю из файла в текущую сессию."""
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify({'error': 'Сессия не найдена'}), 400

    filename = request.form.get('filename', '').strip()
    if not filename:
        return jsonify({'error': 'Имя файла не указано'}), 400

    session = get_session(session_id)

    try:
        # Временно сохраняем старую историю для проверки
        old_history = session.history.copy()
        session.load(filename)

        # Проверяем, загрузилось ли что-то
        if not session.history:
            session.history = old_history  # откат, если загрузка не дала результатов
            return jsonify({'error': 'Файл пуст или имеет неверный формат'}), 400

        return jsonify({'message': f'История загружена из {filename} (сообщений: {len(session.history)})'})
    except FileNotFoundError:
        return jsonify({'error': f'Файл {filename} не найден'}), 404
    except Exception as e:
        return jsonify({'error': f'Ошибка при загрузке: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)