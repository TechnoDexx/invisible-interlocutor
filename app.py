# app.py
from flask import Flask, render_template, request, jsonify, make_response, redirect
from core.ai_client import AIClient
from core.session import Session
from core.users import Users
from core.history import MessageHistory
import os
import uuid
import threading
from dotenv import load_dotenv
from flask_wtf import CSRFProtect
from flask_login import LoginManager, login_user, logout_user, current_user

load_dotenv()
debug = os.getenv('DEBUG', '').lower() in ('true', '1', 'yes')

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

csrf = CSRFProtect(app)
users_db = Users()
history_db = MessageHistory()   # <--- НОВОЕ

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return users_db.get_user_by_id(user_id)

ai_client = AIClient(
    api_key=os.getenv('API_KEY'),
    base_url=os.getenv('BASE_URL'),
    project=os.getenv('PROJECT'),
    prompt_id=os.getenv('PROMPT_ID')
)

sessions = {}

def get_session(session_id):
    if session_id not in sessions:
        sessions[session_id] = Session()
    return sessions[session_id]

# ---------- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ АСИНХРОННОГО СОХРАНЕНИЯ ----------
def save_message_async(user_id, session_id, role, content, timestamp=None):
    """Сохраняет сообщение в YDB в фоновом потоке."""
    try:
        history_db.save_message(user_id, session_id, role, content, timestamp)
    except Exception as e:
        print(f"[ASYNC SAVE] Ошибка сохранения: {e}")

# ---------- МАРШРУТЫ ----------
@app.route('/')
def index():
    username = current_user.username if current_user.is_authenticated else None
    session_id = request.cookies.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())
        sessions[session_id] = Session()
    session = get_session(session_id)
    # Если пользователь авторизован, но история в памяти пуста — загружаем из БД
    if current_user.is_authenticated and not session.history:
        full_history = history_db.get_full_history(current_user.id, session_id)
        if full_history:
            session.history = full_history
            session.user_id = current_user.id
    history = session.history
    response = make_response(render_template('index.html', history=history, username=username))
    response.set_cookie('session_id', session_id, max_age=60*60*24*30)
    return response

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

            # ---- ПЕРЕНЕСЕНИЕ АНОНИМНОЙ ИСТОРИИ В YDB ----
            session_id = request.cookies.get('session_id')
            if session_id and session_id in sessions:
                session = sessions[session_id]
                if session.history and session.user_id is None:
                    # Сохраняем анонимную историю в БД
                    history_db.save_history(user.id, session_id, session.history)
                    # Очищаем память, чтобы не дублировать
                    session.clear()
                # Устанавливаем user_id сессии
                session.user_id = user.id

            # ---- ВОССТАНОВЛЕНИЕ КОНТЕКСТА (АСИНХРОННО) ----
            def restore_context():
                # Загружаем маркеры из БД
                markers = history_db.get_markers(user.id, session_id)
                if markers:
                    try:
                        response_text = ai_client.ask(markers)
                        # Добавляем ответ в сессию (если она ещё существует)
                        if session_id in sessions:
                            sess = sessions[session_id]
                            sess.add_assistant_message(response_text, user_id=user.id)
                            # Сохраняем ответ в БД
                            history_db.save_message(user.id, session_id, "assistant", response_text)
                    except Exception as e:
                        print(f"[CONTEXT RESTORE] Ошибка: {e}")

            threading.Thread(target=restore_context, daemon=True).start()

            return redirect('/')
        else:
            return 'Неверный логин или пароль', 401
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect('/')

@app.route('/send', methods=['POST'])
def send():
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify({'error': 'Сессия не найдена'}), 400
    session = get_session(session_id)
    user_message = request.form.get('user_message', '').strip()
    if not user_message:
        return jsonify({'error': 'Сообщение пустое'}), 400

    # Добавляем сообщение пользователя в память
    session.add_user_message(user_message)

    # Асинхронно сохраняем в БД (если пользователь авторизован)
    if session.user_id:
        threading.Thread(
            target=save_message_async,
            args=(session.user_id, session_id, "user", user_message),
            daemon=True
        ).start()

    try:
        # Отправляем полную историю в AI
        response_text = ai_client.ask(session.history)
        session.add_assistant_message(response_text)

        # Асинхронно сохраняем ответ ассистента
        if session.user_id:
            threading.Thread(
                target=save_message_async,
                args=(session.user_id, session_id, "assistant", response_text),
                daemon=True
            ).start()

        return jsonify({'reply': response_text})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/save', methods=['POST'])
def save_history():
    # можно оставить для локального сохранения в файл (для отладки)
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
        # Если загрузили историю и есть user_id — сохраняем в YDB
        if session.user_id:
            history_db.save_history(session.user_id, session_id, session.history)
        return jsonify({'message': f'История загружена из {filename} ({len(session.history)} сообщений)'})
    except FileNotFoundError:
        return jsonify({'error': f'Файл {filename} не найден'}), 404
    except Exception as e:
        return jsonify({'error': f'Ошибка: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)