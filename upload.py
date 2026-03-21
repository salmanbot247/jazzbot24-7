import os, re, time, threading, queue, subprocess, requests, telebot
from telebot import types
from playwright.sync_api import sync_playwright

TOKEN = "8485872476:AAE-mNl9roDNnwDQV16M2WREkf479kKCOzs"
CHAT_ID = 7144917062
bot = telebot.TeleBot(TOKEN)

task_queue = queue.Queue()
is_working = False
worker_lock = threading.Lock()
user_context = {"state": "IDLE", "number": None, "otp": None, "pending_link": None}

BROWSER_ARGS = ["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage", "--single-process"]
YOUTUBE_DOMAINS = ["youtube.com", "youtu.be", "youtube-nocookie.com"]
ANDROID_UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
WEB_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

def is_youtube(link): return any(d in link for d in YOUTUBE_DOMAINS)
def get_ua(link): return ANDROID_UA if is_youtube(link) else WEB_UA
def safe_filename(t): return re.sub(r'[\\/*?:"<>|]', '', t).strip().replace(' ', '_')[:80]
def msg(text, **kw): bot.send_message(CHAT_ID, text, parse_mode="Markdown", **kw)
def divider(): return "─────────────────────"
def file_ok(f, min_mb=2): return os.path.exists(f) and os.path.getsize(f)/(1024*1024) >= min_mb
def clean(f):
    if os.path.exists(f): os.remove(f)

def take_screenshot(page, caption="📸"):
    try:
        page.screenshot(path="s.png")
        with open("s.png", "rb") as f: bot.send_photo(CHAT_ID, f, caption=caption)
        os.remove("s.png")
    except: pass

def do_login(page, context):
    msg("🔐 *LOGIN REQUIRED*\n\n📱 Jazz number bhejein\nFormat: `03XXXXXXXXX`")
    user_context["state"] = "WAITING_FOR_NUMBER"
    for _ in range(300):
        if user_context["state"] == "NUMBER_RECEIVED": break
        time.sleep(1)
    else:
        msg("⏰ Timeout! Task cancel.")
        return False

    page.locator("#msisdn").fill(user_context["number"])
    time.sleep(1)
    page.locator("#signinbtn").first.click()
    time.sleep(3)
    take_screenshot(page, "📱 Number submit")
    msg("✅ Number accept hua!\n\n🔢 *OTP bhejein:*")
    user_context["state"] = "WAITING_FOR_OTP"
    for _ in range(300):
        if user_context["state"] == "OTP_RECEIVED": break
        time.sleep(1)
    else:
        msg("⏰ Timeout! Task cancel.")
        return False

    for i, digit in enumerate(user_context["otp"].strip()[:6], 1):
        try:
            f = page.locator(f"//input[@aria-label='Digit {i}']")
            if f.is_visible():
                f.fill(digit)
                time.sleep(0.2)
        except: pass

    time.sleep(5)
    take_screenshot(page, "🔢 OTP submit")
    context.storage_state(path="state.json")
    msg("✅ *LOGIN SUCCESSFUL!*\n\n🍪 Session save!\nLink bhejein 🚀")
    user_context["state"] = "IDLE"
    return True

def check_login_status():
    msg("🔍 Jazz Drive login check ho raha hai...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 720},
            storage_state="state.json" if os.path.exists("state.json") else None
        )
        page = ctx.new_page()
        try:
            page.goto("https://cloud.jazzdrive.com.pk/", wait_until="networkidle", timeout=90000)
            time.sleep(3)
            if page.locator("#msisdn").is_visible():
                msg("⚠️ Session expire!\nLogin karte hain...")
                do_login(page, ctx)
            else:
                msg("✅ *LOGIN VALID HAI!*\n\n🚀 Link bhejein!")
        except Exception as e:
            msg(f"❌ Error:\n`{str(e)[:150]}`")
        finally:
            browser.close()

def ask_quality(link):
    user_context["pending_link"] = link
    user_context["state"] = "WAITING_FOR_QUALITY"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.row("🎯 360p", "📱 480p")
    markup.row("💻 720p", "🖥️ 1080p")
    markup.row("⭐ Best Quality")
    msg("📺 *YOUTUBE DETECTED*\n\n🎬 Quality select karein:", reply_markup=markup)

def get_height(label):
    for h in ["360", "480", "720", "1080"]:
        if h in label: return h
    return None

@bot.message_handler(commands=["start"])
def welcome(m):
    msg(f"🤖 *JAZZ DRIVE BOT*\n\n📎 Direct link → Upload\n📺 YouTube → Quality select\n\n{divider()}\n/checklogin\n/status\n/cmd", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(commands=["checklogin"])
def cmd_check(m): threading.Thread(target=check_login_status, daemon=True).start()

@bot.message_handler(commands=["status"])
def cmd_status(m):
    icon = "🟢" if is_working else "🔴"
    cookie = "✅" if os.path.exists("state.json") else "❌"
    msg(f"📊 *STATUS*\n\n{icon} {'Working' if is_working else 'Idle'}\n📋 Queue: {task_queue.qsize()}\n🍪 Session: {cookie}")

@bot.message_handler(commands=["cmd"])
def cmd_shell(m):
    try:
        c = m.text.replace("/cmd ", "", 1).strip()
        out = subprocess.check_output(c, shell=True, stderr=subprocess.STDOUT).decode()
        bot.reply_to(m, f"```\n{out[:4000]}\n```", parse_mode="Markdown")
    except subprocess.CalledProcessError as e:
        bot.reply_to(m, f"❌\n```\n{e.output.decode()[:3000]}\n```", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(m, f"❌ `{e}`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def handle(m):
    global is_working
    text = (m.text or "").strip()
    kb_remove = types.ReplyKeyboardRemove()

    if user_context["state"] == "WAITING_FOR_NUMBER":
        user_context["number"] = text
        user_context["state"] = "NUMBER_RECEIVED"
        bot.reply_to(m, "✅ Number receive hua...")
        return

    if user_context["state"] == "WAITING_FOR_OTP":
        user_context["otp"] = text
        user_context["state"] = "OTP_RECEIVED"
        bot.reply_to(m, "✅ OTP receive hua...")
        return

    if user_context["state"] == "WAITING_FOR_QUALITY":
        clean_label = re.sub(r'[🎯📱💻🖥️⭐]', '', text).strip()
        height = get_height(clean_label)
        link = user_context["pending_link"]
        user_context["state"] = "IDLE"
        user_context["pending_link"] = None
        msg(f"✅ *{clean_label}* select!\nQueue mein add...", reply_markup=kb_remove)
        task_queue.put({"link": link, "height": height, "label": clean_label})
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
            bot.reply_to(m, f"✅ Queue mein add!\nPosition: *{task_queue.qsize()}*", parse_mode="Markdown")
            with worker_lock:
                if not is_working:
                    is_working = True
                    threading.Thread(target=worker_loop, daemon=True).start()
    else:
        bot.reply_to(m, "ℹ️ Link bhejein ya /checklogin")

def worker_loop():
    global is_working
    try:
        while not task_queue.empty():
            item = task_queue.get()
            short = item["link"][:55] + "..." if len(item["link"]) > 55 else item["link"]
            msg(f"🎬 *PROCESSING...*\n\n🔗 `{short}`")
            try: process_file(item["link"], item["height"], item["label"])
            except Exception as e: msg(f"❌ Error:\n`{str(e)[:150]}`")
            finally: task_queue.task_done()
        msg("✅ *QUEUE COMPLETE!*\n\nAgla link bhejein 😊")
    except Exception as e:
        msg(f"⚠️ Worker crash:\n`{str(e)[:150]}`")
    finally:
        with worker_lock:
            is_working = False

def get_yt_title(link):
    try:
        ua = get_ua(link)
        result = subprocess.check_output(
            ["yt-dlp", "--no-warnings", "--get-title", "--user-agent", ua, link],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        return safe_filename(result) if result else None
    except: return None

def process_file(link, height=None, label=""):
    yt = is_youtube(link)
    ua = get_ua(link)
    min_size = 5 if yt else 2

    video_title = None
    if yt:
        msg("📝 Video info fetch ho rahi hai...")
        video_title = get_yt_title(link)
        if video_title:
            msg(f"🎬 *{video_title.replace('_',' ')}*\n📐 Quality: *{label}*")

    suffix = f"_{label.replace(' ','')}" if label and label != "Best Quality" else "_best"
    OUT = f"{video_title}{suffix}.mp4" if video_title else "downloaded_file.mp4"
    success = False

    msg("⬇️ *DOWNLOADING...*")

    # Method 1: yt-dlp
    if not success:
        if yt and height:
            fmt = f"bestvideo[height<={height}][vcodec^=avc][ext=mp4]+bestaudio[acodec^=mp4a]/bestvideo[height<={height}][ext=mp4]+bestaudio/best[height<={height}]/best"
        elif yt:
            fmt = "bestvideo[vcodec^=avc][ext=mp4]+bestaudio[acodec^=mp4a]/bestvideo[ext=mp4]+bestaudio/best"
        else:
            fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"

        msg(f"🔄 *Method 1/5* — yt-dlp ({'Android UA' if yt else 'Desktop UA'})")
        clean(OUT)
        subprocess.run([
            "yt-dlp", "--no-warnings", "--no-playlist",
            "--socket-timeout", "60", "--retries", "5",
            "--fragment-retries", "5", "--concurrent-fragments", "4",
            "-f", fmt, "--merge-output-format", "mp4",
            "--user-agent", ua, "--no-check-certificates",
            "-o", OUT, link
        ])
        if os.path.exists(OUT):
            sz = os.path.getsize(OUT)/(1024*1024)
            msg(f"📦 yt-dlp: *{sz:.1f} MB*")
            if file_ok(OUT, min_size): success = True
            else: clean(OUT)

    # Method 2: aria2c
    if not success and not yt:
        msg("🔄 *Method 2/5* — aria2c")
        clean(OUT)
        subprocess.run(["aria2c", "-x", "16", "-s", "16", "-k", "1M",
                        "--timeout=60", "--user-agent", ua,
                        "--allow-overwrite=true", "-o", OUT, link])
        if os.path.exists(OUT):
            sz = os.path.getsize(OUT)/(1024*1024)
            msg(f"📦 aria2c: *{sz:.1f} MB*")
            if file_ok(OUT, min_size): success = True
            else: clean(OUT)

    # Method 3: wget
    if not success and not yt:
        msg("🔄 *Method 3/5* — wget")
        clean(OUT)
        subprocess.run(["wget", "-q", "--tries=3", "--timeout=60",
                        f"--user-agent={ua}", "--no-check-certificate", "-O", OUT, link])
        if os.path.exists(OUT):
            sz = os.path.getsize(OUT)/(1024*1024)
            msg(f"📦 wget: *{sz:.1f} MB*")
            if file_ok(OUT, min_size): success = True
            else: clean(OUT)

    # Method 4: curl
    if not success and not yt:
        msg("🔄 *Method 4/5* — curl")
        clean(OUT)
        subprocess.run(["curl", "-L", "--retry", "3", "--max-time", "300",
                        "-H", f"User-Agent: {ua}", "-o", OUT, link])
        if os.path.exists(OUT):
            sz = os.path.getsize(OUT)/(1024*1024)
            msg(f"📦 curl: *{sz:.1f} MB*")
            if file_ok(OUT, min_size): success = True
            else: clean(OUT)

    # Method 5: requests
    if not success and not yt:
        msg("🔄 *Method 5/5* — requests")
        clean(OUT)
        try:
            with requests.get(link, headers={"User-Agent": ua}, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(OUT, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk: f.write(chunk)
            if os.path.exists(OUT):
                sz = os.path.getsize(OUT)/(1024*1024)
                msg(f"📦 requests: *{sz:.1f} MB*")
                if file_ok(OUT, min_size): success = True
                else: clean(OUT)
        except Exception as e:
            msg(f"⚠️ Method 5: `{str(e)[:100]}`")

    if not success:
        msg("❌ *DOWNLOAD FAILED*\n\nSab methods fail.\nFresh link bhejein.")
        return

    sz = os.path.getsize(OUT)/(1024*1024)
    msg(f"✅ *DOWNLOAD DONE!*\n\n📦 {sz:.1f} MB\n\n☁️ Jazz Drive upload ho raha hai...")
    jazz_drive_upload(OUT)
    clean(OUT)

def jazz_drive_upload(filename):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 720},
            storage_state="state.json" if os.path.exists("state.json") else None
        )
        page = ctx.new_page()
        try:
            msg("🌐 Jazz Drive khul raha hai...")
            page.goto("https://cloud.jazzdrive.com.pk/", wait_until="networkidle", timeout=90000)
            time.sleep(3)

            if page.locator("#msisdn").is_visible():
                msg("⚠️ Session expire!\nLogin karo...")
                ok = do_login(page, ctx)
                if not ok:
                    msg("❌ Login fail.")
                    return
                page.goto("https://cloud.jazzdrive.com.pk/", wait_until="networkidle", timeout=90000)
                time.sleep(3)

            ctx.storage_state(path="state.json")
            sz = os.path.getsize(filename)/(1024*1024)
            msg(f"📤 *UPLOADING...*\n{sz:.1f} MB")
            time.sleep(2)

            # Upload button click
            try:
                page.evaluate("document.querySelectorAll('header button').forEach(b => { if(b.innerHTML.includes('svg') || b.innerHTML.includes('upload')) b.click(); })")
                time.sleep(2)
            except: pass

            # File chooser
            abs_path = os.path.abspath(filename)
            try:
                dialog = page.locator("div[role='dialog']")
                if dialog.is_visible():
                    with page.expect_file_chooser() as fc_info:
                        dialog.locator("text=/upload/i").first.click()
                    fc_info.value.set_files(abs_path)
                else:
                    page.locator("input[type=file]").set_input_files(abs_path)
            except:
                page.locator("input[type=file]").set_input_files(abs_path)

            time.sleep(3)
            try:
                yes_btn = page.get_by_text("Yes", exact=True)
                if yes_btn.is_visible(): yes_btn.click()
            except: pass

            wait_sec = max(60, int(sz * 4))
            msg(f"⏳ Uploading... (~{wait_sec}s)")
            time.sleep(wait_sec)
            ctx.storage_state(path="state.json")
            msg("🎉 *UPLOAD COMPLETE!*\n\nJazz Drive pe save! 🚀")

        except Exception as e:
            msg(f"❌ Upload error:\n`{str(e)[:200]}`")
        finally:
            browser.close()

if __name__ == "__main__":
    msg("🤖 *BOT ONLINE!*\n\n✅ Ready! Link bhejein.")
    bot.infinity_polling()
    
