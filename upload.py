import os, re, time, threading, queue, subprocess, requests, zipfile, telebot
from telebot import types
from playwright.sync_api import sync_playwright

TOKEN = "8485872476:AAE-mNl9roDNnwDQV16M2WREkf479kKCOzs"
CHAT_ID = 7144917062
bot = telebot.TeleBot(TOKEN)

task_queue = queue.Queue()
is_working = False
worker_lock = threading.Lock()
queue_paused = False
current_task = {"name": None}
user_context = {"state": "IDLE", "number": None, "otp": None}

BROWSER_ARGS = ["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage", "--single-process"]
WEB_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
ANDROID_UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"

VIDEO_EXTS = [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts"]
ZIP_EXTS = [".zip", ".rar", ".7z", ".tar", ".gz"]
SOCIAL_SITES = ["youtube.com", "youtu.be", "facebook.com", "fb.watch",
                "instagram.com", "twitter.com", "x.com", "tiktok.com",
                "dailymotion.com", "vimeo.com", "soundcloud.com",
                "bilibili.com", "reddit.com", "twitch.tv"]

def is_zip_url(url): return any(url.lower().endswith(e) or e in url.lower() for e in ZIP_EXTS)
def is_m3u8(url): return ".m3u8" in url.lower()
def is_social(url): return any(s in url for s in SOCIAL_SITES)
def is_video_file(f): return any(f.lower().endswith(e) for e in VIDEO_EXTS)
def safe_fn(t): return re.sub(r'[\\/*?:"<>|]', '', t).strip().replace(' ', '_')[:80]
def file_ok(f, mb=1): return os.path.exists(f) and os.path.getsize(f)/(1024*1024) >= mb
def clean(f):
    if os.path.exists(f): os.remove(f)

def msg(text, **kw):
    try: bot.send_message(CHAT_ID, text, parse_mode="Markdown", **kw)
    except: pass

def take_screenshot(page, caption="📸"):
    try:
        page.screenshot(path="s.png")
        with open("s.png", "rb") as f: bot.send_photo(CHAT_ID, f, caption=caption)
        os.remove("s.png")
    except: pass

# ═══════════════════════════════════════
# 🔑 Login
# ═══════════════════════════════════════
def do_login(page, context):
    msg("🔐 *LOGIN REQUIRED*\n\n📱 Jazz number bhejein\nFormat: `03XXXXXXXXX`")
    user_context["state"] = "WAITING_FOR_NUMBER"
    for _ in range(300):
        if user_context["state"] == "NUMBER_RECEIVED": break
        time.sleep(1)
    else:
        msg("⏰ Timeout!")
        return False

    page.locator("#msisdn").fill(user_context["number"])
    time.sleep(1)
    page.locator("#signinbtn").first.click()
    time.sleep(3)
    take_screenshot(page, "📱 Number submit")
    msg("✅ Number accept!\n\n🔢 *OTP bhejein:*")
    user_context["state"] = "WAITING_FOR_OTP"
    for _ in range(300):
        if user_context["state"] == "OTP_RECEIVED": break
        time.sleep(1)
    else:
        msg("⏰ Timeout!")
        return False

    for i, digit in enumerate(user_context["otp"].strip()[:6], 1):
        try:
            f = page.locator(f"//input[@aria-label='Digit {i}']")
            if f.is_visible(): f.fill(digit); time.sleep(0.2)
        except: pass

    time.sleep(5)
    take_screenshot(page, "🔢 OTP submit")
    context.storage_state(path="state.json")
    msg("✅ *LOGIN SUCCESSFUL!*\n\n🍪 Session save!\nLink bhejein 🚀")
    user_context["state"] = "IDLE"
    return True

def check_login_status():
    msg("🔍 Jazz Drive login check...")
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
                msg("✅ *LOGIN VALID!*\n\n🚀 Link bhejein!")
        except Exception as e:
            msg(f"❌ Error:\n`{str(e)[:150]}`")
        finally:
            browser.close()

# ═══════════════════════════════════════
# 📊 JazzDrive Storage Check
# ═══════════════════════════════════════
def check_storage():
    msg("📊 Storage check ho raha hai...")
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

            storage_text = page.inner_text("body")
            # Storage info dhundo
            match = re.search(r'(\d+\.?\d*)\s*(GB|MB)\s*of\s*(\d+\.?\d*)\s*(GB|MB)', storage_text)
            if match:
                msg(f"💾 *Storage Info:*\n\n📦 Used: {match.group(1)} {match.group(2)}\n📁 Total: {match.group(3)} {match.group(4)}")
            else:
                take_screenshot(page, "📊 Storage info")
        except Exception as e:
            msg(f"❌ Error:\n`{str(e)[:150]}`")
        finally:
            browser.close()

# ═══════════════════════════════════════
# 📋 JazzDrive Files List
# ═══════════════════════════════════════
def list_files():
    msg("📋 Files list ho rahi hai...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 720},
            storage_state="state.json" if os.path.exists("state.json") else None
        )
        page = ctx.new_page()
        try:
            page.goto("https://cloud.jazzdrive.com.pk/#/folders", wait_until="networkidle", timeout=90000)
            time.sleep(3)
            take_screenshot(page, "📋 JazzDrive Files")
        except Exception as e:
            msg(f"❌ Error:\n`{str(e)[:150]}`")
        finally:
            browser.close()

# ═══════════════════════════════════════
# 🤖 Bot Commands
# ═══════════════════════════════════════
@bot.message_handler(commands=["start"])
def welcome(m):
    msg(
        "🤖 *JAZZ DRIVE BOT v2*\n\n"
        "📎 Direct/M3U8 link → Upload\n"
        "📦 ZIP/RAR → Extract → Upload\n"
        "🌐 FB/IG/TikTok/Twitter → Upload\n\n"
        "─────────────────────\n"
        "⚙️ *Commands:*\n"
        "/checklogin — Login check\n"
        "/status — Queue status\n"
        "/pause — Queue pause\n"
        "/resume — Queue resume\n"
        "/cancel — Current task cancel\n"
        "/clear — Queue clear\n"
        "/storage — JazzDrive storage\n"
        "/files — JazzDrive files\n"
        "/cmd — Server command",
        reply_markup=types.ReplyKeyboardRemove()
    )

@bot.message_handler(commands=["checklogin"])
def cmd_check(m):
    threading.Thread(target=check_login_status, daemon=True).start()

@bot.message_handler(commands=["storage"])
def cmd_storage(m):
    threading.Thread(target=check_storage, daemon=True).start()

@bot.message_handler(commands=["files"])
def cmd_files(m):
    threading.Thread(target=list_files, daemon=True).start()

@bot.message_handler(commands=["status"])
def cmd_status(m):
    global queue_paused
    icon = "🟢" if is_working else "🔴"
    pause_status = "⏸️ Paused" if queue_paused else "▶️ Running"
    cookie = "✅" if os.path.exists("state.json") else "❌"
    current = current_task["name"] or "Nothing"
    msg(
        f"📊 *BOT STATUS*\n\n"
        f"{icon} *State:* {'Working' if is_working else 'Idle'}\n"
        f"🔄 *Queue:* {task_queue.qsize()} pending\n"
        f"{pause_status}\n"
        f"🍪 *Session:* {cookie}\n"
        f"📌 *Current:* `{current[:40]}`"
    )

@bot.message_handler(commands=["pause"])
def cmd_pause(m):
    global queue_paused
    queue_paused = True
    msg("⏸️ *Queue paused!*\nCurrent task complete hogi phir ruk jaega.\n\n/resume se dobara shuru karo.")

@bot.message_handler(commands=["resume"])
def cmd_resume(m):
    global queue_paused, is_working
    queue_paused = False
    msg("▶️ *Queue resumed!*")
    with worker_lock:
        if not is_working and not task_queue.empty():
            is_working = True
            threading.Thread(target=worker_loop, daemon=True).start()

@bot.message_handler(commands=["cancel"])
def cmd_cancel(m):
    current_task["name"] = None
    msg("⛔ *Current task cancel ho jaega.*\nQueue ka agla task shuru hoga.")

@bot.message_handler(commands=["clear"])
def cmd_clear(m):
    count = task_queue.qsize()
    while not task_queue.empty():
        try: task_queue.get_nowait()
        except: break
    msg(f"🗑️ *Queue cleared!*\n{count} tasks remove kiye gaye.")

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

    if text.startswith("http"):
        # Multiple links support - har line ek link
        links = [l.strip() for l in text.split('\n') if l.strip().startswith('http')]
        if not links: links = [text]

        for link in links:
            if is_zip_url(link):
                task_queue.put({"link": link, "type": "zip"})
            elif is_social(link):
                task_queue.put({"link": link, "type": "social"})
            else:
                task_queue.put({"link": link, "type": "direct"})

        bot.reply_to(m,
            f"✅ *{len(links)} link(s) add!*\n"
            f"📋 Queue: *{task_queue.qsize()}*",
            parse_mode="Markdown")

        with worker_lock:
            if not is_working:
                is_working = True
                threading.Thread(target=worker_loop, daemon=True).start()
    else:
        bot.reply_to(m, "ℹ️ Link bhejein ya /start dekho")

# ═══════════════════════════════════════
# 🔄 Worker
# ═══════════════════════════════════════
def worker_loop():
    global is_working, queue_paused
    try:
        while not task_queue.empty():
            # Pause check
            while queue_paused:
                time.sleep(5)

            item = task_queue.get()
            short = item["link"][:50] + "..." if len(item["link"]) > 50 else item["link"]
            current_task["name"] = short
            msg(f"🎬 *PROCESSING...*\n\n🔗 `{short}`")
            try:
                if item["type"] == "zip":
                    process_zip(item["link"])
                elif item["type"] == "social":
                    process_social(item["link"])
                else:
                    process_direct(item["link"])
            except Exception as e:
                msg(f"❌ Error:\n`{str(e)[:150]}`")
            finally:
                task_queue.task_done()
                current_task["name"] = None

        msg("✅ *QUEUE COMPLETE!*\n\nAgla link bhejein 😊")
    except Exception as e:
        msg(f"⚠️ Worker crash:\n`{str(e)[:150]}`")
    finally:
        with worker_lock:
            is_working = False

# ═══════════════════════════════════════
# ⬇️ Download Helper
# ═══════════════════════════════════════
def download_file(url, out_path):
    # M3U8
    if is_m3u8(url):
        if not out_path.endswith('.mp4'):
            out_path = out_path.rsplit('.', 1)[0] + '.mp4'
        try:
            subprocess.run([
                "ffmpeg", "-y", "-user_agent", WEB_UA,
                "-i", url, "-c", "copy", "-bsf:a", "aac_adtstoasc", out_path
            ], capture_output=True, timeout=600)
            if file_ok(out_path): return out_path
        except: pass
        return None

    # aria2c
    try:
        out_dir = os.path.dirname(out_path)
        out_name = os.path.basename(out_path)
        subprocess.run([
            "aria2c", "-x", "16", "-s", "16", "-k", "1M",
            f"--user-agent={WEB_UA}", "--allow-overwrite=true",
            "-d", out_dir, "-o", out_name, url
        ], capture_output=True, timeout=300)
        if file_ok(out_path): return out_path
    except: pass

    # curl
    try:
        subprocess.run([
            "curl", "-L", "--retry", "3", "--max-time", "300",
            "-H", f"User-Agent: {WEB_UA}", "-o", out_path, url
        ], timeout=300)
        if file_ok(out_path): return out_path
    except: pass

    # requests
    try:
        with requests.get(url, headers={"User-Agent": WEB_UA}, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk: f.write(chunk)
        if file_ok(out_path): return out_path
    except: pass

    return None

# ═══════════════════════════════════════
# 🌐 Social Media Download
# ═══════════════════════════════════════
def process_social(url):
    ts = int(time.time())
    out_path = f"/tmp/{ts}.%(ext)s"
    ua = ANDROID_UA if "youtu" in url else WEB_UA

    msg(f"🌐 *Social media link detect hua!*\n⬇️ Downloading...")

    result = subprocess.run([
        "yt-dlp", "--no-warnings", "--no-playlist",
        "--user-agent", ua,
        "-f", "best[height<=720]/best",
        "--merge-output-format", "mp4",
        "-o", out_path, url
    ], capture_output=True, text=True, timeout=300)

    import glob
    files = glob.glob(f"/tmp/{ts}.*")
    if not files:
        msg(f"❌ Download fail!\n`{result.stderr[:150]}`")
        return

    fp = files[0]
    sz = os.path.getsize(fp)/(1024*1024)
    msg(f"✅ Downloaded! *{sz:.1f} MB*\n☁️ Upload ho raha hai...")
    jazz_drive_upload(fp)
    clean(fp)

# ═══════════════════════════════════════
# 📦 ZIP Process
# ═══════════════════════════════════════
def process_zip(url):
    zip_path = "/tmp/series_download.zip"
    extract_dir = "/tmp/series_extracted"
    clean(zip_path)
    if os.path.exists(extract_dir):
        import shutil; shutil.rmtree(extract_dir)
    os.makedirs(extract_dir, exist_ok=True)

    msg("⬇️ *ZIP download ho raha hai...*")
    result = download_file(url, zip_path)

    if not result:
        msg("❌ ZIP download fail!")
        return

    sz = os.path.getsize(zip_path)/(1024*1024)
    msg(f"✅ *{sz:.1f} MB* downloaded!\n📂 Extract ho raha hai...")

    try:
        if zipfile.is_zipfile(zip_path):
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
        else:
            subprocess.run(["unzip", "-o", zip_path, "-d", extract_dir], timeout=120)
    except Exception as e:
        msg(f"❌ Extract fail:\n`{str(e)[:100]}`")
        return

    clean(zip_path)

    video_files = []
    for root, dirs, files in os.walk(extract_dir):
        for f in sorted(files):
            if is_video_file(f):
                video_files.append(os.path.join(root, f))

    if not video_files:
        msg("❌ ZIP mein koi video nahi mili!")
        return

    msg(
        f"✅ *{len(video_files)} episodes mile!*\n\n" +
        "\n".join([f"• {os.path.basename(v)}" for v in video_files[:10]]) +
        ("\n..." if len(video_files) > 10 else "") +
        "\n\n☁️ *Upload shuru...*"
    )

    for i, vp in enumerate(video_files, 1):
        fname = os.path.basename(vp)
        fsize = os.path.getsize(vp)/(1024*1024)
        msg(f"📤 *Episode {i}/{len(video_files)}*\n📁 {fname}\n📦 {fsize:.1f} MB")
        jazz_drive_upload(vp)
        clean(vp)
        msg(f"✅ *Episode {i}/{len(video_files)} done!*")

    import shutil; shutil.rmtree(extract_dir, ignore_errors=True)
    msg(f"🎉 *SERIES COMPLETE!*\n✅ {len(video_files)} episodes uploaded!")

# ═══════════════════════════════════════
# 📎 Direct Link
# ═══════════════════════════════════════
def process_direct(url):
    out_name = url.split("/")[-1].split("?")[0] or "file.mp4"
    out_name = safe_fn(out_name)
    if "." not in out_name: out_name += ".mp4"
    if ".m3u8" in out_name.lower():
        out_name = re.sub(r'[.]av[0-9]+', '', out_name.lower().replace(".m3u8", ".mp4"))
    out_path = f"/tmp/{out_name}"
    clean(out_path)

    msg(f"⬇️ *Downloading...*\n📁 `{out_name}`")
    result = download_file(url, out_path)
    if not result:
        msg("❌ Download fail! Fresh link bhejein.")
        return

    sz = os.path.getsize(result)/(1024*1024)
    msg(f"✅ *{sz:.1f} MB* downloaded!\n☁️ Upload ho raha hai...")
    jazz_drive_upload(result)
    clean(result)

# ═══════════════════════════════════════
# ☁️ JazzDrive Upload
# ═══════════════════════════════════════
def jazz_drive_upload(filename):
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
                msg("⚠️ Session expire! Login karo...")
                ok = do_login(page, ctx)
                if not ok:
                    msg("❌ Login fail.")
                    return
                page.goto("https://cloud.jazzdrive.com.pk/", wait_until="networkidle", timeout=90000)
                time.sleep(3)

            ctx.storage_state(path="state.json")
            abs_path = os.path.abspath(filename)

            try:
                page.evaluate("document.querySelectorAll('header button').forEach(b => { if(b.innerHTML.includes('svg') || b.innerHTML.includes('upload')) b.click(); })")
                time.sleep(2)
            except: pass

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

            sz = os.path.getsize(filename)/(1024*1024)
            wait_sec = max(60, int(sz * 4))
            msg(f"⏳ Uploading `{os.path.basename(filename)}`... (~{wait_sec}s)")

            elapsed = 0
            upload_done = False
            while elapsed < wait_sec:
                time.sleep(30)
                elapsed += 30
                try:
                    if page.locator("text=Uploads completed").is_visible():
                        msg(f"✅ Upload complete! ({elapsed}s)")
                        upload_done = True
                        break
                except: pass
                if elapsed % 60 == 0:
                    take_screenshot(page, f"📸 {elapsed}s /
