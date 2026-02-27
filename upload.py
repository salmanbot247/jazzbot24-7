import os
import time
import threading
import queue
import subprocess
import telebot
from telebot import types
from playwright.sync_api import sync_playwright

# 🔑 Apni Details
TOKEN = "8485872476:AAE-mNl9roDNnwDQV16M2WREkf479kKCOzs"
chat_id = 7144917062
bot = telebot.TeleBot(TOKEN)

# 🔄 Queue System (Kaam ki Line)
task_queue = queue.Queue()
is_working = False

user_context = {"state": "IDLE", "number": None, "otp": None}
XPATH_ACCEPT_ALL = "//button[contains(text(), 'Accept All')]"

# 🔥 Browser Settings (Turbo)
BROWSER_ARGS = ["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage", "--single-process"]

def take_screenshot(page, caption):
    try:
        path = "status.png"
        page.screenshot(path=path)
        with open(path, 'rb') as photo:
            bot.send_photo(chat_id, photo, caption=caption)
        os.remove(path)
    except: pass

@bot.message_handler(commands=['start'])
def welcome(message):
    bot.send_message(chat_id, 
        "🤖 **GOD MODE ACTIVATED**\n\n"
        "1️⃣ **Queue:** Jitne marzi direct link bhejein, main line mein laga lunga.\n"
        "2️⃣ **Shell:** `/cmd <command>` (Server Control).\n"
        "3️⃣ **Status:** `/status` (Check Queue).")

# 💻 HACKER FEATURE: Server Control
@bot.message_handler(commands=['cmd'])
def shell_command(message):
    try:
        cmd = message.text.replace("/cmd ", "")
        output = subprocess.check_output(cmd, shell=True).decode("utf-8")
        if len(output) > 4000: output = output[:4000] # Telegram limit
        if not output: output = "✅ Command Executed (No Output)"
        bot.reply_to(message, f"```\n{output}\n```", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

@bot.message_handler(commands=['status'])
def check_status(message):
    q_len = task_queue.qsize()
    status = "🟢 Working" if is_working else "IDLE"
    bot.send_message(chat_id, f"📊 **STATUS REPORT**\n\n⚙️ State: {status}\n📚 Pending Files: {q_len}")

@bot.message_handler(func=lambda m: True)
def handle_msg(message):
    text = message.text.strip()
    
    # Login System
    if user_context["state"] == "WAITING_FOR_NUMBER":
        user_context["number"] = text
        user_context["state"] = "NUMBER_RECEIVED"
    elif user_context["state"] == "WAITING_FOR_OTP":
        user_context["otp"] = text
        user_context["state"] = "OTP_RECEIVED"
    
    # Link Handling (YouTube system khatam kar diya, direct queue mein jayega)
    elif text.startswith("http"):
        task_queue.put(text)
        q_len = task_queue.qsize()
        bot.reply_to(message, f"✅ **Added to Queue!**\nPosition: {q_len}")
        
        # Agar bot soya hua hai to jagao
        if not is_working:
            threading.Thread(target=worker_loop).start()

def worker_loop():
    global is_working
    is_working = True
    
    while not task_queue.empty():
        link = task_queue.get()
        bot.send_message(chat_id, f"🎬 **Processing Next File...**\nLink: {link}")
        process_file(link)
        task_queue.task_done()
    
    is_working = False
    bot.send_message(chat_id, "💤 All tasks done. Going to sleep.")

def process_file(link):
    filename = "downloaded_video.mp4"
    try:
        # 1. Download (Direct links with curl)
        bot.send_message(chat_id, "⬇️ Downloading...")
        os.system(f"curl -L -A 'Mozilla/5.0' -o {filename} '{link}'")
        
        if not os.path.exists(filename) or os.path.getsize(filename) < 1000:
            bot.send_message(chat_id, "❌ Download Failed. Skipping...")
            return

        # 2. Upload
        bot.send_message(chat_id, "⬆️ Uploading to Jazz...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
            context = browser.new_context(viewport={'width': 1280, 'height': 720}, storage_state="state.json" if os.path.exists("state.json") else None)
            page = context.new_page()
            
            try:
                page.goto("https://cloud.jazzdrive.com.pk/", wait_until="networkidle", timeout=90000)
                time.sleep(2)

                # Auto Login Handling
                if page.locator("//*[@id='msisdn']").is_visible():
                    bot.send_message(chat_id, "🔑 Login Expired! Queue Paused. Number bhejein:")
                    user_context["state"] = "WAITING_FOR_NUMBER"
                    while user_context["state"] != "NUMBER_RECEIVED": time.sleep(1)
                    page.locator("//*[@id='msisdn']").fill(user_context["number"])
                    page.locator("//*[@id='signinbtn']").first.click()
                    
                    bot.send_message(chat_id, "🔢 OTP bhejein:")
                    user_context["state"] = "WAITING_FOR_OTP"
                    while user_context["state"] != "OTP_RECEIVED": time.sleep(1)
                    page.locator("//input[@aria-label='Digit 1']").press_sequentially(user_context["otp"], delay=100)
                    time.sleep(5)
                    context.storage_state(path="state.json")

                # Upload Steps
                try: page.evaluate("document.querySelectorAll('header button').forEach(b => { if(b.innerHTML.includes('svg')) b.click(); })")
                except: pass
                time.sleep(2)

                try:
                    if page.locator("div[role='dialog']").is_visible():
                        with page.expect_file_chooser() as fc_info:
                            page.locator("div[role='dialog'] >> text=/upload files/i").first.click()
                        fc_info.value.set_files(os.path.abspath(filename))
                    else:
                        page.set_input_files("input[type='file']", os.path.abspath(filename))
                except: page.set_input_files("input[type='file']", os.path.abspath(filename))

                time.sleep(3)
                if page.get_by_text("Yes", exact=True).is_visible(): page.get_by_text("Yes", exact=True).click()

                # Wait for upload
                start_time = time.time()
                while not page.get_by_text("Uploads completed").is_visible():
                    if time.time() - start_time > 300: # 5 min timeout
                        break
                    time.sleep(1)
                
                bot.send_message(chat_id, "✅ Upload Success!")
            
            except Exception as e:
                take_screenshot(page, "❌ Upload Error")
                bot.send_message(chat_id, f"Upload Failed: {str(e)[:100]}")
            
            browser.close()

    except Exception as e:
        bot.send_message(chat_id, f"Critical Error: {str(e)}")
    finally:
        if os.path.exists(filename): os.remove(filename)

bot.polling(non_stop=True)
