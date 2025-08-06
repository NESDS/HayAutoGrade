import requests
import uuid

from config import (
    GIGACHAT_AUTH, GIGACHAT_SCOPE, GIGACHAT_API_URL, GIGACHAT_TOKEN_URL, GIGACHAT_MODEL,
    VERIFICATION_TEMPERATURE, VERIFICATION_MAX_TOKENS
)

class LLMService:
    def generate_response(self, messages: list) -> str:
        """Генерация ответа через ГигаЧат с получением нового токена"""
        try:
            token_headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
                'RqUID': str(uuid.uuid4()),
                'Authorization': f'Basic {GIGACHAT_AUTH}'
            }
            
            token_data = f'scope={GIGACHAT_SCOPE}'
            
            response = requests.post(GIGACHAT_TOKEN_URL, headers=token_headers, data=token_data, verify=False)
            response.raise_for_status()
            
            token_json = response.json()
            if 'access_token' not in token_json:
                raise Exception(f"Ошибка получения токена: {token_json}")
                
            token = token_json['access_token']
            
            api_headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': f'Bearer {token}'
            }
            
            payload = {
                "model": GIGACHAT_MODEL,
                "messages": messages,
                "temperature": VERIFICATION_TEMPERATURE,
                "max_tokens": VERIFICATION_MAX_TOKENS,
                "stream": False
            }
            
            response = requests.post(GIGACHAT_API_URL, headers=api_headers, json=payload, verify=False)
            response.raise_for_status()
            
            response_json = response.json()
            if 'choices' not in response_json or not response_json['choices']:
                raise Exception(f"Некорректный ответ API: {response_json}")
                
            return response_json['choices'][0]['message']['content']
            
        except Exception as e:
            print(f"❌ Ошибка LLM API: {e}")
            return "Извините, произошла ошибка при обработке запроса. Попробуйте позже."

llm_service = LLMService() 