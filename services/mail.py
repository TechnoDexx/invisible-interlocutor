# services/mail.py
from flask_mail import Message
import secrets


class MailService:
    def __init__(self, app, users_db, mail):
        self.app = app
        self.users_db = users_db
        self.mail = mail

    def send_email(self, to, subject, body, html=None):
        """Отправляет письмо через Flask-Mail."""
        try:
            msg = Message(subject=subject,
                          recipients=[to],
                          body=body,
                          html=html)
            self.mail.send(msg)
            return True
        except Exception as e:
            print(f"[MailService] Ошибка отправки: {e}")
            return False

    def send_verification_email(self, user):
        token = secrets.token_urlsafe(32)
        self.users_db.set_verification_token(user.user_id, token)
        confirm_url = f"{self.app.config['BASE_URL']}/verify-email/{token}"
        subject = "Подтверждение email"
        body = f"""
Здравствуйте, {user.username}!

Подтвердите свой email, перейдя по ссылке:
{confirm_url}

Ссылка действительна 24 часа. Если вы не регистрировались, проигнорируйте это письмо.
"""
        html = f"""
<p>Здравствуйте, {user.username}!</p>
<p>Подтвердите свой email, перейдя по ссылке:</p>
<p><a href="{confirm_url}">{confirm_url}</a></p>
<p>Ссылка действительна 24 часа. Если вы не регистрировались, проигнорируйте это письмо.</p>
"""
        return self.send_email(user.email, subject, body, html)

    def send_reset_password_email(self, user):
        token = secrets.token_urlsafe(32)
        self.users_db.set_reset_token(user.email, token)
        reset_url = f"{self.app.config['BASE_URL']}/reset-password/{token}"
        subject = "Сброс пароля"
        body = f"""
Здравствуйте, {user.username}!

Для сброса пароля перейдите по ссылке:
{reset_url}

Ссылка действительна 1 час. Если вы не запрашивали сброс, проигнорируйте это письмо.
"""
        html = f"""
<p>Здравствуйте, {user.username}!</p>
<p>Для сброса пароля перейдите по ссылке:</p>
<p><a href="{reset_url}">{reset_url}</a></p>
<p>Ссылка действительна 1 час. Если вы не запрашивали сброс, проигнорируйте это письмо.</p>
"""
        return self.send_email(user.email, subject, body, html)

    def send_email_change_confirmation(self, user, new_email, token):
        confirm_url = f"{self.app.config['BASE_URL']}/confirm-email-change/{token}"
        subject = "Подтверждение смены email"
        body = f"""
Здравствуйте, {user.username}!

Вы запросили смену email на {new_email}. Для подтверждения перейдите по ссылке:
{confirm_url}

Ссылка действительна 24 часа. Если вы не запрашивали смену email, проигнорируйте это письмо.
"""
        html = f"""
<p>Здравствуйте, {user.username}!</p>
<p>Вы запросили смену email на <strong>{new_email}</strong>.</p>
<p>Для подтверждения перейдите по ссылке:</p>
<p><a href="{confirm_url}">{confirm_url}</a></p>
<p>Ссылка действительна 24 часа. Если вы не запрашивали смену email, проигнорируйте это письмо.</p>
"""
        return self.send_email(new_email, subject, body, html)