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
    """Title se special chars hataao"""
    title = re.sub(r'[\\/*?:"<>|]', '', title)
    title = title.strip().replace(' ', '_')
    return title[:80]  # max 80 chars

# ═══════════════════════════════════════
# 📸 Screenshot
# ═══════════════════════════════════════
def take_screenshot(page, caption="Screenshot"):
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
    bot.send_message(CHAT_ID,
        "🔑 *Login Zaruri Hai!*\nJazz number bhejein (03xxxxxxxxx):",
        parse_mode="Markdown")
    user_context["state"] = "WAITING_FOR_NUMBER"

    for _ in range(300):
        if user_context["state"] == "NUMBER_RECEIVED":
            break
        time.sleep(1)
    else:
        bot.send_message(CHAT_ID, "⏰ Timeout! Number nahi aaya.")
        return False

    page.locator("#msisdn").fill(user_context["number"])
    time.sleep(1)
    page.locator("#signinbtn").first.click()
    time.sleep(3)
    take_screenshot(page, "Number enter kiya")

    bot.send_message(CHAT_ID, "🔢 *OTP bhejein:*", parse_mode="Markdown")
    user_context["state"] = "WAITING_FOR_OTP"

    for _ in range(300):
        if user_context["state"] == "OTP_RECEIVED":
            break
        time.sleep(1)
    else:
        bot.send_message(CHAT_ID, "⏰ Timeout! OTP nahi aaya.")
        return False

    for i, digit in enumerate(user_context["otp"].strip()[:6], 1):
        try:
            f = page.locator(f"//input[@aria-label='Digit {i}']")
            if f.is_visible():
                f.fill(digit)
                time.sleep(0.2)
        except:
            pass

    time.sleep(5)
    take_screenshot(page, "OTP enter kiya")
    context.storage_state(path="state.json")
    bot.send_message(CHAT_ID, "✅ *Login ho gaya! Cookie save.* 🍪", parse_mode="Markdown")
    user_context["state"] = "IDLE"
    return True

# ═══════════════════════════════════════
# 🔍 Login Check
# ═══════════════════════════════════════
def check_login_status():
    bot.send_message(CHAT_ID, "🔍 *Login check ho raha hai...*", parse_mode="Markdown")
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
                bot.send_message(CHAT_ID, "⚠️ Session expire! Login karte hain...")
                do_login(page, ctx)
            else:
                bot.send_message(CHAT_ID, "✅ *Login Valid!* Link bhejein. 🚀", parse_mode="Markdown")
        except Exception as e:
            bot.send_message(CHAT_ID, f"Login check error: {str(e)[:150]}")
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

    bot.send_message(CHAT_ID,
        "📺 *YouTube Video Detect Hua!*\nKaunsi quality chahiye?",
        parse_mode="Markdown",
        reply_markup=markup)

def get_height_from_label(label):
    if "360" in label: return "360"
    if "480" in label: return "480"
    if "720" in label: return "720"
    if "1080" in label: return "1080"
    return None  # None = best

# ═══════════════════════════════════════
# 🤖 Bot Commands
# ═══════════════════════════════════════
@bot.message_handler(commands=['start'])
def welcome(message):
    bot.send_message(CHAT_ID,
        "🤖 *Bot Ready!*\n\n"
        "📎 Direct link bhejein → Jazz Drive upload\n"
        "📺 YouTube link → Quality select\n"
        "🔍 /checklogin\n"
        "📊 /status\n"
        "💻 /cmd command",
        parse_mode="Markdown",
        reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(commands=['checklogin'])
def cmd_checklogin(message):
    threading.Thread(target=check_login_status, daemon=True).start()

@bot.message_handler(commands=['status'])
def cmd_status(message):
    status = "🟢 Busy" if is_working else "😴 IDLE"
    cookie = "✅" if os.path.exists("state.json") else "❌"
    bot.send_message(CHAT_ID,
        f"📊 *Status*\n{status}\nQueue: {task_queue.qsize()}\nCookie: {cookie}",
        parse_mode="Markdown")

@bot.message_handler(commands=['cmd'])
def cmd_shell(message):
    try:
        cmd = message.text.replace("/cmd ", "", 1).strip()
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode()
        out = out[:4000] or "Done."
        bot.reply_to(message, f"```\n{out}\n```", parse_mode="Markdown")
    except subprocess.CalledProcessError as e:
        bot.reply_to(message, f"Error:\n{e.output.decode()[:3000]}")
    except Exception as e:
        bot.reply_to(message, str(e))

@bot.message_handler(func=lambda m: True)
def handle_msg(message):
    global is_working
    text = message.text.strip() if message.text else ""
    remove_kb = types.ReplyKeyboardRemove()

    # ── Login states ──
    if user_context["state"] == "WAITING_FOR_NUMBER":
        user_context["number"] = text
        user_context["state"] = "NUMBER_RECEIVED"
        bot.reply_to(message, "✅ Number mil gaya...")
        return

    if user_context["state"] == "WAITING_FOR_OTP":
        user_context["otp"] = text
        user_context["state"] = "OTP_RECEIVED"
        bot.reply_to(message, "✅ OTP mil gaya...")
        return

    # ── Quality select ──
    if user_context["state"] == "WAITING_FOR_QUALITY":
        label = text.replace("🎯","").replace("📱","").replace("💻","").replace("🖥️","").replace("⭐","").strip()
        height = get_height_from_label(label)
        link = user_context["pending_link"]
        user_context["state"] = "IDLE"
        user_context["pending_link"] = None

        bot.send_message(CHAT_ID,
            f"✅ *{label} select kiya!*\nQueue mein add ho raha hai...",
            parse_mode="Markdown",
            reply_markup=remove_kb)

        task_queue.put({"link": link, "height": height, "label": label})

        with worker_lock:
            if not is_working:
                is_working = True
                threading.Thread(target=worker_loop, daemon=True).start()
        return

    # ── Link ──
    if text.startswith("http"):
        if is_youtube(text):
            ask_quality(text)
        else:
            task_queue.put({"link": text, "height": None, "label": "Direct"})
            bot.reply_to(message,
                f"✅ *Queue mein add!* Position: {task_queue.qsize()}",
                parse_mode="Markdown")
            with worker_lock:
                if not is_working:
                    is_working = True
                    threading.Thread(target=worker_loop, daemon=True).start()
    else:
        bot.reply_to(message, "ℹ️ Link bhejein ya /checklogin karo")

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
            short  = link[:60] + "..." if len(link) > 60 else link
            bot.send_message(CHAT_ID, f"🎬 *Processing...*\n`{short}`", parse_mode="Markdown")
            try:
                process_file(link, height, label)
            except Exception as e:
                bot.send_message(CHAT_ID, f"❌ Error: {str(e)[:150]}")
            finally:
                task_queue.task_done()

        bot.send_message(CHAT_ID,
            "✅ *Sab ho gaya!*\n📎 Agla link bhejein ya ruk jaao.",
            parse_mode="Markdown")
    except Exception as e:
        bot.send_message(CHAT_ID, f"Worker crash: {str(e)[:150]}")
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
    """YouTube video ka title lao"""
    try:
        result = subprocess.check_output(
            f"yt-dlp --no-warnings --get-title '{link}'",
            shell=True, stderr=subprocess.DEVNULL
        ).decode().strip()
        return safe_filename(result) if result else None
    except:
        return None

def process_file(link, height=None, label=""):
    yt = is_youtube(link)
    min_size = 5 if yt else 2  # YouTube ke liye 5MB minimum

    # ── YouTube title fetch ──
    video_title = None
    if yt:
        bot.send_message(CHAT_ID, "📝 Video title fetch kar raha hoon...")
        video_title = get_yt_title(link)
        if video_title:
            bot.send_message(CHAT_ID, f"🎬 *Title:* {video_title.replace('_', ' ')}", parse_mode="Markdown")

    # Final filename: title + quality ya generic
    if video_title:
        q_suffix = f"_{label.replace(' ','')}" if label and label != "Best Quality" else "_best"
        OUT = f"{video_title}{q_suffix}.mp4"
    else:
        OUT = "downloaded_file.mp4"

    success = False

    try:
        bot.send_message(CHAT_ID, "⬇️ *Download shuru...*", parse_mode="Markdown")

        # ══════════════════════════════════════
        # Method 1: yt-dlp
        # ══════════════════════════════════════
        if not success:
            q_label = label if label else "Best"

            if yt and height:
                # Specific quality: avc codec prefer karo (widely compatible)
                q_fmt = (
                    f"bestvideo[height<={height}][vcodec^=avc][ext=mp4]+"
                    f"bestaudio[acodec^=mp4a]/"
                    f"bestvideo[height<={height}][ext=mp4]+bestaudio/"
                    f"bestvideo[height<={height}]+bestaudio/"
                    f"best[height<={height}]/best"
                )
            elif yt:
                # Best quality YouTube
                q_fmt = (
                    "bestvideo[vcodec^=avc][ext=mp4]+bestaudio[acodec^=mp4a]/"
                    "bestvideo[ext=mp4]+bestaudio/"
                    "bestvideo+bestaudio/best"
                )
            else:
                q_fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"

            bot.send_message(CHAT_ID, f"🔄 yt-dlp ({q_label})...")
            clean(OUT)
            os.system(
                f"yt-dlp --no-warnings --no-playlist "
                f"--socket-timeout 60 --retries 5 "
                f"--fragment-retries 5 "
                f"--concurrent-fragments 4 "
                f"-f '{q_fmt}' "
                f"--merge-output-format mp4 "
                f"--add-header 'User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64)' "
                f"--no-check-certificates "
                f"-o '{OUT}' '{link}'"
            )

            if os.path.exists(OUT):
                sz = os.path.getsize(OUT) / (1024*1024)
                bot.send_message(CHAT_ID, f"📦 yt-dlp: {sz:.1f} MB")
                if file_ok(OUT, min_size):
                    success = True
                else:
                    bot.send_message(CHAT_ID, f"⚠️ {sz:.1f}MB — bahut chhota, agle method try...")
                    clean(OUT)

        # ══════════════════════════════════════
        # Method 2: aria2c (direct links)
        # ══════════════════════════════════════
        if not success and not yt:
            bot.send_message(CHAT_ID, "🔄 aria2c try kar raha hoon...")
            clean(OUT)
            os.system(
                f"aria2c -x 16 -s 16 -k 1M "
                f"--timeout=60 --retry-wait=3 --max-tries=3 "
                f"--user-agent='Mozilla/5.0' "
                f"--allow-overwrite=true "
                f"-o '{OUT}' '{link}'"
            )
            if os.path.exists(OUT):
                sz = os.path.getsize(OUT) / (1024*1024)
                bot.send_message(CHAT_ID, f"📦 aria2c: {sz:.1f} MB")
                if file_ok(OUT, min_size): success = True
                else: clean(OUT)

        # ══════════════════════════════════════
        # Method 3: wget
        # ══════════════════════════════════════
        if not success and not yt:
            bot.send_message(CHAT_ID, "🔄 wget try kar raha hoon...")
            clean(OUT)
            os.system(
                f"wget -q --tries=3 --timeout=60 "
                f"--user-agent='Mozilla/5.0' "
                f"--no-check-certificate "
                f"-O '{OUT}' '{link}'"
            )
            if os.path.exists(OUT):
                sz = os.path.getsize(OUT) / (1024*1024)
                bot.send_message(CHAT_ID, f"📦 wget: {sz:.1f} MB")
                if file_ok(OUT, min_size): success = True
                else: clean(OUT)

        # ══════════════════════════════════════
        # Method 4: curl
        # ══════════════════════════════════════
        if not success and not yt:
            bot.send_message(CHAT_ID, "🔄 curl try kar raha hoon...")
            clean(OUT)
            os.system(
                f"curl -L --retry 3 --max-time 300 "
                f"-H 'User-Agent: Mozilla/5.0' "
                f"-H 'Accept: */*' "
                f"-H 'Referer: {link}' "
                f"-o '{OUT}' '{link}'"
            )
            if os.path.exists(OUT):
                sz = os.path.getsize(OUT) / (1024*1024)
                bot.send_message(CHAT_ID, f"📦 curl: {sz:.1f} MB")
                if file_ok(OUT, min_size): success = True
                else: clean(OUT)

        # ══════════════════════════════════════
        # Method 5: Python requests
        # ══════════════════════════════════════
        if not success and not yt:
            bot.send_message(CHAT_ID, "🔄 Python requests try kar raha hoon...")
            clean(OUT)
            try:
                hdrs = {'User-Agent': 'Mozilla/5.0', 'Accept': '*/*', 'Referer': link}
                with requests.get(link, headers=hdrs, stream=True,
                                  allow_redirects=True, timeout=60) as r:
                    r.raise_for_status()
                    with open(OUT, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk: f.write(chunk)
                if os.path.exists(OUT):
                    sz = os.path.getsize(OUT) / (1024*1024)
                    bot.send_message(CHAT_ID, f"📦 requests: {sz:.1f} MB")
                    if file_ok(OUT, min_size): success = True
                    else: clean(OUT)
            except Exception as e:
                bot.send_message(CHAT_ID, f"Method 5 error: {str(e)[:100]}")

        # ══════════════════════════════════════
        # Final
        # ══════════════════════════════════════
        if not success:
            bot.send_message(CHAT_ID,
                "❌ *Download fail!*\n\n"
                "• Link expire ho gaya ⏰\n"
                "• Login chahiye 🔐\n"
                "• Site blocked 🚫\n\n"
                "📎 Fresh link bhejein.",
                parse_mode="Markdown")
            return

        size_mb = os.path.getsize(OUT) / (1024 * 1024)
        display_name = OUT.replace('_', ' ').replace('.mp4', '')
        bot.send_message(CHAT_ID,
            f"✅ *Download Complete!*\n"
            f"🎬 {display_name}\n"
            f"📦 Size: {size_mb:.1f} MB\n"
            f"⬆️ Jazz Drive pe upload ho raha hai...",
            parse_mode="Markdown")

        jazz_drive_upload(OUT)

    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ Process error: {str(e)[:200]}")
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
        upload_success = False

        try:
            bot.send_message(CHAT_ID, "🌐 Jazz Drive khul raha hai...")
            page.goto("https://cloud.jazzdrive.com.pk/", wait_until="networkidle", timeout=90000)
            time.sleep(3)

            if page.locator("#msisdn").is_visible():
                bot.send_message(CHAT_ID, "⚠️ Session expire! Login karo.")
                ok = do_login(page, ctx)
                if not ok:
                    bot.send_message(CHAT_ID, "❌ Login fail — skip.")
                    return
                page.goto("https://cloud.jazzdrive.com.pk/", wait_until="networkidle", timeout=90000)
                time.sleep(3)

            ctx.storage_state(path="state.json")

            bot.send_message(CHAT_ID, "📤 *File select ho rahi hai...*", parse_mode="Markdown")
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
                    page.set_input_files("input[type='file']", os.path.abspath(filename))
            except:
                page.set_input_files("input[type='file']", os.path.abspath(filename))

            time.sleep(3)

            try:
                if page.get_by_text("Yes", exact=True).is_visible():
                    page.get_by_text("Yes", exact=True).click()
            except: pass

            # ── Upload wait — progress har 30 sec ──
            bot.send_message(CHAT_ID, "⏳ *Upload chal raha hai...*", parse_mode="Markdown")
            start = time.time()
            last_update = start

            while True:
                try:
                    if page.get_by_text("Uploads completed").is_visible():
                        upload_success = True
                        break
                except: pass

                elapsed = time.time() - start

                if time.time() - last_update >= 30:
                    mins = int(elapsed // 60)
                    secs = int(elapsed % 60)
                    bot.send_message(CHAT_ID, f"⏳ Upload jari... {mins}m {secs}s")
                    last_update = time.time()

                if elapsed > 1200:  # 20 min timeout
                    take_screenshot(page, "Upload 20min timeout")
                    bot.send_message(CHAT_ID,
                        "⚠️ *20 min ho gaye.* Jazz Drive app mein check karo.",
                        parse_mode="Markdown")
                    break

                time.sleep(2)

            if upload_success:
                ctx.storage_state(path="state.json")
                take_screenshot(page, "✅ Upload Complete!")
                display = os.path.basename(filename).replace('_',' ').replace('.mp4','')
                bot.send_message(CHAT_ID,
                    f"🎉 *Upload ho gayi!*\n🎬 {display}\n📎 Agla link bhejein.",
                    parse_mode="Markdown")

        except Exception as e:
            take_screenshot(page, "❌ Error")
            bot.send_message(CHAT_ID, f"Upload Error: {str(e)[:200]}")
            raise
        finally:
            browser.close()

# ═══════════════════════════════════════
# 🚀 Start
# ═══════════════════════════════════════
threading.Thread(target=check_login_status, daemon=True).start()
bot.polling(non_stop=True, timeout=60, long_polling_timeout=60)
