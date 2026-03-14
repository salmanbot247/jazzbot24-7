import os
import re
import time
import threading
import queue
import subprocess
import requests
import telebot
from telebot import types
from playwright.sync_api import sync_playwright

# ═══════════════════════════════════════
# 🔑 Apni Details
# ═══════════════════════════════════════
TOKEN = "8485872476:AAE-mNl9roDNnwDQV16M2WREkf479kKCOzs"
CHAT_ID = 7144917062
bot = telebot.TeleBot(TOKEN)

# 🔄 Queue + State
task_queue = queue.Queue()
is_working = False
worker_lock = threading.Lock()
user_context = {
    "state": "IDLE",
    "number": None,
    "otp": None,
    "pending_link": None,
}

BROWSER_ARGS = [
    "--disable-gpu", "--no-sandbox",
    "--disable-dev-shm-usage", "--single-process"
]

YOUTUBE_DOMAINS = ["youtube.com", "youtu.be", "youtube-nocookie.com"]

def is_youtube(link):
    return any(d in link for d in YOUTUBE_DOMAINS)

def safe_filename(title):
    title = re.sub(r'[\\/*?:"<>|]', '', title)
    title = title.strip().replace(' ', '_')
    return title[:80]

def msg(text, **kwargs):
    bot.send_message(CHAT_ID, text, parse_mode="Markdown", **kwargs)

def divider():
    return "─────────────────────"

# ═══════════════════════════════════════
# 📸 Screenshot
# ═══════════════════════════════════════
def take_screenshot(page, caption="📸"):
    try:
        page.screenshot(path="s.png")
        with open("s.png", 'rb') as f:
            bot.send_photo(CHAT_ID, f, caption=caption)
        os.remove("s.png")
    except:
        pass

# ═══════════════════════════════════════
# 🔑 Login (OTP FIXED)
# ═══════════════════════════════════════
def do_login(page, context):
    msg(
        f"╔══════════════════════╗\n"
        f"║   🔐  *LOGIN REQUIRED* ║\n"
        f"╚══════════════════════╝\n\n"
        f"📱 Apna Jazz number bhejein\n"
        f"Format: `03XXXXXXXXX`"
    )
    user_context["state"] = "WAITING_FOR_NUMBER"

    for _ in range(300):
        if user_context["state"] == "NUMBER_RECEIVED": break
        time.sleep(1)
    else:
        msg("⏰ *Timeout!* Number nahi aaya. Task cancel.")
        return False

    page.locator("#msisdn").fill(user_context["number"])
    time.sleep(1)
    page.locator("#signinbtn").first.click()
    time.sleep(4)
    take_screenshot(page, "📱 Number submit kiya")

    msg(
        f"✅ Number accept hua!\n\n"
        f"🔢 *OTP bhejein* jo aapke\n"
        f"Jazz number pe aaya hai:"
    )
    user_context["state"] = "WAITING_FOR_OTP"

    for _ in range(300):
        if user_context["state"] == "OTP_RECEIVED": break
        time.sleep(1)
    else:
        msg("⏰ *Timeout!* OTP nahi aaya. Task cancel.")
        return False

    otp_str = user_context["otp"].strip()[:4]
    
    # 🛠️ THE OTP FIX (JS Injection)
    try:
        page.fill('#otp', otp_str, timeout=3000)
    except:
        try:
            page.evaluate(f'document.getElementById("otp").value = "{otp_str}"')
        except:
            for digit in otp_str:
                page.keyboard.press(digit)
                time.sleep(0.1)

    time.sleep(1)
    
    try:
        page.locator('#signinbtn').click(timeout=5000)
    except:
        page.click('button:has-text("Login")')

    time.sleep(8)
    take_screenshot(page, "🔢 OTP submit kiya")
    context.storage_state(path="state.json")
    msg(
        f"┌─────────────────────┐\n"
        f"│  ✅  *LOGIN SUCCESSFUL* │\n"
        f"└─────────────────────┘\n\n"
        f"🍪 Session save ho gayi!\n"
        f"Aab link bhejein. 🚀"
    )
    user_context["state"] = "IDLE"
    return True

# ═══════════════════════════════════════
# 🔍 Login Check
# ═══════════════════════════════════════
def check_login_status():
    msg(
        f"🔍 *Jazz Drive* login check\n"
        f"ho raha hai, please wait..."
    )
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        ctx = browser.new_context(
            viewport={'width': 1280, 'height': 720},
            storage_state="state.json" if os.path.exists("state.json") else None
        )
        page = ctx.new_page()
        try:
            page.goto("https://cloud.jazzdrive.com.pk/", wait_until="networkidle", timeout=90000)
            time.sleep(3)
            if page.locator("#msisdn").is_visible() or page.locator('input[type="tel"]').is_visible():
                msg("⚠️ *Session expire ho gayi!*\nLogin karte hain...")
                do_login(page, ctx)
            else:
                msg(
                    f"╔══════════════════════╗\n"
                    f"║  ✅  *LOGIN VALID HAI!* ║\n"
                    f"╚══════════════════════╝\n\n"
                    f"🚀 Link bhejein — ready hoon!"
                )
        except Exception as e:
            msg(f"❌ Login check error:\n`{str(e)[:150]}`")
        finally:
            browser.close()

# ═══════════════════════════════════════
# 📺 YouTube Quality Keyboard
# ═══════════════════════════════════════
def ask_quality(link):
    user_context["pending_link"] = link
    user_context["state"] = "WAITING_FOR_QUALITY"

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.row("🎯 360p", "📱 480p")
    markup.row("💻 720p", "🖥️ 1080p")
    markup.row("⭐ Best Quality")

    msg(
        f"╔══════════════════════╗\n"
        f"║  📺  *YOUTUBE DETECTED* ║\n"
        f"╚══════════════════════╝\n\n"
        f"🎬 Kaunsi quality mein\n"
        f"download karein?",
        reply_markup=markup
    )

def get_height_from_label(label):
    if "360" in label: return "360"
    if "480" in label: return "480"
    if "720" in label: return "720"
    if "1080" in label: return "1080"
    return None

# ═══════════════════════════════════════
# 🤖 Bot Commands
# ═══════════════════════════════════════
@bot.message_handler(commands=['start'])
def welcome(message):
    msg(
        f"╔════════════════════════╗\n"
        f"║  🤖  *JAZZ DRIVE BOT* ║\n"
        f"╚════════════════════════╝\n\n"
        f"*Kya kar sakta hoon:*\n\n"
        f"📎 Direct link → Jazz Drive upload\n"
        f"📺 YouTube link → Quality select\n"
        f"📋 Queue system — ek ke baad ek\n\n"
        f"{divider()}\n"
        f"*Commands:*\n"
        f"🔍 /checklogin — Login status\n"
        f"📊 /status — Queue status\n"
        f"💻 /cmd — Server command",
        reply_markup=types.ReplyKeyboardRemove()
    )

@bot.message_handler(commands=['checklogin'])
def cmd_checklogin(message):
    threading.Thread(target=check_login_status, daemon=True).start()

@bot.message_handler(commands=['status'])
def cmd_status(message):
    status_icon = "🟢" if is_working else "🔴"
    status_text = "Kaam chal raha hai" if is_working else "Khali (IDLE)"
    cookie = "✅ Active" if os.path.exists("state.json") else "❌ Nahi hai"
    msg(
        f"╔══════════════════════╗\n"
        f"║   📊  *BOT STATUS* ║\n"
        f"╚══════════════════════╝\n\n"
        f"{status_icon} *State:* {status_text}\n"
        f"📋 *Queue:* {task_queue.qsize()} files pending\n"
        f"🍪 *Session:* {cookie}"
    )

@bot.message_handler(commands=['cmd'])
def cmd_shell(message):
    try:
        cmd = message.text.replace("/cmd ", "", 1).strip()
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode()
        out = out[:4000] or "✅ Done (no output)"
        bot.reply_to(message, f"💻 *Output:*\n```\n{out}\n```", parse_mode="Markdown")
    except subprocess.CalledProcessError as e:
        bot.reply_to(message, f"❌ *Error:*\n
http://googleusercontent.com/immersive_entry_chip/0
