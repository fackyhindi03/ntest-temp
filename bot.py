#!/usr/bin/env python3
# bot.py

from dotenv import load_dotenv
load_dotenv()

import os
import logging
from functools import wraps
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
)
from telegram.utils.helpers import escape_markdown
from telegram.error import BadRequest
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
)
from requests.exceptions import ReadTimeout

import hianimez_scraper
from hianimez_scraper import (
    search_anime,
    get_episodes_list,
    extract_episode_stream_and_subtitle,
)
from utils import download_and_rename_subtitle

# ――――――――――――――――――――――――――
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN not set")

ANIWATCH_API_BASE = os.getenv("ANIWATCH_API_BASE")
if not ANIWATCH_API_BASE:
    raise RuntimeError("ANIWATCH_API_BASE not set")

# Override the scraper’s base (only used in search & list)
hianimez_scraper.ANIWATCH_API_BASE = ANIWATCH_API_BASE

# Authorized user IDs
AUTHORIZED_USERS = {1423807625, 5476335536, 2096201372, 633599652}

def restricted(func):
    @wraps(func)
    def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        if update.effective_user.id not in AUTHORIZED_USERS:
            return context.bot.send_message(
                update.effective_chat.id,
                "🚫 Access denied. Contact @THe_vK_3."
            )
        return func(update, context, *args, **kwargs)
    return wrapped

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

updater = Updater(TELEGRAM_TOKEN, use_context=True)
dispatcher = updater.dispatcher

# caches
search_cache = {}    # chat_id → [ (title, slug), … ]
episode_cache = {}   # chat_id → [ (num, eid), … ]


@restricted
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        '🌸 <b>Hianime Downloader</b> 🌸\n\n'
        'Use <code>/search &lt;anime name&gt;</code> to begin.',
        parse_mode="HTML"
    )


@restricted
def search_command(update: Update, context: CallbackContext):
    if not context.args:
        return update.message.reply_text("Usage: `/search Naruto`", parse_mode="MarkdownV2")

    chat_id = update.effective_chat.id
    query = " ".join(context.args)
    msg = update.message.reply_text(f"🔍 Searching for *{query}*…", parse_mode="MarkdownV2")

    try:
        results = search_anime(query)
    except Exception:
        logger.exception("Search failed")
        return msg.edit_text("❌ Search failed. Try again.")

    if not results:
        return msg.edit_text(f"No results for *{query}*.", parse_mode="MarkdownV2")

    search_cache[chat_id] = [(t, slug) for t, _, slug in results]
    buttons = [
        [InlineKeyboardButton(title, callback_data=f"anime_idx:{i}")]
        for i, (title, _) in enumerate(search_cache[chat_id])
    ]
    msg.edit_text("Select an anime:", reply_markup=InlineKeyboardMarkup(buttons))


@restricted
def anime_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    try:
        query.answer()
    except BadRequest as e:
        logger.warning("Could not answer callback query: %s", e)
    chat_id = query.message.chat.id

    idx = int(query.data.split(":",1)[1])
    title, slug = search_cache[chat_id][idx]
    context.user_data["anime_title"] = title

    query.edit_message_text(f"🔍 Fetching episodes for *{title}*…", parse_mode="MarkdownV2")
    episodes = get_episodes_list(slug)
    episode_cache[chat_id] = episodes

    buttons = [
        [InlineKeyboardButton(f"Episode {num}", callback_data=f"episode_idx:{i}")]
        for i, (num, _) in enumerate(episodes)
    ]
    query.edit_message_text("Select an episode:", reply_markup=InlineKeyboardMarkup(buttons))


@restricted
def episode_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    try:
        query.answer()
    except BadRequest as e:
        logger.warning("Could not answer callback query: %s", e) 
    chat_id = query.message.chat.id

    idx = int(query.data.split(":",1)[1])
    ep_num, ep_id = episode_cache[chat_id][idx]    
    # ep_id still holds the strange slug from the API
    slug = ep_id            # the entire slug string
    try:
        hls, sub = extract_episode_stream_and_subtitle(slug, ep_num)
    except Exception as e:
        logger.error("Scraper error for %s ep%s: %s", slug, ep_num, e)
        return query.message.reply_text(
            "⚠️ Sorry, I couldn’t fetch that episode. It may not exist or the page structure changed."
        )
    if not hls:
        return query.message.reply_text("❌ Couldn't find a video stream for that episode.")

    # send HLS
    safe = escape_markdown(hls, version=2)
    context.bot.send_message(chat_id=chat_id, text=f"🔗 `{safe}`", parse_mode="MarkdownV2")

    # send subtitle if available
    if sub:
        local_vtt = download_and_rename_subtitle(sub, ep_num)
        with open(local_vtt, "rb") as f:
            context.bot.send_document(chat_id, document=InputFile(f))
    else:
        context.bot.send_message(chat_id, text="⚠️ Subtitle not available.")


dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("search", search_command))
dispatcher.add_handler(CallbackQueryHandler(anime_callback, pattern=r"^anime_idx:"))
dispatcher.add_handler(CallbackQueryHandler(episode_callback, pattern=r"^episode_idx:"))

if __name__ == "__main__":
    updater.start_polling()
    updater.idle()
