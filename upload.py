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
worker_lock = threading.Lock()
user_context = {"state": "IDLE", "number": None, "otp": None}

# 🔥 Browser Settings
BROWSER_ARGS = [
    "--disable-gpu", "--no-sandbox",
    "--disable-dev-shm-usage", "--single-process"
]

def take_screenshot(page, caption="Screenshot"):
    try:
        path = "status.png"
        page.screenshot(path=path)
        with open(path, 'rb') as photo:
            bot.send_photo(CHAT_ID, photo, caption=caption)
        os.remove(path)
    except:
        pass

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
        bot.send_message(CHAT_ID, "Timeout! Number nahi aaya.")
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
        bot.send_message(CHAT_ID, "Timeout! OTP nahi aaya.")
        return False

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
    take_screenshot(page, "OTP enter kiya")
    context.storage_state(path="state.json")
    bot.send_message(CHAT_ID, "✅ *Login ho gaya! Cookie save ho gayi.* 🍪", parse_mode="Markdown")
    user_context["state"] = "IDLE"
    return True

def check_login_status():
    bot.send_message(CHAT_ID, "🔍 *Login check ho raha hai...*", parse_mode="Markdown")
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
                bot.send_message(CHAT_ID, "Session expire ho gayi, login karte hain...")
                do_login(page, context)
            else:
                bot.send_message(CHAT_ID,
                    "✅ *Login Valid Hai!*\nLink bhejein. 🚀",
                    parse_mode="Markdown")
        except Exception as e:
            bot.send_message(CHAT_ID, f"Login check error: {str(e)[:200]}")
        finally:
            browser.close()

@bot.message_handler(commands=['start'])
def welcome(message):
    bot.send_message(CHAT_ID,
        "🤖 *Bot Ready!*\n\n"
        "📎 Direct link bhejein\n"
        "🔍 /checklogin\n"
        "💻 /cmd command\n"
        "📊 /status",
        parse_mode="Markdown")

@bot.message_handler(commands=['checklogin'])
def manual_login_check(message):
    threading.Thread(target=check_login_status, daemon=True).start()

@bot.message_handler(commands=['cmd'])
def shell_command(message):
    try:
        cmd = message.text.replace("/cmd ", "", 1).strip()
        if not cmd:
            bot.reply_to(message, "Command likhein: /cmd ls")
            return
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode("utf-8")
        output = output[:4000] if len(output) > 4000 else output
        output = output or "Done (No Output)"
        bot.reply_to(message, f"```\n{output}\n```", parse_mode="Markdown")
    except subprocess.CalledProcessError as e:
        bot.reply_to(message, f"Error: {e.output.decode()[:3000]}")
    except Exception as e:
        bot.reply_to(message, f"Error: {str(e)}")

@bot.message_handler(commands=['status'])
def check_status(message):
    status = "Kaam Chal Raha Hai" if is_working else "IDLE"
    cookie = "Saved" if os.path.exists("state.json") else "Nahi Hai"
    bot.send_message(CHAT_ID,
        f"📊 *Status*\n\n{status}\nQueue: {task_queue.qsize()}\nCookie: {cookie}",
        parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def handle_msg(message):
    global is_working
    text = message.text.strip() if message.text else ""

    if user_context["state"] == "WAITING_FOR_NUMBER":
        user_context["number"] = text
        user_context["state"] = "NUMBER_RECEIVED"
        bot.reply_to(message, "Number mil gaya...")
        return

    if user_context["state"] == "WAITING_FOR_OTP":
        user_context["otp"] = text
        user_context["state"] = "OTP_RECEIVED"
        bot.reply_to(message, "OTP mil gaya...")
        return

    if text.startswith("http"):
        task_queue.put(text)
        bot.reply_to(message,
            f"✅ *Queue mein add!* Position: {task_queue.qsize()}",
            parse_mode="Markdown")

        # Lock se check karo - double thread na bane
        with worker_lock:
            if not is_working:
                is_working = True
                threading.Thread(target=worker_loop, daemon=True).start()
    else:
        bot.reply_to(message, "Direct link bhejein ya /checklogin karo")

def worker_loop():
    global is_working
    try:
        while not task_queue.empty():
            link = task_queue.get()
            short = link[:70] + "..." if len(link) > 70 else link
            bot.send_message(CHAT_ID,
                f"🎬 *Processing...*\n`{short}`",
                parse_mode="Markdown")
            try:
                process_file(link)
            except Exception as e:
                bot.send_message(CHAT_ID, f"File Error: {str(e)[:200]}")
            finally:
                task_queue.task_done()

        bot.send_message(CHAT_ID,
            "✅ *Sab ho gaya!*\n\n📎 Agla link bhejein ya ruk jaao.",
            parse_mode="Markdown")

    except Exception as e:
        bot.send_message(CHAT_ID, f"Worker crash: {str(e)[:200]}")
    finally:
        # HAMESHA reset hoga - yahi fix hai
        with worker_lock:
            is_working = False

def process_file(link):
    filename = "downloaded_file.mp4"
    try:
        bot.send_message(CHAT_ID, "⬇️ *Downloading...*", parse_mode="Markdown")

        # Pehle yt-dlp try karo (Google, YouTube, aur baaki sab ke liye)
        ytdlp_cmd = (
            f"yt-dlp --no-warnings --no-playlist "
            f"-f 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best' "
            f"--merge-output-format mp4 "
            f"-o '{filename}' '{link}'"
        )
        ret = os.system(ytdlp_cmd)

        # Agar yt-dlp kaam na kare toh curl try karo
        if not os.path.exists(filename) or os.path.getsize(filename) < 1000:
            bot.send_message(CHAT_ID, "⬇️ yt-dlp se nahi hua, curl try kar raha hoon...")
            if os.path.exists(filename):
                os.remove(filename)
            os.system(f"curl -L --retry 3 -A 'Mozilla/5.0' -o '{filename}' '{link}'")

        # Dono fail
        if not os.path.exists(filename) or os.path.getsize(filename) < 1000:
            bot.send_message(CHAT_ID,
                "❌ *Download fail ho gaya.*\n"
                "Link expired ho sakta hai ya protected hai.\n"
                "Naya/fresh link bhejein.",
                parse_mode="Markdown")
            return

        size_mb = os.path.getsize(filename) / (1024 * 1024)
        bot.send_message(CHAT_ID,
            f"✅ *Download Done!* {size_mb:.1f} MB\nUploading...",
            parse_mode="Markdown")

        jazz_drive_upload(filename)

    except Exception as e:
        bot.send_message(CHAT_ID, f"Error: {str(e)[:200]}")
        raise
    finally:
        if os.path.exists(filename):
            os.remove(filename)

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

            if page.locator("#msisdn").is_visible():
                bot.send_message(CHAT_ID, "Session expire! Login karo.", parse_mode="Markdown")
                success = do_login(page, context)
                if not success:
                    bot.send_message(CHAT_ID, "Login fail - skip.")
                    return
                page.goto("https://cloud.jazzdrive.com.pk/", wait_until="networkidle", timeout=90000)
                time.sleep(3)

            context.storage_state(path="state.json")

            bot.send_message(CHAT_ID, "📤 *Uploading...*", parse_mode="Markdown")
            time.sleep(2)

            try:
                page.evaluate("""
                    document.querySelectorAll('header button').forEach(b => {
                        if(b.innerHTML.includes('svg') || b.innerHTML.includes('upload')) b.click();
                    });
                """)
                time.sleep(2)
            except:
                pass

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

            try:
                if page.get_by_text("Yes", exact=True).is_visible():
                    page.get_by_text("Yes", exact=True).click()
            except:
                pass

            bot.send_message(CHAT_ID, "⏳ Upload chal raha hai...")
            start = time.time()
            while True:
                try:
                    if page.get_by_text("Uploads completed").is_visible():
                        upload_success = True
                        break
                except:
                    pass
                if time.time() - start > 600:
                    bot.send_message(CHAT_ID, "10 min timeout. Jazz Drive check karo.")
                    break
                time.sleep(2)

            if upload_success:
                context.storage_state(path="state.json")
                take_screenshot(page, "Upload Complete!")
                bot.send_message(CHAT_ID,
                    "🎉 *Jazz Drive pe upload ho gayi!*",
                    parse_mode="Markdown")

        except Exception as e:
            take_screenshot(page, "Error")
            bot.send_message(CHAT_ID, f"Upload Error: {str(e)[:200]}")
            raise
        finally:
            browser.close()

# Start
threading.Thread(target=check_login_status, daemon=True).start()
# timeout aur read_timeout badhaya — ReadTimeout fix
bot.polling(non_stop=True, timeout=60, long_polling_timeout=60, allowed_updates=None)
