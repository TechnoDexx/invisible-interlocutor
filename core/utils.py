# Определяем коды цветов
class Colors:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

""" Использование
print(f"{Colors.RED}Этот текст красный{Colors.RESET}")
print(f"{Colors.GREEN}А этот зелёный{Colors.RESET}")
"""
