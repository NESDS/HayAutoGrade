"""
Главный файл для запуска HAG MVP бота.

Поддерживает два режима:
- Telegram бот (по умолчанию)
- СберЧат бот (--sberchat)

Использование:
    python main.py              # Запуск Telegram бота
    python main.py --sberchat   # Запуск СберЧат бота
    python main.py --telegram   # Явный запуск Telegram бота
"""

import sys
import asyncio
import argparse


def start_telegram_bot():
    """Запуск Telegram бота"""
    from telegram_bot import main
    print("🤖 Запускаю Telegram бота...")
    asyncio.run(main())


def start_sberchat_bot():
    """Запуск СберЧат бота"""
    from sberchat_bot import main, SBERCHAT_AVAILABLE
    
    if not SBERCHAT_AVAILABLE:
        print("❌ sber-sberchat-bot-sdk не установлен!")
        print("   Установите пакет из корпоративного репозитория")
        print("   Или используйте Telegram: python main.py --telegram")
        sys.exit(1)
    
    print("🤖 Запускаю СберЧат бота...")
    main()


def main():
    parser = argparse.ArgumentParser(description="HayAutoGrade Bot")
    parser.add_argument("--sberchat", action="store_true", help="Запустить СберЧат бота")
    parser.add_argument("--telegram", action="store_true", help="Запустить Telegram бота (по умолчанию)")
    args = parser.parse_args()
    
    print("=" * 50)
    print("🎯 HayAutoGrade - HAY Group Grade Assessment Bot")
    print("=" * 50)
    
    if args.sberchat:
        start_sberchat_bot()
    else:
        start_telegram_bot()


if __name__ == "__main__":
    main()
