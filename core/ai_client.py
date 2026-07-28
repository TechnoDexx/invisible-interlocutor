import openai
import time
import httpx  # добавляем для явного указания типа ошибки (опционально)


class AIClient():
    """
    Клиент для взаимодействия с AI через OpenAI-совместимый API.
    Поддерживает фильтрацию истории (только role и content),
    повторные попытки при сбоях и таймаут запроса.
    """

    def __init__(self, api_key, base_url, project, prompt_id):
        """
        Инициализация клиента.
        Все параметры обязательны и проверяются.
        """
        if not api_key:
            raise ValueError("API key is required")
        if not base_url:
            raise ValueError("Base URL is required")
        if not project:
            raise ValueError("Project is required")
        if not prompt_id:
            raise ValueError("Prompt ID is required")

        self.client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            project=project
        )
        self.prompt_id = prompt_id

    def ask(self, history, retries=10, timeout=10):
        """
        Отправляет историю диалога в модель и возвращает ответ.

        Аргументы:
            history (list): список сообщений (словарей) с полями role, content, и возможно другими.
            retries (int): количество попыток при сбоях.
            timeout (int): таймаут запроса в секундах.

        Возвращает:
            str: ответ модели.

        Исключения:
            ValueError: если история пуста после фильтрации.
            APIConnectionError: если после всех попыток соединение не установлено.
        """
        # 1. Фильтруем историю: оставляем только role и content
        filtered_history = []
        for msg in history:
            if isinstance(msg, dict):
                filtered_msg = {
                    "role": msg.get("role"),
                    "content": msg.get("content")
                }
                # Пропускаем сообщения с пустыми role или content
                if filtered_msg["role"] and filtered_msg["content"] is not None:
                    filtered_history.append(filtered_msg)
            # Если msg не словарь — игнорируем (защита от битых данных)

        # 2. Проверяем, что история не пуста
        if not filtered_history:
            raise ValueError("История не содержит валидных сообщений")

        # 3. Цикл повторных попыток
        answer = None
        for attempt in range(retries):
            try:
                # Отправляем запрос с таймаутом
                response = self.client.responses.create(
                    prompt={"id": self.prompt_id},
                    input=filtered_history,
                    timeout=timeout  # явный таймаут на запрос (в секундах)
                )
                answer = response.output_text
                break  # успешно — выходим

            except Exception as e:
                # Если это последняя попытка — пробрасываем ошибку выше
                if attempt == retries - 1:
                    raise

                # Иначе ждём с увеличивающейся паузой
                # (1, 2, 3, 4, ... секунд)
                wait = 1 * (attempt + 1)
                print(f"[AIClient] Попытка {attempt+1} не удалась. Повтор через {wait}с...")
                time.sleep(wait)
                continue

        return answer