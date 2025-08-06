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
                    answer3_text TEXT
                )
            """)
            
            # Очищаем таблицу
            cursor.execute("DELETE FROM conflicts")
            print("🗑️ Очистили старые конфликты")
            
            # Переносим данные
            conflicts_added = 0
            for _, row in df.iterrows():
                # Проверяем есть ли третий вопрос (колонка 8 = номер вопроса 3)
                has_third = pd.notna(row.iloc[8])
                
                if has_third:
                    # Конфликт из 3 вопросов
                    cursor.execute("""
                        INSERT INTO conflicts (
                            question1_id, answer1_id, question1_text, answer1_text,
                            question2_id, answer2_id, question2_text, answer2_text,
                            question3_id, answer3_id, question3_text, answer3_text
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        int(row.iloc[0]), int(row.iloc[2]), str(row.iloc[1]), str(row.iloc[3]),  # вопрос 1
                        int(row.iloc[4]), int(row.iloc[6]), str(row.iloc[5]), str(row.iloc[7]),  # вопрос 2  
                        int(row.iloc[8]), int(row.iloc[10]), str(row.iloc[9]), str(row.iloc[11]) # вопрос 3
                    ))
                    conflicts_added += 1
                else:
                    # Конфликт из 2 вопросов
                    cursor.execute("""
                        INSERT INTO conflicts (
                            question1_id, answer1_id, question1_text, answer1_text,
                            question2_id, answer2_id, question2_text, answer2_text
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        int(row.iloc[0]), int(row.iloc[2]), str(row.iloc[1]), str(row.iloc[3]),  # вопрос 1
                        int(row.iloc[4]), int(row.iloc[6]), str(row.iloc[5]), str(row.iloc[7])   # вопрос 2
                    ))
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