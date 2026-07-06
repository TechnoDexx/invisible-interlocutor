class Session():
    def __init__(self,history=[]):
        self.history=self.history
    
    def add_user_message(self,prompt_text):
        """добавляет сообщения пользователя"""
        
    
    def add_assistant_message(self,answer_text):
        """добавляет ответ ассистента"""
        self.history.append({"role": "assistant", "content": answer_text})
    
    def clear(self):
        """Очищает историю"""
        self.history=None
    
    def save(self,filename):
        """Сохраняет историю в JSON
        (если имя не указано - запрашивает через input)"""
    
    def load(self,filename):
        """Загружает из JSON (с проверками и
        вопросом о замене)"""
                        
    def print(self):
        """Печатает историю в консоль"""
        
    def is_empty(self):
        """Проверяет, пуста ли история"""
    
    def __len__(self):
        return len(self.history)           