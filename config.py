import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Telegram Bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# GigaChat конфигурация
GIGACHAT_AUTH = os.getenv("GIGACHAT_AUTH")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_CORP")
GIGACHAT_API_URL = os.getenv("GIGACHAT_API_URL", "https://gigachat.devices.sberbank.ru/api/v1/chat/completions")
GIGACHAT_TOKEN_URL = os.getenv("GIGACHAT_TOKEN_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat-2-Max")

# OpenAI конфигурация
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-chat-latest")
OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")

# Настройки верификации
VERIFICATION_TEMPERATURE = float(os.getenv("VERIFICATION_TEMPERATURE", "0.3"))
VERIFICATION_MAX_TOKENS = int(os.getenv("VERIFICATION_MAX_TOKENS", "10000"))
ENABLE_AI_VERIFICATION = os.getenv("ENABLE_AI_VERIFICATION", "True").lower() in ("true", "1", "yes")



MESSAGES = {
    'welcome': """Опрос из {total} вопросов.

Нажмите "Начать" для старта.""",
    
    'question_template': """Вопрос {current} из {total}:

{question}""",
    

} 