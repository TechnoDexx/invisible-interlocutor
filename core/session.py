import sys
class Session():
    def __init__(self,filename,history=[]):
        self.history=self.history
        self.filename=filename
    # ===== БЕЗОПАСНЫЙ ВВОД ДЛЯ DOCKER =====
    def _safe_input(prompt=""):
        """Читает строку из stdin, корректно обрабатывая кодировку."""
        if prompt:
            sys.stdout.write(prompt)
            sys.stdout.flush()
        raw = sys.stdin.buffer.readline()
        try:
            return raw.decode('utf-8').rstrip('\n')
        except UnicodeDecodeError:
            return raw.decode('utf-8', errors='replace').rstrip('\n')
        
    def add_user_message(self,prompt_text):
        """добавляет сообщения пользователя"""
        self.history.append({"role": "user", "content": prompt_text})
    
    def add_assistant_message(self,answer_text):
        """добавляет ответ ассистента"""
        self.history.append({"role": "assistant", "content": answer_text})
    
    def clear(self):
        """Очищает историю"""
        self.history=None
    
    def save(self,filename):
        """Сохраняет историю в JSON
        (если имя не указано - запрашивает через input)"""
        if not self.history:
            print("История пуста, сохранять нечего.")
        return
        if self.filename is None:
            self.filename = safe_input("Введите имя файла (c расширением): ")
        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)
        print(f"История сохранена в {self.filename}")
    
    def load(self,filename):
        """Загружает из JSON (с проверками и
        вопросом о замене)"""
        
                        
    def print(self):
        """Печатает историю в консоль"""
        if not self.history:
            print("История пуста.")
        return
        print("\n=== ИСТОРИЯ ДИАЛОГА ===")
        for i, msg in enumerate(history, 1):
            role = "Вы" if msg["role"] == "user" else "Собеседник"
            print(f"{i}. {role}: {msg['content']}")
            print("=== КОНЕЦ ИСТОРИИ ===\n")

        
    def is_empty(self):
        """Проверяет, пуста ли история"""
    
    def __len__(self):
        return len(self.history)           