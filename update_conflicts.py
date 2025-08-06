#!/usr/bin/env python3
import pandas as pd
import sqlite3
import os

def update_conflicts():
    try:
        print("📋 Читаем конфликты из Excel...")
        # Читаем лист с конфликтами
        df = pd.read_excel('data/hag.xlsx', sheet_name='conflicts')
        print(f"📊 Найдено строк с конфликтами: {len(df)}")
        
        # Подключаемся к БД
        with sqlite3.connect('data/database.db') as conn:
            cursor = conn.cursor()
            
            # Создаем таблицу конфликтов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conflicts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question1_id INTEGER NOT NULL,
                    answer1_id INTEGER NOT NULL, 
                    question1_text TEXT NOT NULL,
                    answer1_text TEXT NOT NULL,
                    question2_id INTEGER NOT NULL,
                    answer2_id INTEGER NOT NULL,
                    question2_text TEXT NOT NULL,
                    answer2_text TEXT NOT NULL,
                    question3_id INTEGER,
                    answer3_id INTEGER,
                    question3_text TEXT,
                    answer3_text TEXT,
                    question4_id INTEGER,
                    answer4_id INTEGER,
                    question4_text TEXT,
                    answer4_text TEXT,
                    question5_id INTEGER,
                    answer5_id INTEGER,
                    question5_text TEXT,
                    answer5_text TEXT
                )
            """)
            
            # Очищаем таблицу
            cursor.execute("DELETE FROM conflicts")
            print("🗑️ Очистили старые конфликты")
            
            # Переносим данные
            conflicts_added = 0
            for _, row in df.iterrows():
                # Проверяем какие вопросы есть в строке
                has_third = pd.notna(row.iloc[8]) if len(row) > 8 else False
                has_fourth = pd.notna(row.iloc[12]) if len(row) > 12 else False
                has_fifth = pd.notna(row.iloc[16]) if len(row) > 16 else False
                
                # Базовые значения для INSERT
                values = [
                    int(row.iloc[0]), int(row.iloc[2]), str(row.iloc[1]), str(row.iloc[3]),  # вопрос 1
                    int(row.iloc[4]), int(row.iloc[6]), str(row.iloc[5]), str(row.iloc[7])   # вопрос 2
                ]
                
                # Добавляем третий вопрос
                if has_third:
                    values.extend([
                        int(row.iloc[8]), int(row.iloc[10]), str(row.iloc[9]), str(row.iloc[11])  # вопрос 3
                    ])
                else:
                    values.extend([None, None, None, None])
                
                # Добавляем четвертый вопрос
                if has_fourth:
                    values.extend([
                        int(row.iloc[12]), int(row.iloc[14]), str(row.iloc[13]), str(row.iloc[15])  # вопрос 4
                    ])
                else:
                    values.extend([None, None, None, None])
                
                # Добавляем пятый вопрос
                if has_fifth:
                    values.extend([
                        int(row.iloc[16]), int(row.iloc[18]), str(row.iloc[17]), str(row.iloc[19])  # вопрос 5
                    ])
                else:
                    values.extend([None, None, None, None])
                
                # Вставляем запись
                cursor.execute("""
                    INSERT INTO conflicts (
                        question1_id, answer1_id, question1_text, answer1_text,
                        question2_id, answer2_id, question2_text, answer2_text,
                        question3_id, answer3_id, question3_text, answer3_text,
                        question4_id, answer4_id, question4_text, answer4_text,
                        question5_id, answer5_id, question5_text, answer5_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, values)
                conflicts_added += 1
            
            conn.commit()
            print(f"✅ Загружено {conflicts_added} конфликтов в базу данных")
            
            # Проверяем результат
            cursor.execute("SELECT COUNT(*) FROM conflicts")
            count = cursor.fetchone()[0]
            print(f"🔍 Проверка: в таблице conflicts {count} записей")
    
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    update_conflicts()