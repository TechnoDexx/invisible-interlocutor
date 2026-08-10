# app.py
import sys
sys.dont_write_bytecode = True
import re
import secrets
import datetime
import json
import io
import os
import uuid
import threading
import atexit
from flask import Flask, render_template, request, jsonify, make_response, redirect, flash, send_file
from flask_mail import Mail
from flask_wtf import CSRFProtect
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from dotenv import load_dotenv
import openai

from core.ai_client import AIClient
from core.session import Session
from core.users import Users
from core.history import MessageHistory, PendingQuestions
from services import MailService

load_dotenv()
debug = os.getenv('DEBUG', '').lower() in ('true', '1', 'yes')
app_debug = os.getenv('APP_DEBUG', '').lower() in ('true', '1', 'yes')
ai_request_timeout = float(os.getenv('AI_REQUEST_TIMEOUT', 10))
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# --- Конфигурация Flask-Mail ---
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.yandex.ru')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 465))
app.config['MAIL_USE_SSL'] = os.getenv(
    'MAIL_USE_SSL', 'True').lower() == 'true'
app.config['MAIL_USE_TLS'] = os.getenv(
    'MAIL_USE_TLS', 'False').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv(
    'MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME'])
app.config['BASE_URL'] = os.getenv('APP_BASE_URL', 'http://localhost:8080')

# Инициализация Flask-Mail
mail = Mail(app)

csrf = CSRFProtect(app)
users_db = Users()
history_db = MessageHistory()
pending_db = PendingQuestions()

# Закрываем YDB-driver при завершении процесса, чтобы не оставлять открытые соединения
atexit.register(users_db.close)
atexit.register(history_db.close)
atexit.register(pending_db.close)

# Передаём mail в MailService
mail_service = MailService(app, users_db, mail)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    return users_db.get_user_by_id(user_id)


ai_client = AIClient(
    api_key=os.getenv('API_KEY'),
    base_url=os.getenv('AI_BASE_URL'),
    project=os.getenv('PROJECT'),
    prompt_id=os.getenv('PROMPT_ID')
)

sessions = {}


def get_session(session_id):
    if session_id not in sessions:
        sessions[session_id] = Session()
    return sessions[session_id]


def save_message_async(user_id, session_id, role, content, timestamp=None):
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

    if current_user.is_authenticated and not session.history:
        full_history = history_db.get_full_history(current_user.id, None)
        if debug:
            print(
                f"[DEBUG /] Загружено {len(full_history)} сообщений для user {current_user.id}")
        if full_history:
            session.history = full_history
            session.user_id = current_user.id

    # Неотвеченные вопросы: сначала YDB, при недоступности — JS подхватит из localStorage
    pending_q = None
    try:
        pending_q = pending_db.get_pending_question(session_id)
    except Exception as e:
        if debug:
            print(f"[DEBUG /] pending_db недоступна, fallback на localStorage: {e}")

    history = session.history
    response = make_response(render_template(
        'index.html', history=history, username=username, pending_q=pending_q))
    response.set_cookie('session_id', session_id, max_age=60*60*24*30)
    return response


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        email = request.form.get('email', '').strip()
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash('Некорректный email', 'danger')
            return render_template('register.html'), 400
        if not username or not password:
            flash('Имя пользователя и пароль обязательны', 'danger')
            return render_template('register.html'), 400
        try:
            users_db.create_user(username, password, email=email)
            flash('Регистрация успешна! Войдите в систему.', 'success')
            return redirect('/login')
        except Exception as e:
            flash(f'Ошибка: {e}', 'danger')
            return render_template('register.html'), 400
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if not username or not password:
            flash('Имя пользователя и пароль обязательны', 'danger')
            return render_template('login.html'), 400
        user = users_db.get_user(username)
        if user and users_db.verify_user(username, password):
            login_user(user)

            session_id = request.cookies.get('session_id')
            if not session_id:
                session_id = str(uuid.uuid4())
            session = get_session(session_id)

            if session.history and session.user_id is None:
                history_db.save_history(user.id, session_id, session.history)
                session.clear()

            session.user_id = user.id

            full_history = history_db.get_full_history(user.id, None)
            if debug:
                print(
                    f"[DEBUG /login] Загружено {len(full_history)} сообщений для user {user.id}")
            if full_history:
                session.history = full_history
            else:
                session.history = []

            session.set_restoring(True)

            def restore_context():
                try:
                    markers = history_db.get_markers(user.id, session_id)
                    if markers:
                        response_text = ai_client.ask(markers)
                        if session_id in sessions:
                            sess = sessions[session_id]
                            sess.add_assistant_message(
                                response_text, user_id=user.id)
                            history_db.save_message(
                                user.id, session_id, "assistant", response_text)
                except Exception as e:
                    print(f"[CONTEXT RESTORE] Ошибка: {e}")
                finally:
                    if session_id in sessions:
                        sessions[session_id].set_restoring(False)

            threading.Thread(target=restore_context, daemon=True).start()

            return redirect('/')
        else:
            flash('Неверный логин или пароль', 'danger')
            return render_template('login.html'), 401
    return render_template('login.html')


@app.route('/logout')
def logout():
    session_id = request.cookies.get('session_id')
    if session_id and session_id in sessions:
        sessions[session_id].clear()
        sessions[session_id].user_id = None
    logout_user()
    response = make_response(redirect('/'))
    response.set_cookie('session_id', '', expires=0)
    return response


@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)

# ========== СМЕНА EMAIL (через токен) ==========


@app.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    new_email = request.form.get('email', '').strip()
    if not re.match(r"[^@]+@[^@]+\.[^@]+", new_email):
        flash('Некорректный email', 'danger')
        return redirect('/profile')

    token = secrets.token_urlsafe(32)
    users_db.set_pending_email(current_user.id, new_email, token)

    if mail_service.send_email_change_confirmation(current_user, new_email, token):
        flash(
            f'Письмо для подтверждения отправлено на {new_email}. Перейдите по ссылке для завершения смены.', 'success')
    else:
        flash('Не удалось отправить письмо. Попробуйте позже.', 'danger')

    return redirect('/profile')


@app.route('/confirm-email-change/<token>')
def confirm_email_change(token):
    if users_db.confirm_email_change(token):
        flash('Email успешно изменён!', 'success')
    else:
        flash('Ссылка недействительна или истекла.', 'danger')
    return redirect('/profile')

# ========== СМЕНА ПАРОЛЯ ==========


@app.route('/profile/change-password', methods=['POST'])
@login_required
def change_password():
    old = request.form.get('old_password', '').strip()
    new = request.form.get('new_password', '').strip()
    if not old or not new:
        flash('Заполните оба поля', 'danger')
        return redirect('/profile')
    if len(new) < 6:
        flash('Новый пароль должен быть не короче 6 символов', 'danger')
        return redirect('/profile')
    if users_db.change_password(current_user.id, old, new):
        flash('Пароль успешно изменён', 'success')
    else:
        flash('Неверный старый пароль', 'danger')
    return redirect('/profile')

# ========== СМЕНА ИМЕНИ ==========


@app.route('/profile/change-username', methods=['POST'])
@login_required
def change_username():
    new_username = request.form.get('new_username', '').strip()
    if not new_username:
        flash('Имя не может быть пустым', 'danger')
        return redirect('/profile')
    if users_db.update_username(current_user.id, new_username):
        flash('Имя пользователя обновлено', 'success')
        return redirect('/profile')
    else:
        flash('Это имя уже занято', 'danger')
        return redirect('/profile')

# ========== УДАЛЕНИЕ АККАУНТА ==========


@app.route('/profile/delete-account', methods=['POST'])
@login_required
def delete_account():
    password = request.form.get('password', '').strip()
    if not password:
        flash('Введите пароль для подтверждения удаления.', 'danger')
        return redirect('/profile')

    if not users_db.verify_user(current_user.username, password):
        flash('Неверный пароль.', 'danger')
        return redirect('/profile')

    user_id = current_user.id
    username = current_user.username

    history_db.delete_user_history(user_id)
    users_db.delete_user(user_id)

    logout_user()

    session_id = request.cookies.get('session_id')
    if session_id and session_id in sessions:
        sessions.pop(session_id, None)

    flash(f'Аккаунт "{username}" и все ваши данные удалены.', 'success')
    return redirect('/')

# ========== ПОДТВЕРЖДЕНИЕ EMAIL ПРИ РЕГИСТРАЦИИ ==========


@app.route('/request-verification', methods=['GET', 'POST'])
@login_required
def request_verification():
    if current_user.email_verified:
        flash('Ваш email уже подтверждён.', 'info')
        return redirect('/profile')

    if request.method == 'POST':
        if mail_service.send_verification_email(current_user):
            flash('Письмо с подтверждением отправлено на ваш email.', 'success')
        else:
            flash('Не удалось отправить письмо. Попробуйте позже.', 'danger')
        return redirect('/profile')

    return render_template('request_verification.html')


@app.route('/verify-email/<token>')
def verify_email(token):
    success, message = users_db.verify_email_by_token(token)
    if success:
        flash('Ваш email успешно подтверждён!', 'success')
        return redirect('/profile')
    else:
        flash(message, 'danger')
        return redirect('/login')

# ========== ВОССТАНОВЛЕНИЕ ПАРОЛЯ ==========


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if not email:
            flash('Введите email', 'danger')
            return render_template('forgot_password.html'), 400

        user = users_db.get_user_by_email(email)
        if user:
            mail_service.send_reset_password_email(user)
        flash('Если пользователь с таким email существует, ссылка для сброса пароля отправлена.', 'info')
        return redirect('/login')

    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET'])
def reset_password_form(token):
    user = users_db.get_user_by_reset_token(token)
    if not user:
        flash('Ссылка недействительна или истекла.', 'danger')
        return redirect('/login')
    return render_template('reset_password.html', token=token)


@app.route('/reset-password', methods=['POST'])
def reset_password():
    token = request.form.get('token', '').strip()
    new_password = request.form.get('new_password', '').strip()
    if not token or not new_password:
        flash('Необходимо указать новый пароль.', 'danger')
        return render_template('reset_password.html', token=token), 400
    if len(new_password) < 6:
        flash('Пароль должен содержать минимум 6 символов.', 'danger')
        return render_template('reset_password.html', token=token), 400

    success, message = users_db.reset_password_by_token(token, new_password)
    if success:
        flash('Пароль успешно изменён! Войдите с новым паролем.', 'success')
        return redirect('/login')
    else:
        flash(message, 'danger')
        return redirect('/login')

# ========== ЭКСПОРТ / ИМПОРТ ИСТОРИИ ДЛЯ АВТОРИЗОВАННЫХ ==========


@app.route('/profile/download-history')
@login_required
def download_history():
    history = history_db.get_full_history(current_user.id, session_id=None)
    if not history:
        flash('История диалогов пуста.', 'warning')
        return redirect('/profile')

    json_data = json.dumps(history, ensure_ascii=False, indent=2)
    file_like = io.BytesIO(json_data.encode('utf-8'))

    return send_file(
        file_like,
        as_attachment=True,
        download_name=f'history_{current_user.username}_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.json',
        mimetype='application/json'
    )

# ========== ИЗМЕНЁННЫЙ МАРШРУТ ИМПОРТА (с проверкой user_id) ==========


@app.route('/profile/upload-history', methods=['POST'])
@login_required
def upload_history():
    if 'history_file' not in request.files:
        flash('Файл не выбран.', 'danger')
        return redirect('/profile')

    file = request.files['history_file']
    if file.filename == '':
        flash('Файл не выбран.', 'danger')
        return redirect('/profile')

    if not file.filename.endswith('.json'):
        flash('Файл должен быть в формате JSON.', 'danger')
        return redirect('/profile')

    try:
        data = json.load(file.stream)
        if not isinstance(data, list):
            flash('Некорректный формат: ожидается список сообщений.', 'danger')
            return redirect('/profile')

        # Проверяем структуру
        for msg in data:
            if not isinstance(msg, dict) or 'role' not in msg or 'content' not in msg:
                flash('Неверная структура сообщений.', 'danger')
                return redirect('/profile')

        # Проверяем user_id (если присутствует)
        file_user_id = None
        for msg in data:
            if 'user_id' in msg and msg['user_id'] is not None:
                file_user_id = msg['user_id']
                break

        if file_user_id is not None and file_user_id != current_user.id:
            flash('Этот файл принадлежит другому пользователю. Импорт отменён.', 'danger')
            return redirect('/profile')

        # Если user_id отсутствует или совпадает — импортируем с привязкой к текущему
        session_id = str(uuid.uuid4())
        history_db.save_history(current_user.id, session_id, data)
        flash(f'Импортировано {len(data)} сообщений.', 'success')
    except json.JSONDecodeError:
        flash('Некорректный JSON-файл.', 'danger')
    except Exception as e:
        flash(f'Ошибка импорта: {e}', 'danger')

    return redirect('/profile')

# ========== МАРШРУТЫ ДЛЯ АНОНИМНЫХ ПОЛЬЗОВАТЕЛЕЙ (СОХРАНЕНИЕ/ЗАГРУЗКА СЕССИИ) ==========


def _sanitize_history_filename(filename, session_id):
    """
    Безопасное имя файла истории: только имя, без путей (basename),
    и только с расширением .json. Иначе - имя по умолчанию.
    """
    filename = (filename or '').strip()
    base = os.path.basename(filename)
    if not base.endswith('.json'):
        base = f'history_{session_id[:8]}.json'
    return base


@app.route('/save', methods=['POST'])
def save_history():
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify({'error': 'Сессия не найдена'}), 400
    session = get_session(session_id)
    if not session.history:
        return jsonify({'error': 'История пуста'}), 400
    filename = request.form.get('filename', '').strip()
    filename = _sanitize_history_filename(filename, session_id)
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
    filename = _sanitize_history_filename(filename, session_id)
    session = get_session(session_id)
    try:
        old_history = session.history.copy()
        session.load(filename)
        if not session.history:
            session.history = old_history
            return jsonify({'error': 'Файл пуст'}), 400
        if session.user_id:
            history_db.save_history(
                session.user_id, session_id, session.history)
        return jsonify({'message': f'История загружена из {filename} ({len(session.history)} сообщений)'})
    except FileNotFoundError:
        return jsonify({'error': f'Файл {filename} не найден'}), 404
    except Exception as e:
        return jsonify({'error': f'Ошибка: {str(e)}'}), 500

# ========== ВСПОМОГАТЕЛЬНЫЕ МАРШРУТЫ ==========


@app.route('/status')
def status():
    session_id = request.cookies.get('session_id')
    if not session_id or session_id not in sessions:
        return jsonify({'restoring': False})
    return jsonify({'restoring': sessions[session_id].restoring})


@app.route('/send', methods=['POST'])
def send():
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify({'error': 'Сессия не найдена'}), 400
    session = get_session(session_id)
    user_message = request.form.get('user_message', '').strip()
    if not user_message:
        return jsonify({'error': 'Сообщение пустое'}), 400

    # Код вопроса генерируется на клиенте (JS); по нему точечно resolve.
    qid = request.form.get('qid') or str(uuid.uuid4())
    user_id = current_user.id if current_user.is_authenticated else None

    # Страховка на случай недоступности YDB: вопрос уже лежит в localStorage (JS),
    # здесь — попытка продублировать в облако. Если YDB недоступна — вопрос ждёт в localStorage.
    try:
        pending_db.save_pending_question(
            session_id=session_id,
            user_id=user_id,
            question_text=user_message,
            qid=qid,
        )
    except Exception as e:
        print(f"[PENDING] YDB недоступна, вопрос останется в localStorage: {e}")

    session.add_user_message(user_message)
    if session.user_id:
        threading.Thread(
            target=save_message_async,
            args=(session.user_id, session_id, "user", user_message),
            daemon=True
        ).start()

    try:
        response_text = ai_client.ask(session.history, timeout=ai_request_timeout)
        session.add_assistant_message(response_text)
        if session.user_id:
            threading.Thread(
                target=save_message_async,
                args=(session.user_id, session_id, "assistant", response_text),
                daemon=True
            ).start()
        # Ответ получен — разрешаем конкретную запись (status -> resolved)
        try:
            pending_db.resolve_pending_question(session_id, qid)
        except Exception as e:
            print(f"[PENDING] Не удалось resolve в YDB: {e}")
        return jsonify({'reply': response_text, 'qid': qid})
    except openai.APITimeoutError as e:
        try:
            pending_db.set_error_reason(session_id, qid, 'timeout')
        except Exception:
            pass
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Таймаут ожидания ответа: {e}'}), 504
    except openai.APIConnectionError as e:
        try:
            pending_db.set_error_reason(session_id, qid, 'network')
        except Exception:
            pass
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Нет соединения с AI: {e}'}), 502
    except Exception as e:
        # Вопрос остаётся в статусе pending (и в localStorage, и в YDB)
        try:
            pending_db.set_error_reason(session_id, qid, 'ai_error')
        except Exception:
            pass
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ========== НЕОТВЕЧЕННЫЕ ВОПРОСЫ ==========


@app.route('/api/pending_sync', methods=['POST'])
def pending_sync():
    """Принимает список висящих вопросов из localStorage клиента и идемпотентно
    докладывает их в YDB (по неизменному qid). Вызывается JS при загрузке и после online."""
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify({'error': 'Сессия не найдена'}), 400

    try:
        data = request.get_json(silent=True) or {}
        items = data.get('items') or []
    except Exception:
        items = []

    user_id = current_user.id if current_user.is_authenticated else None
    inserted = 0
    try:
        pending_db._lazy_cleanup(24)
        for item in items:
            qid = (item.get('id') or '').strip()
            question_text = (item.get('question_text') or '').strip()
            timestamp = item.get('timestamp')
            if not qid or not question_text:
                continue
            try:
                if pending_db.save_pending_question(
                    session_id=session_id,
                    user_id=user_id,
                    question_text=question_text,
                    qid=qid,
                    timestamp=timestamp,
                ):
                    inserted += 1
            except Exception as e:
                print(f"[PENDING SYNC] Ошибка записи {qid}: {e}")
        return jsonify({'synced': inserted, 'ok': True})
    except Exception as e:
        print(f"[PENDING SYNC] Ошибка: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/retry-question', methods=['POST'])
def retry_question():
    session_id = request.cookies.get('session_id')
    if not session_id:
        flash('Сессия не найдена.', 'danger')
        return redirect('/')
    pending = pending_db.get_pending_question(session_id)
    if not pending:
        flash('Нет вопросов для повторной отправки.', 'info')
        return redirect('/')

    session = get_session(session_id)
    history = session.history if session else []
    try:
        response_text = ai_client.ask(
            history + [{"role": "user", "content": pending['question_text']}],
            timeout=ai_request_timeout,
        )
        session.add_assistant_message(response_text)
        # Разрешаем конкретную запись, а не все pending подряд
        pending_db.resolve_pending_question(session_id, pending['id'])
        flash('Ответ получен.', 'success')
    except openai.APITimeoutError:
        pending_db.set_error_reason(session_id, pending['id'], 'timeout')
        flash('Не удалось получить ответ (таймаут). Попробуйте позже.', 'danger')
    except openai.APIConnectionError:
        pending_db.set_error_reason(session_id, pending['id'], 'network')
        flash('Не удалось получить ответ (нет соединения). Попробуйте позже.', 'danger')
    except Exception as e:
        pending_db.set_error_reason(session_id, pending['id'], 'ai_error')
        flash(f'Не удалось получить ответ. Попробуйте позже.', 'danger')

    return redirect('/')


@app.route('/pending-dismiss', methods=['POST'])
def pending_dismiss():
    session_id = request.cookies.get('session_id')
    if not session_id:
        return redirect('/')
    qid = request.form.get('qid', '').strip()
    if not qid:
        flash('Не указан вопрос.', 'info')
        return redirect('/')
    try:
        # resolved + error_reason='dismissed' — вопрос не воскреснет в выборках pending
        pending_db.resolve_pending_question(session_id, qid, reason='dismissed')
    except Exception as e:
        print(f"[PENDING DISMISS] Ошибка: {e}")
    return redirect('/')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=app_debug, host='0.0.0.0', port=port)
