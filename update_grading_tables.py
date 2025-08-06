#!/usr/bin/env python3
import pandas as pd
import sqlite3
import os

def update_grading_tables():
    """Обновление таблиц для расчета грейда из Excel файла"""
    try:
        print("📋 Читаем таблицы грейдинга из Excel...")
        
        # Подключаемся к БД
        with sqlite3.connect('data/database.db') as conn:
            cursor = conn.cursor()
            
            # === ТАБЛИЦА P1 ===
            print("📊 Обрабатываем таблицу P1...")
            df_p1 = pd.read_excel('data/hag.xlsx', sheet_name='p1')
            
            # Создаем таблицу p1
            cursor.execute("DROP TABLE IF EXISTS grading_p1")
            cursor.execute("""
                CREATE TABLE grading_p1 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    answer_q8 INTEGER,
                    answer_q9 INTEGER, 
                    answer_q10 INTEGER,
                    p1_value INTEGER
                )
            """)
            
            # Заполняем таблицу p1
            for _, row in df_p1.iterrows():
                cursor.execute("""
                    INSERT INTO grading_p1 (answer_q8, answer_q9, answer_q10, p1_value)
                    VALUES (?, ?, ?, ?)
                """, (
                    int(row.iloc[0]),  # ответ на вопрос 8
                    int(row.iloc[1]),  # ответ на вопрос 9  
                    int(row.iloc[2]),  # ответ на вопрос 10
                    int(row.iloc[3])   # значение p1
                ))
            
            # === ТАБЛИЦА P2 ===
            print("📊 Обрабатываем таблицу P2...")
            df_p2 = pd.read_excel('data/hag.xlsx', sheet_name='p2')
            
            # Создаем таблицу p2
            cursor.execute("DROP TABLE IF EXISTS grading_p2")
            cursor.execute("""
                CREATE TABLE grading_p2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    answer_q11 INTEGER,
                    answer_q12 INTEGER,
                    p2_value INTEGER
                )
            """)
            
            # Заполняем таблицу p2
            for _, row in df_p2.iterrows():
                cursor.execute("""
                    INSERT INTO grading_p2 (answer_q11, answer_q12, p2_value)
                    VALUES (?, ?, ?)
                """, (
                    int(row.iloc[0]),  # ответ на вопрос 11
                    int(row.iloc[1]),  # ответ на вопрос 12
                    int(row.iloc[2])   # значение p2
                ))
            
            # === ТАБЛИЦА P3 ===
            print("📊 Обрабатываем таблицу P3...")
            df_p3 = pd.read_excel('data/hag.xlsx', sheet_name='p3')
            
            # Создаем таблицу p3 (таблица поиска по p1 и p2)
            cursor.execute("DROP TABLE IF EXISTS grading_p3")
            cursor.execute("""
                CREATE TABLE grading_p3 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    p1_value REAL,
                    p2_value INTEGER,
                    p3_value INTEGER
                )
            """)
            
            # Заполняем таблицу p3
            for _, row in df_p3.iterrows():
                cursor.execute("""
                    INSERT INTO grading_p3 (p1_value, p2_value, p3_value)
                    VALUES (?, ?, ?)
                """, (
                    float(row.iloc[0]),  # p1 значение
                    int(row.iloc[1]),    # p2 значение
                    int(row.iloc[2])     # p3 значение
                ))
                
            # === ТАБЛИЦА P4-14 ===
            print("📊 Обрабатываем таблицу P4-14...")
            df_p4_14 = pd.read_excel('data/hag.xlsx', sheet_name='p4-14')
            
            # Создаем таблицу p4_14
            cursor.execute("DROP TABLE IF EXISTS grading_p4_14")
            cursor.execute("""
                CREATE TABLE grading_p4_14 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    answer_q16 INTEGER,
                    answer_q13 INTEGER,
                    answer_q14 INTEGER,
                    p4_value INTEGER
                )
            """)
            
            # Заполняем таблицу p4_14
            for _, row in df_p4_14.iterrows():
                cursor.execute("""
                    INSERT INTO grading_p4_14 (answer_q16, answer_q13, answer_q14, p4_value)
                    VALUES (?, ?, ?, ?)
                """, (
                    int(row.iloc[0]),  # ответ на вопрос 16
                    int(row.iloc[1]),  # ответ на вопрос 13
                    int(row.iloc[2]),  # ответ на вопрос 14
                    int(row.iloc[3])   # значение p4
                ))
                
            # === ТАБЛИЦА P4-15 ===
            print("📊 Обрабатываем таблицу P4-15...")
            df_p4_15 = pd.read_excel('data/hag.xlsx', sheet_name='p4-15')
            
            # Создаем таблицу p4_15
            cursor.execute("DROP TABLE IF EXISTS grading_p4_15")
            cursor.execute("""
                CREATE TABLE grading_p4_15 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    answer_q16 INTEGER,
                    answer_q13 INTEGER,
                    answer_q15 INTEGER,
                    p4_value INTEGER
                )
            """)
            
            # Заполняем таблицу p4_15
            for _, row in df_p4_15.iterrows():
                cursor.execute("""
                    INSERT INTO grading_p4_15 (answer_q16, answer_q13, answer_q15, p4_value)
                    VALUES (?, ?, ?, ?)
                """, (
                    int(row.iloc[0]),  # ответ на вопрос 16
                    int(row.iloc[1]),  # ответ на вопрос 13
                    int(row.iloc[2]),  # ответ на вопрос 15
                    int(row.iloc[3])   # значение p4
                ))
                
            # === ТАБЛИЦА ГРЕЙД ===
            print("📊 Обрабатываем таблицу грейдов...")
            df_grade = pd.read_excel('data/hag.xlsx', sheet_name='грейд')
            
            # Создаем таблицу грейдов
            cursor.execute("DROP TABLE IF EXISTS grading_scale")
            cursor.execute("""
                CREATE TABLE grading_scale (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    low_bound INTEGER,
                    mid_point INTEGER,
                    high_bound INTEGER,
                    sber_grade TEXT
                )
            """)
            
            # Заполняем таблицу грейдов
            for _, row in df_grade.iterrows():
                if pd.notna(row.iloc[0]):  # Пропускаем пустые строки
                    cursor.execute("""
                        INSERT INTO grading_scale (low_bound, mid_point, high_bound, sber_grade)
                        VALUES (?, ?, ?, ?)
                    """, (
                        int(row.iloc[0]),      # Low
                        int(row.iloc[1]),      # Mid point  
                        int(row.iloc[2]),      # High
                        str(row.iloc[3]) if pd.notna(row.iloc[3]) else None  # Sber Grade
                    ))
            
            conn.commit()
            print("✅ Все таблицы грейдинга успешно загружены в базу данных")
            
            # Проверяем результат
            tables = ['grading_p1', 'grading_p2', 'grading_p3', 'grading_p4_14', 'grading_p4_15', 'grading_scale']
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"🔍 Таблица {table}: {count} записей")
    
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    update_grading_tables()