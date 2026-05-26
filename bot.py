import os
import asyncio
import logging
from datetime import datetime
import cohere
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.chat_action import ChatActionSender

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load Environment Variables
load_dotenv()

# Read Environment Variables
TOKEN = os.getenv("TOKEN")
COHERE_API = os.getenv("COHERE_API")
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")  # this line

# Parse Admin IDs
ADMIN_IDS = set()
if ADMIN_IDS_STR:
    for admin in ADMIN_IDS_STR.split(","):
        admin = admin.strip()
        if admin.isdigit():
            ADMIN_IDS.add(int(admin))

# Initialize Cohere Client
co = None
if COHERE_API:
    try:
        co = cohere.ClientV2(api_key=COHERE_API)
    except Exception as e:
        logger.error(f"Failed to initialize Cohere ClientV2: {e}")
else:
    logger.warning("COHERE_API is not set in environment.")

# In-Memory State Storage
# USER_STATES structure: { user_id: { "language": str, "role": str, "history": list, "message_count": int, "is_onboarding": bool } }
USER_STATES = {}

# FEEDBACK_LOGS structure: list of dicts
FEEDBACK_LOGS = []

# Load text resources
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    with open(os.path.join(BASE_DIR, "prompt-base"), "r", encoding="utf-8") as f:
        PROMPT_BASE = f.read().strip()
except Exception as e:
    logger.error(f"Error loading prompt-base: {e}")
    PROMPT_BASE = "Your name is Ask IUCA. You are an AI assistant for IUCA in Kyrgyzstan."

try:
    with open(os.path.join(BASE_DIR, "knowledge-base"), "r", encoding="utf-8") as f:
        KNOWLEDGE_BASE = f.read().strip()
except Exception as e:
    logger.error(f"Error loading knowledge-base: {e}")
    KNOWLEDGE_BASE = "International University of Central Asia (IUCA) is located in Tokmok, Kyrgyzstan."

# Language and Role specific system prompts (6 variants)
LANG_ROLE_INSTRUCTIONS = {
    ("ru", "student"): "You must respond in Russian. Tone: Informal (ты), conversational, short & direct.\nNever use Markdown formatting, asterisks (*), or any special text styling.",
    ("ru", "parent"): "You must respond in Russian. Tone: Formal (вы), literary, thorough & precise.\nNever use Markdown formatting, asterisks (*), or any special text styling.",
    ("ky", "student"): "You must respond in Kyrgyz. Tone: Friendly, simple Kyrgyz, short & direct.\nNever use Markdown formatting, asterisks (*), or any special text styling.",
    ("ky", "parent"): "You must respond in Kyrgyz. Tone: Formal, literary Kyrgyz, respectful & precise.\nNever use Markdown formatting, asterisks (*), or any special text styling.",
    ("en", "student"): "You must respond in English. Tone: Casual & friendly, concise & direct.\nNever use Markdown formatting, asterisks (*), or any special text styling.",
    ("en", "parent"): "You must respond in English. Tone: Formal, respectful & thorough.\nNever use Markdown formatting, asterisks (*), or any special text styling."
}

# Prompts for languages and roles
LANG_PROMPT = "Выберите язык | Тилди тандаңыз | Choose your language"
ROLE_PROMPT = "Выберите вашу роль | Ролуңузду тандаңыз | Choose your role"

# Onboarding Keyboards
lang_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
    [InlineKeyboardButton(text="🇰🇬 Кыргызча", callback_data="lang_ky")],
    [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")]
])

role_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🎓 Студент | Student", callback_data="role_student")],
    [InlineKeyboardButton(text="👨👩 Родитель | Ата-эне | Parent", callback_data="role_parent")]
])

# Helper function to construct system prompts
def build_system_prompt(lang: str, role: str) -> str:
    instruction = LANG_ROLE_INSTRUCTIONS.get((lang, role), "")
    return f"{PROMPT_BASE}\n\n{KNOWLEDGE_BASE}\n\n{instruction}"

# Helper function to generate and send first-time greeting
async def generate_and_send_greeting(bot: Bot, chat_id: int, user_id: int):
    state = USER_STATES[user_id]
    lang = state["language"]
    role = state["role"]
    
    sys_prompt = build_system_prompt(lang, role)
    
    # Ask Cohere to greet the user
    greeting_prompt = {
        "en": "Hello! Introduce yourself to me in the language and tone specified in your instructions. Keep it very short.",
        "ru": "Привет! Представься мне на русском языке в соответствии со своими инструкциями по тону общения. Отвечай кратко.",
        "ky": "Салам! Багыттооңорго ылайык кыргыз тилинде мага өзүңдү тааныштыр. Кыска жооп бер."
    }.get(lang, "Hello! Please greet me.")
    
    async with ChatActionSender.typing(bot=bot, chat_id=chat_id):
        try:
            if not co:
                raise ValueError("Cohere API client is not initialized")
                
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: co.chat(
                    model="command-a-03-2025",
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": greeting_prompt}
                    ]
                )
            )
            
            # Safe extraction of text response
            content = response.message.content
            if isinstance(content, list):
                reply_text = content[0].text
            elif isinstance(content, str):
                reply_text = content
            else:
                reply_text = str(content)
                
            reply_text = reply_text.replace("*", "").strip()
            
        except Exception as e:
            logger.error(f"Error calling Cohere for greeting: {e}")
            reply_text = {
                "en": "Hello! I am Ask IUCA, a special assistant made just for IUCA. How can I help you today?",
                "ru": "Привет! Я Ask IUCA — специальный помощник для МУЦА. Чем я могу помочь тебе сегодня?",
                "ky": "Салам! Мен Ask IUCA — БАЭУ үчүн атайын жасалган жардамчымын. Бүгүн сизге кантип жардам бере алам?"
            }.get(lang, "Hello! Welcome to Ask IUCA.")
            
        # Send greeting
        await bot.send_message(chat_id=chat_id, text=reply_text)
        
        # Save greeting to history
        state["history"] = [{"role": "assistant", "content": reply_text}]

# Router initialization
router = Router()

# Command Handlers

@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    
    # 1. Clear all existing user state & start onboarding
    USER_STATES[user_id] = {
        "language": None,
        "role": None,
        "history": [],
        "message_count": 0,
        "is_onboarding": True
    }
    
    # 2. Show language selection (inline buttons, no prompt text)
    await message.answer(text=LANG_PROMPT, reply_markup=lang_keyboard)

@router.message(Command("help"))
async def cmd_help(message: Message):
    user_id = message.from_user.id
    state = USER_STATES.get(user_id)
    lang = state["language"] if state else None
    
    if lang == "ru":
        help_text = (
            "🤖 Доступные команды:\n\n"
            "/start - Полный сброс настроек и перезапуск обучения\n"
            "/help - Показать список доступных команд\n"
            "/about - Описание бота и контакты МУЦА\n"
            "/settings - Показать текущие настройки с кнопками изменения\n"
            "/reset - Очистить историю диалога (сохранить язык и роль)"
        )
    elif lang == "ky":
        help_text = (
            "🤖 Жеткиликтүү буйруктар:\n\n"
            "/start - Толук тазалоо жана баштапкы жөндөөлөрдү баштоо\n"
            "/help - Буйруктардын тизмесин көрсөтүү\n"
            "/about - Бот жөнүндө маалымат жана МУЦА байланыштары\n"
            "/settings - Учурдагы жөндөөлөрдү көрсөтүү жана өзгөртүү\n"
            "/reset - Сүйлөшүү тарыхын тазалоо (тил жана роль сакталат)"
        )
    else:
        help_text = (
            "🤖 Available commands:\n\n"
            "/start - Full reset of history & settings, restart onboarding\n"
            "/help - Show plain-text list of all commands\n"
            "/about - Show bot description + IUCA contact info\n"
            "/settings - Show current language & role with change buttons\n"
            "/reset - Clear conversation history only — keep language & role"
        )
        
    await message.answer(help_text)

@router.message(Command("about"))
async def cmd_about(message: Message):
    user_id = message.from_user.id
    state = USER_STATES.get(user_id)
    lang = state["language"] if state else None
    
    if lang == "ru":
        about_text = (
            "ℹ️ О боте \"Ask IUCA\":\n"
            "Я — виртуалный помощник Международного Университета Центральной Азии (МУЦА) в г. Токмок.\n"
            "Помогаю студентам и абитуриентам с вопросами о поступлении, учебных программах, стоимости обучения, стипендиях и жизни на кампусе.\n\n"
            "📞 Контакты МУЦА:\n"
            "📍 Адрес: Кыргызстан, г. Токмок, ул. Комсомольская 141а\n"
            "📧 Email: info@iuca.kg\n"
            "📱 WhatsApp / Приемная комиссия: +996 503 434 410\n"
            "☎️ Телефон: +996 3138 60263\n"
            "🕒 Часы работы: Пн-Пт, 9:00 - 17:00\n"
            "📸 Instagram: @iucatokmok"
        )
    elif lang == "ky":
        about_text = (
            "ℹ️ \"Ask IUCA\" боту жөнүндө:\n"
            "Мен Токмок шаарындагы Борбордук Азия Эл аралык Университетинин (БАЭУ) виртуалдык жардамчысымын.\n"
            "Студенттерге жана абитуриенттерге окууга кирүү, окуу программалары, келишим баалары, стипендиялар жана кампустагы жашоо боюнча маалымат алууга жардам берем.\n\n"
            "📞 БАЭУ байланыштары:\n"
            "📍 Дареги: Кыргызстан, Токмок ш., Комсомольская көч. 141а\n"
            "📧 Электрондук почта: info@iuca.kg\n"
            "📱 WhatsApp / Кабыл алуу комиссиясы: +996 503 434 410\n"
            "☎️ Телефон: +996 3138 60263\n"
            "🕒 Иштөө убактысы: Дүйш-Жум, 9:00 - 17:00\n"
            "📸 Instagram: @iucatokmok"
        )
    else:
        about_text = (
            "ℹ️ About \"Ask IUCA\" Bot:\n"
            "I am the virtual assistant for the International University of Central Asia (IUCA) in Tokmok, Kyrgyzstan.\n"
            "I help students and prospective applicants with enrollment, academic programs, tuition fees, scholarships, dormitory, and student life.\n\n"
            "📞 IUCA Contact Info:\n"
            "📍 Address: 141a Komsomolskaya Str., Tokmok, 724915, Chui Region, Kyrgyzstan\n"
            "📧 Email: info@iuca.kg\n"
            "📱 WhatsApp / Admissions: +996 503 434 410\n"
            "☎️ Phone: +996 3138 60263\n"
            "🕒 Working Hours: Mon-Fri, 9:00 AM - 5:00 PM\n"
            "📸 Instagram: @iucatokmok"
        )
        
    await message.answer(about_text)

@router.message(Command("settings"))
async def cmd_settings(message: Message):
    user_id = message.from_user.id
    state = USER_STATES.get(user_id)
    
    if not state or not state.get("language") or not state.get("role"):
        # Reset and restart onboarding
        USER_STATES[user_id] = {
            "language": None,
            "role": None,
            "history": [],
            "message_count": 0,
            "is_onboarding": True
        }
        await message.answer(text=LANG_PROMPT, reply_markup=lang_keyboard)
        return
        
    lang = state["language"]
    role = state["role"]
    
    lang_names = {"ru": "Русский 🇷🇺", "ky": "Кыргызча 🇰🇬", "en": "English 🇬🇧"}
    role_names = {"student": "🎓 Student", "parent": "👨‍👩‍👧 Parent"}
    
    text = (
        f"⚙️ Settings / Настройки / Жөндөөлөр:\n\n"
        f"🌐 Language / Язык / Тил: {lang_names.get(lang, lang)}\n"
        f"👤 Role / Роль / Роль: {role_names.get(role, role)}"
    )
    
    settings_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Change Language", callback_data="change_lang")],
        [InlineKeyboardButton(text="👤 Change Role", callback_data="change_role")]
    ])
    
    await message.answer(text, reply_markup=settings_keyboard)

@router.message(Command("reset"))
async def cmd_reset(message: Message):
    user_id = message.from_user.id
    state = USER_STATES.get(user_id)
    
    if not state or not state.get("language") or not state.get("role"):
        await message.answer(
            "🇷🇺 Пожалуйста, отправьте команду /start для настройки.\n"
            "🇰🇬 Сураныч, жөндөө үчүн /start буйругун жөнөтүңүз.\n"
            "🇬🇧 Please send the /start command to setup the bot."
        )
        return
        
    state["history"] = []
    
    confirm_text = {
        "en": "Conversation history has been reset. You can start a new dialogue now!",
        "ru": "История диалога сброшена. Вы можете начать новый диалог!",
        "ky": "Сүйлөшүү тарыхы тазаланды. Жаңы маек баштасаңыз болот!"
    }.get(state["language"], "Conversation history has been reset.")
    
    await message.answer(confirm_text)

@router.message(Command("admin_feedback"))
async def cmd_admin_feedback(message: Message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        # Ignore or deny access
        await message.answer("❌ You are not authorized to view admin logs.")
        return
        
    if not FEEDBACK_LOGS:
        await message.answer("📝 No feedback entries found.")
        return
        
    recent_feedback = FEEDBACK_LOGS[-30:]
    lines = ["📋 Recent Feedback (Last 30 entries):"]
    for i, entry in enumerate(reversed(recent_feedback), 1):
        username = f"@{entry['username']}" if entry['username'] else "No username"
        line = (
            f"{i}. User ID: {entry['user_id']} ({username})\n"
            f"   Vote: {entry['vote']} | Lang: {entry['language']} | Role: {entry['role']}\n"
            f"   Messages: {entry['message_count']} | Time: {entry['timestamp']}"
        )
        lines.append(line)
        
    await message.answer("\n\n".join(lines))

# Inline Callback Query Handlers

@router.callback_query(F.data.startswith("lang_"))
async def handle_lang_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = callback.data.split("_")[1]
    
    if user_id not in USER_STATES:
        USER_STATES[user_id] = {
            "language": None,
            "role": None,
            "history": [],
            "message_count": 0,
            "is_onboarding": True
        }
        
    USER_STATES[user_id]["language"] = lang
    
    # 3. Show role selection (inline buttons, no prompt text)
    await callback.message.edit_text(text=ROLE_PROMPT, reply_markup=role_keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("role_"))
async def handle_role_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    role = callback.data.split("_")[1]
    
    if user_id not in USER_STATES:
        USER_STATES[user_id] = {
            "language": None,
            "role": None,
            "history": [],
            "message_count": 0,
            "is_onboarding": False
        }
        
    USER_STATES[user_id]["role"] = role
    is_onboarding = USER_STATES[user_id].get("is_onboarding", False)
    
    # Delete keyboard message
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete role selection message: {e}")
        
    await callback.answer()
    
    # If first time setup, generate AI greeting
    if is_onboarding:
        USER_STATES[user_id]["is_onboarding"] = False
        await generate_and_send_greeting(callback.bot, callback.message.chat.id, user_id)

@router.callback_query(F.data == "change_lang")
async def handle_change_lang(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in USER_STATES:
        USER_STATES[user_id] = {
            "language": None,
            "role": None,
            "history": [],
            "message_count": 0,
            "is_onboarding": False
        }
    
    USER_STATES[user_id]["is_onboarding"] = False
    await callback.message.edit_text(text=ROLE_PROMPT, reply_markup=lang_keyboard)
    await callback.answer()

@router.callback_query(F.data == "change_role")
async def handle_change_role(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in USER_STATES:
        USER_STATES[user_id] = {
            "language": None,
            "role": None,
            "history": [],
            "message_count": 0,
            "is_onboarding": False
        }
        
    USER_STATES[user_id]["is_onboarding"] = False
    await callback.message.edit_text(text=ROLE_PROMPT, reply_markup=role_keyboard)
    await callback.answer()

# Feedback System Response Handler

@router.callback_query(F.data.startswith("feedback_"))
async def handle_feedback_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    vote_val = callback.data.split("_")[1]
    vote_emoji = "👍" if vote_val == "yes" else "👎"
    
    state = USER_STATES.get(user_id)
    if state:
        lang = state.get("language")
        role = state.get("role")
        msg_count = state.get("message_count", 0)
    else:
        lang = "Unknown"
        role = "Unknown"
        msg_count = 0
        
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Record to global feedback list
    FEEDBACK_LOGS.append({
        "user_id": user_id,
        "username": callback.from_user.username,
        "vote": vote_emoji,
        "language": lang,
        "role": role,
        "message_count": msg_count,
        "timestamp": timestamp
    })
    
    thank_you = {
        "en": "Thank you for your feedback!",
        "ru": "Спасибо за ваш отзыв!",
        "ky": "Пикириңиз үчүн рахмат!"
    }.get(lang, "Thank you for your feedback!")
    
    await callback.answer(thank_you)
    
    # Edit original message to thank-you message
    try:
        await callback.message.edit_text(text=thank_you, reply_markup=None)
    except Exception as e:
        logger.error(f"Error editing feedback message: {e}")

# General Conversation Handling

@router.message()
async def handle_conversation(message: Message):
    # Ignore non-text messages
    if not message.text:
        return
        
    user_id = message.from_user.id
    state = USER_STATES.get(user_id)
    
    # If language or role missing, ask user to run /start
    if not state or not state.get("language") or not state.get("role"):
        await message.answer(
            "🇷🇺 Пожалуйста, отправьте команду /start для настройки.\n"
            "🇰🇬 Сураныч, жөндөө үчүн /start буйругун жөнөтүңүз.\n"
            "🇬🇧 Please send the /start command to setup the bot."
        )
        return
        
    lang = state["language"]
    role = state["role"]
    history = state["history"]
    
    # 1. Append user message to history
    history.append({"role": "user", "content": message.text})
    
    # 2. Keep last 12 messages (sliding window)
    if len(history) > 12:
        history = history[-12:]
    state["history"] = history
    
    # Dynamic System Prompt Construction
    sys_prompt = build_system_prompt(lang, role)
    
    # Prepare messages payload
    api_messages = [{"role": "system", "content": sys_prompt}]
    for msg in history:
        api_messages.append({"role": msg["role"], "content": msg["content"]})
        
    # 3. Show "typing" action
    async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
        try:
            if not co:
                raise ValueError("Cohere API client is not initialized")
                
            # 4. Call Cohere
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: co.chat(
                    model="command-a-03-2025",
                    messages=api_messages
                )
            )
            
            content = response.message.content
            if isinstance(content, list):
                reply_text = content[0].text
            elif isinstance(content, str):
                reply_text = content
            else:
                reply_text = str(content)
                
        except Exception as e:
            logger.error(f"Error calling Cohere API: {e}")
            reply_text = {
                "en": "Sorry, I am having trouble connecting to my brain. Please try again later.",
                "ru": "Извините, у меня возникли трудности с подключением. Пожалуйста, попробуйте позже.",
                "ky": "Кечиресиз, мага туташууда кыйынчылыктар жаралды. Кийинчерээк кайталап көрүңүз."
            }.get(lang, "Sorry, I am having trouble connecting. Please try again later.")
            
    # 5. Strip all asterisks (*) from response
    reply_text = reply_text.replace("*", "").strip()
    
    # Send reply
    await message.answer(reply_text)
    
    # 6. Append assistant reply to history (cap at 12)
    history.append({"role": "assistant", "content": reply_text})
    if len(history) > 12:
        history = history[-12:]
    state["history"] = history
    
    # 7. Increment message counter
    state["message_count"] += 1
    
    # Feedback Prompt (every 10 messages)
    if state["message_count"] % 10 == 0:
        fb_text = {
            "en": "Is this conversation helpful so far?",
            "ru": "Полезен ли этот диалог на данный момент?",
            "ky": "Бул сүйлөшүү азырынча сизге пайдалуубу?"
        }.get(lang, "Is this conversation helpful so far?")
        
        fb_yes = {"en": "👍 Yes", "ru": "👍 Да", "ky": "👍 Ооба"}.get(lang, "👍 Yes")
        fb_no = {"en": "👎 No", "ru": "👎 Нет", "ky": "👎 Жок"}.get(lang, "👎 No")
        
        fb_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=fb_yes, callback_data="feedback_yes"),
                InlineKeyboardButton(text=fb_no, callback_data="feedback_no")
            ]
        ])
        
        # Tiny delay to send feedback keyboard right after the assistant reply
        await asyncio.sleep(0.5)
        await message.answer(text=fb_text, reply_markup=fb_keyboard)

# Main Startup Sequence

async def main():
    if not TOKEN:
        logger.error("TOKEN environment variable is not set! Exiting.")
        return
        
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    
    # Register routers
    dp.include_router(router)
    
    # Start Polling
    logger.info("Starting Ask IUCA Bot...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
