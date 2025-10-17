#!/usr/bin/env python3
import pandas as pd
import sqlite3
import os

def extract_answer_value(variant_text: str) -> int:
    """
    Извлечь номер ответа из текста варианта
    "1. Стандартные задачи..." -> 1
    "2. Типовые задачи..." -> 2
    ...
    "8. Инновационные решения..." -> 8
    """
    text = str(variant_text).strip()
    
    for i in range(1, 9):  # от 1 до 8
        if text.startswith(f'{i}.'):
            return i
    
    raise ValueError(f"Неизвестный формат варианта: {variant_text}")

def update_question_variants():
    """Обновление таблиц для связанных вариантов вопросов 11 и 12"""
    try:
        print("📋 Читаем связанные варианты Q11-Q12 из Excel...")
        
        # Подключаемся к БД
        with sqlite3.connect('data/database.db') as conn:
            cursor = conn.cursor()
            
            # Читаем единый лист q11-12
            df = pd.read_excel('data/hag.xlsx', sheet_name='q11-12')
            print(f"📊 Найдено строк в листе q11-12: {len(df)}")
            print(f"📊 Колонки: {list(df.columns)}")
            
            # Удаляем старые таблицы
            cursor.execute("DROP TABLE IF EXISTS question_variants_q11")
            cursor.execute("DROP TABLE IF EXISTS question_variants_q12")
            print("🗑️ Удалили старые таблицы question_variants_q11 и question_variants_q12")
            
            # Создаем новую объединенную таблицу question_variants_q11_q12
            cursor.execute("""
                CREATE TABLE question_variants_q11_q12 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    p1_value INTEGER NOT NULL,
                    q11_variant_text TEXT NOT NULL,
                    q11_answer_value INTEGER NOT NULL,
                    q12_variant_text TEXT NOT NULL,
                    q12_answer_value INTEGER NOT NULL
                )
            """)
            print("✅ Создана новая таблица question_variants_q11_q12")
            
            # Определяем структуру данных по колонкам
            columns = list(df.columns)
            print(f"🔍 Анализируем структуру данных...")
            
            # Предполагаемая структура: p1, q11_text, q12_text
            # Или: p1, q11_text, q11_answer, q12_text, q12_answer
            variants_added = 0
            
            for _, row in df.iterrows():
                try:
                    # Базовое извлечение p1
                    p1_value = int(row.iloc[0])  # Первая колонка всегда P1
                    
                    # Извлекаем Q11 данные
                    q11_variant_text = str(row.iloc[1]).strip()  # Вторая колонка - Q11 текст
                    q11_answer_value = extract_answer_value(q11_variant_text)
                    
                    # Извлекаем Q12 данные
                    # Ищем колонку с Q12 (может быть 2-я, 3-я или далее)
                    q12_variant_text = None
                    for col_idx in range(2, len(row)):
                        if pd.notna(row.iloc[col_idx]):
                            candidate_text = str(row.iloc[col_idx]).strip()
                            # Проверяем, что это похоже на вариант ответа (начинается с цифры)
                            try:
                                extract_answer_value(candidate_text)
                                q12_variant_text = candidate_text
                                break
                            except ValueError:
                                continue
                    
                    if q12_variant_text is None:
                        print(f"⚠️ Не найден Q12 текст для строки с P1={p1_value}")
                        continue
                    
                    q12_answer_value = extract_answer_value(q12_variant_text)
                    
                    # Сохраняем в БД
                    cursor.execute("""
                        INSERT INTO question_variants_q11_q12 
                        (p1_value, q11_variant_text, q11_answer_value, q12_variant_text, q12_answer_value)
                        VALUES (?, ?, ?, ?, ?)
                    """, (p1_value, q11_variant_text, q11_answer_value, q12_variant_text, q12_answer_value))
                    variants_added += 1
                    
                except Exception as e:
                    print(f"⚠️ Пропущена строка: {e}")
                    continue
            
            conn.commit()
            print(f"✅ Загружено связанных вариантов Q11-Q12: {variants_added}")
            
            # Проверяем результат
            cursor.execute("SELECT COUNT(*) FROM question_variants_q11_q12")
            total_count = cursor.fetchone()[0]
            
            print(f"🔍 Проверка: в таблице question_variants_q11_q12 {total_count} записей")
            
            # Показываем примеры данных
            cursor.execute("SELECT p1_value, q11_answer_value, q12_answer_value FROM question_variants_q11_q12 LIMIT 5")
            samples = cursor.fetchall()
            print("🔍 Примеры данных:")
            for p1, q11_ans, q12_ans in samples:
                print(f"   P1={p1} → Q11={q11_ans} → Q12={q12_ans}")
    
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    update_question_variants()
