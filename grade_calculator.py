#!/usr/bin/env python3
import sqlite3
from typing import Optional, Dict, List, Tuple

class GradeCalculator:
    """Класс для расчета грейда пользователя по алгоритму"""
    
    def __init__(self, db_path: str = "data/database.db"):
        self.db_path = db_path
    
    def calculate_grade(self, user_id: int, session_id: int) -> Dict:
        """
        Основной метод расчета грейда для пользователя
        
        Алгоритм:
        1. Получить все ответы пользователя для сессии
        2. Вычислить p1 по таблице p1 (вопросы 8, 9, 10)
        3. Вычислить p2 по таблице p2 (вопросы 11, 12)
        4. Вычислить p3 по таблице p3 (поиск по p1, p2)
        5. Определить есть ли ответ на вопрос 14 или 15
        6. Вычислить p4 по соответствующей таблице p4-14 или p4-15
        7. Итоговый параметр p = p1 + p3 + p4 (p2 не суммируется)
        8. Определить грейд по таблице грейдов
        
        Возвращает: словарь с результатами расчета
        """
        try:
            # Получаем все ответы пользователя
            user_answers = self._get_user_answers(user_id, session_id)
            if not user_answers:
                return {"error": "Не найдены ответы пользователя"}
            
            result = {
                "user_id": user_id,
                "session_id": session_id,
                "answers": user_answers,
                "calculations": {},
                "final_grade": None,
                "grade_range": None
            }
            
            # Шаг 1: Вычисляем p1
            p1 = self._calculate_p1(user_answers)
            if p1 is None:
                return {"error": "Не удалось вычислить параметр p1"}
            result["calculations"]["p1"] = p1
            
            # Шаг 2: Вычисляем p2  
            p2 = self._calculate_p2(user_answers)
            if p2 is None:
                return {"error": "Не удалось вычислить параметр p2"}
            result["calculations"]["p2"] = p2
            
            # Шаг 3: Вычисляем p3 по таблице поиска
            p3 = self._calculate_p3(p1, p2)
            if p3 is None:
                return {"error": "Не удалось вычислить параметр p3"}
            result["calculations"]["p3"] = p3
            
            # Шаг 4: Определяем p4 (вопрос 14 или 15)
            p4 = self._calculate_p4(user_answers)
            if p4 is None:
                return {"error": "Не удалось вычислить параметр p4"}
            result["calculations"]["p4"] = p4
            
            # Шаг 5: Итоговый параметр p = p1 + p3 + p4
            total_p = p1 + p3 + p4
            result["calculations"]["total_p"] = total_p
            
            # Шаг 6: Определяем грейд
            grade_info = self._determine_grade(total_p)
            if grade_info:
                result["final_grade"] = grade_info["grade"]
                result["grade_range"] = f"{grade_info['low']}-{grade_info['high']}"
                result["calculations"]["grade_info"] = grade_info
            else:
                return {"error": "Не удалось определить грейд"}
            
            return result
            
        except Exception as e:
            return {"error": f"Ошибка при расчете грейда: {str(e)}"}
    
    def _get_user_answers(self, user_id: int, session_id: int) -> Dict[int, int]:
        """Получить все ответы пользователя для сессии"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT question, final_answer 
                FROM responses 
                WHERE user = ? AND session_id = ? AND status = 'active'
                ORDER BY question
            """, (user_id, session_id))
            
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
    
    def _calculate_p1(self, user_answers: Dict[int, int]) -> Optional[int]:
        """Вычислить p1 по таблице p1 (вопросы 8, 9, 10)"""
        # Проверяем наличие нужных ответов
        if 8 not in user_answers or 9 not in user_answers or 10 not in user_answers:
            return None
            
        answer_q8 = user_answers[8]
        answer_q9 = user_answers[9] 
        answer_q10 = user_answers[10]
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p1_value FROM grading_p1 
                WHERE answer_q8 = ? AND answer_q9 = ? AND answer_q10 = ?
            """, (answer_q8, answer_q9, answer_q10))
            
            result = cursor.fetchone()
            return result[0] if result else None
    
    def _calculate_p2(self, user_answers: Dict[int, int]) -> Optional[int]:
        """Вычислить p2 по таблице p2 (вопросы 11, 12)"""
        # Проверяем наличие нужных ответов
        if 11 not in user_answers or 12 not in user_answers:
            return None
            
        answer_q11 = user_answers[11]
        answer_q12 = user_answers[12]
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p2_value FROM grading_p2 
                WHERE answer_q11 = ? AND answer_q12 = ?
            """, (answer_q11, answer_q12))
            
            result = cursor.fetchone()
            return result[0] if result else None
    
    def _calculate_p3(self, p1: int, p2: int) -> Optional[int]:
        """Вычислить p3 по таблице поиска p3 (по уже вычисленным p1 и p2)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p3_value FROM grading_p3 
                WHERE p1_value = ? AND p2_value = ?
            """, (float(p1), p2))
            
            result = cursor.fetchone()
            return result[0] if result else None
    
    def _calculate_p4(self, user_answers: Dict[int, int]) -> Optional[int]:
        """Вычислить p4 в зависимости от того, есть ли ответ на вопрос 14 или 15"""
        # Проверяем общие вопросы (13, 16)
        if 13 not in user_answers or 16 not in user_answers:
            return None
            
        answer_q13 = user_answers[13]
        answer_q16 = user_answers[16]
        
        # Проверяем есть ли ответ на вопрос 14
        if 14 in user_answers:
            return self._calculate_p4_by_q14(answer_q16, answer_q13, user_answers[14])
        
        # Проверяем есть ли ответ на вопрос 15
        if 15 in user_answers:
            return self._calculate_p4_by_q15(answer_q16, answer_q13, user_answers[15])
            
        return None
    
    def _calculate_p4_by_q14(self, answer_q16: int, answer_q13: int, answer_q14: int) -> Optional[int]:
        """Вычислить p4 по таблице p4-14"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p4_value FROM grading_p4_14 
                WHERE answer_q16 = ? AND answer_q13 = ? AND answer_q14 = ?
            """, (answer_q16, answer_q13, answer_q14))
            
            result = cursor.fetchone()
            return result[0] if result else None
    
    def _calculate_p4_by_q15(self, answer_q16: int, answer_q13: int, answer_q15: int) -> Optional[int]:
        """Вычислить p4 по таблице p4-15"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p4_value FROM grading_p4_15 
                WHERE answer_q16 = ? AND answer_q13 = ? AND answer_q15 = ?
            """, (answer_q16, answer_q13, answer_q15))
            
            result = cursor.fetchone()
            return result[0] if result else None
    
    def _determine_grade(self, total_p: int) -> Optional[Dict]:
        """Определить грейд по итоговому параметру p"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT low_bound, mid_point, high_bound, sber_grade 
                FROM grading_scale 
                WHERE ? >= low_bound AND ? <= high_bound
                ORDER BY low_bound
            """, (total_p, total_p))
            
            result = cursor.fetchone()
            if result:
                return {
                    "low": result[0],
                    "mid": result[1], 
                    "high": result[2],
                    "grade": result[3] if result[3] else "—"
                }
            return None
    
    def calculate_intermediate_p1(self, user_id: int, session_id: int) -> Optional[int]:
        """
        Промежуточный расчёт P1 для определения вариантов вопросов 11 и 12
        
        Используется после ответа на 10-й вопрос для выбора адаптивных вариантов.
        Возвращает значение P1 или None при ошибке.
        """
        try:
            # Получаем ответы пользователя на вопросы 8, 9, 10
            user_answers = self._get_user_answers(user_id, session_id)
            
            # Проверяем, что есть ответы на нужные вопросы
            required_questions = {8, 9, 10}
            available_questions = set(user_answers.keys())
            
            if not required_questions.issubset(available_questions):
                missing = required_questions - available_questions
                print(f"⚠️ Не хватает ответов на вопросы: {missing}")
                return None
            
            # Вычисляем P1 используя существующую логику
            p1_value = self._calculate_p1(user_answers)
            
            if p1_value is not None:
                print(f"✅ Промежуточный P1 = {p1_value}")
            else:
                print("❌ Не удалось вычислить P1")
                
            return p1_value
            
        except Exception as e:
            print(f"❌ Ошибка при расчёте промежуточного P1: {str(e)}")
            return None

# Пример использования
if __name__ == "__main__":
    calculator = GradeCalculator()
    
    # Тестовый пример (нужны реальные данные)
    # result = calculator.calculate_grade(user_id=123, session_id=1)
    # print(result)
    print("Калькулятор грейдов создан успешно!")