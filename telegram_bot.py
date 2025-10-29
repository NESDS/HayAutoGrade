import asyncio
from typing import List, Dict
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from aiogram import F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, BotCommand
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from database import Database
from config import TELEGRAM_BOT_TOKEN
from processing_agents import VerificationAgent, AnswerCompilerAgent, ClassificationAgent
from html_report_generator import HTMLReportGenerator
from llm_services import LLMFactory

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
        
        # Регистрируем обработчики callback-ов для адаптивных вопросов
        self.dp.callback_query.register(self.handle_adaptive_callback, F.data.startswith("q11_"))
        self.dp.callback_query.register(self.handle_adaptive_callback, F.data.startswith("q12_"))
        self.dp.callback_query.register(self.handle_restart_callback, F.data == "restart_from_q8")
        
        # Регистрируем обработчик функционала (вопрос 18)
        self.dp.callback_query.register(self.handle_functionality_callback, F.data.startswith("func_"))
        
        # Регистрируем обработчик выбора LLM
        self.dp.callback_query.register(self.handle_llm_selection, F.data.startswith("llm_"))
        
        # Регистрируем обработчик выбора элемента иерархии штата (вопрос 1)
        self.dp.callback_query.register(self.handle_hierarchy_selection, F.data.startswith("hier_"))
    
    async def start_command(self, message: Message):
        """Начать опрос"""
        user_id = message.from_user.id
        
        # Всегда показываем выбор LLM при старте
        await self.show_llm_selection(message, user_id)
    
    async def show_llm_selection(self, message: Message, user_id: int):
        """Показать выбор LLM пользователю"""
        text = """🤖 Выберите AI помощника для обработки ваших ответов:

🇷🇺 **GigaChat** - российская разработка Сбера
🇺🇸 **GPT-5** - OpenAI GPT-5 Chat Latest"""
        
        # Создаем кнопки выбора
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🇷🇺 GigaChat", callback_data="llm_gigachat")],
            [InlineKeyboardButton(text="🇺🇸 GPT-5", callback_data="llm_openai")]
        ])
        
        await message.answer(text, reply_markup=keyboard)
    
    async def handle_llm_selection(self, callback_query: CallbackQuery):
        """Обработка выбора LLM"""
        user_id = callback_query.from_user.id
        llm_type = callback_query.data.split('_')[1]  # llm_gigachat -> gigachat
        
        # Убираем кнопки выбора
        service = LLMFactory.create_service(llm_type)
        selected_text = f"✅ Выбран AI помощник: {service.emoji} **{service.name}**"
        
        try:
            await callback_query.message.edit_text(text=selected_text, reply_markup=None)
        except Exception as e:
            print(f"⚠️ Не удалось отредактировать сообщение: {e}")
        
        await callback_query.answer(f"Выбран {service.name}!")
        
        # Начинаем опрос с выбранным LLM
        await self.start_survey_with_llm(callback_query.message, user_id, llm_type)
    
    async def start_survey_with_llm(self, message: Message, user_id: int, llm_type: str):
        """Начать опрос с выбранным LLM"""
        session_id = self.db.get_next_session_id(user_id)
        
        # Получаем список вопросов с правильной фильтрацией
        remaining_questions = self.db.get_remaining_questions(user_id, session_id)
        
        # Создаем новое состояние пользователя
        state = {
            'session_id': session_id,
            'remaining_questions': remaining_questions,
            'conversation': [],
            'llm_type': llm_type  # Сохраняем выбранный LLM в состоянии
        }
        
        # Сохраняем активную сессию и состояние в памяти
        self.active_sessions[user_id] = {
            'session_id': session_id,
            'state': state
        }
        
        # Показываем какой LLM используется
        service = LLMFactory.create_service(llm_type)
        await message.answer(f"🚀 Начинаю опрос! (Сессия #{session_id})\n💡 Используется: {service.emoji} {service.name}")
        
        # Вводное пояснение для пользователя
        intro_text = """
📋 <b>Важная информация перед началом:</b>

Этот опрос поможет оценить уровень позиции в вашей команде по международной методике <b>HAY Group</b>.

<b>Как отвечать:</b>
• Исходите из <i>реальных требований и сложности роли</i>, а не из качеств конкретного сотрудника
• В примерах приведены ориентиры для условной должности — «Менеджер по продажам»
• Используйте примеры как <i>образец стиля ответа</i>, а не как точный шаблон
• Ваша задача — описать именно <i>ту роль, которую вы оцениваете</i>

Удачи! 🍀
"""
        await message.answer(intro_text, parse_mode="HTML")
        
        await self.send_next_question(message, user_id, session_id)
    
    def get_agents_for_user(self, user_id: int):
        """Получить агенты с правильным LLM для пользователя"""
        # Получаем тип LLM из текущей сессии
        if user_id in self.active_sessions:
            llm_type = self.active_sessions[user_id]['state'].get('llm_type', 'gigachat')
        else:
            llm_type = 'gigachat'  # fallback если нет активной сессии
        
        # Создаем LLM сервис
        llm_service = LLMFactory.create_service(llm_type)
        
        # Создаем агенты с этим сервисом
        from processing_agents import FunctionalityAgent  # Добавляем импорт
        
        verification_agent = VerificationAgent(llm_service)
        answer_agent = AnswerCompilerAgent(llm_service)
        classification_agent = ClassificationAgent(llm_service)
        functionality_agent = FunctionalityAgent(llm_service)
        
        return {
            'verification': verification_agent,
            'answer': answer_agent,
            'classification': classification_agent,
            'functionality': functionality_agent
        }
    
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
        
        # Проверяем, ожидаются ли дополнения к функционалу (вопрос 18)
        if state.get('awaiting_functionality_addition', False):
            await self.handle_functionality_addition(message, user_id, session_id, user_answer)
            return
        
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
        
        # Получаем агенты с правильным LLM
        agents = self.get_agents_for_user(user_id)
        verification_agent = agents['verification']
        answer_agent = agents['answer'] 
        classification_agent = agents['classification']
        
        if question_data['answer_options']:
            # Получаем портрет для контекста
            portrait = self.db.get_session_portrait(user_id, session_id)
            
            # Показываем typing indicator (если есть классификатор)
            if question_data.get('classifier'):
                await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
            
            final_answer = classification_agent.classify_answer(question_data, user_answer, portrait)
            
            # Сохраняем ответ в БД и проверяем конфликты (только для вопросов с классификатором)
            has_classifier = bool(question_data.get('classifier'))
            response_id, conflicts = self.db.save_response(user_id, session_id, current_question, user_answer, final_answer, None, check_conflicts=has_classifier)
            
            # Генерируем/обновляем портрет пользователя
            self.db.generate_user_portrait(user_id, session_id)
            
            # Обрабатываем конфликты если они найдены
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
            
            # Если есть классификатор, показываем уровень пользователю
            if question_data.get('classifier'):
                try:
                    level_number = int(final_answer)
                    hay_description = self.db.get_hay_level_description(current_question, level_number)
                    if hay_description:
                        await message.answer(f"📊 Определён уровень {level_number}: {hay_description}")
                except (ValueError, TypeError):
                    pass  # Если final_answer не число, пропускаем
            
            await self.next_question(message, user_id, session_id)
        else:
            # Получаем портрет пользователя для контекста
            portrait = self.db.get_session_portrait(user_id, session_id)
            
            # Показываем typing indicator
            await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
            
            is_accepted, response_text = verification_agent.process_answer(
                question_data, user_answer, state['conversation'], portrait
            )
            
            if is_accepted:
                # Портрет уже получен выше, используем его
                full_answer = answer_agent.create_full_answer(question_data, state['conversation'], portrait)
                final_answer = classification_agent.classify_answer(question_data, full_answer, portrait)
                
                # Сохраняем ответ в БД и проверяем конфликты (только для вопросов с классификатором)
                # В поле answer записываем полный ответ из диалога, а не только последнее сообщение
                has_classifier = bool(question_data.get('classifier'))
                response_id, conflicts = self.db.save_response(user_id, session_id, current_question, full_answer, final_answer, None, check_conflicts=has_classifier)
                
                # Генерируем/обновляем портрет пользователя
                self.db.generate_user_portrait(user_id, session_id)
                
                # Обрабатываем конфликты если они найдены
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
                
                # Формируем ответ с уровнем HAY если есть классификатор
                response_message = f"✅ Принято! {response_text}"
                
                # Если есть классификатор, показываем уровень
                if question_data.get('classifier'):
                    try:
                        level_number = int(final_answer)
                        hay_description = self.db.get_hay_level_description(current_question, level_number)
                        if hay_description:
                            response_message += f"\n\n📊 Определён уровень {level_number}: {hay_description}"
                    except (ValueError, TypeError):
                        pass  # Если final_answer не число, пропускаем
                
                await message.answer(response_message)
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
        
        detector = ConflictDetector(self.db)
        
        # Получаем LLM сервис из состояния сессии
        llm_type = state.get('llm_type', 'gigachat')
        llm = LLMFactory.create_service(llm_type)
        
        # Получаем портрет пользователя для контекста
        portrait = self.db.get_session_portrait(user_id, session_id)
        
        # Сначала показываем пользователю детали конфликта
        conflict_details = "⚠️ **ОБНАРУЖЕНО ПРОТИВОРЕЧИЕ В ОТВЕТАХ**\n\n"
        conflict_details += "Ваши ответы на следующие вопросы противоречат друг другу:\n\n"
        
        # Получаем детали для каждого вопроса в конфликте
        user_responses = self.db.get_user_responses(user_id, session_id, only_active=True)
        response_map = {r['question']: r for r in user_responses}
        
        for i, q_info in enumerate(conflict['questions'], 1):
            question_id = q_info['question_id']
            question_text = q_info['question_text']
            answer_text = q_info.get('answer_text', '')  # Общее описание уровня из конфликтов
            
            # Получаем уровень из response_map
            if question_id in response_map:
                user_response = response_map[question_id]
                level = user_response.get('final_answer', '')
                
                conflict_details += f"**{i}. Вопрос {question_id}:** {question_text}\n"
                
                # Показываем уровень и общее описание
                if level and str(level).isdigit():
                    level_num = int(level)
                    conflict_details += f"   ├─ 🔢 Уровень {level_num}"
                    
                    # Добавляем общее описание из конфликтов
                    if answer_text:
                        conflict_details += f": _{answer_text[:100]}{'...' if len(answer_text) > 100 else ''}_\n"
                    else:
                        conflict_details += "\n"
                    
                    # Добавляем описание по HAY из справочника
                    try:
                        hay_desc = self.db.get_hay_level_description(question_id, level_num)
                        if hay_desc:
                            conflict_details += f"   └─ 📊 HAY: _{hay_desc[:100]}{'...' if len(hay_desc) > 100 else ''}_\n"
                    except (ValueError, TypeError):
                        pass
                else:
                    conflict_details += f"   └─ (уровень не определён)\n"
                
                conflict_details += "\n"
        
        await message.answer(conflict_details)
        
        # Выводим техническую информацию о конфликте БЕЗ LLM
        print("\n" + "="*70)
        print("📊 ТЕХНИЧЕСКАЯ ИНФОРМАЦИЯ О КОНФЛИКТЕ")
        print("="*70)
        print(f"Конфликт ID: {conflict.get('id', 'N/A')}")
        print(f"Вопросы в конфликте: {conflict['question_ids']}")
        print()
        
        # Выводим детали по каждому вопросу
        for q_info in conflict['questions']:
            question_id = q_info['question_id']
            
            # Получаем фактический уровень пользователя
            if question_id in response_map:
                user_level = response_map[question_id].get('final_answer', '')
                print(f"Вопрос {question_id}:")
                print(f"  ├─ Уровень пользователя: {user_level}")
                print(f"  └─ Краткое описание уровня: {q_info['answer_text'][:80]}...")
                print()
        
        print(f"❌ КОНФЛИКТ: Комбинация уровней {[response_map[q_id].get('final_answer', '?') for q_id in conflict['question_ids']]} несовместима.")
        print("="*70 + "\n")
        
        # Показываем typing indicator
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        
        # Генерируем промпт для объяснения конфликта с учетом контекста
        explanation_prompt = detector.generate_conflict_explanation(conflict, portrait)
        
        print("🤖 КОНФЛИКТАТОР - Отправляем запрос в LLM для объяснения конфликта...")
        print("-" * 50)
        print(explanation_prompt)
        print("-" * 50 + "\n")
        
        # Получаем объяснение от LLM (используем task_type='explanation' для более креативного ответа)
        messages = [{"role": "user", "content": explanation_prompt}]
        explanation = llm.generate_response(messages, task_type='explanation')
        
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
        
        # Отправляем объяснение от LLM
        await message.answer(f"🤖 {explanation}")
        await message.answer(f"🔄 Предлагаю ответить на эти вопросы заново...")
        
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
            
            # Проверяем, нужна ли специальная логика для вопросов 1, 3, 11, 12 или 18
            if next_question_id == 1:
                await self.send_hierarchy_question(message, user_id, session_id)
            elif next_question_id == 3:
                await self.auto_fill_question_3(message, user_id, session_id)
            elif next_question_id == 11:
                await self.send_adaptive_question_11(message, user_id, session_id)
            elif next_question_id == 12:
                await self.send_adaptive_question_12(message, user_id, session_id)
            elif next_question_id == 18:
                await self.send_adaptive_question_18(message, user_id, session_id)
            else:
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
        """Генерирует HTML и XLSX отчеты и отправляет пользователю"""
        try:
            await message.answer("🎉 Опрос завершен! Генерирую ваши отчеты...", reply_markup=ReplyKeyboardRemove())
            
            # Генерируем HTML отчет
            report_path = self.report_generator.save_report_to_file(
                user_id=user_id, 
                session_id=session_id,
                output_path=f"reports/report_user_{user_id}_session_{session_id}.html"
            )
            
            # Отправляем HTML файл пользователю
            from aiogram.types import FSInputFile
            document = FSInputFile(report_path)
            
            await message.answer_document(
                document=document,
                caption=f"📊 Ваш персональный HTML отчет\n"
                       f"👤 Пользователь: #{user_id}\n"
                       f"📋 Сессия: #{session_id}\n"
                       f"📅 Дата: {self._get_current_datetime()}"
            )
            
            # Генерируем и отправляем XLSX отчет (калькулятор)
            await self.generate_and_send_xlsx_report(message, user_id, session_id)
            
            await message.answer("✅ Все отчеты готовы! Спасибо за участие в опросе.")
            
        except Exception as e:
            print(f"Ошибка при генерации отчета: {e}")
            import traceback
            traceback.print_exc()
            await message.answer("❌ Произошла ошибка при генерации отчета. Обратитесь к администратору.")
    
    async def generate_and_send_xlsx_report(self, message: Message, user_id: int, session_id: int):
        """Генерирует XLSX отчет (калькулятор) и отправляет пользователю"""
        try:
            await message.answer("📊 Генерирую Excel калькулятор...")
            
            # Импортируем генератор
            from xlsx_report_generator import XLSXReportGenerator
            
            # Генерируем отчет
            xlsx_generator = XLSXReportGenerator()
            report_path = xlsx_generator.generate_report(user_id, session_id)
            
            # Отправляем файл пользователю
            from aiogram.types import FSInputFile
            document = FSInputFile(report_path)
            
            await message.answer_document(
                document=document,
                caption=f"📊 Ваш персональный калькулятор грейда\n"
                       f"👤 Пользователь: #{user_id}\n"
                       f"📋 Сессия: #{session_id}\n"
                       f"📅 Дата: {self._get_current_datetime()}\n\n"
                       f"✨ Файл содержит все ваши ответы с расчетом грейда"
            )
            
            print(f"✅ XLSX отчет отправлен пользователю {user_id}")
            
        except Exception as e:
            print(f"❌ Ошибка при генерации XLSX отчета: {e}")
            import traceback
            traceback.print_exc()
            await message.answer("⚠️ Не удалось сгенерировать Excel калькулятор. HTML отчет доступен выше.")
    
    async def send_adaptive_question_11(self, message: Message, user_id: int, session_id: int):
        """Отправка вопроса 11 с адаптивными вариантами на основе P1"""
        try:
            # Вычисляем промежуточный P1
            from grade_calculator import GradeCalculator
            calculator = GradeCalculator()
            p1_value = calculator.calculate_intermediate_p1(user_id, session_id)
            
            if p1_value is None:
                print("⚠️ Не удалось вычислить P1, показываем варианты для Q8,Q9,Q10")
                await self.show_missing_p1_options(message, user_id, session_id)
                return
            
            # Получаем варианты для Q11
            variants = self.db.get_question_variants(11, p1_value)
            question_data = self.db.get_question(11)
            
            if not variants:
                print("⚠️ Нет вариантов для Q11, используем стандартную логику")
                await self.send_question(message, 11)
                return
            
            # Убираем Q11 из remaining_questions
            state = self.active_sessions[user_id]['state']
            if 11 in state['remaining_questions']:
                state['remaining_questions'].remove(11)
            self.active_sessions[user_id]['state'] = state
            
            # Убираем старую reply клавиатуру (если была)
            await message.answer("⏳", reply_markup=ReplyKeyboardRemove())
            
            # Формируем сообщение и клавиатуру
            if len(variants) == 1:
                text = self._format_single_variant_message(question_data, p1_value, variants[0])
                keyboard = self._create_single_variant_keyboard(variants[0], 11)
            else:
                text = self._format_multiple_variants_message(question_data, p1_value, variants)
                keyboard = self._create_multiple_variants_keyboard(variants, 11)
            
            await message.answer(text, reply_markup=keyboard)
            
        except Exception as e:
            print(f"❌ Ошибка в адаптивном Q11: {e}")
            # Fallback к стандартной логике
            await self.send_question(message, 11)
    
    def _format_single_variant_message(self, question_data: Dict, p1_value: int, variant: Dict) -> str:
        """Формат сообщения для единственного варианта"""
        return f"""Вопрос {question_data['id']}: {question_data['question']}

🔍 Исходя из ваших предыдущих ответов (P1 = {p1_value}), возможен только следующий вариант:

📋 {variant['variant_text']}

Согласны ли вы с этим вариантом?"""

    def _format_multiple_variants_message(self, question_data: Dict, p1_value: int, variants: List[Dict]) -> str:
        """Формат сообщения для множественных вариантов"""
        text = f"""Вопрос {question_data['id']}: {question_data['question']}

🔍 Исходя из ваших предыдущих ответов (P1 = {p1_value}), возможны следующие варианты:

"""
        # Добавляем все варианты в текст сообщения
        for variant in variants:
            text += f"📋 {variant['variant_text']}\n\n"
        
        text += "Выберите наиболее подходящий вариант:"
        return text

    def _create_single_variant_keyboard(self, variant: Dict, question_num: int) -> InlineKeyboardMarkup:
        """Клавиатура для единственного варианта"""
        buttons = [
            [InlineKeyboardButton(
                text=f"✅ Вариант {variant['answer_value']}", 
                callback_data=f"q{question_num}_accept_{variant['answer_value']}"
            )],
            [InlineKeyboardButton(
                text="🔄 Переответить с 8-го вопроса", 
                callback_data="restart_from_q8"
            )]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    def _create_multiple_variants_keyboard(self, variants: List[Dict], question_num: int) -> InlineKeyboardMarkup:
        """Клавиатура для множественных вариантов"""
        buttons = []
        
        # Кнопки для каждого варианта - только номера
        for variant in variants:
            buttons.append([InlineKeyboardButton(
                text=f"{variant['answer_value']}",  # Только номер
                callback_data=f"q{question_num}_select_{variant['answer_value']}"
            )])
        
        # Кнопка пересдачи
        buttons.append([InlineKeyboardButton(
            text="🔄 Переответить с 8-го вопроса",
            callback_data="restart_from_q8"
        )])
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    async def handle_adaptive_callback(self, callback_query: CallbackQuery):
        """Обработка выбора варианта ответа для адаптивных вопросов"""
        data = callback_query.data
        user_id = callback_query.from_user.id
        
        if user_id not in self.active_sessions:
            await callback_query.answer("❌ Сессия не найдена. Напишите /start")
            return
        
        session_id = self.active_sessions[user_id]['session_id']
        
        try:
            # Парсим callback_data: "q11_accept_2" или "q11_select_3"
            parts = data.split('_')
            question_num = int(parts[0][1:])  # q11 -> 11
            action = parts[1]  # accept или select
            answer_value = int(parts[2])  # номер ответа
            
            # Получаем полный текст варианта
            variant_text = self._get_variant_text_by_value(question_num, answer_value, user_id, session_id)
            
            # Сохраняем ответ БЕЗ вызова агентов обработки
            response_id, conflicts = self.db.save_response(
                user=user_id,
                session_id=session_id,
                question=question_num,
                answer=variant_text,
                final_answer=str(answer_value),  # Сразу финальный ответ
                user_state=None
            )
            
            # Генерируем/обновляем портрет пользователя
            self.db.generate_user_portrait(user_id, session_id)
            
            # Проверяем конфликты (стандартная логика)
            if conflicts:
                state = self.active_sessions[user_id]['state']
                await self.handle_conflict(callback_query.message, user_id, session_id, conflicts[0], state)
                return
            
            await callback_query.answer("✅ Ответ принят!")
            
            # Убираем кнопки из исходного сообщения
            try:
                await callback_query.message.edit_reply_markup(reply_markup=None)
            except Exception as e:
                print(f"⚠️ Не удалось убрать кнопки: {e}")
            
            # Отправляем подтверждение выбора в отдельном сообщении
            selected_text = f"✅ **Выбран вариант:**\n\n📋 {variant_text}"
            await callback_query.message.answer(selected_text)
            
            # Переходим к следующему вопросу
            if question_num == 11:
                # Переходим к адаптивному Q12
                await self.send_adaptive_question_12(callback_query.message, user_id, session_id)
            else:
                # Q12 завершён, переходим к обычной логике
                await self.next_question(callback_query.message, user_id, session_id)
                
        except Exception as e:
            print(f"❌ Ошибка обработки callback: {e}")
            await callback_query.answer("❌ Произошла ошибка")

    async def handle_restart_callback(self, callback_query: CallbackQuery):
        """Обработка пересдачи с 8-го вопроса"""
        user_id = callback_query.from_user.id
        
        if user_id not in self.active_sessions:
            await callback_query.answer("❌ Сессия не найдена")
            return
        
        session_id = self.active_sessions[user_id]['session_id']
        
        try:
            # Деактивируем ответы на вопросы 8-12
            self.db.reset_questions_from_8(user_id, session_id)
            
            # Обновляем состояние пользователя
            state = self.active_sessions[user_id]['state']
            state['remaining_questions'] = self.db.get_remaining_questions(user_id, session_id)
            state['conversation'] = []
            
            # Сохраняем состояние
            self.active_sessions[user_id]['state'] = state
            self.db.save_user_state(user_id, session_id, state)
            
            await callback_query.answer("🔄 Начинаем заново с 8-го вопроса")
            
            # Убираем кнопки из предыдущего сообщения
            try:
                await callback_query.message.edit_text(
                    text="🔄 Пересдаём вопросы с 8-го...",
                    reply_markup=None
                )
            except Exception as e:
                print(f"⚠️ Не удалось отредактировать сообщение: {e}")
            
            await callback_query.message.answer("Хорошо, давайте пересдадим вопросы с 8-го.", 
                                               reply_markup=ReplyKeyboardRemove())
            
            # Переходим к вопросу 8
            await self.send_next_question(callback_query.message, user_id, session_id)
            
        except Exception as e:
            print(f"❌ Ошибка пересдачи: {e}")
            await callback_query.answer("❌ Произошла ошибка")

    async def handle_functionality_callback(self, callback_query: CallbackQuery):
        """Обработка кнопки принятия функционала (вопрос 18)"""
        user_id = callback_query.from_user.id
        
        if user_id not in self.active_sessions:
            await callback_query.answer("❌ Сессия не найдена")
            return
        
        session_id = self.active_sessions[user_id]['session_id']
        
        try:
            if callback_query.data == "func_accept_18":
                # Получаем текст сообщения с функционалом
                message_text = callback_query.message.text
                
                # Извлекаем сгенерированный функционал из сообщения
                # Ищем функционал между "сформирован следующий функционал:" и "При необходимости"
                start_marker = "сформирован следующий функционал:\n\n"
                end_marker = "\n\nПри необходимости"
                
                start_pos = message_text.find(start_marker)
                end_pos = message_text.find(end_marker)
                
                if start_pos != -1 and end_pos != -1:
                    functionality = message_text[start_pos + len(start_marker):end_pos].strip()
                else:
                    functionality = "Функционал принят как есть"
                
                # Сохраняем как ответ на вопрос 18 (без проверки конфликтов - у Q18 нет классификатора)
                self.db.save_response(user_id, session_id, 18, functionality, functionality, None, check_conflicts=False)
                
                # Обновляем портрет пользователя
                self.db.generate_user_portrait(user_id, session_id)
                
                # Убираем состояние ожидания дополнений
                state = self.active_sessions[user_id]['state']
                state['awaiting_functionality_addition'] = False
                state.pop('generated_functionality', None)
                self.active_sessions[user_id]['state'] = state
                
                # Убираем кнопки и показываем что функционал принят
                try:
                    await callback_query.message.edit_text(
                        text=f"✅ **Функционал принят:**\n\n{functionality}",
                        reply_markup=None
                    )
                except Exception as e:
                    print(f"⚠️ Не удалось отредактировать сообщение: {e}")
                
                await callback_query.answer("✅ Функционал принят!")
                
                # Переходим к следующему вопросу
                await self.send_next_question(callback_query.message, user_id, session_id)
                
        except Exception as e:
            print(f"❌ Ошибка обработки функционала: {e}")
            await callback_query.answer("❌ Произошла ошибка")

    async def handle_functionality_addition(self, message: Message, user_id: int, session_id: int, addition_text: str):
        """Обработка текстовых дополнений к функционалу"""
        try:
            state = self.active_sessions[user_id]['state']
            generated_functionality = state.get('generated_functionality', '')
            
            # Объединяем сгенерированный функционал с дополнениями пользователя
            full_functionality = f"{generated_functionality}\n\n**Дополнения:**\n{addition_text}"
            
            # Сохраняем объединенный функционал как ответ на вопрос 18 (без проверки конфликтов)
            self.db.save_response(user_id, session_id, 18, full_functionality, full_functionality, None, check_conflicts=False)
            
            # Обновляем портрет пользователя
            self.db.generate_user_portrait(user_id, session_id)
            
            # Убираем состояние ожидания дополнений
            state['awaiting_functionality_addition'] = False
            state.pop('generated_functionality', None)
            self.active_sessions[user_id]['state'] = state
            
            # Подтверждаем получение дополнений
            await message.answer(f"✅ **Функционал сохранен с вашими дополнениями:**\n\n{full_functionality}")
            
            # Переходим к следующему вопросу
            await self.send_next_question(message, user_id, session_id)
            
        except Exception as e:
            print(f"❌ Ошибка обработки дополнений функционала: {e}")
            await message.answer("❌ Произошла ошибка при сохранении дополнений")

    def _get_variant_text_by_value(self, question_num: int, answer_value: int, user_id: int, session_id: int) -> str:
        """Получить полный текст варианта по номеру ответа"""
        try:
            from grade_calculator import GradeCalculator
            calculator = GradeCalculator()
            p1_value = calculator.calculate_intermediate_p1(user_id, session_id)
            
            if p1_value is not None:
                variants = self.db.get_question_variants(question_num, p1_value)
                
                for variant in variants:
                    if variant['answer_value'] == answer_value:
                        return variant['variant_text']
            
            return f"Вариант {answer_value}"  # Fallback
            
        except Exception as e:
            print(f"❌ Ошибка получения текста варианта: {e}")
            return f"Вариант {answer_value}"

    async def send_adaptive_question_12(self, message: Message, user_id: int, session_id: int):
        """Отправка вопроса 12 с адаптивными вариантами с учетом ответа на Q11"""
        try:
            # Вычисляем промежуточный P1
            from grade_calculator import GradeCalculator
            calculator = GradeCalculator()
            p1_value = calculator.calculate_intermediate_p1(user_id, session_id)
            
            if p1_value is None:
                print("⚠️ Не удалось вычислить P1 для Q12, показываем варианты для Q8,Q9,Q10")
                await self.show_missing_p1_options(message, user_id, session_id)
                return
            
            # Получаем ответ на Q11 из БД
            user_responses = self.db.get_user_responses(user_id, session_id)
            q11_answer = None
            
            for response in user_responses:
                if response['question'] == 11:  # question номер 11
                    q11_final_answer = response['final_answer']  # final_answer
                    try:
                        q11_answer = int(q11_final_answer)
                        break
                    except (ValueError, TypeError):
                        print(f"⚠️ Не удалось преобразовать ответ Q11 в число: {q11_final_answer}")
                        continue
            
            if q11_answer is None:
                print("⚠️ Не найден ответ на Q11, используем стандартную логику")
                await self.send_question(message, 12)
                return
            
            print(f"🔍 Для Q12: P1={p1_value}, Q11_answer={q11_answer}")
            
            # Получаем варианты для Q12 с учетом ответа на Q11
            variants = self.db.get_question_variants(12, p1_value, q11_answer)
            question_data = self.db.get_question(12)
            
            if not variants:
                print("⚠️ Нет вариантов для Q12, используем стандартную логику")
                await self.send_question(message, 12)
                return
            
            # Убираем Q12 из remaining_questions
            state = self.active_sessions[user_id]['state']
            if 12 in state['remaining_questions']:
                state['remaining_questions'].remove(12)
            self.active_sessions[user_id]['state'] = state
            
            # Убираем старую reply клавиатуру (если была)
            await message.answer("⏳", reply_markup=ReplyKeyboardRemove())
            
            # Формируем сообщение и клавиатуру
            if len(variants) == 1:
                text = self._format_single_variant_message(question_data, p1_value, variants[0])
                keyboard = self._create_single_variant_keyboard(variants[0], 12)
            else:
                text = self._format_multiple_variants_message(question_data, p1_value, variants)
                keyboard = self._create_multiple_variants_keyboard(variants, 12)
            
            await message.answer(text, reply_markup=keyboard)
            
        except Exception as e:
            print(f"❌ Ошибка в адаптивном Q12: {e}")
            # Fallback к стандартной логике
            await self.send_question(message, 12)
    
    async def send_adaptive_question_18(self, message: Message, user_id: int, session_id: int):
        """Отправка вопроса 18 с автогенерированным функционалом"""
        try:
            # Получаем портрет пользователя
            portrait = self.db.get_session_portrait(user_id, session_id)
            
            if not portrait:
                print("⚠️ Портрет пользователя пуст, используем стандартную логику")
                await self.send_question(message, 18)
                return
            
            # Создаем FunctionalityAgent
            agents = self.get_agents_for_user(user_id)
            functionality_agent = agents['functionality']
            
            # Показываем typing indicator
            await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
            
            # Генерируем функционал
            generated_functionality = functionality_agent.generate_functionality(portrait)
            
            # Убираем Q18 из remaining_questions и сохраняем сгенерированный функционал
            state = self.active_sessions[user_id]['state']
            if 18 in state['remaining_questions']:
                state['remaining_questions'].remove(18)
            
            # Сохраняем состояние для обработки дополнений к функционалу
            state['awaiting_functionality_addition'] = True
            state['generated_functionality'] = generated_functionality
            self.active_sessions[user_id]['state'] = state
            
            # Получаем данные вопроса
            question_data = self.db.get_question(18)
            
            # Сначала убираем старую клавиатуру от предыдущего вопроса
            await message.answer("⏳", reply_markup=ReplyKeyboardRemove())
            
            # Формируем сообщение
            text = f"📋 **{question_data['question']}**\n\n"
            text += f"На основании ваших предыдущих ответов сформирован следующий функционал:\n\n"
            text += f"{generated_functionality}\n\n"
            text += f"При необходимости можете добавить еще функции, напишите их. "
            text += f"Или нажмите \"✅ Принять как есть\", если функционал подходит."
            
            # Создаем inline клавиатуру
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Принять как есть", callback_data=f"func_accept_18")]
            ])
            
            # Отправляем сообщение с inline кнопкой
            await message.answer(text, reply_markup=keyboard)
            
        except Exception as e:
            print(f"❌ Ошибка в адаптивном Q18: {e}")
            # Fallback к стандартной логике
            await self.send_question(message, 18)
    
    async def show_missing_p1_options(self, message: Message, user_id: int, session_id: int):
        """Показать пользователю его ответы на Q8,Q9,Q10 и предложить пересдать"""
        try:
            # Получаем ответы пользователя на Q8, Q9, Q10
            responses = self.db.get_user_responses(user_id, session_id)
            q8_q9_q10_answers = {}
            
            for r in responses:
                if r['question'] in [8, 9, 10]:
                    q8_q9_q10_answers[r['question']] = {
                        'answer': r['answer'],
                        'final_answer': r['final_answer']
                    }
            
            # Формируем сообщение с текущими ответами
            text = """❌ Не удалось определить варианты для следующих вопросов на основе ваших предыдущих ответов.

📋 Ваши текущие ответы:"""
            
            answers_for_p1 = []
            for q_num in [8, 9, 10]:
                if q_num in q8_q9_q10_answers:
                    answer_info = q8_q9_q10_answers[q_num]
                    final = answer_info['final_answer'] or answer_info['answer']
                    text += f"\n• Вопрос {q_num}: {final}"
                    answers_for_p1.append(final)
                else:
                    text += f"\n• Вопрос {q_num}: (нет ответа)"
                    answers_for_p1.append("не указан")
            
            # Добавляем техническую информацию о P1
            if len(answers_for_p1) == 3:
                text += f"\n\n⚠️ Комбинация Q8={answers_for_p1[0]}, Q9={answers_for_p1[1]}, Q10={answers_for_p1[2]} не найдена в справочнике P1."
            
            text += "\n\n🔄 Предлагаем пересдать вопросы 8-10 для корректного определения вариантов."
            
            # Создаем кнопку для пересдачи
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="🔄 Переответить с 8-го вопроса",
                    callback_data="restart_from_q8"
                )]
            ])
            
            await message.answer(text, reply_markup=keyboard)
            
        except Exception as e:
            print(f"❌ Ошибка в show_missing_p1_options: {e}")
            # Fallback - показываем простое сообщение
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="🔄 Переответить с 8-го вопроса",
                    callback_data="restart_from_q8"
                )]
            ])
            
            await message.answer(
                "❌ Не удалось определить варианты ответов.\n\n🔄 Предлагаем пересдать вопросы с 8-го.",
                reply_markup=keyboard
            )
    
    def _get_current_datetime(self) -> str:
        """Возвращает текущую дату и время в читаемом формате"""
        from datetime import datetime
        return datetime.now().strftime("%d.%m.%Y %H:%M")
    
    async def auto_fill_question_3(self, message: Message, user_id: int, session_id: int):
        """Автоматическое заполнение вопроса 3 на основе пути из вопроса 1"""
        try:
            # Получаем ответ на вопрос 1
            user_responses = self.db.get_user_responses(user_id, session_id, only_active=True)
            q1_answer = None
            
            for response in user_responses:
                if response['question'] == 1:
                    q1_answer = response['answer']
                    break
            
            if not q1_answer:
                # Если нет ответа на вопрос 1, показываем стандартный вопрос 3
                print("⚠️ Нет ответа на вопрос 1, используем стандартную логику для Q3")
                await self.send_question(message, 3)
                return
            
            # Получаем полный путь из иерархии по названию роли
            # Ищем элемент с такой ролью
            import sqlite3
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT full_path FROM shtat_hierarchy
                    WHERE role = ?
                    LIMIT 1
                """, (q1_answer,))
                result = cursor.fetchone()
            
            if not result or not result[0]:
                # Если не нашли путь, используем сам ответ
                hierarchy_path = q1_answer
            else:
                hierarchy_path = result[0]
            
            # Получаем данные вопроса 3 для отображения
            question_data = self.db.get_question(3)
            
            # Сохраняем ответ БЕЗ проверки конфликтов (у вопроса 3 нет классификатора)
            self.db.save_response(
                user=user_id,
                session_id=session_id,
                question=3,
                answer=hierarchy_path,
                final_answer=hierarchy_path,
                user_state=None,
                check_conflicts=False
            )
            
            # Генерируем/обновляем портрет пользователя
            self.db.generate_user_portrait(user_id, session_id)
            
            # Убираем вопрос 3 из remaining_questions
            state = self.active_sessions[user_id]['state']
            if 3 in state['remaining_questions']:
                state['remaining_questions'].remove(3)
            
            # Обновляем состояние
            self.active_sessions[user_id]['state'] = state
            self.db.save_user_state(user_id, session_id, state)
            
            # Показываем пользователю, что вопрос автоматически заполнен
            info_text = f"📋 **Вопрос 3:** {question_data['question']}\n\n"
            info_text += f"✅ **Автоматически заполнено на основе выбранной роли:**\n\n"
            info_text += f"📍 {hierarchy_path}"
            
            await message.answer(info_text)
            
            # Переходим к следующему вопросу
            await self.next_question(message, user_id, session_id)
            
        except Exception as e:
            print(f"❌ Ошибка в auto_fill_question_3: {e}")
            import traceback
            traceback.print_exc()
            # Fallback к стандартной логике
            await self.send_question(message, 3)
    
    async def send_hierarchy_question(self, message: Message, user_id: int, session_id: int, parent_id: int = 0, current_path: str = ""):
        """Отправка вопроса 1 с выбором из иерархии штата"""
        try:
            # Получаем дочерние элементы
            children = self.db.get_hierarchy_children(parent_id)
            
            if not children:
                # Если нет детей, что-то пошло не так
                await message.answer("❌ Не найдены элементы иерархии. Используем стандартный вопрос.")
                await self.send_question(message, 1)
                return
            
            # Получаем данные вопроса
            question_data = self.db.get_question(1)
            
            # Убираем старую reply клавиатуру
            await message.answer("⏳", reply_markup=ReplyKeyboardRemove())
            
            # Формируем сообщение
            if parent_id == 0:
                # Корневой уровень - компании
                text = f"📋 **{question_data['question']}**\n\n"
                text += "Выберите компанию:"
            else:
                # Вложенный уровень
                text = f"📋 **{question_data['question']}**\n\n"
                text += f"📍 Текущий путь: {current_path}\n\n"
                text += "Выберите элемент:"
            
            # Создаем inline клавиатуру
            keyboard_buttons = []
            for child in children:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=child['role'],
                        callback_data=f"hier_{child['id']}"
                    )
                ])
            
            # Добавляем кнопку "Назад" если не на корневом уровне
            if parent_id != 0:
                parent_item = self.db.get_hierarchy_item(parent_id)
                if parent_item and parent_item['id_rod'] is not None:
                    keyboard_buttons.append([
                        InlineKeyboardButton(
                            text="⬅️ Назад",
                            callback_data=f"hier_back_{parent_item['id_rod']}"
                        )
                    ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
            
            # Сохраняем текущий путь в состоянии
            state = self.active_sessions[user_id]['state']
            state['hierarchy_current_path'] = current_path
            state['hierarchy_parent_id'] = parent_id
            self.active_sessions[user_id]['state'] = state
            
            # Отправляем сообщение
            await message.answer(text, reply_markup=keyboard)
            
        except Exception as e:
            print(f"❌ Ошибка в send_hierarchy_question: {e}")
            # Fallback к стандартной логике
            await self.send_question(message, 1)
    
    async def handle_hierarchy_selection(self, callback_query: CallbackQuery):
        """Обработка выбора элемента из иерархии штата"""
        user_id = callback_query.from_user.id
        
        if user_id not in self.active_sessions:
            await callback_query.answer("❌ Сессия не найдена. Напишите /start")
            return
        
        session_id = self.active_sessions[user_id]['session_id']
        state = self.active_sessions[user_id]['state']
        
        try:
            # Парсим callback_data: "hier_123" или "hier_back_0"
            data = callback_query.data
            
            if data.startswith("hier_back_"):
                # Возврат на предыдущий уровень
                parent_id = int(data.split('_')[2])
                
                # Определяем путь для родителя
                if parent_id == 0:
                    new_path = ""
                else:
                    parent_item = self.db.get_hierarchy_item(parent_id)
                    if parent_item:
                        # Берем путь родителя из его full_path
                        new_path = parent_item['full_path']
                    else:
                        new_path = ""
                
                # Убираем кнопки из текущего сообщения
                try:
                    await callback_query.message.delete()
                except:
                    pass
                
                await callback_query.answer("⬅️ Возврат назад")
                
                # Показываем предыдущий уровень
                await self.send_hierarchy_question(
                    callback_query.message, 
                    user_id, 
                    session_id, 
                    parent_id=parent_id,
                    current_path=new_path
                )
                
            else:
                # Выбор элемента: "hier_123"
                selected_id = int(data.split('_')[1])
                
                # Получаем информацию об элементе
                selected_item = self.db.get_hierarchy_item(selected_id)
                
                if not selected_item:
                    await callback_query.answer("❌ Элемент не найден")
                    return
                
                # Проверяем, является ли элемент конечным (листом)
                is_leaf = self.db.is_hierarchy_leaf(selected_id)
                
                if is_leaf:
                    # Это конечная роль - сохраняем как ответ на вопрос 1
                    role_name = selected_item['role']
                    full_path = selected_item['full_path']
                    
                    # Сохраняем ответ БЕЗ проверки конфликтов (у вопроса 1 нет классификатора)
                    self.db.save_response(
                        user=user_id,
                        session_id=session_id,
                        question=1,
                        answer=role_name,
                        final_answer=role_name,
                        user_state=None,
                        check_conflicts=False
                    )
                    
                    # Генерируем/обновляем портрет пользователя
                    self.db.generate_user_portrait(user_id, session_id)
                    
                    # Убираем вопрос 1 из remaining_questions
                    if 1 in state['remaining_questions']:
                        state['remaining_questions'].remove(1)
                    
                    # Очищаем данные иерархии из состояния
                    state.pop('hierarchy_current_path', None)
                    state.pop('hierarchy_parent_id', None)
                    
                    # Обновляем состояние
                    self.active_sessions[user_id]['state'] = state
                    self.db.save_user_state(user_id, session_id, state)
                    
                    # Убираем кнопки из сообщения
                    try:
                        await callback_query.message.delete()
                    except:
                        pass
                    
                    await callback_query.answer("✅ Роль выбрана!")
                    
                    # Показываем подтверждение
                    confirmation_text = f"✅ **Выбрана роль:**\n\n"
                    confirmation_text += f"📋 {role_name}\n\n"
                    confirmation_text += f"📍 Путь: {full_path}"
                    await callback_query.message.answer(confirmation_text)
                    
                    # Переходим к следующему вопросу
                    await self.next_question(callback_query.message, user_id, session_id)
                    
                else:
                    # Это не конечный элемент - показываем его детей
                    new_path = selected_item['full_path']
                    
                    # Убираем кнопки из текущего сообщения
                    try:
                        await callback_query.message.delete()
                    except:
                        pass
                    
                    await callback_query.answer(f"➡️ {selected_item['role']}")
                    
                    # Показываем детей выбранного элемента
                    await self.send_hierarchy_question(
                        callback_query.message, 
                        user_id, 
                        session_id, 
                        parent_id=selected_id,
                        current_path=new_path
                    )
                    
        except Exception as e:
            print(f"❌ Ошибка в handle_hierarchy_selection: {e}")
            import traceback
            traceback.print_exc()
            await callback_query.answer("❌ Произошла ошибка")
    
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