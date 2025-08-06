import asyncio
from typing import List, Dict
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from aiogram import F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, BotCommand

from database import Database
from config import TELEGRAM_BOT_TOKEN
from processing_agents import verification_agent, answer_agent, classification_agent
from html_report_generator import HTMLReportGenerator

class TelegramBot:
    def __init__(self):
        self.bot = Bot(token=TELEGRAM_BOT_TOKEN)
        self.dp = Dispatcher()
        self.db = Database()
        self.report_generator = HTMLReportGenerator()
        # Словарь для хранения активных сессий пользователей
        self.active_sessions = {}
        
        self.dp.message.register(self.start_command, Command("start"))
        self.dp.message.register(self.handle_message, ~F.text.startswith("/"))
    
    async def start_command(self, message: Message):
        """Начать опрос"""
        user_id = message.from_user.id
        session_id = self.db.get_next_session_id(user_id)
        
        # Получаем список вопросов с правильной фильтрацией
        remaining_questions = self.db.get_remaining_questions(user_id, session_id)
        
        # Создаем новое состояние пользователя
        state = {
            'session_id': session_id,
            'remaining_questions': remaining_questions,
            'conversation': []
        }
        
        # Сохраняем активную сессию и состояние в памяти
        self.active_sessions[user_id] = {
            'session_id': session_id,
            'state': state
        }
        
        await message.answer(f"Начинаю опрос! (Сессия #{session_id})")
        await self.send_next_question(message, user_id, session_id)
    
    async def send_question(self, message: Message, question_id: int):
        """Отправить вопрос"""
        question_data = self.db.get_question(question_id)
        
        if question_data['answer_options']:
            options = [opt.strip() for opt in question_data['answer_options'].split(';')]
            keyboard = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text=opt)] for opt in options],
                resize_keyboard=True
            )
            await message.answer(f"Вопрос {question_id}: {question_data['question']}", reply_markup=keyboard)
        else:
            await message.answer(f"Вопрос {question_id}: {question_data['question']}", reply_markup=ReplyKeyboardRemove())
    
    async def handle_message(self, message: Message):
        """Обработка ответов"""
        user_id = message.from_user.id
        user_answer = message.text
        
        print(f"🔍 Получено сообщение от пользователя {user_id}: '{user_answer}'")
        
        # Проверяем, есть ли активная сессия для пользователя
        if user_id not in self.active_sessions:
            print("❌ Нет активной сессии, отправляю сообщение о /start")
            await message.answer("Напишите /start для начала опроса")
            return
            
        session_data = self.active_sessions[user_id]
        session_id = session_data['session_id']
        state = session_data['state']
        
        print(f"🔍 Active Session ID: {session_id}")
        print(f"🔍 User state: {state}")
        
        if not state:
            print("❌ Состояние не найдено, отправляю сообщение о /start")
            await message.answer("Напишите /start для начала опроса")
            return
        
        if not state['remaining_questions']:
            await message.answer("🎉 Опрос завершен!", reply_markup=ReplyKeyboardRemove())
            # Удаляем только активную сессию из памяти, состояние остается в БД
            if user_id in self.active_sessions:
                del self.active_sessions[user_id]
            return
            
        current_question = state['remaining_questions'][0]
        question_data = self.db.get_question(current_question)
        print(f"🔍 Current question: {current_question}")
        print(f"🔍 Question text: {question_data['question']}")
        print(f"🔍 Conversation before: {state['conversation']}")
        
        # Добавляем ответ пользователя в conversation
        state['conversation'].append(user_answer)
        
        # Обновляем состояние в памяти
        self.active_sessions[user_id]['state'] = state
        
        print(f"🔍 Conversation after: {state['conversation']}")
        
        if question_data['answer_options']:
            final_answer = classification_agent.classify_answer(question_data, user_answer)
            
            # Сначала сохраняем ответ в БД без обновленного state
            self.db.save_response(user_id, session_id, current_question, user_answer, final_answer, None)
            
            # Теперь пересчитываем список оставшихся вопросов с учетом нового ответа
            state['remaining_questions'] = self.db.get_remaining_questions(user_id, session_id)
            state['conversation'] = []  # Сбрасываем conversation для следующего вопроса
            
            # Обновляем состояние в памяти
            self.active_sessions[user_id]['state'] = state
            
            # Сохраняем обновленное состояние
            self.db.save_user_state(user_id, session_id, state)
            
            await self.next_question(message, user_id, session_id)
        else:
            is_accepted, response_text = verification_agent.process_answer(
                question_data, user_answer, state['conversation']
            )
            
            if is_accepted:
                full_answer = answer_agent.create_full_answer(question_data, state['conversation'])
                final_answer = classification_agent.classify_answer(question_data, full_answer)
                
                # Сначала сохраняем ответ в БД без обновленного state + проверяем конфликты
                # В поле answer записываем полный ответ из диалога, а не только последнее сообщение
                response_id, conflicts = self.db.save_response(user_id, session_id, current_question, full_answer, final_answer, None)
                
                # Проверяем конфликты
                if conflicts:
                    # Берем первый конфликт (может быть только один)
                    first_conflict = conflicts[0]
                    await self.handle_conflict(message, user_id, session_id, first_conflict, state)
                    return  # Прекращаем обработку, конфликт обнаружен
                
                # Теперь пересчитываем список оставшихся вопросов с учетом нового ответа
                state['remaining_questions'] = self.db.get_remaining_questions(user_id, session_id)
                state['conversation'] = []  # Сбрасываем conversation для следующего вопроса
                
                # Обновляем состояние в памяти
                self.active_sessions[user_id]['state'] = state
                
                # Сохраняем обновленное состояние
                self.db.save_user_state(user_id, session_id, state)
                
                await message.answer(f"✅ Принято! {response_text}")
                await self.next_question(message, user_id, session_id)
            else:
                # Добавляем вопрос бота в conversation и обновляем состояние
                state['conversation'].append(response_text)
                
                # Обновляем состояние в памяти
                self.active_sessions[user_id]['state'] = state
                
                await message.answer(f"❓ {response_text}")
    
    async def handle_conflict(self, message: Message, user_id: int, session_id: int, 
                            conflict: Dict, state: Dict):
        """Обработка обнаруженного конфликта"""
        from conflictator import ConflictDetector
        from llm_service import LLMService
        
        detector = ConflictDetector(self.db)
        llm = LLMService()
        
        # Генерируем промпт для объяснения конфликта
        explanation_prompt = detector.generate_conflict_explanation(conflict)
        
        # Получаем объяснение от LLM
        messages = [{"role": "user", "content": explanation_prompt}]
        explanation = llm.generate_response(messages)
        
        print("📥 КОНФЛИКТАТОР - Получен ответ от LLM:")
        print("-" * 50)
        print(explanation)
        print("-" * 50)
        
        # Получаем ID вопросов, участвующих в конфликте
        conflicted_questions = conflict['question_ids']
        print(f"🔄 КОНФЛИКТАТОР - Возвращаем вопросы в очередь: {conflicted_questions}")
        
        # Добавляем конфликтующие вопросы обратно в remaining (с учетом подвопросов)
        self.db.add_questions_to_remaining(user_id, session_id, conflicted_questions)
        
        # Обновляем состояние
        state['remaining_questions'] = self.db.get_remaining_questions(user_id, session_id)
        state['conversation'] = []  # Сбрасываем conversation
        
        # Обновляем состояние в памяти и БД
        self.active_sessions[user_id]['state'] = state
        self.db.save_user_state(user_id, session_id, state)
        
        # Сообщаем пользователю о конфликте
        await message.answer(f"⚠️ Обнаружено противоречие в ваших ответах!")
        await message.answer(f"🤖 {explanation}")
        await message.answer(f"🔄 Предлагаю ответить на некоторые вопросы заново...")
        
        # Продолжаем опрос с конфликтующих вопросов
        await self.next_question(message, user_id, session_id)
    
    async def next_question(self, message: Message, user_id: int, session_id: int):
        """Переход к следующему вопросу"""
        await self.send_next_question(message, user_id, session_id)
    
    async def send_next_question(self, message: Message, user_id: int, session_id: int):
        """Отправить следующий вопрос из списка"""
        # Получаем состояние из памяти
        if user_id not in self.active_sessions:
            await message.answer("Напишите /start для начала опроса")
            return
            
        state = self.active_sessions[user_id]['state']
        
        if state['remaining_questions']:
            next_question_id = state['remaining_questions'][0]
            await self.send_question(message, next_question_id)
        else:
            # Сохраняем финальное состояние с пустым remaining_questions
            self.db.save_user_state(user_id, session_id, state)
            # Удаляем только активную сессию из памяти, состояние остается в БД
            if user_id in self.active_sessions:
                del self.active_sessions[user_id]
            
            # Генерируем и отправляем отчет
            await self.generate_and_send_report(message, user_id, session_id)
    
    async def generate_and_send_report(self, message: Message, user_id: int, session_id: int):
        """Генерирует HTML отчет и отправляет пользователю"""
        try:
            await message.answer("🎉 Опрос завершен! Генерирую ваш отчет...", reply_markup=ReplyKeyboardRemove())
            
            # Генерируем HTML отчет
            report_path = self.report_generator.save_report_to_file(
                user_id=user_id, 
                session_id=session_id,
                output_path=f"reports/report_user_{user_id}_session_{session_id}.html"
            )
            
            # Отправляем файл пользователю
            from aiogram.types import FSInputFile
            document = FSInputFile(report_path)
            
            await message.answer_document(
                document=document,
                caption=f"📊 Ваш персональный отчет по опросу\n"
                       f"👤 Пользователь: #{user_id}\n"
                       f"📋 Сессия: #{session_id}\n"
                       f"📅 Дата: {self._get_current_datetime()}"
            )
            
            await message.answer("✅ Отчет готов! Спасибо за участие в опросе.")
            
        except Exception as e:
            print(f"Ошибка при генерации отчета: {e}")
            await message.answer("❌ Произошла ошибка при генерации отчета. Обратитесь к администратору.")
    
    def _get_current_datetime(self) -> str:
        """Возвращает текущую дату и время в читаемом формате"""
        from datetime import datetime
        return datetime.now().strftime("%d.%m.%Y %H:%M")
    
    async def setup_bot_commands(self):
        """Настройка меню команд бота"""
        commands = [
            BotCommand(command="start", description="Начать опрос")
        ]
        await self.bot.set_my_commands(commands)

    async def start_polling(self):
        """Запуск бота"""
        await self.setup_bot_commands()
        await self.dp.start_polling(self.bot)

async def main():
    bot = TelegramBot()
    await bot.start_polling()

if __name__ == "__main__":
    asyncio.run(main()) 