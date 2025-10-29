"""
Скрипт для обработки файла штата и создания иерархической структуры
роль -> id -> id_rod (родительский id)
"""

import pandas as pd
import sqlite3
import os


def build_hierarchy_from_excel(excel_path):
    """
    Читает Excel файл со штатом и строит иерархическую структуру
    
    Возвращает DataFrame с колонками: роль, id, id_rod, полный_путь
    """
    # Читаем Excel файл
    df = pd.read_excel(excel_path)
    
    print(f"Прочитано {len(df)} строк из файла")
    print(f"Колонки: {df.columns.tolist()}\n")
    
    # Структура для хранения иерархии
    hierarchy = []
    role_to_id = {}  # Словарь для отслеживания уже созданных ролей
    id_to_role = {}  # Словарь для получения названия роли по ID
    current_id = 0
    
    # Функция для получения или создания ID для роли
    def get_or_create_id(role_name, parent_id=None):
        nonlocal current_id
        
        # Создаём уникальный ключ для роли (роль + родитель)
        key = (role_name, parent_id)
        
        if key not in role_to_id:
            current_id += 1
            role_to_id[key] = current_id
            id_to_role[current_id] = role_name
            hierarchy.append({
                'роль': role_name,
                'id': current_id,
                'id_rod': parent_id if parent_id is not None else 0,
                'полный_путь': ''  # Заполним позже
            })
        
        return role_to_id[key]
    
    # Обрабатываем каждую строку
    for idx, row in df.iterrows():
        # Получаем компанию (уровень 0)
        company = row['Компания']
        if pd.isna(company):
            continue
            
        # Создаём или получаем ID компании (родитель = 0)
        company_id = get_or_create_id(company, parent_id=None)
        
        # Строим цепочку: Компания -> Уровень 1 -> Уровень 2 -> ... -> Оцениваемая роль
        parent_id = company_id
        
        # Проходим по уровням иерархии (Уровень 1, 2, 3, 4, ...)
        level_columns = [col for col in df.columns if col.startswith('Уровень')]
        
        for level_col in level_columns:
            level_value = row[level_col]
            
            # Пропускаем пустые значения
            if pd.isna(level_value):
                break
            
            # Очищаем от лишних символов (например, \n в конце)
            level_value = str(level_value).strip()
            
            # Создаём или получаем ID для этого уровня
            level_id = get_or_create_id(level_value, parent_id)
            parent_id = level_id
        
        # Добавляем саму оцениваемую роль как конечный узел
        role_name = row['Оцениваемая роль']
        if not pd.isna(role_name):
            role_name = str(role_name).strip()
            get_or_create_id(role_name, parent_id)
    
    # Создаём DataFrame из результата
    result_df = pd.DataFrame(hierarchy)
    
    # Сортируем по id для удобства
    result_df = result_df.sort_values('id').reset_index(drop=True)
    
    # Функция для построения полного пути для элемента
    def build_full_path(item_id, df):
        path_parts = []
        current_id = item_id
        
        # Поднимаемся по иерархии до корня
        while current_id != 0:
            row = df[df['id'] == current_id].iloc[0]
            path_parts.insert(0, row['роль'])
            current_id = row['id_rod']
        
        return ' -> '.join(path_parts)
    
    # Заполняем полный путь для каждого элемента
    print("Построение полных путей...")
    result_df['полный_путь'] = result_df['id'].apply(lambda x: build_full_path(x, result_df))
    
    return result_df


def save_hierarchy_to_excel(hierarchy_df, output_path):
    """
    Сохраняет иерархию в Excel файл
    """
    hierarchy_df.to_excel(output_path, index=False, sheet_name='Иерархия')
    print(f"\nРезультат сохранён в Excel: {output_path}")


def load_hierarchy_to_db(hierarchy_df, db_path):
    """
    Загружает иерархию в базу данных SQLite
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Удаляем старую таблицу, если существует
        cursor.execute("DROP TABLE IF EXISTS shtat_hierarchy")
        
        # Создаём новую таблицу
        cursor.execute("""
            CREATE TABLE shtat_hierarchy (
                id INTEGER PRIMARY KEY,
                role TEXT NOT NULL,
                id_rod INTEGER NOT NULL,
                full_path TEXT NOT NULL
            )
        """)
        
        # Загружаем данные
        for _, row in hierarchy_df.iterrows():
            cursor.execute("""
                INSERT INTO shtat_hierarchy (id, role, id_rod, full_path)
                VALUES (?, ?, ?, ?)
            """, (
                row['id'],
                row['роль'],
                row['id_rod'],
                row['полный_путь']
            ))
        
        conn.commit()
    
    print(f"Загружено {len(hierarchy_df)} записей в таблицу shtat_hierarchy")
    print(f"База данных: {db_path}")


def print_hierarchy_tree(hierarchy_df, parent_id=0, level=0, max_display=50):
    """
    Выводит иерархию в виде дерева (для визуализации)
    """
    items = hierarchy_df[hierarchy_df['id_rod'] == parent_id]
    
    displayed = 0
    for _, item in items.iterrows():
        if displayed >= max_display:
            print("  " * level + "... (ещё элементы)")
            break
            
        print("  " * level + f"[{item['id']}] {item['роль']}")
        displayed += 1
        
        # Рекурсивно выводим детей
        print_hierarchy_tree(hierarchy_df, item['id'], level + 1, max_display - displayed)


def main():
    # Путь к файлу
    base_dir = os.path.dirname(os.path.abspath(__file__))
    excel_path = os.path.join(base_dir, 'data', 'штат.xlsx')
    
    print("="*80)
    print("ОБРАБОТКА ФАЙЛА ШТАТА")
    print("="*80)
    
    # Проверяем существование файла
    if not os.path.exists(excel_path):
        print(f"ОШИБКА: Файл не найден: {excel_path}")
        return
    
    # Строим иерархию
    print(f"\nЧтение файла: {excel_path}\n")
    hierarchy_df = build_hierarchy_from_excel(excel_path)
    
    # Выводим статистику
    print("\n" + "="*80)
    print("СТАТИСТИКА")
    print("="*80)
    print(f"Всего элементов в иерархии: {len(hierarchy_df)}")
    print(f"Корневых элементов (id_rod = 0): {len(hierarchy_df[hierarchy_df['id_rod'] == 0])}")
    
    # Выводим первые 15 записей
    print("\n" + "="*80)
    print("ПЕРВЫЕ 15 ЗАПИСЕЙ")
    print("="*80)
    pd.set_option('display.max_colwidth', 60)
    print(hierarchy_df.head(15).to_string(index=False))
    
    # Выводим примеры с полным путем
    print("\n" + "="*80)
    print("ПРИМЕРЫ С ПОЛНЫМ ПУТЕМ")
    print("="*80)
    print("\nПримеры конечных ролей с полными путями:")
    # Показываем несколько примеров ролей с длинными путями
    sample_roles = hierarchy_df[hierarchy_df['полный_путь'].str.contains(' -> ', na=False)].sample(min(10, len(hierarchy_df)))
    for _, row in sample_roles.iterrows():
        print(f"\n[ID: {row['id']}] {row['роль']}")
        print(f"   Путь: {row['полный_путь']}")
    
    # Выводим дерево иерархии
    print("\n" + "="*80)
    print("ДЕРЕВО ИЕРАРХИИ (первые 50 узлов)")
    print("="*80)
    print_hierarchy_tree(hierarchy_df, parent_id=0, level=0, max_display=50)
    
    # Сохраняем результаты
    print("\n" + "="*80)
    print("СОХРАНЕНИЕ РЕЗУЛЬТАТОВ")
    print("="*80)
    
    # Сохраняем в Excel
    output_excel = os.path.join(base_dir, 'data', 'штат_иерархия.xlsx')
    save_hierarchy_to_excel(hierarchy_df, output_excel)
    
    # Загружаем в базу данных
    db_path = os.path.join(base_dir, 'data', 'database.db')
    load_hierarchy_to_db(hierarchy_df, db_path)
    
    print("\n" + "="*80)
    print("ГОТОВО!")
    print("="*80)


if __name__ == '__main__':
    main()

