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

# ── User Agents ──────────────────────────
ANDROID_UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
WEB_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

def is_youtube(link):
    return any(d in link for d in YOUTUBE_DOMAINS)

def get_ua(link):
    return ANDROID_UA if is_youtube(link) else WEB_UA

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
# 🔑 Login
# ═══════════════════════════════════════
def do_login(page, context):
    msg(
        f"╔══════════════════════╗\n"
        f"║   🔐  *LOGIN REQUIRED*   ║\n"
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
    time.sleep(3)
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

    for i, digit in enumerate(user_context["otp"].strip()[:6], 1):
        try:
            f = page.locator(f"//input[@aria-label='Digit {i}']")
            if f.is_visible():
                f.fill(digit)
                time.sleep(0.2)
        except: pass

    time.sleep(5)
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
            if page.locator("#msisdn").is_visible():
                msg("⚠️ *Session expire ho gayi!*\nLogin karte hain...")
                do_login(page, ctx)
            else:
                msg(
                    f"╔══════════════════════╗\n"
                    f"║  ✅  *LOGIN VALID HAI!*  ║\n"
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
        f"║  📺  *YOUTUBE DETECTED*  ║\n"
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
        f"║  🤖  *JAZZ DRIVE BOT*  ║\n"
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
        f"║   📊  *BOT STATUS*      ║\n"
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
        bot.reply_to(message, f"❌ *Error:*\n```\n{e.output.decode()[:3000]}\n```", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ `{str(e)}`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def handle_msg(message):
    global is_working
    text = message.text.strip() if message.text else ""
    remove_kb = types.ReplyKeyboardRemove()

    if user_context["state"] == "WAITING_FOR_NUMBER":
        user_context["number"] = text
        user_context["state"] = "NUMBER_RECEIVED"
        bot.reply_to(message, "✅ Number receive hua...")
        return

    if user_context["state"] == "WAITING_FOR_OTP":
        user_context["otp"] = text
        user_context["state"] = "OTP_RECEIVED"
        bot.reply_to(message, "✅ OTP receive hua...")
        return

    if user_context["state"] == "WAITING_FOR_QUALITY":
        label = text.replace("🎯","").replace("📱","").replace("💻","").replace("🖥️","").replace("⭐","").strip()
        height = get_height_from_label(label)
        link = user_context["pending_link"]
        user_context["state"] = "IDLE"
        user_context["pending_link"] = None

        msg(
            f"✅ *{label}* quality select!\n"
            f"📋 Queue mein add ho raha hai...",
            reply_markup=remove_kb
        )

        task_queue.put({"link": link, "height": height, "label": label})
        with worker_lock:
            if not is_working:
                is_working = True
                threading.Thread(target=worker_loop, daemon=True).start()
        return

    if text.startswith("http"):
        if is_youtube(text):
            ask_quality(text)
        else:
            task_queue.put({"link": text, "height": None, "label": "Direct"})
            bot.reply_to(message,
                f"✅ *Queue mein add!*\n"
                f"📍 Position: *{task_queue.qsize()}*",
                parse_mode="Markdown")
            with worker_lock:
                if not is_working:
                    is_working = True
                    threading.Thread(target=worker_loop, daemon=True).start()
    else:
        bot.reply_to(message,
            f"ℹ️ Direct link bhejein\n"
            f"ya `/checklogin` try karein",
            parse_mode="Markdown")

# ═══════════════════════════════════════
# 🔄 Worker Loop
# ═══════════════════════════════════════
def worker_loop():
    global is_working
    try:
        while not task_queue.empty():
            item = task_queue.get()
            link  = item["link"]
            height = item["height"]
            label  = item["label"]
            short  = link[:55] + "..." if len(link) > 55 else link
            msg(
                f"╔══════════════════════╗\n"
                f"║   🎬  *PROCESSING...*   ║\n"
                f"╚══════════════════════╝\n\n"
                f"🔗 `{short}`"
            )
            try:
                process_file(link, height, label)
            except Exception as e:
                msg(f"❌ *Error:*\n`{str(e)[:150]}`")
            finally:
                task_queue.task_done()

        msg(
            f"╔══════════════════════╗\n"
            f"║  ✅  *QUEUE COMPLETE!*  ║\n"
            f"╚══════════════════════╝\n\n"
            f"📎 Agla link bhejein\n"
            f"ya rest karo! 😊"
        )
    except Exception as e:
        msg(f"⚠️ Worker crash:\n`{str(e)[:150]}`")
    finally:
        with worker_lock:
            is_working = False

# ═══════════════════════════════════════
# ⬇️ Universal Downloader
# ═══════════════════════════════════════
def file_ok(f, min_mb=2):
    if not os.path.exists(f): return False
    return os.path.getsize(f) / (1024*1024) >= min_mb

def clean(f):
    if os.path.exists(f): os.remove(f)

def get_yt_title(link):
    try:
        ua = get_ua(link)
        result = subprocess.check_output(
            f"yt-dlp --no-warnings --get-title --user-agent '{ua}' '{link}'",
            shell=True, stderr=subprocess.DEVNULL
        ).decode().strip()
        return safe_filename(result) if result else None
    except:
        return None

def process_file(link, height=None, label=""):
    yt = is_youtube(link)
    ua = get_ua(link)  # Android for YT, Desktop for others
    min_size = 5 if yt else 2

    video_title = None
    if yt:
        msg(f"📝 *Video info fetch ho rahi hai...*")
        video_title = get_yt_title(link)
        if video_title:
            display = video_title.replace('_', ' ')
            msg(
                f"🎬 *{display}*\n"
                f"📐 Quality: *{label}*"
            )

    if video_title:
        q_suffix = f"_{label.replace(' ','')}" if label and label != "Best Quality" else "_best"
        OUT = f"{video_title}{q_suffix}.mp4"
    else:
        OUT = "downloaded_file.mp4"

    success = False

    try:
        msg(
            f"┌─────────────────────┐\n"
            f"│  ⬇️  *DOWNLOADING...*  │\n"
            f"└─────────────────────┘"
        )

        # ── Method 1: yt-dlp + correct UA ──
        if not success:
            q_label = label if label else "Best"
            if yt and height:
                q_fmt = (
                    f"bestvideo[height<={height}][vcodec^=avc][ext=mp4]+"
                    f"bestaudio[acodec^=mp4a]/"
                    f"bestvideo[height<={height}][ext=mp4]+bestaudio/"
                    f"bestvideo[height<={height}]+bestaudio/"
                    f"best[height<={height}]/best"
                )
            elif yt:
                q_fmt = (
                    "bestvideo[vcodec^=avc][ext=mp4]+bestaudio[acodec^=mp4a]/"
                    "bestvideo[ext=mp4]+bestaudio/bestvideo+bestaudio/best"
                )
            else:
                q_fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"

            msg(f"🔄 *Method 1/5* — yt-dlp `({q_label})` UA: {'Android' if yt else 'Desktop'}")
            clean(OUT)
            os.system(
                f"yt-dlp --no-warnings --no-playlist "
                f"--socket-timeout 60 --retries 5 "
                f"--fragment-retries 5 "
                f"--concurrent-fragments 4 "
                f"-f '{q_fmt}' "
                f"--merge-output-format mp4 "
                f"--user-agent '{ua}' "
                f"--no-check-certificates "
                f"-o '{OUT}' '{link}'"
            )
            if os.path.exists(OUT):
                sz = os.path.getsize(OUT) / (1024*1024)
                msg(f"📦 yt-dlp result: *{sz:.1f} MB*")
                if file_ok(OUT, min_size): success = True
                else:
                    msg(f"⚠️ Too small ({sz:.1f}MB) — next method...")
                    clean(OUT)

        # ── Method 2: aria2c ──
        if not success and not yt:
            msg("🔄 *Method 2/5* — aria2c")
            clean(OUT)
            os.system(
                f"aria2c -x 16 -s 16 -k 1M "
                f"--timeout=60 --retry-wait=3 --max-tries=3 "
                f"--user-agent='{ua}' --allow-overwrite=true "
                f"-o '{OUT}' '{link}'"
            )
            if os.path.exists(OUT):
                sz = os.path.getsize(OUT) / (1024*1024)
                msg(f"📦 aria2c result: *{sz:.1f} MB*")
                if file_ok(OUT, min_size): success = True
                else: clean(OUT)

        # ── Method 3: wget ──
        if not success and not yt:
            msg("🔄 *Method 3/5* — wget")
            clean(OUT)
            os.system(
                f"wget -q --tries=3 --timeout=60 "
                f"--user-agent='{ua}' --no-check-certificate "
                f"-O '{OUT}' '{link}'"
            )
            if os.path.exists(OUT):
                sz = os.path.getsize(OUT) / (1024*1024)
                msg(f"📦 wget result: *{sz:.1f} MB*")
                if file_ok(OUT, min_size): success = True
                else: clean(OUT)

        # ── Method 4: curl ──
        if not success and not yt:
            msg("🔄 *Method 4/5* — curl")
            clean(OUT)
            os.system(
                f"curl -L --retry 3 --max-time 300 "
                f"-H 'User-Agent: {ua}' -H 'Accept: */*' "
                f"-H 'Referer: {link}' -o '{OUT}' '{link}'"
            )
            if os.path.exists(OUT):
                sz = os.path.getsize(OUT) / (1024*1024)
                msg(f"📦 curl result: *{sz:.1f} MB*")
                if file_ok(OUT, min_size): success = True
                else: clean(OUT)

        # ── Method 5: requests ──
        if not success and not yt:
            msg("🔄 *Method 5/5* — Python requests")
            clean(OUT)
            try:
                hdrs = {'User-Agent': ua, 'Accept': '*/*', 'Referer': link}
                with requests.get(link, headers=hdrs, stream=True,
                                  allow_redirects=True, timeout=60) as r:
                    r.raise_for_status()
                    with open(OUT, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk: f.write(chunk)
                if os.path.exists(OUT):
                    sz = os.path.getsize(OUT) / (1024*1024)
                    msg(f"📦 requests result: *{sz:.1f} MB*")
                    if file_ok(OUT, min_size): success = True
                    else: clean(OUT)
            except Exception as e:
                msg(f"⚠️ Method 5 error: `{str(e)[:100]}`")

        if not success:
            msg(
                f"╔══════════════════════╗\n"
                f"║  ❌  *DOWNLOAD FAILED*  ║\n"
                f"╚══════════════════════╝\n\n"
                f"Sab 5 methods fail ho gaye!\n\n"
                f"*Possible reasons:*\n"
                f"⏰ Link expire ho gaya\n"
                f"🔐 Login/auth chahiye\n"
                f"🚫 Site ne block kiya\n\n"
                f"📎 Fresh link bhejein."
            )
            return

        size_mb = os.path.getsize(OUT) / (1024*1024)
        display = OUT.replace('_', ' ').replace('.mp4', '')
        msg(
            f"╔══════════════════════╗\n"
            f"║  ✅  *DOWNLOAD DONE!*   ║\n"
            f"╚══════════════════════╝\n\n"
            f"🎬 *{display[:40]}*\n"
            f"📦 Size: *{size_mb:.1f} MB*\n\n"
            f"☁️ Jazz Drive pe upload\n"
            f"ho raha hai..."
        )

        jazz_drive_upload(OUT)

    except Exception as e:
        msg(f"❌ *Process Error:*\n`{str(e)[:200]}`")
        raise
    finally:
        clean(OUT)

# ═══════════════════════════════════════
# ☁️ Jazz Drive Upload
# ═══════════════════════════════════════
def jazz_drive_upload(filename):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        ctx = browser.new_context(
            viewport={'width': 1280, 'height': 720},
            storage_state="state.json" if os.path.exists("state.json") else None
        )
        page = ctx.new_page()

        try:
            msg("🌐 *Jazz Drive* khul raha hai...")
            page.goto("https://cloud.jazzdrive.com.pk/", wait_until="networkidle", timeout=90000)
            time.sleep(3)

            if page.locator("#msisdn").is_visible():
                msg("⚠️ *Session expire ho gayi!*\nLogin karo pehle...")
                ok = do_login(page, ctx)
                if not ok:
                    msg("❌ Login fail — file skip kar raha hoon.")
                    return
                page.goto("https://cloud.jazzdrive.com.pk/", wait_until="networkidle", timeout=90000)
                time.sleep(3)

            ctx.storage_state(path="state.json")

            msg(
                f"┌─────────────────────┐\n"
                f"│  📤  *UPLOADING...*    │\n"
                f"└─────────────────────┘\n\n"
                f"File select ho rahi hai..."
            )
            time.sleep(2)

            try:
                page.evaluate("""
                    document.querySelectorAll('header button').forEach(b => {
                        if(b.innerHTML.includes('svg') || b.innerHTML.includes('upload')) b.click();
                    });
                """)
                time.sleep(2)
            except: pass

            try:
                dialog = page.locator("div[role='dialog']")
                if dialog.is_visible():
                    with page.expect_file_chooser() as fc:
                        dialog.locator("text=/upload/i").first.click()
                    fc.value.set_files(os.path.abspath(filename))
                else:
                    page.set_input_files("input[type='file']", os.path.abspath(filename)
