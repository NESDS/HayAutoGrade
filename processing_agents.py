from typing import Dict, List, Tuple
from llm_service import llm_service

class VerificationAgent:
    def process_answer(self, question_data: Dict, user_answer: str, conversation: List[str]) -> Tuple[bool, str]:
        """Обработка ответа пользователя: проверка + уточнение если нужно"""
        
        # Формируем структурированный диалог
        dialog_text = "ДИАЛОГ:\n"
        
        # Добавляем первоначальный вопрос бота
        dialog_text += f"Бот: {question_data['question']}\n"
        
        # Добавляем весь диалог (включая текущий ответ пользователя, который уже в conversation)
        for i, msg in enumerate(conversation):
            if i % 2 == 0:  # четные индексы - ответы пользователя
                dialog_text += f"Пользователь: {msg}\n"
            else:  # нечетные - вопросы бота
                dialog_text += f"Бот: {msg}\n"
        
        # Используем готовый промпт из таблицы и подставляем диалог
        prompt = question_data['verification_instruction'].format(user_answer=dialog_text)

        print("🔍 ВЕРИФИКАТОР - Отправляю в LLM:")
        print("-" * 50)
        print(prompt)
        print("-" * 50)
        
        messages = [{"role": "user", "content": prompt}]
        response = llm_service.generate_response(messages)
        
        print("✅ ОТВЕТ LLM:")
        print(response)
        print("-" * 50)
        
        # Простой парсинг
        if "ПРИНЯТО" in response.upper():
            return True, "Отлично!"
        else:
            return False, response.replace("УТОЧНИ:", "").strip()

class AnswerCompilerAgent:
    def create_full_answer(self, question_data: Dict, conversation: List[str]) -> str:
        """Создание полного ответа из диалога"""
        # Собираем только ответы пользователя из диалога
        user_answers = []
        for i, msg in enumerate(conversation):
            if i % 2 == 0:  # четные индексы - ответы пользователя
                user_answers.append(msg)
        
        # Формируем структурированный диалог для LLM
        dialog_for_llm = "ДИАЛОГ:\n"
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
        response = llm_service.generate_response(messages)
        
        print("✅ ОТВЕТ LLM:")
        print(response)
        print("-" * 50)
        
        return response.strip()

class ClassificationAgent:
    def classify_answer(self, question_data: Dict, full_answer: str) -> str:
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
        
        print("🏷️ КЛАССИФИКАТОР - Отправляю в LLM:")
        print("-" * 50)
        print(prompt)
        print("-" * 50)
        
        messages = [{"role": "user", "content": prompt}]
        response = llm_service.generate_response(messages)
        
        print("✅ ОТВЕТ LLM (КЛАССИФИКАЦИЯ):")
        print(response)
        print("-" * 50)
        
        return response.strip()

verification_agent = VerificationAgent()
answer_agent = AnswerCompilerAgent()
classification_agent = ClassificationAgent() 