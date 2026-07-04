class AiClient():
    def __init__(self,api_key, base_url, project, prompt_id, retries, delay,history):
        self.api_key=api_key
        self.base_url=base_url
        self.project=project
        self.prompt_id=prompt_id
        self.retries=retries
        self.delay=delay
        self.history=history