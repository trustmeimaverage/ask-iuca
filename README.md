# Ask IUCA

A Telegram bot serving as an AI assistant for the [International University of Central Asia (IUCA)](https://iuca.kg), located in Tokmok, Kyrgyzstan. It answers questions about enrollment, academic programs, tuition, scholarships, campus life, and general university information.

---

## Stack

- **Python 3.13** managed via [`uv`](https://github.com/astral-sh/uv)
- **aiogram 3.x** — Telegram bot framework
- **Google Gemini API** — AI backend
- **python-dotenv** — environment config

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/trustmeimaverage/ask-iuca.git
cd ask-iuca
```

### 2. Configure environment variables

Copy the example file and fill in your credentials:

```bash
cp .env.example .env
```

`ADMIN_IDS` is a comma-separated list of Telegram user IDs that have access to `/admin_feedback`. It can be left empty if you don't need admin access.

### 3. Install dependencies and run

The project uses `uv` for dependency and Python version management:

```bash
uv run --python 3.13 --with-requirements requirements.txt bot.py
```

---

## Architecture

All state is held in memory — there is no database. This means state is lost on restart.

Each user has an entry in `USER_STATES` containing their chosen language, role, conversation history, and message count. Feedback entries are collected in `FEEDBACK_LOGS`.

**System prompt** is assembled on every request from three parts in this order:

```
prompt-base  +  knowledge-base  +  lang×role instruction
```

The lang×role instruction is placed last to exploit recency bias in the model, making language-lock rules harder to ignore.

**Conversation history** is capped at 12 messages per user (rolling window).

**Feedback** is prompted every 10 messages via inline Yes/No buttons and stored in memory, viewable by admins via `/admin_feedback`.

---

## Commands

| Command | Description |
|---|---|
| `/start` | Full reset of history and settings, restarts onboarding |
| `/help` | List all available commands |
| `/about` | Bot description and IUCA contact info |
| `/settings` | Show current language and role with change buttons |
| `/reset` | Clear conversation history, keep language and role |
| `/admin_feedback` | Admin only — show last 30 feedback entries |

---

## Supported Languages and Roles

Users choose both at the start of every session via inline keyboards.

**Languages:** Russian, Kyrgyz, English

**Roles:** Student, Parent

Each combination has its own tone and formality level (6 variants total). The bot's name, Ask IUCA, is never translated regardless of the chosen language.

---

## Safeguards

**Language enforcement** — two layers:

- The system prompt for every lang×role variant ends with an explicit language-lock instruction naming every forbidden script.
- Post-processing: Arabic Unicode blocks (U+0600–06FF, U+0750–077F, U+FB50–FDFF) are detected after every model response. If found, the reply is dropped and a localized fallback is sent instead.

**Formatting cleanup** — asterisks (`*`) and em dashes (`—`) are stripped from every model response before it reaches the user.

---

## Knowledge Base and Prompt

`knowledge-base` and `prompt-base` are plain text files loaded once at startup. To update the bot's knowledge or behavior, edit these files and restart the process — no code changes needed.

`tokenizer.py` can be used to check how many tokens the current `knowledge-base` consumes.
