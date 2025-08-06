TELEGRAM_BOT_TOKEN = "7260844276:AAEaneNIDohXDbfJI3vTJtaFVtETRb9YakU"


GIGACHAT_AUTH = "MjkwYjYzMjMtNDAxOS00NTBlLWIxNTAtNDUyZGI1ODA4ZmY2OmQ1NTdmN2JkLWM5MTktNDcxZi1hZTc1LWEzMTI1ODFhNjc2MA=="
GIGACHAT_SCOPE = "GIGACHAT_API_CORP"
GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
GIGACHAT_TOKEN_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_MODEL = "GigaChat-2-Max"

VERIFICATION_TEMPERATURE = 0.3
VERIFICATION_MAX_TOKENS = 10000
ENABLE_AI_VERIFICATION = True



MESSAGES = {
    'welcome': """Опрос из {total} вопросов.

Нажмите "Начать" для старта.""",
    
    'question_template': """Вопрос {current} из {total}:

{question}""",
    

} 