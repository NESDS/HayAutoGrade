import sqlite3
from typing import List, Dict, Optional, Union, Tuple
import json

class Database:
    def __init__(self, db_path: str = "data/database.db"):
        self.db_path = db_path
    


    def get_question(self, question_id: int) -> Optional[Dict]:
        """Получение вопроса по ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, question, answer_options, verification_instruction, 
                       classifier, show_conditions, section
                FROM questions WHERE id = ?
            """, (question_id,))
            result = cursor.fetchone()
            
            if result:
                return {
                    'id': result[0],
                    'question': result[1],
                    'answer_options': result[2],
                    'verification_instruction': result[3],
                    'classifier': result[4],
                    'show_conditions': result[5],
                    'section': result[6]
                }
            return None
    
    def get_all_questions(self) -> List[Dict]:
        """Получение всех вопросов"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, question, answer_options, verification_instruction, 
                       classifier, show_conditions, section
                FROM questions ORDER BY id
            """)
            results = cursor.fetchall()
            
            questions = []
            for result in results:
                questions.append({
                    'id': result[0],
                    'question': result[1],
                    'answer_options': result[2],
                    'verification_instruction': result[3],
                    'classifier': result[4],
                    'show_conditions': result[5],
                    'section': result[6]
                })
            return questions
    
    def get_hay_definition(self, question_number: int, answer_number: int) -> Optional[str]:
        """Получение определения по Hay для конкретного ответа"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT hay_definition 
                FROM hay_dictionary 
                WHERE question_number = ? AND answer_number = ?
            """, (question_number, answer_number))
            
            result = cursor.fetchone()
            return result[0] if result else None
    
    def get_all_hay_definitions(self, question_number: int = None) -> List[Dict]:
        """
        Получение всех определений Hay
        Если указан question_number, возвращает только для этого вопроса
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if question_number is not None:
                cursor.execute("""
                    SELECT question_number, answer_number, hay_definition
                    FROM hay_dictionary
                    WHERE question_number = ?
                    ORDER BY answer_number
                """, (question_number,))
            else:
                cursor.execute("""
                    SELECT question_number, answer_number, hay_definition
                    FROM hay_dictionary
                    ORDER BY question_number, answer_number
                """)
            
            results = cursor.fetchall()
            definitions = []
            for result in results:
                definitions.append({
                    'question_number': result[0],
                    'answer_number': result[1],
                    'hay_definition': result[2]
                })
            return definitions
    
    def save_response(self, user: int, session_id: int, question: int, answer: str, final_answer: str = None, user_state: Dict = None, status: str = 'active', check_conflicts: bool = True) -> Tuple[int, List[Dict]]:
        """
        Сохранение ответа в базу данных + опциональная проверка конфликтов
        
        Args:
            check_conflicts: Проверять ли конфликты после сохранения (только для вопросов с классификатором)
        
        Возвращает: (response_id, список_конфликтов)
        """
        user_state_json = json.dumps(user_state, ensure_ascii=False) if user_state else None
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Помечаем предыдущие ответы на этот вопрос как 'inactive'
            cursor.execute("""
                UPDATE responses 
                SET status = 'inactive' 
                WHERE user = ? AND session_id = ? AND question = ?
            """, (user, session_id, question))
            
            # Сохраняем новый ответ
            cursor.execute("""
                INSERT INTO responses (user, session_id, question, answer, final_answer, user_state, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user, session_id, question, answer, final_answer, user_state_json, status))
            conn.commit()
            response_id = cursor.lastrowid
        
        # Проверяем конфликты только если нужно (для вопросов с классификатором)
        conflicts = []
        if check_conflicts:
            from conflictator import ConflictDetector
            detector = ConflictDetector(self)
            conflicts = detector.check_conflicts_after_answer(user, session_id, question, final_answer or answer)
            
            # Если есть конфликты, помечаем участвующие ответы как 'conflicted'
            if conflicts:
                self._mark_responses_as_conflicted(user, session_id, conflicts)
        
        return response_id, conflicts
    
    def _mark_responses_as_conflicted(self, user: int, session_id: int, conflicts: List[Dict]) -> None:
        """Помечает ответы, участвующие в конфликтах, как 'inactive'"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            for conflict in conflicts:
                for question_id in conflict['question_ids']:
                    cursor.execute("""
                        UPDATE responses 
                        SET status = 'inactive' 
                        WHERE user = ? AND session_id = ? AND question = ?
                    """, (user, session_id, question_id))
            
            conn.commit()
    
    def add_questions_to_remaining(self, user: int, session_id: int, question_ids: List[int]) -> None:
        """Добавляет вопросы обратно в remaining_questions в состоянии пользователя"""
        state = self.get_user_state(user, session_id)
        if state and 'remaining_questions' in state:
            # Расширяем список вопросов с учетом подвопросов
            expanded_question_ids = self._expand_with_subquestions(question_ids)
            
            # Добавляем вопросы, которых еще нет в remaining
            # remaining_questions содержит просто ID вопросов (int), а не объекты
            existing_ids = state['remaining_questions']  # Это уже список ID
            for question_id in expanded_question_ids:
                if question_id not in existing_ids:
                    state['remaining_questions'].append(question_id)
            
            # Сохраняем обновленное состояние
            self.save_user_state(user, session_id, state)
    
    def _expand_with_subquestions(self, question_ids: List[int]) -> List[int]:
        """
        Расширяет список вопросов подвопросами
        Если в списке есть вопрос 13, добавляет вопросы 14 и 15
        """
        expanded_ids = list(question_ids)  # Копируем исходный список
        
        for question_id in question_ids:
            if question_id == 13:
                # Добавляем подвопросы 14 и 15, если их еще нет
                if 14 not in expanded_ids:
                    expanded_ids.append(14)
                if 15 not in expanded_ids:
                    expanded_ids.append(15)
        
        return expanded_ids
    
    def get_user_responses(self, user: int, session_id: int, only_active: bool = True) -> List[Dict]:
        """
        Получение ответов пользователя для конкретной сессии
        only_active: если True, возвращает только активные ответы, если False - все ответы
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if only_active:
                cursor.execute("""
                    SELECT id, question, answer, final_answer, status
                    FROM responses 
                    WHERE user = ? AND session_id = ? AND status = 'active'
                    ORDER BY question
                """, (user, session_id))
            else:
                cursor.execute("""
                    SELECT id, question, answer, final_answer, status
                    FROM responses 
                    WHERE user = ? AND session_id = ?
                    ORDER BY question
                """, (user, session_id))
            
            results = cursor.fetchall()
            
            responses = []
            for result in results:
                responses.append({
                    'id': result[0],
                    'question': result[1],
                    'answer': result[2],
                    'final_answer': result[3],
                    'status': result[4]
                })
            return responses
    
    def get_next_session_id(self, user: int) -> int:
        """Получение следующего номера сессии для пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT MAX(session_id)
                FROM responses 
                WHERE user = ?
            """, (user,))
            result = cursor.fetchone()
            
            max_session_id = result[0] if result[0] is not None else 0
            return max_session_id + 1
    
    def save_user_state(self, user: int, session_id: int, state: Dict) -> None:
        """Сохранение состояния пользователя в последнюю запись"""
        state_json = json.dumps(state, ensure_ascii=False)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Ищем последнюю запись этого пользователя в этой сессии
            cursor.execute("""
                SELECT id FROM responses 
                WHERE user = ? AND session_id = ?
                ORDER BY id DESC LIMIT 1
            """, (user, session_id))
            
            existing = cursor.fetchone()
            
            if existing:
                # Обновляем user_state в существующей записи
                cursor.execute("""
                    UPDATE responses 
                    SET user_state = ? 
                    WHERE id = ?
                """, (state_json, existing[0]))
                conn.commit()
            # Если записи нет - ничего не делаем, состояние сохранится после первого ответа
    
    def get_user_state(self, user: int, session_id: int) -> Optional[Dict]:
        """Получение состояния пользователя из последней записи"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_state FROM responses 
                WHERE user = ? AND session_id = ? AND user_state IS NOT NULL
                ORDER BY id DESC LIMIT 1
            """, (user, session_id))
            
            result = cursor.fetchone()
            
            if result and result[0]:
                try:
                    return json.loads(result[0])
                except json.JSONDecodeError:
                    return None
            return None
    
    def delete_user_state(self, user: int, session_id: int) -> None:
        """Удаление состояния пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE responses 
                SET user_state = NULL 
                WHERE user = ? AND session_id = ?
            """, (user, session_id))
            conn.commit()
    
    def get_all_question_ids(self) -> List[int]:
        """Получение списка всех ID вопросов из базы данных"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM questions ORDER BY id")
            results = cursor.fetchall()
            return [result[0] for result in results]
    
    def get_remaining_questions(self, user: int, session_id: int) -> List[int]:
        """Получение списка вопросов, которые нужно задать пользователю в текущей сессии"""
        user_responses = self.get_user_responses(user, session_id)
        answered_questions = {response['question'] for response in user_responses}
        
        all_questions = self.get_all_questions()
        
        remaining = []
        for question in all_questions:
            question_id = question['id']
            
            if question_id in answered_questions:
                continue
                
            if question['show_conditions']:
                if not self._should_show_question(question['show_conditions'], user_responses):
                    continue
                    
            remaining.append(question_id)
            
        return sorted(remaining)
    
    def _should_show_question(self, show_conditions_json: str, user_responses: List[Dict]) -> bool:
        """Проверяет, нужно ли показывать вопрос на основе условий"""
        try:
            conditions = json.loads(show_conditions_json)
            if not conditions or 'show_if' not in conditions:
                return True
                
            show_if = conditions['show_if']
            
            responses_dict = {}
            for response in user_responses:
                answer_value = response['final_answer'] if response['final_answer'] else response['answer']
                responses_dict[f"question_{response['question']}"] = answer_value
            
            for condition_question, required_answers in show_if.items():
                if condition_question not in responses_dict:
                    return False
                    
                user_answer = responses_dict[condition_question]
                if user_answer not in required_answers:
                    return False
                    
            return True
            
        except (json.JSONDecodeError, KeyError, TypeError):
            return True
    
    def get_question_variants(self, question_num: int, p1_value: int, q11_answer: int = None) -> List[Dict]:
        """
        Получить варианты ответов для вопроса по значению P1
        Для Q11: использует только p1_value
        Для Q12: использует p1_value + q11_answer
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if question_num == 11:
                # Для Q11 получаем все уникальные варианты Q11 для данного P1
                cursor.execute("""
                    SELECT DISTINCT q11_variant_text, q11_answer_value 
                    FROM question_variants_q11_q12
                    WHERE p1_value = ?
                    ORDER BY q11_answer_value
                """, (p1_value,))
                
                results = cursor.fetchall()
                variants = []
                for variant_text, answer_value in results:
                    variants.append({
                        'variant_text': variant_text,
                        'answer_value': answer_value
                    })
                
            elif question_num == 12:
                # Для Q12 нужен ответ на Q11
                if q11_answer is None:
                    print(f"⚠️ Для Q12 нужен ответ на Q11")
                    return []
                
                # Получаем варианты Q12 для данного P1 и ответа Q11
                cursor.execute("""
                    SELECT q12_variant_text, q12_answer_value 
                    FROM question_variants_q11_q12
                    WHERE p1_value = ? AND q11_answer_value = ?
                    ORDER BY q12_answer_value
                """, (p1_value, q11_answer))
                
                results = cursor.fetchall()
                variants = []
                for variant_text, answer_value in results:
                    variants.append({
                        'variant_text': variant_text,
                        'answer_value': answer_value
                    })
            else:
                # Для других вопросов возвращаем пустой список
                print(f"⚠️ Адаптивные варианты доступны только для Q11 и Q12")
                return []
            
            return variants
    
    def has_single_variant(self, question_num: int, p1_value: int, q11_answer: int = None) -> bool:
        """Проверить, есть ли только один вариант для данного P1 (и Q11 для вопроса 12)"""
        variants = self.get_question_variants(question_num, p1_value, q11_answer)
        return len(variants) == 1
    
    def get_user_answers_subset(self, user_id: int, session_id: int, question_ids: List[int]) -> Dict[int, int]:
        """
        Получить ответы пользователя только на указанные вопросы
        Возвращает: {question_id: final_answer_as_int}
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Формируем запрос с плейсхолдерами для IN clause
            placeholders = ','.join('?' * len(question_ids))
            cursor.execute(f"""
                SELECT question, final_answer 
                FROM responses 
                WHERE user = ? AND session_id = ? AND status = 'active' 
                  AND question IN ({placeholders})
                ORDER BY question
            """, [user_id, session_id] + question_ids)
            
            results = cursor.fetchall()
            answers = {}
            
            for question_id, final_answer in results:
                # Преобразуем final_answer в числовое значение
                try:
                    answers[question_id] = int(final_answer)
                except (ValueError, TypeError):
                    # Если не удается преобразовать, пропускаем
                    continue
                    
            return answers
    
    def reset_questions_from_8(self, user_id: int, session_id: int) -> None:
        """
        Деактивировать ответы на вопросы 8-12 и добавить их обратно в remaining_questions
        1. UPDATE responses SET status='inactive' WHERE question IN (8,9,10,11,12)
        2. Добавить 8,9,10,11,12 в remaining_questions текущего состояния
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 1. Деактивируем ответы на вопросы 8-12
            cursor.execute("""
                UPDATE responses 
                SET status = 'inactive' 
                WHERE user = ? AND session_id = ? AND question IN (8, 9, 10, 11, 12)
            """, (user_id, session_id))
            
            conn.commit()
        
        # 2. Обновляем состояние пользователя - добавляем вопросы обратно в remaining
        state = self.get_user_state(user_id, session_id)
        if state and 'remaining_questions' in state:
            # Добавляем вопросы 8-12, если их еще нет в remaining
            questions_to_add = [8, 9, 10, 11, 12]
            existing_ids = state['remaining_questions']
            
            for question_id in questions_to_add:
                if question_id not in existing_ids:
                    existing_ids.append(question_id)
            
            # Сортируем для правильного порядка
            state['remaining_questions'] = sorted(existing_ids)
            
            # Сохраняем обновленное состояние
            self.save_user_state(user_id, session_id, state)
    
    def update_session_portrait(self, user_id: int, session_id: int, portrait: str) -> None:
        """Обновляет портрет пользователя в последней записи сессии"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE responses 
                SET user_portrait = ?
                WHERE user = ? AND session_id = ? AND id = (
                    SELECT MAX(id) FROM responses 
                    WHERE user = ? AND session_id = ?
                )
            """, (portrait, user_id, session_id, user_id, session_id))
            conn.commit()
    
    def get_session_portrait(self, user_id: int, session_id: int) -> Optional[str]:
        """Получает портрет пользователя для сессии"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_portrait FROM responses 
                WHERE user = ? AND session_id = ? AND user_portrait IS NOT NULL
                ORDER BY id DESC LIMIT 1
            """, (user_id, session_id))
            
            result = cursor.fetchone()
            return result[0] if result and result[0] else None
    
    def generate_user_portrait(self, user_id: int, session_id: int) -> Optional[str]:
        """
        Генерирует портрет пользователя на основе активных ответов сессии
        Формат: Вопрос - Полный ответ - Уровень с описанием
        """
        # Получаем все активные ответы текущей сессии
        responses = self.get_user_responses(user_id, session_id, only_active=True)
        
        if not responses:
            return None
        
        # Формируем структурированный портрет без LLM
        portrait_parts = []
        for response in responses:
            question_data = self.get_question(response['question'])
            if question_data:
                question_text = question_data['question']
                full_answer = response['answer']  # Полный ответ пользователя
                level = response['final_answer'] or response['answer']  # Уровень/классификация
                
                # Формат: Вопрос N: [текст вопроса] → Ответ: [полный ответ] → Уровень: [final_answer]
                portrait_line = f"Вопрос {response['question']}: {question_text}\n→ Ответ: {full_answer}\n→ Уровень: {level}"
                portrait_parts.append(portrait_line)
        
        if not portrait_parts:
            return None
            
        # Объединяем все части с разделителем
        portrait = "\n\n".join(portrait_parts)
        
        # Сохраняем портрет в БД
        self.update_session_portrait(user_id, session_id, portrait)
        
        return portrait
    
    def get_hay_level_description(self, question_number: int, answer_number: int) -> Optional[str]:
        """Получает описание уровня HAY из справочника"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT hay_definition 
                FROM hay_dictionary 
                WHERE question_number = ? AND answer_number = ?
            """, (question_number, answer_number))
            result = cursor.fetchone()
            return result[0] if result else None


 