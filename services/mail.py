# services/mail.py
import os
import secrets
from threading import Thread
from flask import current_app, render_template
from flask_mail import Message
from datetime import datetime, timedelta
import re

class MailService:
    """Сервис для работы с электронной почтой: подтверждение email, восстановление пароля."""

    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Инициализация с приложением Flask."""
        self.app = app
        # Настройки SMTP
        app.config.setdefault('MAIL_SERVER', os.getenv('MAIL_SERVER', 'smtp.yandex.ru'))
        app.config.setdefault('MAIL_PORT', int(os.getenv('MAIL_PORT', 587)))
        app.config.setdefault('MAIL_USE_TLS', os.getenv('MAIL_USE_TLS', 'true').lower() in ('true', '1', 'yes'))
        app.config.setdefault('MAIL_USE_SSL', os.getenv('MAIL_USE_SSL', 'false').lower() in ('true', '1', 'yes'))
        app.config.setdefault('MAIL_USERNAME', os.getenv('MAIL_USERNAME'))
        app.config.setdefault('MAIL_PASSWORD', os.getenv('MAIL_PASSWORD'))
        app.config.setdefault('MAIL_DEFAULT_SENDER', os.getenv('MAIL_DEFAULT_SENDER'))
        app.config.setdefault('MAIL_VERIFICATION_TOKEN_EXPIRE_HOURS', 24)
        app.config.setdefault('MAIL_RESET_TOKEN_EXPIRE_HOURS', 1)

        # Инициализация Flask-Mail
        from flask_mail import Mail
        self.mail = Mail(app)

    def _send_async_email(self, msg):
        """Асинхронная отправка письма."""
        with self.app.app_context():
            try:
                self.mail.send(msg)
            except Exception as e:
                current_app.logger.error(f"Ошибка отправки письма: {e}")

    def send_email(self, subject, recipients, body=None, html=None):
        """
        Отправляет письмо асинхронно.
        subject — тема письма.
        recipients — список получателей.
        body — текст письма (plain text).
        html — HTML-версия письма.
        """
        if not recipients:
            return
        msg = Message(subject, recipients=recipients, body=body, html=html)
        Thread(target=self._send_async_email, args=(msg,)).start()

    def generate_verification_token(self, user_id):
        """Генерирует токен для подтверждения email (сохраняется в users.py)."""
        return secrets.token_urlsafe(32)

    def generate_reset_token(self, user_id):
        """Генерирует токен для сброса пароля."""
        return secrets.token_urlsafe(32)

    def send_verification_email(self, user):
        """
        Отправляет письмо с подтверждением email.
        user — объект User (должен содержать email, id, username).
        """
        if not user.email:
            current_app.logger.warning(f"Попытка отправить подтверждение без email: user_id={user.id}")
            return False

        token = self.generate_verification_token(user.id)
        # Здесь нужно сохранить токен в users.py (добавим позже)
        # Пока просто формируем ссылку
        verify_url = f"{self.app.config.get('BASE_URL', 'http://localhost:8080')}/verify-email/{token}"
        html = f"""
        <p>Здравствуйте, {user.username}!</p>
        <p>Для подтверждения вашего email перейдите по ссылке:</p>
        <a href="{verify_url}">{verify_url}</a>
        <p>Ссылка действительна в течение {self.app.config['MAIL_VERIFICATION_TOKEN_EXPIRE_HOURS']} часов.</p>
        <p>С уважением,<br>Незримый собеседник</p>
        """
        self.send_email(
            subject='Подтверждение email',
            recipients=[user.email],
            body=f"Для подтверждения email перейдите по ссылке: {verify_url}",
            html=html
        )
        return True

    def send_reset_password_email(self, user):
        """
        Отправляет письмо для сброса пароля.
        user — объект User.
        """
        if not user.email:
            current_app.logger.warning(f"Попытка сброса пароля без email: user_id={user.id}")
            return False

        token = self.generate_reset_token(user.id)
        reset_url = f"{self.app.config.get('BASE_URL', 'http://localhost:8080')}/reset-password/{token}"
        html = f"""
        <p>Здравствуйте, {user.username}!</p>
        <p>Для сброса пароля перейдите по ссылке:</p>
        <a href="{reset_url}">{reset_url}</a>
        <p>Ссылка действительна в течение {self.app.config['MAIL_RESET_TOKEN_EXPIRE_HOURS']} часа.</p>
        <p>Если вы не запрашивали сброс пароля, просто проигнорируйте это письмо.</p>
        <p>С уважением,<br>Незримый собеседник</p>
        """
        self.send_email(
            subject='Сброс пароля',
            recipients=[user.email],
            body=f"Для сброса пароля перейдите по ссылке: {reset_url}",
            html=html
        )
        return True