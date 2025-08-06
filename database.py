import sqlite3
from typing import List, Dict, Optional, Union, Tuple
import json
import os

class Database:
    def __init__(self, db_path: str = "data/database.db"):
        self.db_path = db_path
        self._ensure_tables_exist()
    


    def get_question(self, question_id: int) -> Optional[Dict]:
        """Получение вопроса по ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM questions WHERE id = ?", (question_id,))
            result = cursor.fetchone()
            
            if result:
                return {
                    'id': result[0],
                    'question': result[1],
                    'answer_options': result[2],
                    'verification_instruction': result[3],
                    'classifier': result[4] if len(result) > 4 else None,
                    'show_conditions': result[5] if len(result) > 5 else None
                }
            return None
    
    def get_all_questions(self) -> List[Dict]:
        """Получение всех вопросов"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM questions ORDER BY id")
            results = cursor.fetchall()
            
            questions = []
            for result in results:
                questions.append({
                    'id': result[0],
                    'question': result[1],
                    'answer_options': result[2],
                    'verification_instruction': result[3],
                    'classifier': result[4] if len(result) > 4 else None,
                    'show_conditions': result[5] if len(result) > 5 else None
                })
            return questions
    
    def save_response(self, user: int, session_id: int, question: int, answer: str, final_answer: str = None, user_state: Dict = None, status: str = 'active') -> Tuple[int, List[Dict]]:
        """
        Сохранение ответа в базу данных + проверка конфликтов
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
        
        # Проверяем конфликты после сохранения ответа
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
    
    def _ensure_tables_exist(self):
        """Создание таблиц, если они не существуют"""
        # Создаем директорию data, если её нет
        data_dir = os.path.dirname(self.db_path)
        if data_dir and not os.path.exists(data_dir):
            os.makedirs(data_dir)
            
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Создание таблицы questions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS questions (
                    id INTEGER PRIMARY KEY,
                    question TEXT,
                    answer_options TEXT,
                    verification_instruction TEXT,
                    classifier TEXT,
                    show_conditions TEXT
                )
            """)
            
            # Создание таблицы responses
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user INTEGER,
                    session_id INTEGER,
                    question INTEGER,
                    answer TEXT,
                    final_answer TEXT,
                    user_state TEXT
                )
            """)
            
            conn.commit()

 