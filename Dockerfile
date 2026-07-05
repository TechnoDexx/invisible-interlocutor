FROM python:3.12-slim

# Устанавливаем локаль и переменные для корректной работы с UTF-8
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONIOENCODING=utf-8

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем requirements.txt отдельно для кэширования зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN python -m pip install --no-cache-dir -r requirements.txt

# Копируем весь код проекта
COPY . .

# Опционально: метаданные образа
LABEL Name=invisibleinterlocutor \
      Version=0.0.1 \
      Description="Незримый собеседник — консольный ИИ-агент для поддержки"

# Точка входа — запуск main.py
ENTRYPOINT ["python", "main.py"]