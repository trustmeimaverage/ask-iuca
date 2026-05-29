import os
import re
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
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")

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

# ── Localized UI strings ───────────────────────────────────────────────────────
# Every user-visible bot message is defined here, keyed by language code.
# "xx" is the pre-language-selection fallback (shown tri-lingually before the
# user has made a choice, e.g. the /start language-picker prompt).

UI = {
    # Shown before language is known — always tri-lingual
    "lang_prompt": "🌍 Выберите язык | Тилди тандаңыз | Choose your language",

    # Everything below is keyed by lang code
    "role_prompt": {
        "ru": "🎭 Пожайлуйста выберите вашу роль",
        "ky": "🎭 Суранам ролуңузду тандаңыз",
        "en": "🎭 Please choose your role",
    },
    "role_student": {
        "ru": "🎓 Студент",
        "ky": "🎓 Студент",
        "en": "🎓 Student",
    },
    "role_parent": {
        "ru": "👨‍👩‍👧 Родитель",
        "ky": "👨‍👩‍👧 Ата-эне",
        "en": "👨‍👩‍👧 Parent",
    },
    "no_setup": {
        "ru": "Пожалуйста, отправьте команду /start для настройки.",
        "ky": "Сураныч, жөндөө үчүн /start буйругун жөнөтүңүз.",
        "en": "Please send the /start command to set up the bot.",
    },
    "help": {
        "ru": (
            "🤖 Доступные команды:\n\n"
            "/start — Полный сброс настроек и перезапуск\n"
            "/help — Список доступных команд\n"
            "/about — О боте и контакты МУЦА\n"
            "/settings — Текущие настройки с кнопками изменения\n"
            "/reset — Очистить историю диалога (язык и роль сохранятся)"
        ),
        "ky": (
            "🤖 Жеткиликтүү буйруктар:\n\n"
            "/start — Толук тазалоо жана баштапкы жөндөөлөрдү баштоо\n"
            "/help — Буйруктардын тизмесин көрсөтүү\n"
            "/about — Бот жөнүндө маалымат жана БАЭУ байланыштары\n"
            "/settings — Учурдагы жөндөөлөрдү көрсөтүү жана өзгөртүү\n"
            "/reset — Сүйлөшүү тарыхын тазалоо (тил жана роль сакталат)"
        ),
        "en": (
            "🤖 Available commands:\n\n"
            "/start — Full reset of history & settings, restart onboarding\n"
            "/help — Show this list of commands\n"
            "/about — Bot description + IUCA contact info\n"
            "/settings — Show current language & role with change buttons\n"
            "/reset — Clear conversation history only — keep language & role"
        ),
    },
    "about": {
        "ru": (
            "ℹ️ О боте \"Ask IUCA\":\n"
            "Я — виртуальный помощник Международного Университета Центральной Азии (МУЦА) в г. Токмок.\n"
            "Помогаю студентам и абитуриентам с вопросами о поступлении, учебных программах, стоимости обучения, стипендиях и жизни на кампусе.\n\n"
            "📞 Контакты МУЦА:\n"
            "📍 Адрес: Кыргызстан, г. Токмок, ул. Комсомольская 141а\n"
            "📧 Email: info@iuca.kg\n"
            "📱 WhatsApp / Приемная комиссия: +996 503 434 410\n"
            "☎️ Телефон: +996 3138 60263\n"
            "🕒 Часы работы: Пн–Пт, 9:00–17:00\n"
            "📸 Instagram: @iucatokmok"
        ),
        "ky": (
            "ℹ️ \"Ask IUCA\" боту жөнүндө:\n"
            "Мен Токмок шаарындагы Борбордук Азия Эл аралык Университетинин (БАЭУ) виртуалдык жардамчысымын.\n"
            "Студенттерге жана абитуриенттерге окууга кирүү, окуу программалары, келишим баалары, стипендиялар жана кампустагы жашоо боюнча маалымат алууга жардам берем.\n\n"
            "📞 БАЭУ байланыштары:\n"
            "📍 Дареги: Кыргызстан, Токмок ш., Комсомольская көч. 141а\n"
            "📧 Электрондук почта: info@iuca.kg\n"
            "📱 WhatsApp / Кабыл алуу комиссиясы: +996 503 434 410\n"
            "☎️ Телефон: +996 3138 60263\n"
            "🕒 Иштөө убактысы: Дүйш–Жум, 9:00–17:00\n"
            "📸 Instagram: @iucatokmok"
        ),
        "en": (
            "ℹ️ About \"Ask IUCA\" Bot:\n"
            "I am the virtual assistant for the International University of Central Asia (IUCA) in Tokmok, Kyrgyzstan.\n"
            "I help students and prospective applicants with enrollment, academic programs, tuition fees, scholarships, dormitory, and student life.\n\n"
            "📞 IUCA Contact Info:\n"
            "📍 Address: 141a Komsomolskaya Str., Tokmok, 724915, Chui Region, Kyrgyzstan\n"
            "📧 Email: info@iuca.kg\n"
            "📱 WhatsApp / Admissions: +996 503 434 410\n"
            "☎️ Phone: +996 3138 60263\n"
            "🕒 Working Hours: Mon–Fri, 9:00 AM – 5:00 PM\n"
            "📸 Instagram: @iucatokmok"
        ),
    },
    "settings_header": {
        "ru": "⚙️ Настройки",
        "ky": "⚙️ Жөндөөлөр",
        "en": "⚙️ Settings",
    },
    "settings_lang_label": {
        "ru": "🌐 Язык",
        "ky": "🌐 Тил",
        "en": "🌐 Language",
    },
    "settings_role_label": {
        "ru": "🎭 Роль",
        "ky": "🎭 Роль",
        "en": "🎭 Role",
    },
    "settings_change_lang_btn": {
        "ru": "🌐 Изменить язык",
        "ky": "🌐 Тилди өзгөртүү",
        "en": "🌐 Change Language",
    },
    "settings_change_role_btn": {
        "ru": "🎭 Изменить роль",
        "ky": "🎭 Ролду өзгөртүү",
        "en": "🎭 Change Role",
    },
    "lang_display": {
        "ru": {"ru": "Русский 🇷🇺", "ky": "Кыргызча 🇰🇬", "en": "English 🇬🇧"},
        "ky": {"ru": "Орусча 🇷🇺", "ky": "Кыргызча 🇰🇬", "en": "Англисче 🇬🇧"},
        "en": {"ru": "Russian 🇷🇺", "ky": "Kyrgyz 🇰🇬", "en": "English 🇬🇧"},
    },
    "role_display": {
        "ru": {"student": "🎓 Студент", "parent": "👨‍👩‍👧 Родитель"},
        "ky": {"student": "🎓 Студент", "parent": "👨‍👩‍👧 Ата-эне"},
        "en": {"student": "🎓 Student", "parent": "👨‍👩‍👧 Parent"},
    },
    "reset_confirm": {
        "ru": "История диалога сброшена. Можете начать новый диалог!",
        "ky": "Сүйлөшүү тарыхы тазаланды. Жаңы маек баштасаңыз болот!",
        "en": "Conversation history has been reset. You can start a new dialogue now!",
    },
    "greeting_fallback": {
        "ru": "Привет! Я Ask IUCA — специальный помощник для МУЦА. Чем могу помочь?",
        "ky": "Салам! Мен Ask IUCA — БАЭУ үчүн атайын жасалган жардамчымын. Кантип жардам бере алам?",
        "en": "Hello! I am Ask IUCA, a special assistant made just for IUCA. How can I help you today?",
    },
    "error_reply": {
        "ru": "Извините, у меня возникли трудности с подключением. Пожалуйста, попробуйте позже.",
        "ky": "Кечиресиз, мага туташууда кыйынчылыктар жаралды. Кийинчерээк кайталап көрүңүз.",
        "en": "Sorry, I am having trouble connecting to my brain. Please try again later.",
    },
    "feedback_prompt": {
        "ru": "Полезен ли этот диалог на данный момент?",
        "ky": "Бул сүйлөшүү азырынча сизге пайдалуубу?",
        "en": "Is this conversation helpful so far?",
    },
    "feedback_yes": {
        "ru": "👍 Да",
        "ky": "👍 Ооба",
        "en": "👍 Yes",
    },
    "feedback_no": {
        "ru": "👎 Нет",
        "ky": "👎 Жок",
        "en": "👎 No",
    },
    "feedback_thanks": {
        "ru": "Спасибо за ваш отзыв!",
        "ky": "Пикириңиз үчүн рахмат!",
        "en": "Thank you for your feedback!",
    },
    # Shown when model replies in the wrong language (post-processing catch)
    "wrong_lang_fallback": {
        "ru": "Извините, что-то пошло не так с моим ответом. Пожалуйста, повторите вопрос.",
        "ky": "Кечиресиз, жообумда бир нерсе туура эмес болду. Суроонузду кайталап көрүңүз.",
        "en": "Sorry, something went wrong with my response. Please try asking again.",
    },
}

def t(key: str, lang: str, fallback_lang: str = "en") -> str:
    """Retrieve a localized string. Falls back to fallback_lang if lang is missing."""
    val = UI.get(key)
    if val is None:
        return key
    if isinstance(val, str):
        return val
    return val.get(lang) or val.get(fallback_lang, key)


# ── Language and Role specific system prompts (6 variants) ────────────────────
# Each instruction ends with an emphatic language-lock rule (Fix 2 — part A).
# The rule is placed last so it sits closest to the model's output, maximising
# recency bias and making it harder for the model to drift.

LANG_ROLE_INSTRUCTIONS = {
    ("ru", "student"): (
        "You must respond EXCLUSIVELY in Russian. "
        "Tone: Informal (ты), conversational, short & direct.\n"
        "Never use Markdown formatting, asterisks (*), or any special text styling.\n"
        "LANGUAGE LOCK — CRITICAL: Every single character of every reply must be Russian. "
        "Do NOT use Arabic, English, Kyrgyz, or any other language or script. "
        "If you are unsure of a word, rephrase in Russian. There are NO exceptions."
    ),
    ("ru", "parent"): (
        "You must respond EXCLUSIVELY in Russian. "
        "Tone: Formal (вы), literary, thorough & precise.\n"
        "Never use Markdown formatting, asterisks (*), or any special text styling.\n"
        "LANGUAGE LOCK — CRITICAL: Every single character of every reply must be Russian. "
        "Do NOT use Arabic, English, Kyrgyz, or any other language or script. "
        "If you are unsure of a word, rephrase in Russian. There are NO exceptions."
    ),
    ("ky", "student"): (
        "You must respond EXCLUSIVELY in Kyrgyz. "
        "Tone: Friendly, simple Kyrgyz, short & direct.\n"
        "Never use Markdown formatting, asterisks (*), or any special text styling.\n"
        "LANGUAGE LOCK — CRITICAL: Every single character of every reply must be Kyrgyz. "
        "Do NOT use Arabic, Russian, English, or any other language or script. "
        "If you are unsure of a word, rephrase in Kyrgyz. There are NO exceptions."
    ),
    ("ky", "parent"): (
        "You must respond EXCLUSIVELY in Kyrgyz. "
        "Tone: Formal, literary Kyrgyz, respectful & precise.\n"
        "Never use Markdown formatting, asterisks (*), or any special text styling.\n"
        "LANGUAGE LOCK — CRITICAL: Every single character of every reply must be Kyrgyz. "
        "Do NOT use Arabic, Russian, English, or any other language or script. "
        "If you are unsure of a word, rephrase in Kyrgyz. There are NO exceptions."
    ),
    ("en", "student"): (
        "You must respond EXCLUSIVELY in English. "
        "Tone: Casual & friendly, concise & direct.\n"
        "Never use Markdown formatting, asterisks (*), or any special text styling.\n"
        "LANGUAGE LOCK — CRITICAL: Every single character of every reply must be English. "
        "Do NOT use Arabic, Russian, Kyrgyz, or any other language or script. "
        "If you are unsure of a word, rephrase in English. There are NO exceptions."
    ),
    ("en", "parent"): (
        "You must respond EXCLUSIVELY in English. "
        "Tone: Formal, respectful & thorough.\n"
        "Never use Markdown formatting, asterisks (*), or any special text styling.\n"
        "LANGUAGE LOCK — CRITICAL: Every single character of every reply must be English. "
        "Do NOT use Arabic, Russian, Kyrgyz, or any other language or script. "
        "If you are unsure of a word, rephrase in English. There are NO exceptions."
    ),
}

# ── Fix 2 (part B): Arabic script detector ────────────────────────────────────
# Unicode range U+0600–U+06FF covers the core Arabic block.
# U+0750–U+077F is Arabic Supplement; U+FB50–U+FDFF is Arabic Presentation Forms-A.
_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF]")

def contains_arabic(text: str) -> bool:
    return bool(_ARABIC_RE.search(text))


# ── Keyboards ──────────────────────────────────────────────────────────────────

# Language keyboard is language-agnostic (always shows all three options)
lang_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🇷🇺 Русский",   callback_data="lang_ru")],
    [InlineKeyboardButton(text="🇰🇬 Кыргызча", callback_data="lang_ky")],
    [InlineKeyboardButton(text="🇬🇧 English",   callback_data="lang_en")],
])

def build_role_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Build a role-selection keyboard with buttons localized to `lang`."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("role_student", lang), callback_data="role_student")],
        [InlineKeyboardButton(text=t("role_parent",  lang), callback_data="role_parent")],
    ])


# ── System prompt builder ──────────────────────────────────────────────────────

def build_system_prompt(lang: str, role: str) -> str:
    instruction = LANG_ROLE_INSTRUCTIONS.get((lang, role), "")
    # Order: base rules → knowledge → language-lock instruction (last = highest recency)
    return f"{PROMPT_BASE}\n\n{KNOWLEDGE_BASE}\n\n{instruction}"


# ── Greeting helper ────────────────────────────────────────────────────────────

async def generate_and_send_greeting(bot: Bot, chat_id: int, user_id: int):
    state = USER_STATES[user_id]
    lang  = state["language"]
    role  = state["role"]

    sys_prompt = build_system_prompt(lang, role)

    greeting_prompt = {
        "en": "Hello! Introduce yourself to me in the language and tone specified in your instructions. Keep it very short.",
        "ru": "Привет! Представься мне на русском языке в соответствии со своими инструкциями по тону общения. Отвечай очень кратко.",
        "ky": "Салам! Багыттооңорго ылайык кыргыз тилинде мага өзүңдү тааныштыр. Кыска жооп бер.",
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
                        {"role": "user",   "content": greeting_prompt},
                    ]
                )
            )

            content = response.message.content
            if isinstance(content, list):
                reply_text = content[0].text
            elif isinstance(content, str):
                reply_text = content
            else:
                reply_text = str(content)

            reply_text = reply_text.replace("*", "").strip()

            # Arabic-script guard
            if contains_arabic(reply_text):
                logger.warning(f"Arabic script detected in greeting for user {user_id}. Falling back.")
                reply_text = t("greeting_fallback", lang)

        except Exception as e:
            logger.error(f"Error calling Cohere for greeting: {e}")
            reply_text = t("greeting_fallback", lang)

    await bot.send_message(chat_id=chat_id, text=reply_text)
    state["history"] = [{"role": "assistant", "content": reply_text}]


# ── Router ─────────────────────────────────────────────────────────────────────
router = Router()


# ── Command handlers ───────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    USER_STATES[user_id] = {
        "language": None,
        "role": None,
        "history": [],
        "message_count": 0,
        "is_onboarding": True,
    }
    await message.answer(text=UI["lang_prompt"], reply_markup=lang_keyboard)


@router.message(Command("help"))
async def cmd_help(message: Message):
    user_id = message.from_user.id
    state = USER_STATES.get(user_id)
    lang = state["language"] if state else None
    await message.answer(t("help", lang or "en"))


@router.message(Command("about"))
async def cmd_about(message: Message):
    user_id = message.from_user.id
    state = USER_STATES.get(user_id)
    lang = state["language"] if state else None
    await message.answer(t("about", lang or "en"))


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    user_id = message.from_user.id
    state = USER_STATES.get(user_id)

    if not state or not state.get("language") or not state.get("role"):
        USER_STATES[user_id] = {
            "language": None,
            "role": None,
            "history": [],
            "message_count": 0,
            "is_onboarding": True,
        }
        await message.answer(text=UI["lang_prompt"], reply_markup=lang_keyboard)
        return

    lang = state["language"]
    role = state["role"]

    lang_display = UI["lang_display"].get(lang, {}).get(lang, lang)
    role_display = UI["role_display"].get(lang, {}).get(role, role)

    text = (
        f"{t('settings_header', lang)}\n\n"
        f"{t('settings_lang_label', lang)}: {lang_display}\n"
        f"{t('settings_role_label', lang)}: {role_display}"
    )

    settings_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("settings_change_lang_btn", lang), callback_data="change_lang")],
        [InlineKeyboardButton(text=t("settings_change_role_btn", lang), callback_data="change_role")],
    ])

    await message.answer(text, reply_markup=settings_keyboard)


@router.message(Command("reset"))
async def cmd_reset(message: Message):
    user_id = message.from_user.id
    state = USER_STATES.get(user_id)

    if not state or not state.get("language") or not state.get("role"):
        lang = state["language"] if state else None
        await message.answer(t("no_setup", lang or "en"))
        return

    state["history"] = []
    await message.answer(t("reset_confirm", state["language"]))


@router.message(Command("admin_feedback"))
async def cmd_admin_feedback(message: Message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.answer("❌ You are not authorized to view admin logs.")
        return

    if not FEEDBACK_LOGS:
        await message.answer("📝 No feedback entries found.")
        return

    recent_feedback = FEEDBACK_LOGS[-30:]
    lines = ["📋 Recent Feedback (Last 30 entries):"]
    for i, entry in enumerate(reversed(recent_feedback), 1):
        username = f"@{entry['username']}" if entry["username"] else "No username"
        line = (
            f"{i}. User ID: {entry['user_id']} ({username})\n"
            f"   Vote: {entry['vote']} | Lang: {entry['language']} | Role: {entry['role']}\n"
            f"   Messages: {entry['message_count']} | Time: {entry['timestamp']}"
        )
        lines.append(line)

    await message.answer("\n\n".join(lines))


# ── Inline callback handlers ───────────────────────────────────────────────────

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
            "is_onboarding": True,
        }

    USER_STATES[user_id]["language"] = lang

    # Role prompt and buttons are now in the chosen language
    await callback.message.edit_text(
        text=t("role_prompt", lang),
        reply_markup=build_role_keyboard(lang),
    )
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
            "is_onboarding": False,
        }

    USER_STATES[user_id]["role"] = role
    is_onboarding = USER_STATES[user_id].get("is_onboarding", False)

    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete role selection message: {e}")

    await callback.answer()

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
            "is_onboarding": False,
        }

    USER_STATES[user_id]["is_onboarding"] = False
    # Language picker is always tri-lingual
    await callback.message.edit_text(text=UI["lang_prompt"], reply_markup=lang_keyboard)
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
            "is_onboarding": False,
        }

    USER_STATES[user_id]["is_onboarding"] = False
    lang = USER_STATES[user_id].get("language") or "en"
    await callback.message.edit_text(
        text=t("role_prompt", lang),
        reply_markup=build_role_keyboard(lang),
    )
    await callback.answer()


# ── Feedback callback ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("feedback_"))
async def handle_feedback_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    vote_val = callback.data.split("_")[1]
    vote_emoji = "👍" if vote_val == "yes" else "👎"

    state = USER_STATES.get(user_id)
    if state:
        lang      = state.get("language", "en")
        role      = state.get("role", "Unknown")
        msg_count = state.get("message_count", 0)
    else:
        lang      = "en"
        role      = "Unknown"
        msg_count = 0

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    FEEDBACK_LOGS.append({
        "user_id":       user_id,
        "username":      callback.from_user.username,
        "vote":          vote_emoji,
        "language":      lang,
        "role":          role,
        "message_count": msg_count,
        "timestamp":     timestamp,
    })

    thank_you = t("feedback_thanks", lang)
    await callback.answer(thank_you)

    try:
        await callback.message.edit_text(text=thank_you, reply_markup=None)
    except Exception as e:
        logger.error(f"Error editing feedback message: {e}")


# ── General conversation handler ───────────────────────────────────────────────

@router.message()
async def handle_conversation(message: Message):
    if not message.text:
        return

    user_id = message.from_user.id
    state   = USER_STATES.get(user_id)

    if not state or not state.get("language") or not state.get("role"):
        lang = state["language"] if state else None
        await message.answer(t("no_setup", lang or "en"))
        return

    lang    = state["language"]
    role    = state["role"]
    history = state["history"]

    history.append({"role": "user", "content": message.text})
    if len(history) > 12:
        history = history[-12:]
    state["history"] = history

    sys_prompt   = build_system_prompt(lang, role)
    api_messages = [{"role": "system", "content": sys_prompt}]
    for msg in history:
        api_messages.append({"role": msg["role"], "content": msg["content"]})

    async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
        try:
            if not co:
                raise ValueError("Cohere API client is not initialized")

            loop     = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: co.chat(
                    model="command-a-03-2025",
                    messages=api_messages,
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
            reply_text = t("error_reply", lang)

    reply_text = reply_text.replace("*", "").strip()

    # Arabic-script guard (Fix 2 — part B)
    if contains_arabic(reply_text):
        logger.warning(f"Arabic script detected in reply for user {user_id} (lang={lang}). Sending fallback.")
        reply_text = t("wrong_lang_fallback", lang)

    await message.answer(reply_text)

    history.append({"role": "assistant", "content": reply_text})
    if len(history) > 12:
        history = history[-12:]
    state["history"] = history

    state["message_count"] += 1

    if state["message_count"] % 10 == 0:
        fb_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=t("feedback_yes", lang), callback_data="feedback_yes"),
            InlineKeyboardButton(text=t("feedback_no",  lang), callback_data="feedback_no"),
        ]])
        await asyncio.sleep(0.5)
        await message.answer(text=t("feedback_prompt", lang), reply_markup=fb_keyboard)


# ── Main ───────────────────────────────────────────────────────────────────────

async def main():
    if not TOKEN:
        logger.error("TOKEN environment variable is not set! Exiting.")
        return

    bot = Bot(token=TOKEN)
    dp  = Dispatcher()
    dp.include_router(router)

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
