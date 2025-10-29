#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор XLSX отчётов с использованием win32com
Заполняет шаблон калькулятор.xlsx данными пользователя
"""

import win32com.client
import os
import sqlite3
from typing import Dict, Optional
from datetime import datetime
from pathlib import Path


class XLSXReportGenerator:
    """Класс для генерации XLSX отчетов через win32com"""
    
    def __init__(self, db_path: str = "data/database.db", template_name: str = "калькулятор.xlsx"):
        self.db_path = db_path
        # Используем Path для корректной работы с кириллицей
        self.template_path = Path("data") / template_name
        self.output_dir = Path("exports")
        
        # Создаём директорию для экспортов если не существует
        self.output_dir.mkdir(exist_ok=True)
    
    def generate_report(self, user_id: int, session_id: int) -> str:
        """
        Генерирует XLSX отчет для пользователя
        
        Args:
            user_id: ID пользователя
            session_id: ID сессии
            
        Returns:
            str: Путь к созданному файлу
        """
        try:
            # Формируем пути используя Path для корректной работы с Unicode
            template_full_path = self.template_path.resolve()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"calculator_user_{user_id}_session_{session_id}_{timestamp}.xlsx"
            output_path = (self.output_dir / output_filename).resolve()
            
            # Проверяем существование шаблона
            if not template_full_path.exists():
                raise FileNotFoundError(f"Шаблон не найден: {template_full_path}")
            
            print(f"[INFO] Генерируем отчет из шаблона: {template_full_path}")
            print(f"[INFO] Сохраним в: {output_path}")
            
            # Получаем данные из БД
            user_data = self._get_user_data(user_id, session_id)
            
            # Запускаем Excel (невидимо)
            excel = None
            workbook = None
            
            try:
                # Используем DispatchEx для создания нового экземпляра Excel
                excel = win32com.client.DispatchEx("Excel.Application")
                
                # Настраиваем Excel
                try:
                    excel.Visible = False
                except:
                    pass  # Если свойство недоступно, продолжаем
                    
                try:
                    excel.DisplayAlerts = False
                except:
                    pass  # Если свойство недоступно, продолжаем
                
                # Открываем шаблон (преобразуем Path в строку для COM)
                workbook = excel.Workbooks.Open(str(template_full_path))
                
                # Заполняем лист "Расчет грейда"
                self._fill_calculator_sheet(workbook, user_data)
                
                # Обновляем все вычисления
                excel.CalculateFull()
                
                # Обновляем сводные таблицы (если есть)
                self._refresh_pivot_tables(workbook)
                
                # Сохраняем результат (преобразуем Path в строку для COM)
                workbook.SaveAs(str(output_path))
                print(f"[SUCCESS] Отчет успешно создан: {output_path}")
                
                return str(output_path)
                
            finally:
                # Обязательно закрываем всё
                try:
                    if workbook:
                        workbook.Close(SaveChanges=False)
                except:
                    pass
                    
                try:
                    if excel:
                        excel.Quit()
                except:
                    pass
        
        except Exception as e:
            print(f"[ERROR] Ошибка при генерации XLSX отчета: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _get_user_data(self, user_id: int, session_id: int) -> Dict:
        """
        Получает данные пользователя из БД
        
        Returns:
            Dict с ключами: question_1, question_3, question_8_hay, question_9_hay и т.д.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Получаем ответы пользователя
            cursor.execute("""
                SELECT 
                    r.question,
                    r.answer,
                    r.final_answer
                FROM responses r
                WHERE r.user = ? AND r.session_id = ? AND r.status = 'active'
                ORDER BY r.question
            """, (user_id, session_id))
            
            responses = cursor.fetchall()
            
            # Формируем словарь с данными
            data = {}
            
            for question_id, answer, final_answer in responses:
                # Сохраняем просто ответ для вопросов 1 и 3
                if question_id in [1, 3]:
                    data[f'question_{question_id}'] = answer
                
                # Для вопросов с HAY получаем расшифровку
                if question_id in [8, 9, 10, 11, 12, 13, 14, 16]:
                    hay_definition = self._get_hay_definition(question_id, final_answer)
                    data[f'question_{question_id}_hay'] = hay_definition or final_answer or ""
            
            print(f"[INFO] Получены данные для пользователя {user_id}, сессия {session_id}")
            print(f"[INFO] Вопросов обработано: {len(responses)}")
            
            return data
    
    def _get_hay_definition(self, question_number: int, answer_number: str) -> Optional[str]:
        """Получает расшифровку HAY для вопроса и ответа"""
        if not answer_number:
            return None
            
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Преобразуем answer_number в число
                answer_num = int(answer_number)
                
                cursor.execute("""
                    SELECT hay_definition 
                    FROM hay_dictionary 
                    WHERE question_number = ? AND answer_number = ?
                """, (question_number, answer_num))
                
                result = cursor.fetchone()
                return result[0] if result else None
        except (ValueError, TypeError):
            return None
    
    def _fill_calculator_sheet(self, workbook, user_data: Dict):
        """Заполняет лист 'Расчет грейда' данными"""
        try:
            # Получаем лист "Расчет грейда"
            worksheet = workbook.Sheets("Расчет грейда")
            
            print(f"[INFO] Заполняем лист 'Расчет грейда' в строке 19:")
            
            # D19 - путь из вопроса 3
            if 'question_3' in user_data:
                worksheet.Range("D19").Value = user_data['question_3']
                print(f"   D19 (Путь): {user_data['question_3'][:50]}...")
            
            # I19 - роль (ответ на первый вопрос)
            if 'question_1' in user_data:
                worksheet.Range("I19").Value = user_data['question_1']
                print(f"   I19 (Роль): {user_data['question_1']}")
            
            # J19 - ответ по HAY на вопрос 10
            if 'question_10_hay' in user_data:
                worksheet.Range("J19").Value = user_data['question_10_hay']
                print(f"   J19 (HAY Q10): {user_data['question_10_hay'][:50]}...")
            
            # K19 - ответ по HAY на вопрос 9
            if 'question_9_hay' in user_data:
                worksheet.Range("K19").Value = user_data['question_9_hay']
                print(f"   K19 (HAY Q9): {user_data['question_9_hay'][:50]}...")
            
            # L19 - ответ по HAY на вопрос 8
            if 'question_8_hay' in user_data:
                worksheet.Range("L19").Value = user_data['question_8_hay']
                print(f"   L19 (HAY Q8): {user_data['question_8_hay'][:50]}...")
            
            # M19 - ответ по HAY на вопрос 11
            if 'question_11_hay' in user_data:
                worksheet.Range("M19").Value = user_data['question_11_hay']
                print(f"   M19 (HAY Q11): {user_data['question_11_hay'][:50]}...")
            
            # N19 - ответ по HAY на вопрос 12
            if 'question_12_hay' in user_data:
                worksheet.Range("N19").Value = user_data['question_12_hay']
                print(f"   N19 (HAY Q12): {user_data['question_12_hay'][:50]}...")
            
            # O19 - ответ по HAY на вопрос 16
            if 'question_16_hay' in user_data:
                worksheet.Range("O19").Value = user_data['question_16_hay']
                print(f"   O19 (HAY Q16): {user_data['question_16_hay'][:50]}...")
            
            # P19 - ответ по HAY на вопрос 13
            if 'question_13_hay' in user_data:
                worksheet.Range("P19").Value = user_data['question_13_hay']
                print(f"   P19 (HAY Q13): {user_data['question_13_hay'][:50]}...")
            
            # Q19 - ответ по HAY на вопрос 14
            if 'question_14_hay' in user_data:
                worksheet.Range("Q19").Value = user_data['question_14_hay']
                print(f"   Q19 (HAY Q14): {user_data['question_14_hay'][:50]}...")
            
            print(f"[SUCCESS] Заполнение завершено")
            
        except Exception as e:
            print(f"[ERROR] Ошибка при заполнении шаблона: {e}")
            raise
    
    def _refresh_pivot_tables(self, workbook):
        """Обновляет все сводные таблицы в книге"""
        try:
            for sheet in workbook.Sheets:
                # Проверяем наличие сводных таблиц на листе
                try:
                    pivot_count = sheet.PivotTables().Count
                    if pivot_count > 0:
                        print(f"[INFO] Обновляем {pivot_count} сводных таблиц на листе '{sheet.Name}'")
                        for i in range(1, pivot_count + 1):
                            sheet.PivotTables(i).RefreshTable()
                except:
                    # На листе нет сводных таблиц, это нормально
                    pass
            
        except Exception as e:
            print(f"[WARNING] Ошибка при обновлении сводных таблиц: {e}")
            # Не падаем, если сводных нет


# Пример использования
if __name__ == "__main__":
    generator = XLSXReportGenerator()
    
    # Тест (замените на реальные ID)
    try:
        report_path = generator.generate_report(user_id=466718085, session_id=21)
        print(f"[SUCCESS] Отчет готов: {report_path}")
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")

