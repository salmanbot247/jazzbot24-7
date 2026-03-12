import os
import time
import threading
import queue
import subprocess
import telebot
from playwright.sync_api import sync_playwright

# 🔑 Apni Details
TOKEN = "8485872476:AAE-mNl9roDNnwDQV16M2WREkf479kKCOzs"
CHAT_ID = 7144917062
bot = telebot.TeleBot(TOKEN)

# 🔄 Queue System
task_queue = queue.Queue()
is_working = False
user_context = {"state": "IDLE", "number": None, "otp": None}

# 🔥 Browser Settings
BROWSER_ARGS = [
    "--disable-gpu", "--no-sandbox",
    "--disable-dev-shm-usage", "--single-process"
]

# ───────────────────────────────────────────────
# 📸 Screenshot Helper
# ───────────────────────────────────────────────
def take_screenshot(page, caption="📸 Screenshot"):
    try:
        path = "status.png"
        page.screenshot(path=path)
        with open(path, 'rb') as photo:
            bot.send_photo(CHAT_ID, photo, caption=caption)
        os.remove(path)
    except:
        pass

# ───────────────────────────────────────────────
# 🔑 Login Helper (Reusable)
# ───────────────────────────────────────────────
def do_login(page, context):
    """Jazz Drive pe login karo aur session save karo. True/False return karta hai."""

    bot.send_message(CHAT_ID,
        "🔑 *Login Zaruri Hai!*\n"
        "Apna Jazz number bhejein (03xxxxxxxxx):",
        parse_mode="Markdown")
    user_context["state"] = "WAITING_FOR_NUMBER"

    # Number ka wait (max 5 min)
    for _ in range(300):
        if user_context["state"] == "NUMBER_RECEIVED":
            break
        time.sleep(1)
    else:
        bot.send_message(CHAT_ID, "⏰ Timeout! Number nahi aaya. Task skip.")
        return False

    # Number fill karo
    page.locator("#msisdn").fill(user_context["number"])
    time.sleep(1)
    page.locator("#signinbtn").first.click()
    time.sleep(3)
    take_screenshot(page, "📱 Number enter kiya")

    # OTP maango
    bot.send_message(CHAT_ID, "🔢 *OTP bhejein jo Jazz number pe aaya:*", parse_mode="Markdown")
    user_context["state"] = "WAITING_FOR_OTP"

    for _ in range(300):
        if user_context["state"] == "OTP_RECEIVED":
            break
        time.sleep(1)
    else:
        bot.send_message(CHAT_ID, "⏰ Timeout! OTP nahi aaya. Task skip.")
        return False

    # OTP digit by digit enter karo
    otp = user_context["otp"].strip()
    for i, digit in enumerate(otp[:6], 1):
        try:
            field = page.locator(f"//input[@aria-label='Digit {i}']")
            if field.is_visible():
                field.fill(digit)
                time.sleep(0.2)
        except:
            pass

    time.sleep(5)
    take_screenshot(page, "✅ OTP enter kiya")

    # ── Cookie Save ──
    context.storage_state(path="state.json")
    bot.send_message(CHAT_ID, "✅ *Login ho gaya! Cookie save ho gayi.* 🍪", parse_mode="Markdown")

    user_context["state"] = "IDLE"
    return True

# ───────────────────────────────────────────────
# 🔍 Login Status Check
# ───────────────────────────────────────────────
def check_login_status():
    """Bot start hote hi check karo — login valid hai ya expire?"""
    bot.send_message(CHAT_ID, "🔍 *Jazz Drive login check ho raha hai...*", parse_mode="Markdown")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 720},
            storage_state="state.json" if os.path.exists("state.json") else None
        )
        page = context.new_page()

        try:
            page.goto("https://cloud.jazzdrive.com.pk/", wait_until="networkidle", timeout=90000)
            time.sleep(3)

            if page.locator("#msisdn").is_visible():
                # Session expire
                bot.send_message(CHAT_ID,
                    "⚠️ *Session Expire Ho Gayi!*\n"
                    "Abhi login karte hain...",
                    parse_mode="Markdown")
                do_login(page, context)
            else:
                # Login theek hai
                bot.send_message(CHAT_ID,
                    "✅ *Login Valid Hai!*\n"
                    "Seedha link bhejein — kaam shuru ho jaayega. 🚀",
                    parse_mode="Markdown")

        except Exception as e:
            bot.send_message(CHAT_ID, f"❌ Login check error: {str(e)[:200]}")
        finally:
            browser.close()

# ───────────────────────────────────────────────
# 🤖 Bot Commands
# ───────────────────────────────────────────────
@bot.message_handler(commands=['start'])
def welcome(message):
    bot.send_message(CHAT_ID,
        "🤖 *Bot Ready!*\n\n"
        "📎 Direct link bhejein → Jazz Drive pe upload\n"
        "🔍 `/checklogin` → Login check karo\n"
        "💻 `/cmd <command>` → Server control\n"
        "📊 `/status` → Queue check",
        parse_mode="Markdown")

@bot.message_handler(commands=['checklogin'])
def manual_login_check(message):
    threading.Thread(target=check_login_status, daemon=True).start()

@bot.message_handler(commands=['cmd'])
def shell_command(message):
    try:
        cmd = message.text.replace("/cmd ", "", 1).strip()
        if not cmd:
            bot.reply_to(message, "❌ Command likhein: `/cmd ls`", parse_mode="Markdown")
            return
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode("utf-8")
        output = output[:4000] if len(output) > 4000 else output
        output = output or "✅ Done (No Output)"
        bot.reply_to(message, f"```\n{output}\n```", parse_mode="Markdown")
    except subprocess.CalledProcessError as e:
        bot.reply_to(message, f"❌ Error:\n```\n{e.output.decode()[:3000]}\n```", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ {str(e)}")

@bot.message_handler(commands=['status'])
def check_status(message):
    status = "🟢 Kaam Chal Raha Hai" if is_working else "😴 IDLE"
    q_len = task_queue.qsize()
    cookie = "✅ Saved" if os.path.exists("state.json") else "❌ Nahi Hai"
    bot.send_message(CHAT_ID,
        f"📊 *Status Report*\n\n"
        f"⚙️ State: {status}\n"
        f"📚 Pending: {q_len} files\n"
        f"🍪 Cookie: {cookie}",
        parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def handle_msg(message):
    text = message.text.strip() if message.text else ""

    # ── Login Flow ──
    if user_context["state"] == "WAITING_FOR_NUMBER":
        user_context["number"] = text
        user_context["state"] = "NUMBER_RECEIVED"
        bot.reply_to(message, "✅ Number mil gaya...")
        return

    if user_context["state"] == "WAITING_FOR_OTP":
        user_context["otp"] = text
        user_context["state"] = "OTP_RECEIVED"
        bot.reply_to(message, "✅ OTP mil gaya, login ho raha hai...")
        return

    # ── Link Handling ──
    if text.startswith("http"):
        task_queue.put(text)
        q_len = task_queue.qsize()
        bot.reply_to(message,
            f"✅ *Queue mein add!*\n📍 Position: {q_len}",
            parse_mode="Markdown")

        global is_working
        if not is_working:
            threading.Thread(target=worker_loop, daemon=True).start()
    else:
        bot.reply_to(message,
            "ℹ️ Direct download link bhejein\n"
            "ya `/checklogin` karo",
            parse_mode="Markdown")

# ───────────────────────────────────────────────
# 🔄 Worker Loop
# ───────────────────────────────────────────────
def worker_loop():
    global is_working
    is_working = True

    while not task_queue.empty():
        link = task_queue.get()
        short = link[:70] + "..." if len(link) > 70 else link
        bot.send_message(CHAT_ID,
            f"🎬 *Processing...*\n🔗 `{short}`",
            parse_mode="Markdown")
        process_file(link)
        task_queue.task_done()

    # ── Queue khaali — agla link maango ──
    is_working = False
    bot.send_message(CHAT_ID,
        "✅ *Sab files upload ho gayi!*\n\n"
        "📎 *Agla link bhejein* ya ruk jaao. 😊",
        parse_mode="Markdown")

# ───────────────────────────────────────────────
# ⬇️ Download
# ───────────────────────────────────────────────
def process_file(link):
    filename = "downloaded_file.mp4"

    try:
        bot.send_message(CHAT_ID, "⬇️ *Downloading...*", parse_mode="Markdown")
        os.system(f"curl -L --retry 3 -A 'Mozilla/5.0' -o '{filename}' '{link}'")

        if not os.path.exists(filename) or os.path.getsize(filename) < 1000:
            bot.send_message(CHAT_ID, "❌ Download fail. Skip kar raha hoon.")
            return

        size_mb = os.path.getsize(filename) / (1024 * 1024)
        bot.send_message(CHAT_ID,
            f"✅ *Download Complete!*\n📦 Size: {size_mb:.1f} MB\n⬆️ Uploading...",
            parse_mode="Markdown")

        jazz_drive_upload(filename)

    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ Critical Error: {str(e)[:200]}")
    finally:
        if os.path.exists(filename):
            os.remove(filename)

# ───────────────────────────────────────────────
# ☁️ Jazz Drive Upload
# ───────────────────────────────────────────────
def jazz_drive_upload(filename):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 720},
            storage_state="state.json" if os.path.exists("state.json") else None
        )
        page = context.new_page()
        upload_success = False

        try:
            bot.send_message(CHAT_ID, "🌐 Jazz Drive khul raha hai...")
            page.goto("https://cloud.jazzdrive.com.pk/", wait_until="networkidle", timeout=90000)
            time.sleep(3)

            # ── Login Expire Check ──
            if page.locator("#msisdn").is_visible():
                bot.send_message(CHAT_ID,
                    "⚠️ *Session Expire Ho Gayi!* Login karna padega.",
                    parse_mode="Markdown")
                success = do_login(page, context)
                if not success:
                    bot.send_message(CHAT_ID, "❌ Login fail — file skip.")
                    browser.close()
                    return
                # Fresh page load after login
                page.goto("https://cloud.jazzdrive.com.pk/", wait_until="networkidle", timeout=90000)
                time.sleep(3)

            # ── Cookie Refresh ──
            context.storage_state(path="state.json")

            # ── Upload Button ──
            bot.send_message(CHAT_ID, "📤 *File select ho rahi hai...*", parse_mode="Markdown")
            time.sleep(2)

            try:
                page.evaluate("""
                    document.querySelectorAll('header button').forEach(b => {
                        if(b.innerHTML.includes('svg') || b.innerHTML.includes('upload')) {
                            b.click();
                        }
                    });
                """)
                time.sleep(2)
            except:
                pass

            # ── File Input ──
            try:
                dialog = page.locator("div[role='dialog']")
                if dialog.is_visible():
                    with page.expect_file_chooser() as fc_info:
                        dialog.locator("text=/upload/i").first.click()
                    fc_info.value.set_files(os.path.abspath(filename))
                else:
                    page.set_input_files("input[type='file']", os.path.abspath(filename))
            except:
                page.set_input_files("input[type='file']", os.path.abspath(filename))

            time.sleep(3)

            # Confirm popup
            try:
                if page.get_by_text("Yes", exact=True).is_visible():
                    page.get_by_text("Yes", exact=True).click()
            except:
                pass

            # ── Upload Complete Wait (max 10 min) ──
            bot.send_message(CHAT_ID, "⏳ *Upload chal raha hai...*", parse_mode="Markdown")
            start = time.time()
            while True:
                try:
                    if page.get_by_text("Uploads completed").is_visible():
                        upload_success = True
                        break
                except:
                    pass
                if time.time() - start > 600:
                    bot.send_message(CHAT_ID, "⚠️ 10 min timeout — Jazz Drive app mein manually check karo.")
                    break
                time.sleep(2)

            # ── Upload Success ──
            if upload_success:
                take_screenshot(page, "✅ Upload Complete!")
                # Cookie fresh save
                context.storage_state(path="state.json")
                bot.send_message(CHAT_ID,
                    "🎉 *File Jazz Drive pe upload ho gayi!*\n\n"
                    "📎 *Agla link bhejein* ya ruk jaao. 😊",
                    parse_mode="Markdown")

        except Exception as e:
            take_screenshot(page, "❌ Error")
            bot.send_message(CHAT_ID, f"❌ Upload Error: {str(e)[:200]}")
        finally:
            browser.close()

# ───────────────────────────────────────────────
# 🚀 Start — Pehle Login Check, Phir Bot On
# ───────────────────────────────────────────────
threading.Thread(target=check_login_status, daemon=True).start()
bot.polling(non_stop=True, timeout=60)
