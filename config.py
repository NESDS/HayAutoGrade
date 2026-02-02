import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Telegram Bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# СберЧат конфигурация (Dialog Bot SDK)
SBERCHAT_TOKEN = os.getenv("SBERCHAT_TOKEN")
SBERCHAT_ENDPOINT = os.getenv("SBERCHAT_ENDPOINT", "epbotsift.sberchat.sberbank.ru")
SBERCHAT_IS_SECURE = os.getenv("SBERCHAT_IS_SECURE", "True").lower() in ("true", "1", "yes")
SBERCHAT_ROOT_CERT = os.getenv("SBERCHAT_ROOT_CERT", "")

# GigaChat конфигурация
GIGACHAT_AUTH = os.getenv("GIGACHAT_AUTH")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_CORP")
GIGACHAT_API_URL = os.getenv("GIGACHAT_API_URL", "https://gigachat.devices.sberbank.ru/api/v1/chat/completions")
GIGACHAT_TOKEN_URL = os.getenv("GIGACHAT_TOKEN_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat-2-Max")

# Настройки для разных типов задач LLM
# Используются для GigaChat и внутренних агентов обработки

LLM_TASK_SETTINGS = {
    # Верификация ответов - требует высокой точности
    'verification': {
        'temperature': 0.2,
        'max_tokens': 16000
    },
    
    # Классификация - требует точности и краткости
    'classification': {
        'temperature': 0.1,
        'max_tokens': 2000
    },
    
    # Компиляция ответов - баланс точности и структурированности
    'compilation': {
        'temperature': 0.3,
        'max_tokens': 10000
    },
    
    # Объяснение конфликтов - может быть более креативным
    'explanation': {
        'temperature': 0.5,
        'max_tokens': 8000
    },
    
    # Функциональный анализ - требует точности
    'functionality': {
        'temperature': 0.2,
        'max_tokens': 12000
    }
}

# Включение AI верификации
ENABLE_AI_VERIFICATION = os.getenv("ENABLE_AI_VERIFICATION", "True").lower() in ("true", "1", "yes")



MESSAGES = {
    'welcome': """Опрос из {total} вопросов.

Нажмите "Начать" для старта.""",
    
    'question_template': """Вопрос {current} из {total}:

{question}""",
    

} 