# 📊 Настройка XLSX отчетов (калькулятор грейда)

## Требования

- **Windows** (для работы win32com)
- **Microsoft Excel** установлен на компьютере
- Python 3.10+

## Установка

### 1. Активируйте виртуальное окружение

```powershell
cd C:\Users\NDSko\Desktop\DevAI\HayAutoGrade
.\hag_venv\Scripts\activate
```

### 2. Установите pywin32

```powershell
pip install pywin32
```

или установите все зависимости:

```powershell
pip install -r requirements.txt
```

### 3. Проверьте наличие шаблона

Убедитесь, что файл `data/калькулятор.xlsx` существует и содержит лист "Расчет грейда".

### 4. Создана директория exports

Директория `exports/` уже создана для хранения сгенерированных файлов.

## Как это работает

1. **Пользователь завершает опрос** в Telegram боте
2. **Генерируется HTML отчет** (как раньше)
3. **Генерируется XLSX калькулятор**:
   - Открывается шаблон `data/калькулятор.xlsx`
   - Заполняется лист "Расчет грейда" строка 19:
     - D19 - путь из вопроса 3
     - I19 - роль (вопрос 1)
     - J19 - HAY вопрос 10
     - K19 - HAY вопрос 9
     - L19 - HAY вопрос 8
     - M19 - HAY вопрос 11
     - N19 - HAY вопрос 12
     - O19 - HAY вопрос 16
     - P19 - HAY вопрос 13
     - Q19 - HAY вопрос 14
   - Обновляются все формулы и сводные таблицы
   - Сохраняется как `exports/calculator_user_{ID}_session_{ID}_{timestamp}.xlsx`
4. **Файл отправляется пользователю** отдельным сообщением

## Структура файлов

```
HayAutoGrade/
├── data/
│   └── калькулятор.xlsx          # Шаблон с формулами
├── exports/                       # Сгенерированные XLSX файлы
│   └── calculator_user_123_session_1_20251030_021530.xlsx
├── reports/                       # HTML отчеты
├── xlsx_report_generator.py       # Генератор XLSX
└── telegram_bot.py                # Интеграция с ботом
```

## Тестирование

Для тестирования генератора без бота:

```python
from xlsx_report_generator import XLSXReportGenerator

generator = XLSXReportGenerator()
report_path = generator.generate_report(user_id=123, session_id=1)
print(f"Отчет создан: {report_path}")
```

Откройте созданный файл в Excel и проверьте:
- ✅ Все ячейки заполнены
- ✅ Формулы работают
- ✅ Сводные таблицы обновлены
- ✅ Условное форматирование применено

## Возможные проблемы

### Ошибка: "Excel.Application не найден"

**Решение:** Установите Microsoft Excel

### Ошибка: "Лист 'Расчет грейда' не найден"

**Решение:** Проверьте шаблон `data/калькулятор.xlsx`

### Excel процессы зависают

**Решение:** Завершите процессы Excel вручную:

```powershell
taskkill /F /IM EXCEL.EXE
```

### Файлы не генерируются

**Решение:** Проверьте права доступа к директории `exports/`

## Отключение XLSX отчетов

Если нужно временно отключить генерацию XLSX, закомментируйте строку в `telegram_bot.py`:

```python
# await self.generate_and_send_xlsx_report(message, user_id, session_id)
```

## Безопасность

- Файлы в `exports/` содержат персональные данные пользователей
- **НЕ добавляйте** директорию `exports/` в git (уже в `.gitignore`)
- Регулярно очищайте старые файлы или настройте автоматическую очистку

## Очистка старых файлов

Создайте задачу для периодической очистки:

```python
import os
import time

def cleanup_old_exports(days=30):
    """Удаляет файлы старше N дней"""
    exports_dir = "exports"
    now = time.time()
    
    for filename in os.listdir(exports_dir):
        filepath = os.path.join(exports_dir, filename)
        if os.path.isfile(filepath):
            file_age_days = (now - os.path.getmtime(filepath)) / 86400
            if file_age_days > days:
                os.remove(filepath)
                print(f"Удален старый файл: {filename}")
```

## Поддержка

При возникновении проблем проверьте:
1. Excel установлен и работает
2. pywin32 установлен корректно
3. Шаблон существует и не поврежден
4. В логах нет ошибок Python

