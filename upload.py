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
    "otp": None
}

BROWSER_ARGS = [
    "--disable-gpu", "--no-sandbox",
    "--disable-dev-shm-usage", "--single-process"
]

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

    try:
        page.fill('input[type="tel"]', user_context["number"].strip(), timeout=5000)
    except:
        page.fill("#msisdn", user_context["number"].strip())
        
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

    otp_val = user_context["otp"].strip()
    
    try:
        page.fill('#otp', otp_val, timeout=3000)
    except:
        try:
            page.evaluate(f'document.getElementById("otp").value = "{otp_val}"')
        except:
            for digit in otp_val[:4]:
                page.keyboard.press(digit)
                time.sleep(0.1)

    time.sleep(2)
    take_screenshot(page, "🔢 OTP submit kiya")
    
    try:
        page.locator("#signinbtn").first.click()
    except:
        page.click('button:has-text("Login")')
        
    time.sleep(10)
    take_screenshot(page, "🌐 Dashboard check")
    
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
                    f"🚀 Direct Link bhejein — ready hoon!"
                )
        except Exception as e:
            take_screenshot(page, "❌ Login check error")
            msg(f"❌ Login check error:\n`{str(e)[:150]}`")
        finally:
            browser.close()

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
        f"📎 Direct link → Download & Upload\n"
        f"⚡ 5 Download Methods Engine\n"
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
        err_msg = e.output.decode()[:3000]
        bot.reply_to(message, f"❌ *Error:*\n```\n{err_msg}\n```", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ `{str(e)}`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def handle_msg(message):
    global is_working
    text = message.text.strip() if message.text else ""

    # ── Login states ──
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

    # ── Direct Link Handler ──
    if text.startswith("http"):
        task_queue.put({"link": text})
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
            f"ℹ️ Sirf Direct Link bhejein\n"
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
            short  = link[:55] + "..." if len(link) > 55 else link
            msg(
                f"╔══════════════════════╗\n"
                f"║   🎬  *PROCESSING...* ║\n"
                f"╚══════════════════════╝\n\n"
                f"🔗 `{short}`"
            )
            try:
                process_file(link)
            except Exception as e:
                msg(f"❌ *Error:*\n`{str(e)[:150]}`")
            finally:
                task_queue.task_done()

        msg(
            f"╔══════════════════════╗\n"
            f"║  ✅  *QUEUE COMPLETE!* ║\n"
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
# ⬇️ Universal Downloader (5 Methods)
# ═══════════════════════════════════════
def file_ok(f, min_mb=1):
    if not os.path.exists(f): return False
    return os.path.getsize(f) / (1024*1024) >= min_mb

def clean(f):
    if os.path.exists(f): os.remove(f)

def process_file(link):
    # Link se filename nikalne ki koshish (default name agar na mile)
    parsed_name = link.split('?')[0].split('/')[-1]
    if not parsed_name or len(parsed_name) < 3:
        parsed_name = f"download_file_{int(time.time())}.mp4"
    OUT = safe_filename(parsed_name)
    
    # Agar extension na ho toh mp4 laga dein
    if '.' not in OUT[-6:]:
        OUT += ".mp4"

    success = False
    min_size = 1 # Minimum 1MB file zaroori hai

    try:
        msg(
            f"┌─────────────────────┐\n"
            f"│  ⬇️  *DOWNLOADING...* │\n"
            f"└─────────────────────┘\n"
            f"📁 Target: `{OUT}`"
        )

        # ── Method 1: yt-dlp (Generic Mode) ──
        if not success:
            msg(f"🔄 *Method 1/5* — yt-dlp")
            clean(OUT)
            os.system(
                f"yt-dlp --no-warnings --no-playlist "
                f"--socket-timeout 60 --retries 3 "
                f"-o '{OUT}' '{link}'"
            )
            if os.path.exists(OUT):
                sz = os.path.getsize(OUT) / (1024*1024)
                msg(f"📦 yt-dlp result: *{sz:.1f} MB*")
                if file_ok(OUT, min_size): success = True
                else: clean(OUT)

        # ── Method 2: aria2c ──
        if not success:
            msg("🔄 *Method 2/5* — aria2c")
            clean(OUT)
            os.system(
                f"aria2c -x 16 -s 16 -k 1M "
                f"--timeout=60 --retry-wait=3 --max-tries=3 "
                f"--user-agent='Mozilla/5.0' --allow-overwrite=true "
                f"-o '{OUT}' '{link}'"
            )
            if os.path.exists(OUT):
                sz = os.path.getsize(OUT) / (1024*1024)
                msg(f"📦 aria2c result: *{sz:.1f} MB*")
                if file_ok(OUT, min_size): success = True
                else: clean(OUT)

        # ── Method 3: wget ──
        if not success:
            msg("🔄 *Method 3/5* — wget")
            clean(OUT)
            os.system(
                f"wget -q --tries=3 --timeout=60 "
                f"--user-agent='Mozilla/5.0' --no-check-certificate "
                f"-O '{OUT}' '{link}'"
            )
            if os.path.exists(OUT):
                sz = os.path.getsize(OUT) / (1024*1024)
                msg(f"📦 wget result: *{sz:.1f} MB*")
                if file_ok(OUT, min_size): success = True
                else: clean(OUT)

        # ── Method 4: curl ──
        if not success:
            msg("🔄 *Method 4/5* — curl")
            clean(OUT)
            os.system(
                f"curl -L --retry 3 --max-time 300 "
                f"-H 'User-Agent: Mozilla/5.0' -H 'Accept: */*' "
                f"-H 'Referer: {link}' -o '{OUT}' '{link}'"
            )
            if os.path.exists(OUT):
                sz = os.path.getsize(OUT) / (1024*1024)
                msg(f"📦 curl result: *{sz:.1f} MB*")
                if file_ok(OUT, min_size): success = True
                else: clean(OUT)

        # ── Method 5: requests ──
        if not success:
            msg("🔄 *Method 5/5* — Python requests")
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
                    msg(f"📦 requests result: *{sz:.1f} MB*")
                    if file_ok(OUT, min_size): success = True
                    else: clean(OUT)
            except Exception as e:
                msg(f"⚠️ Method 5 error: `{str(e)[:100]}`")

        # ── Final ──
        if not success:
            msg(
                f"╔══════════════════════╗\n"
                f"║  ❌  *DOWNLOAD FAILED* ║\n"
                f"╚══════════════════════╝\n\n"
                f"Sab 5 methods fail ho gaye!\n\n"
                f"*Possible reasons:*\n"
                f"⏰ Link expire ho gaya\n"
                f"🔐 Login/auth chahiye\n"
                f"🚫 Site ne block kiya\n\n"
                f"📎 Fresh direct link bhejein."
            )
            return

        size_mb = os.path.getsize(OUT) / (1024*1024)
        msg(
            f"╔══════════════════════╗\n"
            f"║  ✅  *DOWNLOAD DONE!* ║\n"
            f"╚══════════════════════╝\n\n"
            f"🎬 *{OUT[:40]}*\n"
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
# ☁️ Jazz Drive Upload (Fixed Completeness)
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
            msg("🌐 *Jazz Drive* khul raha hai...")
            page.goto("https://cloud.jazzdrive.com.pk/", wait_until="networkidle", timeout=90000)
            time.sleep(3)

            if page.locator("#msisdn").is_visible() or page.locator('input[type="tel"]').is_visible():
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
                f"│  📤  *UPLOADING...* │\n"
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
                    page.set_input_files("input[type='file']", os.path.abspath(filename))
            except:
                page.set_input_files("input[type='file']", os.path.abspath(filename))

            time.sleep(3)

            try:
                if page.get_by_text("Yes", exact=True).is_visible():
                    page.get_by_text("Yes", exact=True).click()
            except: pass

            msg("⏳ *Upload jari hai...*\nHar 30 sec mein update milega.")
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
                    msg(f"📡 *Upload progress:* `{mins}m {secs}s` elapsed...")
                    last_update = time.time()

                if elapsed > 1200:
                    take_screenshot(page, "⏰ 20min timeout")
                    msg(
                        f"⚠️ *20 dakika ho gaye!*\n"
                        f"Jazz Drive app mein\n"
                        f"manually check karein."
                    )
                    break

                time.sleep(2)

            if upload_success:
                ctx.storage_state(path="state.json")
                take_screenshot(page, "✅ Upload Complete!")
                display = os.path.basename(filename).replace('_',' ')
                msg(
                    f"╔══════════════════════╗\n"
                    f"║  🎉  *UPLOAD SUCCESS!* ║\n"
                    f"╚══════════════════════╝\n\n"
                    f"🎬 *{display[:40]}*\n\n"
                    f"✅ Jazz Drive mein save!\n"
                    f"📎 Agla link bhejein. 🚀"
                )

        except Exception as e:
            take_screenshot(page, "❌ Upload Error")
            msg(f"❌ *Upload Error:*\n`{str(e)[:200]}`")
            raise
        finally:
            browser.close()

# ═══════════════════════════════════════
# 🚀 Start
# ═══════════════════════════════════════
threading.Thread(target=check_login_status, daemon=True).start()
bot.polling(non_stop=True, timeout=60, long_polling_timeout=60)
                  
