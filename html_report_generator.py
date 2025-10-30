#!/usr/bin/env python3
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional
from grade_calculator import GradeCalculator

class HTMLReportGenerator:
    """Класс для генерации HTML отчетов пользователей"""
    
    def __init__(self, db_path: str = "data/database.db"):
        self.db_path = db_path
        self.grade_calculator = GradeCalculator(db_path)
    
    def generate_report(self, user_id: int, session_id: int) -> str:
        """
        Генерирует HTML отчет для пользователя
        
        Структура отчета:
        1. Заголовок с результатом грейда
        2. Таблица с вопросами и ответами пользователя
        
        Если есть ошибка в расчете грейда - включает ее в отчет, но все равно показывает Q&A
        """
        try:
            # Получаем детали вопросов и ответов сначала
            qa_details = self._get_questions_and_answers(user_id, session_id)
            if not qa_details:
                return self._generate_error_report("Не найдены вопросы и ответы")
            
            # Пытаемся получить результат расчета грейда
            grade_result = self.grade_calculator.calculate_grade(user_id, session_id)
            
            # Генерируем HTML в любом случае (с ошибкой или без)
            html_content = self._build_html_report(grade_result, qa_details, user_id, session_id)
            
            return html_content
            
        except Exception as e:
            return self._generate_error_report(f"Критическая ошибка при генерации отчета: {str(e)}")
    
    def save_report_to_file(self, user_id: int, session_id: int, output_path: Optional[str] = None) -> str:
        """Сохраняет отчет в HTML файл"""
        html_content = self.generate_report(user_id, session_id)
        
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"report_user_{user_id}_session_{session_id}_{timestamp}.html"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return output_path
    
    def _get_questions_and_answers(self, user_id: int, session_id: int) -> List[Dict]:
        """Получает детальную информацию о вопросах и ответах пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            conn.text_factory = str
            cursor = conn.cursor()
            
            # Получаем ответы пользователя с текстами вопросов и разделами
            cursor.execute("""
                SELECT 
                    r.question as question_id,
                    q.question as question_text,
                    r.answer as full_answer,
                    r.final_answer as classified_answer,
                    q.classifier as has_classifier,
                    q.section as section
                FROM responses r
                JOIN questions q ON r.question = q.id  
                WHERE r.user = ? AND r.session_id = ? AND r.status = 'active'
                ORDER BY r.question
            """, (user_id, session_id))
            
            results = cursor.fetchall()
            qa_details = []
            
            for question_id, question_text, full_answer, classified_answer, has_classifier, section in results:
                # Показываем classified_answer только если у вопроса есть классификатор
                display_level = classified_answer if (has_classifier and has_classifier.strip()) else None
                
                # Получаем расшифровку Hay, если есть классифицированный ответ
                hay_definition = None
                if display_level:
                    try:
                        answer_number = int(display_level)
                        cursor.execute("""
                            SELECT hay_definition 
                            FROM hay_dictionary 
                            WHERE question_number = ? AND answer_number = ?
                        """, (question_id, answer_number))
                        result = cursor.fetchone()
                        if result:
                            hay_definition = result[0]
                    except (ValueError, TypeError):
                        pass  # Если classified_answer не число, пропускаем
                
                qa_details.append({
                    "question_id": question_id,
                    "question_text": question_text,
                    "full_answer": full_answer,
                    "classified_answer": display_level,
                    "hay_definition": hay_definition,
                    "section": section
                })
            
            return qa_details
    

    
    def _generate_diagnostic_info(self, user_id: int, session_id: int, grade_result: Dict) -> str:
        """Генерирует диагностическую информацию при ошибке расчета грейда"""
        try:
            # Получаем ответы пользователя для диагностики
            with sqlite3.connect(self.db_path) as conn:
                conn.text_factory = str
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT question, final_answer 
                    FROM responses 
                    WHERE user = ? AND session_id = ? AND status = 'active'
                    ORDER BY question
                """, (user_id, session_id))
                
                user_answers = {row[0]: row[1] for row in cursor.fetchall()}
            
            diagnostics = []
            
            # Проверяем наличие ответов для расчета p1 (вопросы 8, 9, 10)
            p1_questions = [8, 9, 10]
            missing_p1 = [q for q in p1_questions if q not in user_answers]
            if missing_p1:
                diagnostics.append(f"❌ P1: Отсутствуют ответы на вопросы {missing_p1}")
            else:
                answers_p1 = [user_answers.get(q, 'N/A') for q in p1_questions]
                diagnostics.append(f"✅ P1: Ответы найдены {answers_p1}")
            
            # Проверяем наличие ответов для расчета p2 (вопросы 11, 12)
            p2_questions = [11, 12]
            missing_p2 = [q for q in p2_questions if q not in user_answers]
            if missing_p2:
                diagnostics.append(f"❌ P2: Отсутствуют ответы на вопросы {missing_p2}")
            else:
                answers_p2 = [user_answers.get(q, 'N/A') for q in p2_questions]
                diagnostics.append(f"✅ P2: Ответы найдены {answers_p2}")
            
            # Проверяем наличие ответов для расчета p4 (вопросы 13, 16 + 14 или 15)
            p4_base_questions = [13, 16]
            missing_p4_base = [q for q in p4_base_questions if q not in user_answers]
            has_q14 = 14 in user_answers
            has_q15 = 15 in user_answers
            
            if missing_p4_base:
                diagnostics.append(f"❌ P4: Отсутствуют базовые ответы на вопросы {missing_p4_base}")
            elif not has_q14 and not has_q15:
                diagnostics.append("❌ P4: Отсутствуют ответы на вопросы 14 или 15")
            else:
                p4_variant = "14" if has_q14 else "15"
                p4_questions = [13, 16, int(p4_variant)]
                answers_p4 = [user_answers.get(q, 'N/A') for q in p4_questions]
                diagnostics.append(f"✅ P4 (вариант {p4_variant}): Ответы найдены {answers_p4}")
            
            # Общая статистика
            total_answers = len(user_answers)
            diagnostics.append(f"📊 Всего ответов в сессии: {total_answers}")
            diagnostics.append(f"📋 Номера отвеченных вопросов: {sorted(user_answers.keys())}")
            
            # Формируем HTML
            diagnostic_html = """
            <div class="error-details" style="margin-top: 20px;">
                <div class="error-title">Диагностика проблемы:</div>
                <div class="diagnostic-list">
            """
            
            for diag in diagnostics:
                diagnostic_html += f'<div class="diagnostic-item">{self._escape_html(diag)}</div>'
            
            diagnostic_html += """
                </div>
            </div>
            """
            
            return diagnostic_html
            
        except Exception as e:
            return f"""
            <div class="error-details" style="margin-top: 20px;">
                <div class="error-title">Дополнительная диагностика:</div>
                <div class="error-message">Ошибка получения диагностической информации: {self._escape_html(str(e))}</div>
            </div>
            """
    
    def _build_html_report(self, grade_result: Dict, qa_details: List[Dict], user_id: int, session_id: int) -> str:
        """Строит полный HTML отчет"""
        
        # Проверяем есть ли ошибка в расчете грейда
        has_grade_error = "error" in grade_result
        error_message = grade_result.get("error", "") if has_grade_error else ""
        
        if has_grade_error:
            # Если есть ошибка - устанавливаем значения по умолчанию
            final_grade = "Ошибка расчета"
            grade_range = ""
            calculations = {}
            p1 = p2 = p3 = p4 = total_p = "Ошибка"
        else:
            # Извлекаем данные для грейда
            final_grade = grade_result.get("final_grade", "Не определен")
            grade_range = grade_result.get("grade_range", "")
            calculations = grade_result.get("calculations", {})
            
            # Формируем детали расчета
            p1 = calculations.get("p1", "N/A")
            p2 = calculations.get("p2", "N/A")  
            p3 = calculations.get("p3", "N/A")
            p4 = calculations.get("p4", "N/A")
            total_p = calculations.get("total_p", "N/A")
        
        # Генерируем строки таблицы с вопросами и ответами (для десктопа)
        qa_rows = ""
        for qa in qa_details:
            # Формируем текст вопроса с разделом
            question_html = ""
            if qa.get('section'):
                question_html += f'<span class="question-section">{self._escape_html(qa["section"])}</span><br>'
            question_html += self._escape_html(qa['question_text'])
            
            # Формируем ответ с уровнем (если есть)
            answer_html = self._escape_html(qa['full_answer'])
            if qa['classified_answer'] and qa['classified_answer'].strip():
                # Добавляем уровень с расшифровкой Hay
                level_text = f'Уровень: {qa["classified_answer"]}'
                if qa.get('hay_definition'):
                    level_text += f' — {self._escape_html(qa["hay_definition"])}'
                answer_html += f'<br><br><span class="answer-level-badge">{level_text}</span>'
            
            qa_rows += f"""
                <tr>
                    <td class="question-id">#{qa['question_id']}</td>
                    <td class="question-text">{question_html}</td>
                    <td class="user-answer">{answer_html}</td>
                </tr>
            """
        
        # Генерируем карточки для мобильных устройств
        qa_cards = ""
        for qa in qa_details:
            # Формируем раздел для мобильной версии
            section_badge = ""
            if qa.get('section'):
                section_badge = f'<div class="qa-card-section">{self._escape_html(qa["section"])}</div>'
            
            # Формируем уровень с расшифровкой для мобильной версии
            level_badge = ""
            if qa['classified_answer'] and qa['classified_answer'].strip():
                level_text = f'Уровень: {qa["classified_answer"]}'
                if qa.get('hay_definition'):
                    level_text += f' — {self._escape_html(qa["hay_definition"])}'
                level_badge = f'<span class="answer-level-badge-mobile">{level_text}</span>'
            
            qa_cards += f"""
                <div class="qa-card">
                    <div class="qa-card-header">
                        <span class="qa-card-number">{qa['question_id']}</span>
                        <span class="qa-card-question">{self._escape_html(qa['question_text'])}</span>
                    </div>
                    {section_badge}
                    <div class="qa-card-body">
                        <div class="qa-card-answer">{self._escape_html(qa['full_answer'])}</div>
                        {level_badge}
                    </div>
                </div>
            """
        
        current_time = datetime.now().strftime("%d.%m.%Y %H:%M")
        
        # Определяем CSS класс и содержимое для секции грейда
        grade_section_class = "grade-section error" if has_grade_error else "grade-section"
        
        # Формируем содержимое секции грейда
        if has_grade_error:
            # Добавляем диагностическую информацию
            diagnostic_info = self._generate_diagnostic_info(user_id, session_id, grade_result)
            
            grade_content = f"""
            <div class="grade-title">Ошибка расчета грейда</div>
            <div class="grade-value">❌</div>
            <div class="grade-range">Не удалось вычислить результат</div>
            
            <div class="error-details">
                <div class="error-title">Основная ошибка:</div>
                <div class="error-message">{self._escape_html(error_message)}</div>
            </div>
            
            {diagnostic_info}
            """
        else:
            grade_content = f"""
            <div class="grade-title">Ваш результат</div>
            <div class="grade-value">{final_grade}</div>
            <div class="grade-range">Диапазон: {grade_range}</div>
            
            <div class="calculation-details">
                <div class="calc-item">
                    <div class="calc-label">Параметр P1</div>
                    <div class="calc-value">{p1}</div>
                </div>
                <div class="calc-item">
                    <div class="calc-label">Параметр P2</div>
                    <div class="calc-value">{p2}</div>
                </div>
                <div class="calc-item">
                    <div class="calc-label">Параметр P3</div>
                    <div class="calc-value">{p3}</div>
                </div>
                <div class="calc-item">
                    <div class="calc-label">Параметр P4</div>
                    <div class="calc-value">{p4}</div>
                </div>
                <div class="calc-item">
                    <div class="calc-label">Итого P</div>
                    <div class="calc-value">{total_p}</div>
                </div>
            </div>
            """
        
        html_template = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Отчет по опросу - Пользователь {user_id}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #2196F3 0%, #21CBF3 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            font-weight: 300;
        }}
        
        .header .subtitle {{
            font-size: 1.1em;
            opacity: 0.9;
        }}
        
        .grade-section {{
            background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        
        .grade-section.error {{
            background: linear-gradient(135deg, #f44336 0%, #d32f2f 100%);
        }}
        
        .grade-title {{
            font-size: 2em;
            margin-bottom: 20px;
            font-weight: 300;
        }}
        
        .grade-value {{
            font-size: 4em;
            font-weight: bold;
            margin-bottom: 15px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}
        
        .grade-range {{
            font-size: 1.3em;
            margin-bottom: 25px;
            opacity: 0.9;
        }}
        
        .calculation-details {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}
        
        .calc-item {{
            background: rgba(255,255,255,0.2);
            padding: 15px;
            border-radius: 10px;
            text-align: center;
        }}
        
        .calc-label {{
            font-size: 0.9em;
            opacity: 0.8;
            margin-bottom: 5px;
        }}
        
        .calc-value {{
            font-size: 1.5em;
            font-weight: bold;
        }}
        
        .error-details {{
            background: rgba(255,255,255,0.2);
            padding: 20px;
            border-radius: 10px;
            margin-top: 20px;
            text-align: left;
        }}
        
        .error-title {{
            font-size: 1.2em;
            font-weight: bold;
            margin-bottom: 10px;
        }}
        
        .error-message {{
            font-size: 1em;
            line-height: 1.4;
            opacity: 0.9;
        }}
        
        .diagnostic-list {{
            margin-top: 15px;
        }}
        
        .diagnostic-item {{
            padding: 8px 12px;
            margin-bottom: 6px;
            background: rgba(255,255,255,0.1);
            border-radius: 6px;
            font-size: 0.95em;
            line-height: 1.4;
            border-left: 3px solid rgba(255,255,255,0.3);
        }}
        
        .content {{
            padding: 40px;
        }}
        
        .section-title {{
            font-size: 1.8em;
            color: #333;
            margin-bottom: 25px;
            text-align: center;
            position: relative;
        }}
        
        .section-title::after {{
            content: '';
            position: absolute;
            bottom: -10px;
            left: 50%;
            transform: translateX(-50%);
            width: 80px;
            height: 3px;
            background: linear-gradient(135deg, #2196F3, #21CBF3);
            border-radius: 2px;
        }}
        
        .qa-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
        }}
        
        .qa-table th {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px 15px;
            text-align: left;
            font-weight: 500;
            font-size: 1.1em;
        }}
        
        .qa-table td {{
            padding: 20px 15px;
            border-bottom: 1px solid #eee;
            vertical-align: top;
        }}
        
        .qa-table tr:last-child td {{
            border-bottom: none;
        }}
        
        .qa-table tr:hover {{
            background-color: #f8f9ff;
            transition: background-color 0.3s ease;
        }}
        
        .question-id {{
            font-weight: bold;
            color: #2196F3;
            width: 80px;
            text-align: center;
        }}
        
        .question-text {{
            color: #333;
            line-height: 1.6;
            font-weight: 500;
        }}
        
        .question-section {{
            display: inline-block;
            padding: 4px 10px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 6px;
            font-size: 0.85em;
            font-weight: 500;
            margin-bottom: 8px;
        }}
        
        .user-answer {{
            color: #555;
            line-height: 1.6;
            background-color: #f9f9f9;
            border-left: 4px solid #2196F3;
            padding-left: 15px;
        }}
        
        .answer-level-badge {{
            display: inline-block;
            padding: 6px 12px;
            background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
            color: white;
            border-radius: 8px;
            font-size: 0.9em;
            font-weight: 500;
        }}
        
        .footer {{
            background: #f5f5f5;
            padding: 20px;
            text-align: center;
            color: #666;
            font-size: 0.9em;
        }}
        
        .qa-card {{
            display: none;
            background: white;
            border-radius: 15px;
            margin-bottom: 20px;
            box-shadow: 0 8px 20px rgba(0,0,0,0.1);
            overflow: hidden;
            border-left: 5px solid #2196F3;
        }}
        
        .qa-card-header {{
            background: linear-gradient(135deg, #f8f9ff 0%, #e3f2fd 100%);
            padding: 15px 20px;
            border-bottom: 1px solid #e0e0e0;
        }}
        
        .qa-card-number {{
            display: inline-block;
            background: #2196F3;
            color: white;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            text-align: center;
            line-height: 30px;
            font-weight: bold;
            font-size: 0.9em;
            margin-right: 15px;
        }}
        
        .qa-card-question {{
            display: inline;
            font-weight: 600;
            color: #333;
            font-size: 1.05em;
            line-height: 1.5;
        }}
        
        .qa-card-section {{
            padding: 8px 20px;
            background: linear-gradient(135deg, #f0f0f0 0%, #e8e8e8 100%);
            border-top: 1px solid #e0e0e0;
            font-size: 0.85em;
            color: #667eea;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .qa-card-body {{
            padding: 20px;
        }}
        
        .qa-card-answer-label {{
            font-size: 0.9em;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
            font-weight: 500;
        }}
        
        .qa-card-answer {{
            background: #f9f9f9;
            padding: 15px;
            border-radius: 10px;
            border-left: 4px solid #2196F3;
            line-height: 1.6;
            color: #333;
        }}
        
        .qa-card-level {{
            margin-top: 12px;
            padding: 8px 12px;
            background: linear-gradient(135deg, #e8f5e8 0%, #f0f8ff 100%);
            border-radius: 6px;
            font-size: 0.9em;
            color: #2e7d32;
            font-weight: 500;
            border-left: 3px solid #4caf50;
        }}
        
        .answer-level-badge-mobile {{
            display: inline-block;
            margin-top: 10px;
            padding: 6px 12px;
            background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
            color: white;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 500;
        }}

        @media (max-width: 768px) {{
            .container {{
                margin: 10px;
                border-radius: 10px;
            }}
            
            .header {{
                padding: 20px 15px;
            }}
            
            .header h1 {{
                font-size: 2em;
            }}
            
            .header .subtitle {{
                font-size: 0.95em;
            }}
            
            .grade-section {{
                padding: 30px 20px;
            }}
            
            .grade-value {{
                font-size: 3em;
            }}
            
            .calculation-details {{
                grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
                gap: 15px;
            }}
            
            .calc-item {{
                padding: 12px;
            }}
            
            .calc-value {{
                font-size: 1.3em;
            }}
            
            .content {{
                padding: 20px 15px;
            }}
            
            .section-title {{
                font-size: 1.5em;
            }}
            
            /* Скрываем таблицу на мобильных */
            .qa-table {{
                display: none;
            }}
            
            /* Показываем карточки на мобильных */
            .qa-card {{
                display: block;
            }}
            
            .error-details {{
                padding: 15px;
                text-align: center;
            }}
        }}
        
        @media (max-width: 480px) {{
            .header h1 {{
                font-size: 1.7em;
            }}
            
            .grade-value {{
                font-size: 2.5em;
            }}
            
            .calculation-details {{
                grid-template-columns: repeat(2, 1fr);
            }}
            
            .qa-card {{
                margin-bottom: 15px;
                border-radius: 12px;
            }}
            
            .qa-card-header {{
                padding: 12px 15px;
            }}
            
            .qa-card-body {{
                padding: 15px;
            }}
            
            .qa-card-number {{
                width: 25px;
                height: 25px;
                line-height: 25px;
                font-size: 0.8em;
                margin-right: 10px;
            }}
            
            .qa-card-question {{
                font-size: 1em;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Отчет по опросу</h1>
            <div class="subtitle">Пользователь #{user_id} | Сессия #{session_id} | {current_time}</div>
        </div>
        
        <div class="{grade_section_class}">
            {grade_content}
        </div>
        
        <div class="content">
            <h2 class="section-title">Вопросы и ответы</h2>
            
            <!-- Таблица для десктопа -->
            <table class="qa-table">
                <thead>
                    <tr>
                        <th>№</th>
                        <th>Вопрос</th>
                        <th>Ответ</th>
                    </tr>
                </thead>
                <tbody>
                    {qa_rows}
                </tbody>
            </table>
            
            <!-- Карточки для мобильных устройств -->
            {qa_cards}
        </div>
        
        <div class="footer">
            <p>Отчет сгенерирован автоматически • HAG MVP System • {current_time}</p>
        </div>
    </div>
</body>
</html>
        """
        
        return html_template
    
    def _generate_error_report(self, error_message: str) -> str:
        """Генерирует HTML отчет с ошибкой"""
        current_time = datetime.now().strftime("%d.%m.%Y %H:%M")
        
        return f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ошибка генерации отчета</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #ff6b6b 0%, #ee5a5a 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        
        .error-container {{
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            text-align: center;
            max-width: 600px;
        }}
        
        .error-icon {{
            font-size: 4em;
            color: #ff6b6b;
            margin-bottom: 20px;
        }}
        
        .error-title {{
            font-size: 2em;
            color: #333;
            margin-bottom: 15px;
        }}
        
        .error-message {{
            font-size: 1.2em;
            color: #666;
            margin-bottom: 25px;
            line-height: 1.6;
        }}
        
        .timestamp {{
            font-size: 0.9em;
            color: #999;
        }}
    </style>
</head>
<body>
    <div class="error-container">
        <div class="error-icon">⚠️</div>
        <h1 class="error-title">Ошибка генерации отчета</h1>
        <p class="error-message">{self._escape_html(error_message)}</p>
        <p class="timestamp">Время: {current_time}</p>
    </div>
</body>
</html>
        """
    
    def _escape_html(self, text: str) -> str:
        """Экранирует HTML символы"""
        if not text:
            return ""
        
        text = str(text)
        html_escape_table = {
            "&": "&amp;",
            '"': "&quot;",
            "'": "&#x27;",
            "<": "&lt;",
            ">": "&gt;",
        }
        
        return "".join(html_escape_table.get(c, c) for c in text)

# Пример использования
if __name__ == "__main__":
    generator = HTMLReportGenerator()
    
    # Тестовый пример (нужны реальные данные)
    # report_path = generator.save_report_to_file(user_id=123, session_id=1)
    # print(f"Отчет сохранен: {report_path}")
    
    print("Генератор HTML отчетов создан успешно!")