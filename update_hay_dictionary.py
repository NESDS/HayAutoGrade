import sqlite3
import pandas as pd

with sqlite3.connect("data/database.db") as conn:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS hay_dictionary")
    cursor.execute("""
        CREATE TABLE hay_dictionary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_number INTEGER NOT NULL,
            answer_number INTEGER NOT NULL,
            hay_definition TEXT NOT NULL,
            UNIQUE(question_number, answer_number)
        )
    """)
    
    df = pd.read_excel("data/hag.xlsx", sheet_name="dict_hay")
    
    for _, row in df.iterrows():
        cursor.execute("""
            INSERT INTO hay_dictionary (question_number, answer_number, hay_definition)
            VALUES (?, ?, ?)
        """, (
            row['номер вопроса'], 
            row['номер ответа'], 
            row['определение по hay']
        ))
    
    conn.commit()
    
    print(f"✅ Загружено {len(df)} определений из справочника Hay")

