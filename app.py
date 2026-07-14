# app.py
from flask import Flask, render_template, request, jsonify, make_response, redirect
from core.ai_client import AIClient
from core.session import Session
from core.users import Users
import os
import uuid
from dotenv import load_dotenv
from flask_wtf import CSRFProtect
from flask_login import LoginManager, login_user, logout_user, current_user

load_dotenv()

debug = os.getenv('DEBUG', '').lower() in ('true', '1', 'yes')

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# ===== ИНИЦИАЛИЗАЦИЯ =====
csrf = CSRFProtect(app)
users_db = Users()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ===== ЗАГРУЗЧИК ПОЛЬЗОВАТЕЛЯ =====
@login_manager.user_loader
def load_user(user_id):
    return users_db.get_user(user_id)

# ===== AI КЛИЕНТ =====
ai_client = AIClient(
    api_key=os.getenv('API_KEY'),
    base_url=os.getenv('BASE_URL'),
    project=os.getenv('PROJECT'),
    prompt_id=os.getenv('PROMPT_ID')
)

# ===== ХРАНИЛИЩЕ СЕССИЙ (в памяти) =====
sessions = {}

def get_session(session_id):
    if session_id not in sessions:
        sessions[session_id] = Session()
    return sessions[session_id]

# ===== ГЛАВНАЯ СТРАНИЦА =====
@app.route('/')
def index():
    username = current_user.username if current_user.is_authenticated else None
    session_id = request.cookies.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())
        sessions[session_id] = Session()

    session = get_session(session_id)
    history = session.history

    response = make_response(render_template('index.html', history=history, username=username))
    response.set_cookie('session_id', session_id, max_age=60*60*24*30)
    return response

# ===== РЕГИСТРАЦИЯ =====
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if not username or not password:
            return 'Имя пользователя и пароль обязательны', 400
        try:
            users_db.create_user(username, password)
            return redirect('/login')
        except Exception as e:
            return f'Ошибка: {e}', 400
    return render_template('register.html')

# ===== ВХОД =====
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if not username or not password:
            return 'Имя пользователя и пароль обязательны', 400

        user = users_db.get_user(username)
        if user and users_db.verify_user(username, password):
            login_user(user)
            return redirect('/')
        else:
            return 'Неверный логин или пароль', 401
    return render_template('login.html')

# ===== ВЫХОД =====
@app.route('/logout')
def logout():
    logout_user()
    return redirect('/')

# ===== ОТПРАВКА СООБЩЕНИЯ =====
@app.route('/send', methods=['POST'])
def send():
    if debug:
        print("=== REQUEST ===")
        print("METHOD:", request.method)
        print("HEADERS:", request.headers)

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

# ===== СОХРАНЕНИЕ ИСТОРИИ =====
@app.route('/save', methods=['POST'])
def save_history():
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify({'error': 'Сессия не найдена'}), 400

    session = get_session(session_id)
    if not session.history:
        return jsonify({'error': 'История пуста'}), 400

    filename = request.form.get('filename', '').strip()
    if not filename:
        filename = f'history_{session_id[:8]}.json'

    try:
        session.save(filename)
        return jsonify({'message': f'История сохранена в {filename}'})
    except Exception as e:
        return jsonify({'error': f'Ошибка: {str(e)}'}), 500

# ===== ЗАГРУЗКА ИСТОРИИ =====
@app.route('/load', methods=['POST'])
def load_history():
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify({'error': 'Сессия не найдена'}), 400

    filename = request.form.get('filename', '').strip()
    if not filename:
        return jsonify({'error': 'Имя файла не указано'}), 400

    session = get_session(session_id)
    try:
        old_history = session.history.copy()
        session.load(filename)
        if not session.history:
            session.history = old_history
            return jsonify({'error': 'Файл пуст'}), 400
        return jsonify({'message': f'История загружена из {filename} ({len(session.history)} сообщений)'})
    except FileNotFoundError:
        return jsonify({'error': f'Файл {filename} не найден'}), 404
    except Exception as e:
        return jsonify({'error': f'Ошибка: {str(e)}'}), 500

# ===== ЗАПУСК =====
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)
