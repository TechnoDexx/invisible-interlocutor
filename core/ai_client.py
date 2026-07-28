import openai
import time


class AIClient():
    """
    Клиент для взаимодействия с AI через OpenAI-совместимый API.
    Поддерживает фильтрацию истории (только role и content),
    повторные попытки при сбоях и таймаут запроса.
    """

    def __init__(self, api_key, base_url, project, prompt_id):
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
        """
        # Фильтруем историю: оставляем только role и content
        filtered_history = []
        for msg in history:
            if isinstance(msg, dict):
                filtered_msg = {
                    "role": msg.get("role"),
                    "content": msg.get("content")
                }
                if filtered_msg["role"] and filtered_msg["content"] is not None:
                    filtered_history.append(filtered_msg)

        if not filtered_history:
            raise ValueError("История не содержит валидных сообщений")

        answer = None
        for attempt in range(retries):
            try:
                response = self.client.responses.create(
                    prompt={"id": self.prompt_id},
                    input=filtered_history,
                    timeout=timeout
                )
                answer = response.output_text
                break
            except Exception as e:
                if attempt == retries - 1:
                    raise
                wait = 1 * (attempt + 1)
                print(
                    f"[AIClient] Попытка {attempt+1} не удалась. Повтор через {wait}с...")
                time.sleep(wait)
                continue
        return answer
