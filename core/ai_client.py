import openai
import time


class AIClient():
    def __init__(self, api_key, base_url, project, prompt_id):
        self.client = openai.OpenAI(api_key,
                                    base_url,
                                    project)
        self.prompt_id = prompt_id

    def ask(self, history, retries=3):
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
                time.sleep(1*retries)
                continue
        return answer
