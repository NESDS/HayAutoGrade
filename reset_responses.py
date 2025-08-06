#!/usr/bin/env python3
"""
Сброс и пересоздание таблицы responses
"""

import sqlite3

def reset_responses_table():
    try:
        with sqlite3.connect("data/database.db") as conn:
            cursor = conn.cursor()
            
            print("🗑️  Удаление старой таблицы responses...")
            cursor.execute("DROP TABLE IF EXISTS responses")
            
            print("📋 Создание таблицы responses...")
            cursor.execute("""
                CREATE TABLE responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user INTEGER,
                    session_id INTEGER,
                    question INTEGER,
                    answer TEXT,
                    final_answer TEXT,
                    user_state TEXT,
                    status TEXT DEFAULT 'active'
                )
            """)
            
            conn.commit()
            print("✅ Таблица responses пересоздана!")
            print("📝 Структура:")
            print("   - Одна таблица responses")
            print("   - Поле user_state для состояний")
            print("   - Поле status для отслеживания статуса ответов")
            print("   - Статусы: 'active', 'inactive'")
            
    except Exception as e:
        print(f"❌ Ошибка при пересоздании таблицы: {e}")

if __name__ == "__main__":
    reset_responses_table() 