"""
Главный файл для запуска HAG MVP бота
"""

import asyncio
from telegram_bot import main

def start_bot():
    """Запуск бота"""
    print("Бот запущен и работает!")
    asyncio.run(main())

if __name__ == "__main__":
    start_bot()