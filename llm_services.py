#!/usr/bin/env python3
"""
Модуль для работы с различными LLM сервисами
"""

import requests
import uuid
from abc import ABC, abstractmethod
from typing import List, Dict

from config import (
    GIGACHAT_AUTH, GIGACHAT_SCOPE, GIGACHAT_API_URL, GIGACHAT_TOKEN_URL, GIGACHAT_MODEL,
    LLM_TASK_SETTINGS
)

class BaseLLMService(ABC):
    """Базовый класс для всех LLM сервисов"""
    
    @abstractmethod
    def generate_response(self, messages: List[Dict], task_type: str = 'verification') -> str:
        """
        Генерация ответа от LLM
        
        Args:
            messages: Список сообщений для LLM
            task_type: Тип задачи ('verification', 'classification', 'compilation', 'explanation', 'functionality')
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Название сервиса"""
        pass
    
    @property
    @abstractmethod
    def emoji(self) -> str:
        """Эмодзи для отображения"""
        pass

class GigaChatService(BaseLLMService):
    """Сервис для работы с GigaChat"""
    
    @property
    def name(self) -> str:
        return "GigaChat"
    
    @property  
    def emoji(self) -> str:
        return "🇷🇺"
    
    def generate_response(self, messages: List[Dict], task_type: str = 'verification') -> str:
        """Генерация ответа через ГигаЧат с получением нового токена"""
        try:
            # Получаем настройки для типа задачи
            settings = LLM_TASK_SETTINGS.get(task_type, LLM_TASK_SETTINGS['verification'])
            
            # Получаем токен
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
            
            # Отправляем запрос к API
            api_headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': f'Bearer {token}'
            }
            
            payload = {
                "model": GIGACHAT_MODEL,
                "messages": messages,
                "temperature": settings['temperature'],
                "max_tokens": settings['max_tokens'],
                "stream": False
            }
            
            response = requests.post(GIGACHAT_API_URL, headers=api_headers, json=payload, verify=False)
            response.raise_for_status()
            
            response_json = response.json()
            if 'choices' not in response_json or not response_json['choices']:
                raise Exception(f"Некорректный ответ API: {response_json}")
                
            return response_json['choices'][0]['message']['content']
            
        except Exception as e:
            print(f"❌ Ошибка GigaChat API: {e}")
            return "Извините, произошла ошибка при обработке запроса GigaChat. Попробуйте позже."

class LLMFactory:
    """Фабрика для создания LLM сервисов"""
    
    _services = {
        'gigachat': GigaChatService
    }
    
    @classmethod
    def create_service(cls, service_type: str) -> BaseLLMService:
        """Создать LLM сервис по типу"""
        service_class = cls._services.get(service_type.lower())
        if service_class:
            return service_class()
        else:
            print(f"⚠️ Неизвестный тип LLM: {service_type}, используем GigaChat")
            return GigaChatService()
    
    @classmethod
    def get_available_services(cls) -> Dict[str, BaseLLMService]:
        """Получить список доступных сервисов"""
        return {name: service_class() for name, service_class in cls._services.items()}

# Создаем экземпляр для обратной совместимости
llm_service = GigaChatService()
