# services/mail.py
import os
import secrets
import datetime
from threading import Thread
from flask import current_app
from flask_mail import Message, Mail


class MailService:
    def __init__(self, app=None, users_db=None):
        self.app = app
        self.users_db = users_db
        self.mail = None
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        self.app = app
        app.config.setdefault('MAIL_SERVER', os.getenv(
            'MAIL_SERVER', 'smtp.yandex.ru'))
        app.config.setdefault('MAIL_PORT', int(os.getenv('MAIL_PORT', 587)))
        app.config.setdefault('MAIL_USE_TLS', os.getenv(
            'MAIL_USE_TLS', 'true').lower() in ('true', '1', 'yes'))
        app.config.setdefault('MAIL_USE_SSL', os.getenv(
            'MAIL_USE_SSL', 'false').lower() in ('true', '1', 'yes'))
        app.config.setdefault('MAIL_USERNAME', os.getenv('MAIL_USERNAME'))
        app.config.setdefault('MAIL_PASSWORD', os.getenv('MAIL_PASSWORD'))
        app.config.setdefault('MAIL_DEFAULT_SENDER',
                              os.getenv('MAIL_DEFAULT_SENDER'))
        app.config.setdefault('MAIL_VERIFICATION_TOKEN_EXPIRE_HOURS', 24)
        app.config.setdefault('MAIL_RESET_TOKEN_EXPIRE_HOURS', 1)
        self.mail = Mail(app)

    def _send_async_email(self, msg):
        with self.app.app_context():
            try:
                self.mail.send(msg)
            except Exception as e:
                current_app.logger.error(f"Ошибка отправки письма: {e}")

    def send_email(self, subject, recipients, body=None, html=None):
        if not recipients:
            return
        msg = Message(subject, recipients=recipients, body=body, html=html)
        Thread(target=self._send_async_email, args=(msg,)).start()

    def generate_verification_token(self):
        return secrets.token_urlsafe(32)

    def generate_reset_token(self):
        return secrets.token_urlsafe(32)

    def send_verification_email(self, user):
        if not user.email:
            current_app.logger.warning(
                f"Нет email для подтверждения: user_id={user.id}")
            return False
        if not self.users_db:
            current_app.logger.error("users_db не передан в MailService")
            return False

        token = self.generate_verification_token()
        self.users_db.set_verification_token(user.id, token)

        base_url = self.app.config.get('BASE_URL', 'http://localhost:8080')
        verify_url = f"{base_url}/verify-email/{token}"
        expire_hours = self.app.config['MAIL_VERIFICATION_TOKEN_EXPIRE_HOURS']

        html = f"""
        <p>Здравствуйте, {user.username}!</p>
        <p>Для подтверждения email перейдите по ссылке:</p>
        <a href="{verify_url}">{verify_url}</a>
        <p>Ссылка действительна {expire_hours} ч.</p>
        <p>С уважением,<br>Незримый собеседник</p>
        """
        self.send_email(
            subject='Подтверждение email',
            recipients=[user.email],
            body=f"Ссылка: {verify_url}",
            html=html
        )
        return True

    def send_reset_password_email(self, user):
        if not user.email:
            current_app.logger.warning(
                f"Нет email для сброса: user_id={user.id}")
            return False
        if not self.users_db:
            current_app.logger.error("users_db не передан в MailService")
            return False

        token = self.generate_reset_token()
        self.users_db.set_reset_token(user.email, token)

        base_url = self.app.config.get('BASE_URL', 'http://localhost:8080')
        reset_url = f"{base_url}/reset-password/{token}"
        expire_hours = self.app.config['MAIL_RESET_TOKEN_EXPIRE_HOURS']

        html = f"""
        <p>Здравствуйте, {user.username}!</p>
        <p>Для сброса пароля перейдите по ссылке:</p>
        <a href="{reset_url}">{reset_url}</a>
        <p>Ссылка действительна {expire_hours} ч.</p>
        <p>С уважением,<br>Незримый собеседник</p>
        """
        self.send_email(
            subject='Сброс пароля',
            recipients=[user.email],
            body=f"Ссылка: {reset_url}",
            html=html
        )
        return True
