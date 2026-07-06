import openai
import time


class AIClient():
    def __init__(self, api_key, base_url, project, prompt_id):
        if not api_key:
            raise ValueError("API key is required")
        if not base_url:
            raise ValueError("Base URL is required")
        if not project:
            raise ValueError("Project is required")
        if not prompt_id:
            raise ValueError("Prompt ID is required")
        self.client = openai.OpenAI(api_key,
                                    base_url,
                                    project)
        self.prompt_id = prompt_id

    def ask(self, history, retries=3):
        answer = None
        for attempt in range(retries):
            try:
                response = self.client.responses.create(
                    prompt={"id": self.prompt_id},
                    input=history
                )
                answer = response.output_text
            except Exception as e:
                if attempt == retries-1:
                    raise
                time.sleep(1*attempt)
                continue
        return answer
