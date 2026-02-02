"""
СберЧат-адаптер для HayAutoGrade.

Полная копия логики telegram_bot.py, адаптированная под Dialog Bot SDK.
Включает: адаптивные вопросы Q11/Q12/Q18, конфликты, отчёты, интерактивные кнопки.

Требует установки sber-sberchat-bot-sdk из корпоративного репозитория.
"""

import logging
import os
import importlib
import importlib.util
from typing import Dict, List, Optional
from datetime import datetime

# Проверка доступности библиотеки СберЧат
SBERCHAT_AVAILABLE = False

try:
    # Шим: устраняем конфликт имён между пакетом dialog_bot_sdk.utils (папка)
    # и модулем dialog_bot_sdk/utils.py (файл)
    try:
        pkg = importlib.import_module("dialog_bot_sdk.utils")
        import dialog_bot_sdk as _dbs
        base_dir = os.path.dirname(_dbs.__file__)
        utils_py_path = os.path.join(base_dir, "utils.py")
        if os.path.isfile(utils_py_path):
            spec = importlib.util.spec_from_file_location("dialog_bot_sdk._utils_file", utils_py_path)
            if spec and spec.loader:
                _utils_file = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(_utils_file)
                for name in dir(_utils_file):
                    if name.startswith("_"):
                        continue
                    try:
                        value = getattr(_utils_file, name)
                    except Exception:
                        continue
                    if not hasattr(pkg, name):
                        setattr(pkg, name, value)
    except Exception:
        pass

    from dialog_bot_sdk.bot import DialogBot
    from dialog_bot_sdk.entities.messaging import (
        UpdateMessage, CommandHandler, MessageHandler, MessageContentType
    )
    from dialog_bot_sdk.entities.media import (
        InteractiveMediaGroup, InteractiveMedia, InteractiveMediaButton,
        InteractiveMediaSelect, InteractiveMediaSelectOption, InteractiveMediaStyle
    )
    SBERCHAT_AVAILABLE = True
except ImportError:
    # Заглушки для типизации когда библиотека недоступна
    DialogBot = None
    UpdateMessage = None
    CommandHandler = None
    MessageHandler = None
    MessageContentType = None
    InteractiveMediaGroup = None
    InteractiveMedia = None
    InteractiveMediaButton = None
    InteractiveMediaSelect = None
    InteractiveMediaSelectOption = None
    InteractiveMediaStyle = None

from database import Database
from config import SBERCHAT_TOKEN, SBERCHAT_ENDPOINT, SBERCHAT_IS_SECURE, SBERCHAT_ROOT_CERT
from processing_agents import VerificationAgent, AnswerCompilerAgent, ClassificationAgent, FunctionalityAgent
from html_report_generator import HTMLReportGenerator
from llm_services import LLMFactory

# Глобальный объект бота (инициализируется в main)
bot = None

# Словарь для хранения активных сессий пользователей
active_sessions: Dict[int, Dict] = {}

# База данных и генератор отчётов
db = Database()
report_generator = HTMLReportGenerator()


def get_current_datetime() -> str:
    """Возвращает текущую дату и время в читаемом формате"""
    return datetime.now().strftime("%d.%m.%Y %H:%M")


def format_question_text(question_text: str) -> str:
    """Форматирует вопрос: вторую часть (пример) делает курсивом (в СберЧате через *)"""
    if '\n\n' in question_text:
        parts = question_text.split('\n\n', 1)
        if len(parts) == 2:
            return f"{parts[0]}\n\n_{parts[1]}_"
    return question_text


def get_agents_for_user(user_id: int) -> Dict:
    """Получить агенты с правильным LLM для пользователя"""
    if user_id in active_sessions:
        llm_type = active_sessions[user_id]['state'].get('llm_type', 'gigachat')
    else:
        llm_type = 'gigachat'
    
    llm_service = LLMFactory.create_service(llm_type)
    
    return {
        'verification': VerificationAgent(llm_service),
        'answer': AnswerCompilerAgent(llm_service),
        'classification': ClassificationAgent(llm_service),
        'functionality': FunctionalityAgent(llm_service)
    }


def split_long_message(text: str, max_length: int = 4000) -> List[str]:
    """Разбивает длинное сообщение на части"""
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    for paragraph in text.split('\n'):
        if len(current_chunk) + len(paragraph) + 1 <= max_length:
            current_chunk += paragraph + '\n'
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            if len(paragraph) > max_length:
                words = paragraph.split(' ')
                temp_chunk = ""
                for word in words:
                    if len(temp_chunk) + len(word) + 1 <= max_length:
                        temp_chunk += word + ' '
                    else:
                        if temp_chunk:
                            chunks.append(temp_chunk.strip())
                        temp_chunk = word + ' '
                current_chunk = temp_chunk
            else:
                current_chunk = paragraph + '\n'
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks if chunks else [text]


# ============================================================
# Команды бота
# ============================================================

def start_command(message: UpdateMessage) -> None:
    """Обработка команды /start - начало опроса"""
    user_id = message.sender_peer.id
    start_survey_with_llm(message, user_id, "gigachat")


def help_command(message: UpdateMessage) -> None:
    """Обработка команды /help"""
    bot.messaging.send_message_sync(
        message.peer,
        "📋 *Команды бота:*\n\n"
        "/start — Начать новый опрос\n"
        "/help — Показать это сообщение\n\n"
        "Просто отвечайте на вопросы текстом или нажимайте кнопки."
    )


# ============================================================
# Основная логика опроса
# ============================================================

def start_survey_with_llm(message: UpdateMessage, user_id: int, llm_type: str) -> None:
    """Начать опрос с выбранным LLM"""
    session_id = db.get_next_session_id(user_id)
    remaining_questions = db.get_remaining_questions(user_id, session_id)
    
    state = {
        'session_id': session_id,
        'remaining_questions': remaining_questions,
        'conversation': [],
        'llm_type': llm_type
    }
    
    active_sessions[user_id] = {
        'session_id': session_id,
        'state': state
    }
    
    service = LLMFactory.create_service(llm_type)
    bot.messaging.send_message_sync(message.peer, f"💡 Используется: {service.emoji} {service.name}")
    
    intro_text = """
Добрый день! Этот опрос поможет оценить уровень позиции в вашей команде по международной методике HAY Group. 

Отвечайте, пожалуйста, исходя из реальных требований и сложности роли, а не из качеств конкретного сотрудника

В примерах к каждому вопросу приведены ориентиры для одной условной должности — «Менеджер по продажам». Используйте их как образец стиля ответа, а не как точный шаблон. Ваша задача — описать именно ту роль, которую вы оцениваете
"""
    
    # Создаём кнопку "Начать интервью"
    button = InteractiveMediaGroup(
        [InteractiveMedia(
            "start_interview",
            InteractiveMediaButton("start_interview", "🚀 Начать интервью"),
            InteractiveMediaStyle.PRIMARY
        )]
    )
    
    bot.messaging.send_message_sync(message.peer, intro_text, [button])


def send_question(peer, question_id: int, user_id: int) -> None:
    """Отправить вопрос"""
    question_data = db.get_question(question_id)
    formatted_question = format_question_text(question_data['question'])
    
    if question_data['answer_options']:
        options = [opt.strip() for opt in question_data['answer_options'].split(';')]
        
        # Создаём кнопки для вариантов ответа
        buttons = []
        for i, opt in enumerate(options):
            buttons.append(InteractiveMedia(
                f"answer_{question_id}_{i}",
                InteractiveMediaButton(f"answer_{question_id}_{i}", opt[:60]),  # Ограничение длины
                InteractiveMediaStyle.DEFAULT
            ))
        
        button_group = InteractiveMediaGroup(buttons)
        bot.messaging.send_message_sync(peer, f"Вопрос {question_id}: {formatted_question}", [button_group])
    else:
        bot.messaging.send_message_sync(peer, f"Вопрос {question_id}: {formatted_question}")


def send_next_question(peer, user_id: int, session_id: int) -> None:
    """Отправить следующий вопрос из списка"""
    if user_id not in active_sessions:
        bot.messaging.send_message_sync(peer, "Напишите /start для начала опроса")
        return
    
    state = active_sessions[user_id]['state']
    
    if state['remaining_questions']:
        next_question_id = state['remaining_questions'][0]
        
        if next_question_id == 11:
            send_adaptive_question_11(peer, user_id, session_id)
        elif next_question_id == 12:
            send_adaptive_question_12(peer, user_id, session_id)
        elif next_question_id == 18:
            send_adaptive_question_18(peer, user_id, session_id)
        else:
            send_question(peer, next_question_id, user_id)
    else:
        db.save_user_state(user_id, session_id, state)
        if user_id in active_sessions:
            del active_sessions[user_id]
        generate_and_send_report(peer, user_id, session_id)


# ============================================================
# Адаптивные вопросы Q11, Q12, Q18
# ============================================================

def send_adaptive_question_11(peer, user_id: int, session_id: int) -> None:
    """Отправка вопроса 11 с адаптивными вариантами на основе P1"""
    try:
        from grade_calculator import GradeCalculator
        calculator = GradeCalculator()
        p1_value = calculator.calculate_intermediate_p1(user_id, session_id)
        
        if p1_value is None:
            print("⚠️ Не удалось вычислить P1, показываем варианты для Q8,Q9,Q10")
            show_missing_p1_options(peer, user_id, session_id)
            return
        
        variants = db.get_question_variants(11, p1_value)
        question_data = db.get_question(11)
        
        if not variants:
            print("⚠️ Нет вариантов для Q11, используем стандартную логику")
            send_question(peer, 11, user_id)
            return
        
        state = active_sessions[user_id]['state']
        if 11 in state['remaining_questions']:
            state['remaining_questions'].remove(11)
        active_sessions[user_id]['state'] = state
        
        formatted_question = format_question_text(question_data['question'])
        
        if len(variants) == 1:
            text = f"""Вопрос {question_data['id']}: {formatted_question}

🔍 Исходя из ваших предыдущих ответов, возможен только следующий вариант:

📋 {variants[0]['variant_text']}

Согласны ли вы с этим вариантом?"""
            
            buttons = [
                InteractiveMedia(
                    f"q11_accept_{variants[0]['answer_value']}",
                    InteractiveMediaButton(f"q11_accept_{variants[0]['answer_value']}", f"✅ Вариант {variants[0]['answer_value']}"),
                    InteractiveMediaStyle.PRIMARY
                ),
                InteractiveMedia(
                    "restart_from_q8",
                    InteractiveMediaButton("restart_from_q8", "🔄 Переответить с 8-го вопроса"),
                    InteractiveMediaStyle.DEFAULT
                )
            ]
        else:
            text = f"""Вопрос {question_data['id']}: {formatted_question}

🔍 Исходя из ваших предыдущих ответов, возможны следующие варианты:

"""
            for variant in variants:
                text += f"📋 {variant['variant_text']}\n\n"
            text += "Выберите наиболее подходящий вариант:"
            
            buttons = []
            for variant in variants:
                buttons.append(InteractiveMedia(
                    f"q11_select_{variant['answer_value']}",
                    InteractiveMediaButton(f"q11_select_{variant['answer_value']}", f"{variant['answer_value']}"),
                    InteractiveMediaStyle.DEFAULT
                ))
            buttons.append(InteractiveMedia(
                "restart_from_q8",
                InteractiveMediaButton("restart_from_q8", "🔄 Переответить с 8-го вопроса"),
                InteractiveMediaStyle.DEFAULT
            ))
        
        button_group = InteractiveMediaGroup(buttons)
        bot.messaging.send_message_sync(peer, text, [button_group])
        
    except Exception as e:
        print(f"❌ Ошибка в адаптивном Q11: {e}")
        send_question(peer, 11, user_id)


def send_adaptive_question_12(peer, user_id: int, session_id: int) -> None:
    """Отправка вопроса 12 с адаптивными вариантами с учетом ответа на Q11"""
    try:
        from grade_calculator import GradeCalculator
        calculator = GradeCalculator()
        p1_value = calculator.calculate_intermediate_p1(user_id, session_id)
        
        if p1_value is None:
            print("⚠️ Не удалось вычислить P1 для Q12")
            show_missing_p1_options(peer, user_id, session_id)
            return
        
        user_responses = db.get_user_responses(user_id, session_id)
        q11_answer = None
        
        for response in user_responses:
            if response['question'] == 11:
                try:
                    q11_answer = int(response['final_answer'])
                    break
                except (ValueError, TypeError):
                    continue
        
        if q11_answer is None:
            print("⚠️ Не найден ответ на Q11, используем стандартную логику")
            send_question(peer, 12, user_id)
            return
        
        print(f"🔍 Для Q12: P1={p1_value}, Q11_answer={q11_answer}")
        
        variants = db.get_question_variants(12, p1_value, q11_answer)
        question_data = db.get_question(12)
        
        if not variants:
            print("⚠️ Нет вариантов для Q12, используем стандартную логику")
            send_question(peer, 12, user_id)
            return
        
        state = active_sessions[user_id]['state']
        if 12 in state['remaining_questions']:
            state['remaining_questions'].remove(12)
        active_sessions[user_id]['state'] = state
        
        formatted_question = format_question_text(question_data['question'])
        
        if len(variants) == 1:
            text = f"""Вопрос {question_data['id']}: {formatted_question}

🔍 Исходя из ваших предыдущих ответов, возможен только следующий вариант:

📋 {variants[0]['variant_text']}

Согласны ли вы с этим вариантом?"""
            
            buttons = [
                InteractiveMedia(
                    f"q12_accept_{variants[0]['answer_value']}",
                    InteractiveMediaButton(f"q12_accept_{variants[0]['answer_value']}", f"✅ Вариант {variants[0]['answer_value']}"),
                    InteractiveMediaStyle.PRIMARY
                ),
                InteractiveMedia(
                    "restart_from_q8",
                    InteractiveMediaButton("restart_from_q8", "🔄 Переответить с 8-го вопроса"),
                    InteractiveMediaStyle.DEFAULT
                )
            ]
        else:
            text = f"""Вопрос {question_data['id']}: {formatted_question}

🔍 Исходя из ваших предыдущих ответов, возможны следующие варианты:

"""
            for variant in variants:
                text += f"📋 {variant['variant_text']}\n\n"
            text += "Выберите наиболее подходящий вариант:"
            
            buttons = []
            for variant in variants:
                buttons.append(InteractiveMedia(
                    f"q12_select_{variant['answer_value']}",
                    InteractiveMediaButton(f"q12_select_{variant['answer_value']}", f"{variant['answer_value']}"),
                    InteractiveMediaStyle.DEFAULT
                ))
            buttons.append(InteractiveMedia(
                "restart_from_q8",
                InteractiveMediaButton("restart_from_q8", "🔄 Переответить с 8-го вопроса"),
                InteractiveMediaStyle.DEFAULT
            ))
        
        button_group = InteractiveMediaGroup(buttons)
        bot.messaging.send_message_sync(peer, text, [button_group])
        
    except Exception as e:
        print(f"❌ Ошибка в адаптивном Q12: {e}")
        send_question(peer, 12, user_id)


def send_adaptive_question_18(peer, user_id: int, session_id: int) -> None:
    """Отправка вопроса 18 с автогенерированным функционалом"""
    try:
        portrait = db.get_session_portrait(user_id, session_id)
        
        if not portrait:
            print("⚠️ Портрет пользователя пуст, используем стандартную логику")
            send_question(peer, 18, user_id)
            return
        
        agents = get_agents_for_user(user_id)
        functionality_agent = agents['functionality']
        
        # Статусное сообщение
        bot.messaging.send_message_sync(peer, "⏳ Генерирую функционал...")
        
        generated_functionality = functionality_agent.generate_functionality(portrait)
        
        state = active_sessions[user_id]['state']
        if 18 in state['remaining_questions']:
            state['remaining_questions'].remove(18)
        
        state['awaiting_functionality_addition'] = True
        state['generated_functionality'] = generated_functionality
        active_sessions[user_id]['state'] = state
        
        question_data = db.get_question(18)
        formatted_question = format_question_text(question_data['question'])
        
        text = f"""📋 *{formatted_question}*

На основании ваших предыдущих ответов сформирован следующий функционал:

{generated_functionality}

При необходимости можете добавить еще функции, напишите их. Или нажмите "✅ Принять как есть", если функционал подходит."""
        
        button = InteractiveMediaGroup([
            InteractiveMedia(
                "func_accept_18",
                InteractiveMediaButton("func_accept_18", "✅ Принять как есть"),
                InteractiveMediaStyle.PRIMARY
            )
        ])
        
        bot.messaging.send_message_sync(peer, text, [button])
        
    except Exception as e:
        print(f"❌ Ошибка в адаптивном Q18: {e}")
        send_question(peer, 18, user_id)


def show_missing_p1_options(peer, user_id: int, session_id: int) -> None:
    """Показать пользователю его ответы на Q8,Q9,Q10 и предложить пересдать"""
    try:
        responses = db.get_user_responses(user_id, session_id)
        q8_q9_q10_answers = {}
        
        for r in responses:
            if r['question'] in [8, 9, 10]:
                q8_q9_q10_answers[r['question']] = {
                    'answer': r['answer'],
                    'final_answer': r['final_answer']
                }
        
        text = """❌ Не удалось определить варианты для следующих вопросов на основе ваших предыдущих ответов.

📋 Ваши текущие ответы:"""
        
        for q_num in [8, 9, 10]:
            if q_num in q8_q9_q10_answers:
                answer_info = q8_q9_q10_answers[q_num]
                final = answer_info['final_answer'] or answer_info['answer']
                text += f"\n• Вопрос {q_num}: {final}"
            else:
                text += f"\n• Вопрос {q_num}: (нет ответа)"
        
        text += "\n\n🔄 Предлагаем пересдать вопросы 8-10 для корректного определения вариантов."
        
        button = InteractiveMediaGroup([
            InteractiveMedia(
                "restart_from_q8",
                InteractiveMediaButton("restart_from_q8", "🔄 Переответить с 8-го вопроса"),
                InteractiveMediaStyle.DEFAULT
            )
        ])
        
        bot.messaging.send_message_sync(peer, text, [button])
        
    except Exception as e:
        print(f"❌ Ошибка в show_missing_p1_options: {e}")
        button = InteractiveMediaGroup([
            InteractiveMedia(
                "restart_from_q8",
                InteractiveMediaButton("restart_from_q8", "🔄 Переответить с 8-го вопроса"),
                InteractiveMediaStyle.DEFAULT
            )
        ])
        bot.messaging.send_message_sync(
            peer,
            "❌ Не удалось определить варианты ответов.\n\n🔄 Предлагаем пересдать вопросы с 8-го.",
            [button]
        )


# ============================================================
# Обработка конфликтов
# ============================================================

def handle_conflict(peer, user_id: int, session_id: int, conflict: Dict, state: Dict) -> None:
    """Обработка обнаруженного конфликта"""
    from conflictator import ConflictDetector
    
    detector = ConflictDetector(db)
    llm_type = state.get('llm_type', 'gigachat')
    llm = LLMFactory.create_service(llm_type)
    portrait = db.get_session_portrait(user_id, session_id)
    
    conflict_details = "⚠️ *ОБНАРУЖЕНО ПРОТИВОРЕЧИЕ В ОТВЕТАХ*\n\n"
    conflict_details += "Ваши ответы на следующие вопросы противоречат друг другу:\n\n"
    
    for i, q_info in enumerate(conflict['questions'], 1):
        question_id = q_info['question_id']
        conflict_details += f"*{i}. Вопрос {question_id}*\n\n"
    
    bot.messaging.send_message_sync(peer, conflict_details)
    
    # Техническая информация
    print("\n" + "="*70)
    print("📊 ТЕХНИЧЕСКАЯ ИНФОРМАЦИЯ О КОНФЛИКТЕ")
    print("="*70)
    print(f"Конфликт ID: {conflict.get('id', 'N/A')}")
    print(f"Вопросы в конфликте: {conflict['question_ids']}")
    print("="*70 + "\n")
    
    # Статусное сообщение
    bot.messaging.send_message_sync(peer, "⏳ Анализирую противоречие...")
    
    explanation_prompt = detector.generate_conflict_explanation(conflict, portrait)
    messages = [{"role": "user", "content": explanation_prompt}]
    explanation = llm.generate_response(messages, task_type='explanation')
    
    conflicted_questions = conflict['question_ids']
    print(f"🔄 КОНФЛИКТАТОР - Возвращаем вопросы в очередь: {conflicted_questions}")
    
    db.add_questions_to_remaining(user_id, session_id, conflicted_questions)
    
    state['remaining_questions'] = db.get_remaining_questions(user_id, session_id)
    state['conversation'] = []
    active_sessions[user_id]['state'] = state
    db.save_user_state(user_id, session_id, state)
    
    bot.messaging.send_message_sync(peer, f"🤖 {explanation}")
    bot.messaging.send_message_sync(peer, f"🔄 Предлагаю ответить на эти вопросы заново...")
    
    send_next_question(peer, user_id, session_id)


# ============================================================
# Генерация и отправка отчётов
# ============================================================

def generate_and_send_report(peer, user_id: int, session_id: int) -> None:
    """Генерирует HTML и XLSX отчеты и отправляет их пользователю"""
    try:
        report_path = report_generator.save_report_to_file(
            user_id=user_id, 
            session_id=session_id,
            output_path=f"reports/report_user_{user_id}_session_{session_id}.html"
        )
        
        from xlsx_report_generator import XLSXReportGenerator
        xlsx_generator = XLSXReportGenerator()
        xlsx_report_path = xlsx_generator.generate_report(user_id, session_id)
        
        # Отправляем HTML отчёт
        with open(report_path, 'rb') as f:
            html_content = f.read()
        
        bot.messaging.send_file_sync(
            peer=peer,
            file=html_content,
            name=f"report_user_{user_id}_session_{session_id}.html",
            text=f"📊 HTML отчет\n📅 Дата: {get_current_datetime()}\n🔢 Сессия: {session_id}"
        )
        
        # Отправляем XLSX отчёт
        with open(xlsx_report_path, 'rb') as f:
            xlsx_content = f.read()
        
        bot.messaging.send_file_sync(
            peer=peer,
            file=xlsx_content,
            name=f"calculator_user_{user_id}_session_{session_id}.xlsx",
            text=f"📊 Excel отчет\n📅 Дата: {get_current_datetime()}\n🔢 Сессия: {session_id}"
        )
        
        print(f"✅ Отчеты отправлены пользователю {user_id}")
        bot.messaging.send_message_sync(peer, "🎉 Интервьюирование завершено. Спасибо!")
        
    except Exception as e:
        print(f"Ошибка при генерации отчета: {e}")
        import traceback
        traceback.print_exc()
        bot.messaging.send_message_sync(peer, "❌ Произошла ошибка при генерации отчета. Обратитесь к администратору.")


# ============================================================
# Обработка callback-ов (нажатий кнопок)
# ============================================================

def handle_interactive(message: UpdateMessage) -> None:
    """Обработка нажатий интерактивных кнопок"""
    try:
        # Получаем ID кнопки
        if not message.message or not message.message.interactive_media_confirm:
            return
        
        callback_id = message.message.interactive_media_confirm.id
        user_id = message.sender_peer.id
        peer = message.peer
        
        print(f"🔘 Callback: {callback_id} от пользователя {user_id}")
        
        # Обработка кнопки "Начать интервью"
        if callback_id == "start_interview":
            if user_id not in active_sessions:
                bot.messaging.send_message_sync(peer, "❌ Сессия не найдена. Напишите /start")
                return
            session_id = active_sessions[user_id]['session_id']
            send_next_question(peer, user_id, session_id)
            return
        
        # Обработка кнопки "Переответить с 8-го вопроса"
        if callback_id == "restart_from_q8":
            if user_id not in active_sessions:
                bot.messaging.send_message_sync(peer, "❌ Сессия не найдена")
                return
            
            session_id = active_sessions[user_id]['session_id']
            db.reset_questions_from_8(user_id, session_id)
            
            state = active_sessions[user_id]['state']
            state['remaining_questions'] = db.get_remaining_questions(user_id, session_id)
            state['conversation'] = []
            active_sessions[user_id]['state'] = state
            db.save_user_state(user_id, session_id, state)
            
            bot.messaging.send_message_sync(peer, "🔄 Пересдаём вопросы с 8-го...")
            bot.messaging.send_message_sync(peer, "Хорошо, давайте пересдадим вопросы с 8-го.")
            send_next_question(peer, user_id, session_id)
            return
        
        # Обработка кнопки "Принять функционал"
        if callback_id == "func_accept_18":
            if user_id not in active_sessions:
                bot.messaging.send_message_sync(peer, "❌ Сессия не найдена")
                return
            
            session_id = active_sessions[user_id]['session_id']
            state = active_sessions[user_id]['state']
            functionality = state.get('generated_functionality', 'Функционал принят как есть')
            
            db.save_response(user_id, session_id, 18, functionality, functionality, None, check_conflicts=False)
            db.generate_user_portrait(user_id, session_id)
            
            state['awaiting_functionality_addition'] = False
            state.pop('generated_functionality', None)
            active_sessions[user_id]['state'] = state
            
            bot.messaging.send_message_sync(peer, f"✅ *Функционал принят:*\n\n{functionality}")
            send_next_question(peer, user_id, session_id)
            return
        
        # Обработка адаптивных вопросов Q11/Q12
        if callback_id.startswith("q11_") or callback_id.startswith("q12_"):
            if user_id not in active_sessions:
                bot.messaging.send_message_sync(peer, "❌ Сессия не найдена. Напишите /start")
                return
            
            session_id = active_sessions[user_id]['session_id']
            
            parts = callback_id.split('_')
            question_num = int(parts[0][1:])  # q11 -> 11
            action = parts[1]  # accept или select
            answer_value = int(parts[2])
            
            variant_text = get_variant_text_by_value(question_num, answer_value, user_id, session_id)
            
            response_id, conflicts = db.save_response(
                user=user_id,
                session_id=session_id,
                question=question_num,
                answer=variant_text,
                final_answer=str(answer_value),
                user_state=None
            )
            
            db.generate_user_portrait(user_id, session_id)
            
            if conflicts:
                state = active_sessions[user_id]['state']
                handle_conflict(peer, user_id, session_id, conflicts[0], state)
                return
            
            bot.messaging.send_message_sync(peer, "✅ Принято! Отлично!")
            
            if question_num == 11:
                send_adaptive_question_12(peer, user_id, session_id)
            else:
                send_next_question(peer, user_id, session_id)
            return
        
        # Обработка ответов на обычные вопросы с кнопками
        if callback_id.startswith("answer_"):
            parts = callback_id.split('_')
            question_id = int(parts[1])
            option_index = int(parts[2])
            
            if user_id not in active_sessions:
                bot.messaging.send_message_sync(peer, "❌ Сессия не найдена. Напишите /start")
                return
            
            session_id = active_sessions[user_id]['session_id']
            question_data = db.get_question(question_id)
            
            if question_data['answer_options']:
                options = [opt.strip() for opt in question_data['answer_options'].split(';')]
                if 0 <= option_index < len(options):
                    user_answer = options[option_index]
                    process_answer(peer, user_id, session_id, user_answer)
            return
        
    except Exception as e:
        logging.exception(f"Ошибка обработки callback: {e}")
        bot.messaging.send_message_sync(message.peer, "❌ Произошла ошибка при обработке.")


def get_variant_text_by_value(question_num: int, answer_value: int, user_id: int, session_id: int) -> str:
    """Получить полный текст варианта по номеру ответа"""
    try:
        from grade_calculator import GradeCalculator
        calculator = GradeCalculator()
        p1_value = calculator.calculate_intermediate_p1(user_id, session_id)
        
        if p1_value is not None:
            variants = db.get_question_variants(question_num, p1_value)
            for variant in variants:
                if variant['answer_value'] == answer_value:
                    return variant['variant_text']
        
        return f"Вариант {answer_value}"
    except Exception as e:
        print(f"❌ Ошибка получения текста варианта: {e}")
        return f"Вариант {answer_value}"


# ============================================================
# Обработка текстовых сообщений
# ============================================================

def handle_text(message: UpdateMessage) -> None:
    """Обработка текстовых ответов"""
    try:
        user_id = message.sender_peer.id
        peer = message.peer
        
        # Получаем текст сообщения
        if not message.message or not message.message.text_message:
            return
        
        user_answer = message.message.text_message.text
        
        if not user_answer:
            return
        
        print(f"🔍 Получено сообщение от пользователя {user_id}: '{user_answer}'")
        
        if user_id not in active_sessions:
            print("❌ Нет активной сессии, отправляю сообщение о /start")
            bot.messaging.send_message_sync(peer, "Напишите /start для начала опроса")
            return
        
        session_data = active_sessions[user_id]
        session_id = session_data['session_id']
        
        process_answer(peer, user_id, session_id, user_answer)
        
    except Exception as e:
        logging.exception("Ошибка обработки сообщения в СберЧате")
        bot.messaging.send_message_sync(message.peer, "❌ Произошла ошибка при обработке запроса.")


def process_answer(peer, user_id: int, session_id: int, user_answer: str) -> None:
    """Обработка ответа пользователя"""
    state = active_sessions[user_id]['state']
    
    print(f"🔍 Active Session ID: {session_id}")
    print(f"🔍 User state: {state}")
    
    # Проверяем, ожидаются ли дополнения к функционалу (вопрос 18)
    if state.get('awaiting_functionality_addition', False):
        handle_functionality_addition(peer, user_id, session_id, user_answer)
        return
    
    if not state['remaining_questions']:
        bot.messaging.send_message_sync(peer, "🎉 Опрос завершен!")
        if user_id in active_sessions:
            del active_sessions[user_id]
        return
    
    current_question = state['remaining_questions'][0]
    question_data = db.get_question(current_question)
    
    print(f"🔍 Current question: {current_question}")
    print(f"🔍 Question text: {question_data['question']}")
    print(f"🔍 Conversation before: {state['conversation']}")
    
    state['conversation'].append(user_answer)
    active_sessions[user_id]['state'] = state
    
    print(f"🔍 Conversation after: {state['conversation']}")
    
    agents = get_agents_for_user(user_id)
    verification_agent = agents['verification']
    answer_agent = agents['answer']
    classification_agent = agents['classification']
    
    if question_data['answer_options']:
        portrait = db.get_session_portrait(user_id, session_id)
        final_answer = classification_agent.classify_answer(question_data, user_answer, portrait)
        
        has_classifier = bool(question_data.get('classifier'))
        response_id, conflicts = db.save_response(user_id, session_id, current_question, user_answer, final_answer, None, check_conflicts=has_classifier)
        
        db.generate_user_portrait(user_id, session_id)
        
        if conflicts:
            first_conflict = conflicts[0]
            handle_conflict(peer, user_id, session_id, first_conflict, state)
            return
        
        state['remaining_questions'] = db.get_remaining_questions(user_id, session_id)
        state['conversation'] = []
        active_sessions[user_id]['state'] = state
        db.save_user_state(user_id, session_id, state)
        
        send_next_question(peer, user_id, session_id)
    else:
        portrait = db.get_session_portrait(user_id, session_id)
        
        # Статусное сообщение
        bot.messaging.send_message_sync(peer, "⏳ Обрабатываю ответ...")
        
        is_accepted, response_text = verification_agent.process_answer(
            question_data, user_answer, state['conversation'], portrait
        )
        
        if is_accepted:
            full_answer = answer_agent.create_full_answer(question_data, state['conversation'], portrait)
            final_answer = classification_agent.classify_answer(question_data, full_answer, portrait)
            
            has_classifier = bool(question_data.get('classifier'))
            response_id, conflicts = db.save_response(user_id, session_id, current_question, full_answer, final_answer, None, check_conflicts=has_classifier)
            
            db.generate_user_portrait(user_id, session_id)
            
            if conflicts:
                first_conflict = conflicts[0]
                handle_conflict(peer, user_id, session_id, first_conflict, state)
                return
            
            state['remaining_questions'] = db.get_remaining_questions(user_id, session_id)
            state['conversation'] = []
            active_sessions[user_id]['state'] = state
            db.save_user_state(user_id, session_id, state)
            
            bot.messaging.send_message_sync(peer, f"✅ Принято! {response_text}")
            send_next_question(peer, user_id, session_id)
        else:
            state['conversation'].append(response_text)
            active_sessions[user_id]['state'] = state
            bot.messaging.send_message_sync(peer, f"❓ {response_text}")


def handle_functionality_addition(peer, user_id: int, session_id: int, addition_text: str) -> None:
    """Обработка текстовых дополнений к функционалу"""
    try:
        state = active_sessions[user_id]['state']
        generated_functionality = state.get('generated_functionality', '')
        
        full_functionality = f"{generated_functionality}\n\n*Дополнения:*\n{addition_text}"
        
        db.save_response(user_id, session_id, 18, full_functionality, full_functionality, None, check_conflicts=False)
        db.generate_user_portrait(user_id, session_id)
        
        state['awaiting_functionality_addition'] = False
        state.pop('generated_functionality', None)
        active_sessions[user_id]['state'] = state
        
        bot.messaging.send_message_sync(peer, f"✅ *Функционал сохранен с вашими дополнениями:*\n\n{full_functionality}")
        send_next_question(peer, user_id, session_id)
        
    except Exception as e:
        print(f"❌ Ошибка обработки дополнений функционала: {e}")
        bot.messaging.send_message_sync(peer, "❌ Произошла ошибка при сохранении дополнений")


# ============================================================
# Точка входа
# ============================================================

def main():
    global bot
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    if not SBERCHAT_AVAILABLE:
        print("❌ sber-sberchat-bot-sdk не установлен!")
        print("   Установите пакет из корпоративного репозитория")
        return
    
    if not SBERCHAT_TOKEN:
        print("❌ SBERCHAT_TOKEN не задан в .env файле!")
        return
    
    # Конфигурация бота
    bot_config = {
        "endpoint": SBERCHAT_ENDPOINT,
        "token": SBERCHAT_TOKEN,
        "is_secure": SBERCHAT_IS_SECURE,
    }
    
    # Добавляем сертификат если файл существует
    if SBERCHAT_ROOT_CERT and os.path.isfile(SBERCHAT_ROOT_CERT):
        bot_config["root_certificates"] = SBERCHAT_ROOT_CERT
    
    bot = DialogBot.create_bot(bot_config)
    
    # Регистрируем команды
    bot.messaging.command_handler([
        CommandHandler(start_command, "start", description="Начать опрос"),
        CommandHandler(help_command, "help", description="Помощь"),
    ])
    
    # Регистрируем обработчики сообщений
    bot.messaging.message_handler([
        MessageHandler(handle_text, MessageContentType.TEXT_MESSAGE),
    ])
    
    # Регистрируем обработчик интерактивных кнопок
    bot.messaging.message_handler([
        MessageHandler(handle_interactive, MessageContentType.INTERACTIVE_MEDIA_CONFIRM),
    ])
    
    print("🤖 СберЧат бот HayAutoGrade запущен!")
    bot.updates.on_updates(do_read_message=True, do_register_commands=True)


if __name__ == "__main__":
    main()
