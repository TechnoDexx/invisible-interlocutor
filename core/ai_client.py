from dotenv import load_dotenv
class AIClient():
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv('API_KEY')
        self.base_url = os.getenv('BASE_URL')
        self.project = os.getenv('PROJECT')
        self.prompt_id = os.getenv('PROMPT_ID')
        self.client = openai.OpenAI(self.api_key,
                                    self.base_url,
                                    self.project)

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
                time.sleep(1)
                continue
        return answer
