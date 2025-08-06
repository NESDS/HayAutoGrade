import sqlite3
import pandas as pd

with sqlite3.connect("data/database.db") as conn:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS questions")
    cursor.execute("""
        CREATE TABLE questions (
            id INTEGER PRIMARY KEY,
            question TEXT,
            answer_options TEXT,
            verification_instruction TEXT,
            classifier TEXT,
            show_conditions TEXT
        )
    """)
    
    df = pd.read_excel("data/hag.xlsx")
    
    for _, row in df.iterrows():
        cursor.execute("""
            INSERT INTO questions (id, question, answer_options, verification_instruction, classifier, show_conditions)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            row['ID'], 
            row['Вопрос'], 
            row.get('Варианты_ответов'),
            row['Инструкция_проверки'], 
            row.get('Классификатор'),
            row.get('Условия_показа')
        ))
    
    conn.commit() 