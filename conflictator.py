#!/usr/bin/env python3
import sqlite3
from typing import List, Dict, Optional, Tuple
from database import Database

class ConflictDetector:
    """Агент для обнаружения и обработки конфликтов в ответах"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def check_conflicts_after_answer(self, user_id: int, session_id: int, 
                                   answered_question: int, answer: str) -> List[Dict]:
        """
        Проверка конфликтов после ответа на вопрос
        Возвращает список найденных конфликтов
        """
        print(f"🔍 Проверка конфликтов Q{answered_question}")
        
        # Получаем только активные ответы текущей сессии
        user_responses = self.db.get_user_responses(user_id, session_id, only_active=True)
        
        # Преобразуем в удобный формат {номер_вопроса: номер_ответа}
        response_map = {}
        for resp in user_responses:
            # Используем final_answer если есть, иначе answer
            answer_text = resp['final_answer'] or resp['answer']
            try:
                # Пытаемся преобразовать ответ в номер
                answer_num = int(answer_text) if answer_text and answer_text.isdigit() else None
                if answer_num:
                    response_map[resp['question']] = answer_num
            except (ValueError, TypeError):
                continue
        
        # Проверяем все конфликты
        conflicts = self._find_active_conflicts(response_map)
        
        if conflicts:
            print(f"⚠️ Найден конфликт: вопросы {conflicts[0]['question_ids']}")
        
        return conflicts
    
    def _find_active_conflicts(self, response_map: Dict[int, int]) -> List[Dict]:
        """Находит все активные конфликты для данного набора ответов"""
        with sqlite3.connect(self.db.db_path) as conn:
            cursor = conn.cursor()
            
            # Получаем все конфликты
            cursor.execute("""
                SELECT id, question1_id, answer1_id, question1_text, answer1_text,
                       question2_id, answer2_id, question2_text, answer2_text,
                       question3_id, answer3_id, question3_text, answer3_text
                FROM conflicts
            """)
            
            all_conflicts = cursor.fetchall()
            active_conflicts = []
            
            for conflict_row in all_conflicts:
                conflict_id = conflict_row[0]
                q1_id, a1_id = conflict_row[1], conflict_row[2]
                q2_id, a2_id = conflict_row[5], conflict_row[6]
                q3_id, a3_id = conflict_row[9], conflict_row[10]
                
                conflict = {
                    'id': conflict_id,
                    'questions': [],
                    'question_ids': []
                }
                
                # Проверяем первую пару (обязательная)
                q1_text, a1_text = conflict_row[3], conflict_row[4]
                
                user_answer_1 = response_map.get(q1_id)
                if user_answer_1 != a1_id:
                    continue  # Первое условие не выполнено
                
                conflict['questions'].append({
                    'question_id': q1_id,
                    'answer_id': a1_id,
                    'question_text': q1_text,
                    'answer_text': a1_text
                })
                conflict['question_ids'].append(q1_id)
                
                # Проверяем вторую пару (обязательная)
                q2_text, a2_text = conflict_row[7], conflict_row[8]
                
                user_answer_2 = response_map.get(q2_id)
                if user_answer_2 != a2_id:
                    continue  # Второе условие не выполнено
                
                conflict['questions'].append({
                    'question_id': q2_id,
                    'answer_id': a2_id,
                    'question_text': q2_text,
                    'answer_text': a2_text
                })
                conflict['question_ids'].append(q2_id)
                
                # Проверяем третью пару (опциональная)
                if q3_id is not None and a3_id is not None:
                    q3_text, a3_text = conflict_row[11], conflict_row[12]
                    
                    user_answer_3 = response_map.get(q3_id)
                    if user_answer_3 != a3_id:
                        continue  # Третье условие не выполнено
                    
                    conflict['questions'].append({
                        'question_id': q3_id,
                        'answer_id': a3_id,
                        'question_text': q3_text,
                        'answer_text': a3_text
                    })
                    conflict['question_ids'].append(q3_id)
                
                # Все условия выполнены - конфликт активен
                active_conflicts.append(conflict)
            
            return active_conflicts
    
    def generate_conflict_explanation(self, conflict: Dict) -> str:
        """Генерирует объяснение одного конфликта"""
        
        prompt = """Ты - эксперт по оценке должностей. Обнаружено логическое противоречие в критериях оценки должности.

ПРОТИВОРЕЧИВЫЕ ОТВЕТЫ:
"""
        
        # Добавляем вопросы из конфликта
        for i, question in enumerate(conflict['questions'], 1):
            prompt += f"• Критерий {i}: {question['question_text']}\n"
            prompt += f"  Выбранный ответ: «{question['answer_text']}»\n\n"
        
        prompt += """ЗАДАЧА:
1. Объясни простыми словами, почему эти ответы противоречат друг другу
2. Приведи конкретный пример из практики
3. Предложи пользователю пересмотреть ответы

ФОРМАТ ОТВЕТА:
🔍 ОБНАРУЖЕНО ПРОТИВОРЕЧИЕ:
[Простое объяснение противоречия]

💡 ПРИМЕР:
[Конкретный пример из практики]

🔧 РЕКОМЕНДАЦИЯ:
Пожалуйста, пересмотрите ваши ответы. Подумайте, какие требования действительно важны для этой должности.

Отвечай строго по формате, дружелюбно и понятно."""
        
        return prompt
    
    def get_conflicted_question_ids(self, conflicts: List[Dict]) -> List[int]:
        """Возвращает список ID вопросов, участвующих в конфликтах"""
        question_ids = set()
        for conflict in conflicts:
            question_ids.update(conflict['question_ids'])
        return list(question_ids)

# Пример использования
if __name__ == "__main__":
    # Тест
    db = Database()
    detector = ConflictDetector(db)
    
    # Симулируем ответы пользователя
    test_responses = {11: 3, 12: 1}  # Возможный конфликт
    conflicts = detector._find_active_conflicts(test_responses)
    
    if conflicts:
        print(f"🔴 Найдено конфликтов: {len(conflicts)}")
        explanation = detector.generate_conflict_explanation(conflicts)
        print(f"📝 Объяснение:\n{explanation}")
        
        conflicted_questions = detector.get_conflicted_question_ids(conflicts)
        print(f"🔄 Нужно переспросить вопросы: {conflicted_questions}")
    else:
        print("✅ Конфликтов не найдено")