from typing import Dict, List, Tuple
from llm_services import BaseLLMService

class VerificationAgent:
    def __init__(self, llm_service: BaseLLMService):
        self.llm_service = llm_service
    
    def process_answer(self, question_data: Dict, user_answer: str, conversation: List[str], user_portrait: str = None) -> Tuple[bool, str]:
        """Обработка ответа пользователя: проверка + уточнение если нужно"""
        
        # Формируем структурированный диалог
        dialog_text = ""
        
        # Добавляем портрет пользователя, если есть
        if user_portrait:
            dialog_text += f"КОНТЕКСТ О ПОЛЬЗОВАТЕЛЕ (предыдущие ответы):\n{user_portrait}\n\n"
            dialog_text += "ВАЖНО: Используй контекст предыдущих ответов для помощи пользователю:\n"
            dialog_text += "- Ссылайся на уже известную информацию для более точных вопросов\n"
            dialog_text += "- Если в предыдущих ответах есть информация, релевантная текущему вопросу - подсвети это пользователю\n"
            dialog_text += "- Помогай пользователю, предлагая варианты на основе его предыдущих ответов\n"
            dialog_text += "- Проверяй логичность новых ответов относительно предыдущих\n\n"
        
        dialog_text += "ТЕКУЩИЙ ДИАЛОГ ПО ВОПРОСУ:\n"
        
        # Добавляем первоначальный вопрос бота
        dialog_text += f"Бот: {question_data['question']}\n"
        
        # Добавляем весь диалог (включая текущий ответ пользователя, который уже в conversation)
        for i, msg in enumerate(conversation):
            if i % 2 == 0:  # четные индексы - ответы пользователя
                dialog_text += f"Пользователь: {msg}\n"
            else:  # нечетные - вопросы бота
                dialog_text += f"Бот: {msg}\n"
        
        # Используем готовый промпт из таблицы и подставляем диалог
        prompt = question_data['verification_instruction'].format(dialog=dialog_text)

        print("🔍 ВЕРИФИКАТОР - Отправляю в LLM:")
        print("-" * 50)
        print(prompt)
        print("-" * 50)
        
        messages = [{"role": "user", "content": prompt}]
        response = self.llm_service.generate_response(messages, task_type='verification')
        
        print("✅ ОТВЕТ LLM:")
        print(response)
        print("-" * 50)
        
        # Простой парсинг
        if "ПРИНЯТО" in response.upper():
            return True, "Отлично!"
        else:
            return False, response.replace("УТОЧНИ:", "").strip()

class AnswerCompilerAgent:
    def __init__(self, llm_service: BaseLLMService):
        self.llm_service = llm_service
    
    def create_full_answer(self, question_data: Dict, conversation: List[str], user_portrait: str = None) -> str:
        """Создание полного ответа из диалога"""
        # Собираем только ответы пользователя из диалога
        user_answers = []
        for i, msg in enumerate(conversation):
            if i % 2 == 0:  # четные индексы - ответы пользователя
                user_answers.append(msg)
        
        # Формируем структурированный диалог для LLM
        dialog_for_llm = ""
        
        # Добавляем портрет пользователя, если есть
        if user_portrait:
            dialog_for_llm += f"КОНТЕКСТ О ПОЛЬЗОВАТЕЛЕ (предыдущие ответы):\n{user_portrait}\n\n"
        
        dialog_for_llm += "ДИАЛОГ:\n"
        for i, msg in enumerate(conversation):
            if i % 2 == 0:  # четные индексы - ответы пользователя
                dialog_for_llm += f"Пользователь: {msg}\n"
            else:  # нечетные - вопросы бота
                dialog_for_llm += f"Бот: {msg}\n"
        
        prompt = f"""Пользователь отвечал на вопрос: "{question_data['question']}"

На основе этого диалога сформулируй краткий и точный итоговый ответ пользователя:

{dialog_for_llm}

Твоя задача - извлечь из диалога только суть ответа пользователя, убрав лишние слова и повторы. Ответ должен быть четким и конкретным."""

        print("📝 АГЕНТ ОТВЕТОВ - Отправляю в LLM:")
        print("-" * 50)
        print(prompt)
        print("-" * 50)

        messages = [{"role": "user", "content": prompt}]
        response = self.llm_service.generate_response(messages, task_type='compilation')
        
        print("✅ ОТВЕТ LLM:")
        print(response)
        print("-" * 50)
        
        return response.strip()

class ClassificationAgent:
    def __init__(self, llm_service: BaseLLMService):
        self.llm_service = llm_service
    
    def classify_answer(self, question_data: Dict, full_answer: str, user_portrait: str = None) -> str:
        """Классификация ответа согласно инструкции из поля Classifier"""
        
        # Проверяем, есть ли инструкция классификации
        classifier_instruction = question_data.get('classifier')
        
        if not classifier_instruction or classifier_instruction.strip() == "":
            print("🏷️ КЛАССИФИКАТОР - Инструкция пуста, возвращаю исходный ответ")
            return full_answer
        
        # Формируем промпт для классификации
        # Поддерживаем разные варианты переменных в шаблоне
        try:
            prompt = classifier_instruction.format(answer=full_answer)
        except KeyError:
            try:
                prompt = classifier_instruction.format(user_answer=full_answer)
            except KeyError:
                # Если нет подстановок, используем инструкцию как есть
                prompt = classifier_instruction
        
        # Добавляем портрет пользователя в начало промпта, если есть
        if user_portrait:
            context_instruction = "КОНТЕКСТ О ПОЛЬЗОВАТЕЛЕ (предыдущие ответы):\n"
            context_instruction += f"{user_portrait}\n\n"
            context_instruction += "ВАЖНО: Используй контекст для более точной классификации:\n"
            context_instruction += "- Учитывай должность: высокие должности (директор, CEO) → обычно высокие уровни\n"
            context_instruction += "- Учитывай должность: низкие должности (оператор, ассистент) → обычно низкие уровни\n"
            context_instruction += "- При сильном противоречии (CEO + низкий уровень): склоняйся к повышению на 1 уровень\n"
            context_instruction += "- При граничных случаях: используй контекст для выбора уровня\n\n"
            prompt = context_instruction + prompt
        
        print("🏷️ КЛАССИФИКАТОР - Отправляю в LLM:")
        print("-" * 50)
        print(prompt)
        print("-" * 50)
        
        messages = [{"role": "user", "content": prompt}]
        response = self.llm_service.generate_response(messages, task_type='classification')
        
        print("✅ ОТВЕТ LLM (КЛАССИФИКАЦИЯ):")
        print(response)
        print("-" * 50)
        
        return response.strip()

# Агенты теперь создаются с передачей llm_service в telegram_bot.py


class FunctionalityAgent:
    """Агент для генерации функционала должности на основе ответов"""
    
    def __init__(self, llm_service):
        self.llm_service = llm_service
    
    def generate_functionality(self, user_portrait: str) -> str:
        """
        Генерирует функционал должности на основе портрета пользователя
        Портрет теперь в формате: Вопрос - Полный ответ - Уровень
        """
        try:
            messages = [
                {
                    "role": "system",
                    "content": """Твоя задача - сгенерировать функционал должности на основе ответов пользователя.

ВАЖНО:
- Создай список из 5-8 основных функций должности
- Формулируй функции конкретно и профессионально
- Каждая функция - отдельный пункт списка
- Используй глаголы в инфинитиве: "Разрабатывать", "Анализировать", "Координировать"
- Основывайся только на предоставленной информации из ответов пользователя

ФОРМАТ ВХОДНЫХ ДАННЫХ:
Ты получишь структурированные ответы в формате:
Вопрос N: [текст вопроса]
→ Ответ: [полный ответ пользователя]
→ Уровень: [классификация ответа]

ПРИМЕР ВЫВОДА:
• Разрабатывать программное обеспечение на языке Python
• Участвовать в проектировании архитектуры системы
• Проводить код-ревью и тестирование
• Исправлять ошибки и оптимизировать производительность
• Участвовать в планировании спринтов
• Документировать техническую документацию

Сгенерируй функционал на основе следующих ответов пользователя:"""
                },
                {
                    "role": "user", 
                    "content": user_portrait or "Информация о должности не предоставлена"
                }
            ]
            
            functionality = self.llm_service.generate_response(messages, task_type='functionality')
            
            # Убираем возможные лишние элементы форматирования
            functionality = functionality.strip()
            
            return functionality
            
        except Exception as e:
            print(f"❌ Ошибка FunctionalityAgent: {e}")
            return "• Выполнение основных рабочих задач\n• Взаимодействие с коллегами\n• Соблюдение корпоративных стандартов"

# PortraitAgent больше не используется - портрет формируется напрямую в database.py
# без использования LLM, просто структурированным форматированием данных 