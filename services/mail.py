# services/mail.py
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import url_for
import secrets


class MailService:
    def __init__(self, app, users_db):
        self.app = app
        self.users_db = users_db
        self.smtp_host = os.getenv('SMTP_HOST', 'smtp.yandex.ru')
        self.smtp_port = int(os.getenv('SMTP_PORT', 465))
        self.smtp_user = os.getenv('SMTP_USER')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.from_email = os.getenv('SMTP_FROM', self.smtp_user)
        self.use_ssl = os.getenv('SMTP_USE_SSL', 'true').lower() == 'true'

    def send_email(self, to_email, subject, body_text, body_html=None):
        """Базовый метод отправки письма."""
        if not self.smtp_user or not self.smtp_password:
            print("[MailService] SMTP не настроен (проверьте переменные окружения)")
            return False

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = to_email

            part_text = MIMEText(body_text, 'plain', 'utf-8')
            msg.attach(part_text)

            if body_html:
                part_html = MIMEText(body_html, 'html', 'utf-8')
                msg.attach(part_html)

            if self.use_ssl:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
                    server.login(self.smtp_user, self.smtp_password)
                    server.sendmail(self.from_email, [
                                    to_email], msg.as_string())
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    server.starttls()
                    server.login(self.smtp_user, self.smtp_password)
                    server.sendmail(self.from_email, [
                                    to_email], msg.as_string())
            return True
        except Exception as e:
            print(f"[MailService] Ошибка отправки письма: {e}")
            return False

    def send_verification_email(self, user):
        """Отправка письма для подтверждения email при регистрации."""
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
        html = body.replace('\n', '<br>')
        return self.send_email(user.email, subject, body, html)

    def send_reset_password_email(self, user):
        """Отправка письма для сброса пароля."""
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
        html = body.replace('\n', '<br>')
        return self.send_email(user.email, subject, body, html)

    # ========== НОВЫЙ МЕТОД ДЛЯ СМЕНЫ EMAIL (через токен) ==========
    def send_email_change_confirmation(self, user, new_email, token):
        """Отправка письма для подтверждения смены email."""
        confirm_url = f"{self.app.config['BASE_URL']}/confirm-email-change/{token}"
        subject = "Подтверждение смены email"
        body = f"""
Здравствуйте, {user.username}!

Вы запросили смену email на {new_email}. Для подтверждения перейдите по ссылке:
{confirm_url}

Ссылка действительна 24 часа. Если вы не запрашивали смену email, проигнорируйте это письмо.
"""
        html = body.replace('\n', '<br>')
        return self.send_email(new_email, subject, body, html)
