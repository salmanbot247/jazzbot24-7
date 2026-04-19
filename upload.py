import os, re, time, threading, queue, subprocess, requests, zipfile, telebot
from telebot import types
from playwright.sync_api import sync_playwright

TOKEN = "8485872476:AAE-mNl9roDNnwDQV16M2WREkf479kKCOzs"
CHAT_ID = 7144917062
bot = telebot.TeleBot(TOKEN)

task_queue = queue.Queue()
is_working = False
worker_lock = threading.Lock()
user_context = {"state": "IDLE", "number": None, "otp": None, "pending_link": None, "pending_type": None, "pending_quality": "1080"}

# Colab se response receive karne ke liye
colab_response = {"value": None, "event": threading.Event()}

BROWSER_ARGS = ["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage", "--single-process"]
WEB_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

VIDEO_EXTS = [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts"]
ZIP_EXTS = [".zip", ".rar", ".7z", ".tar", ".gz"]

def is_zip_url(link):
    return any(link.lower().endswith(ext) or ext in link.lower() for ext in ZIP_EXTS)

def is_video_file(filename):
    return any(filename.lower().endswith(ext) for ext in VIDEO_EXTS)

def is_m3u8(url):
    return '.m3u8' in url.lower()

def safe_filename(t):
    return re.sub(r'[\\/*?:"<>|]', '', t).strip().replace(' ', '_')[:80]

def msg(text, **kw):
    try:
        bot.send_message(CHAT_ID, text, **kw)
    except Exception as e:
        try:
            clean_text = re.sub(r'[*_`\[\]]', '', text)
            bot.send_message(CHAT_ID, clean_text)
        except: pass

def file_ok(f, min_mb=0.5):
    return os.path.exists(f) and os.path.getsize(f)/(1024*1024) >= min_mb

def clean(f):
    if os.path.exists(f): os.remove(f)

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
    msg("LOGIN REQUIRED\n\nJazz number bhejein\nFormat: 03XXXXXXXXX")
    user_context["state"] = "WAITING_FOR_NUMBER"
    for _ in range(500):
        if user_context["state"] == "NUMBER_RECEIVED": break
        time.sleep(1)
    else:
        msg("Timeout! Task cancel.")
        return False

    page.locator("#msisdn").fill(user_context["number"])
    time.sleep(1)
    page.locator("#signinbtn").first.click()
    time.sleep(3)
    take_screenshot(page, "Number submit")
    msg("Number accept!\n\nOTP bhejein:")
    user_context["state"] = "WAITING_FOR_OTP"
    for _ in range(500):
        if user_context["state"] == "OTP_RECEIVED": break
        time.sleep(1)
    else:
        msg("Timeout! Task cancel.")
        return False

    for i, digit in enumerate(user_context["otp"].strip()[:6], 1):
        try:
            f = page.locator(f"//input[@aria-label='Digit {i}']")
            if f.is_visible(): f.fill(digit); time.sleep(0.2)
        except: pass

    time.sleep(5)
    take_screenshot(page, "OTP submit")
    context.storage_state(path="state.json")
    msg("LOGIN SUCCESSFUL!\n\nSession save!\nLink bhejein")
    user_context["state"] = "IDLE"
    return True

def check_login_status():
    msg("Jazz Drive login check...")
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
                msg("Session expire!\nLogin karte hain...")
                do_login(page, ctx)
            else:
                msg("LOGIN VALID!\n\nLink bhejein!")
        except Exception as e:
            msg(f"Error: {str(e)[:150]}")
        finally:
            browser.close()

# ═══════════════════════════════════════
# 🤖 Bot Commands
# ═══════════════════════════════════════
@bot.message_handler(commands=["start"])
def welcome(m):
    msg(
        "JAZZ DRIVE BOT\n\n"
        "Direct link - Upload\n"
        "ZIP/RAR link - Extract - Sab episodes upload\n\n"
        "/checklogin - Login status\n"
        "/status - Queue status\n"
        "/pause - Queue pause\n"
        "/resume - Queue resume\n"
        "/cancel - Task cancel\n"
        "/clear - Queue clear\n"
        "/cmd - Server command"
    )

@bot.message_handler(commands=["checklogin"])
def cmd_check(m):
    threading.Thread(target=check_login_status, daemon=True).start()

@bot.message_handler(commands=["status"])
def cmd_status(m):
    icon = "Working" if is_working else "Idle"
    cookie = "Active" if os.path.exists("state.json") else "None"
    msg(f"BOT STATUS\n\nState: {icon}\nQueue: {task_queue.qsize()}\nSession: {cookie}")

@bot.message_handler(commands=["pause"])
def cmd_pause(m):
    global queue_paused
    queue_paused = True
    msg("Queue paused!\n/resume se dobara shuru karo.")

@bot.message_handler(commands=["resume"])
def cmd_resume(m):
    global queue_paused, is_working
    queue_paused = False
    msg("Queue resumed!")
    with worker_lock:
        if not is_working and not task_queue.empty():
            is_working = True
            threading.Thread(target=worker_loop, daemon=True).start()

@bot.message_handler(commands=["cancel"])
def cmd_cancel(m):
    msg("Current task cancel hoga. Agla task shuru hoga.")

@bot.message_handler(commands=["clear"])
def cmd_clear(m):
    count = task_queue.qsize()
    while not task_queue.empty():
        try: task_queue.get_nowait()
        except: break
    msg(f"Queue cleared! {count} tasks remove kiye.")

@bot.message_handler(commands=["cmd"])
def cmd_shell(m):
    try:
        c = m.text.replace("/cmd ", "", 1).strip()
        out = subprocess.check_output(c, shell=True, stderr=subprocess.STDOUT).decode()
        bot.reply_to(m, f"{out[:4000]}")
    except subprocess.CalledProcessError as e:
        bot.reply_to(m, f"Error:\n{e.output.decode()[:3000]}")
    except Exception as e:
        bot.reply_to(m, f"Error: {e}")

@bot.message_handler(func=lambda m: True)
def handle(m):
    global is_working
    text = (m.text or "").strip()

    # Colab ka response aaya
    if text.startswith("[YT_RES]") or text.startswith("[YT_ERR]"):
        colab_response["value"] = text
        colab_response["event"].set()
        return

    if user_context["state"] == "WAITING_FOR_NUMBER":
        user_context["number"] = text
        user_context["state"] = "NUMBER_RECEIVED"
        bot.reply_to(m, "Number receive hua...")
        return

    if user_context["state"] == "WAITING_FOR_OTP":
        user_context["otp"] = text
        user_context["state"] = "OTP_RECEIVED"
        bot.reply_to(m, "OTP receive hua...")
        return

    if user_context["state"] == "WAITING_FOR_YT_QUALITY":
        q_map = {"1": "2160", "2": "1440", "3": "1080", "4": "720", "5": "480", "6": "360"}
        user_context["pending_quality"] = q_map.get(text.strip(), "1080")
        user_context["state"] = "WAITING_FOR_FOLDER"
        bot.reply_to(m, f"Quality: {user_context['pending_quality']}p ✅\n\n📁 Folder name bhejein\n(ya 'root' likhein)")
        return

    if user_context["state"] == "WAITING_FOR_FOLDER":
        folder_name = text if text.strip().upper() != "ROOT" and text.strip() != "" else ""
        link = user_context["pending_link"]
        ltype = user_context["pending_type"]
        user_context["pending_link"] = None
        user_context["pending_type"] = None
        user_context["state"] = "IDLE"
        task_queue.put({"link": link, "type": ltype, "folder": folder_name, "quality": user_context.get("pending_quality", "1080")})
        folder_info = f"Folder: {folder_name}" if folder_name else "Folder: Root (default)"
        bot.reply_to(m, f"Task add!\n{folder_info}\nQueue: {task_queue.qsize()}")
        with worker_lock:
            if not is_working:
                is_working = True
                threading.Thread(target=worker_loop, daemon=True).start()
        return

    if text.startswith("http"):
        is_yt = "youtube.com" in text or "youtu.be" in text
        ltype = "youtube" if is_yt else ("zip" if is_zip_url(text) else "direct")
        user_context["pending_link"] = text
        user_context["pending_type"] = ltype

        if is_yt:
            user_context["state"] = "WAITING_FOR_YT_QUALITY"
            bot.reply_to(m, "YouTube link mila!\n\n🎬 Quality choose karo:\n1. 4K (2160p)\n2. 2K (1440p)\n3. Full HD (1080p)\n4. HD (720p)\n5. SD (480p)\n6. Low (360p)")
        else:
            user_context["state"] = "WAITING_FOR_FOLDER"
            bot.reply_to(m, f"{'ZIP/RAR' if ltype == 'zip' else 'Direct'} link mila!\n\n📁 Folder name bhejein\n(ya 'root' likhein agar koi folder nahi chahiye)")

    else:
        bot.reply_to(m, "Link bhejein ya /start dekho")

# ═══════════════════════════════════════
# 🔄 Worker
# ═══════════════════════════════════════
queue_paused = False

def worker_loop():
    global is_working, queue_paused
    try:
        while not task_queue.empty():
            while queue_paused:
                time.sleep(5)
            item = task_queue.get()
            short = item["link"][:60]
            msg(f"PROCESSING...\n\n{short}")
            try:
                if item["type"] == "zip":
                    process_zip(item["link"], item.get("folder", ""))
                elif item["type"] == "youtube":
                    process_youtube(item["link"], item.get("quality", "1080"), item.get("folder", ""))
                else:
                    process_direct(item["link"], item.get("folder", ""))
            except Exception as e:
                msg(f"Error: {str(e)[:150]}")
            finally:
                task_queue.task_done()
        msg("QUEUE COMPLETE!\n\nAgla link bhejein")
    except Exception as e:
        msg(f"Worker crash: {str(e)[:150]}")
    finally:
        with worker_lock:
            is_working = False

# ═══════════════════════════════════════
# ⬇️ MULTI-ENGINE DOWNLOADER (NEW METHODS)
# ═══════════════════════════════════════
def download_file(url, out_path):
    last_error = "Unknown Error"
    clean(out_path)
    
    # Engine 1: FFmpeg (For live streams/m3u8)
    if is_m3u8(url):
        if not out_path.endswith('.mp4'): out_path = out_path.rsplit('.', 1)[0] + '.mp4'
        msg("⚙️ Engine 1: FFmpeg Stream Downloader...")
        try:
            subprocess.run(["ffmpeg", "-y", "-user_agent", WEB_UA, "-i", url, "-c", "copy", "-bsf:a", "aac_adtstoasc", out_path], capture_output=True, timeout=600)
            if file_ok(out_path): return out_path, "Success"
        except Exception as e: last_error = f"FFmpeg Error: {str(e)}"
        return None, last_error

    # Engine 2: Advanced cURL (Spoofing)
    msg("⚙️ Engine 2: Advanced cURL...")
    try:
        subprocess.run([
            "curl", "-L", "-k", "--retry", "3",
            "-H", f"User-Agent: {WEB_UA}",
            "-H", "Accept-Language: en-US,en;q=0.9",
            "-H", "Referer: https://www.google.com/",
            "-o", out_path, url
        ], timeout=300)
        if file_ok(out_path, min_mb=0.1): return out_path, "Success"
    except Exception as e: last_error = f"cURL error: {e}"

    clean(out_path)

    # Engine 3: WGET (Linux Native)
    msg("⚙️ Engine 3: Wget Downloader...")
    try:
        subprocess.run([
            "wget", "-q", "--tries=3", "--timeout=120",
            "--header", f"User-Agent: {WEB_UA}",
            "--header", "Referer: https://www.google.com/",
            "-O", out_path, url
        ], timeout=300)
        if file_ok(out_path, min_mb=0.1): return out_path, "Success"
    except Exception as e: last_error = f"Wget error: {e}"

    clean(out_path)

    # Engine 4: Python Requests
    msg("⚙️ Engine 4: Requests Fallback...")
    try:
        headers = {"User-Agent": WEB_UA, "Referer": "https://www.google.com/"}
        with requests.get(url, headers=headers, stream=True, timeout=60) as r:
            r.raise_for_status() 
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk: f.write(chunk)
        if file_ok(out_path, min_mb=0.1): 
            return out_path, "Success"
        else:
            last_error = "Server ne access deny kardia (IP Mismatch / Blocked)"
    except Exception as e:
        last_error = f"Requests Error: {str(e)}"

    return None, last_error

# ═══════════════════════════════════════
# 📦 ZIP Process
# ═══════════════════════════════════════
def process_zip(url, folder_name=""):
    import shutil
    zip_path = "/tmp/series_download.zip"
    extract_dir = "/tmp/series_extracted"
    clean(zip_path)
    if os.path.exists(extract_dir): shutil.rmtree(extract_dir)
    os.makedirs(extract_dir, exist_ok=True)

    msg("ZIP download ho raha hai...")
    result, error_msg = download_file(url, zip_path)

    if not result or not file_ok(zip_path):
        msg(f"ZIP download fail!\nReason: {error_msg}")
        return

    sz = os.path.getsize(zip_path)/(1024*1024)
    msg(f"Downloaded! {sz:.1f} MB\nExtracting...")

    try:
        if zipfile.is_zipfile(zip_path):
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
        else:
            subprocess.run(["unzip", "-o", zip_path, "-d", extract_dir], timeout=120)
    except Exception as e:
        msg(f"Extract fail: {str(e)[:100]}")
        return

    clean(zip_path)

    video_files = []
    for root, dirs, files in os.walk(extract_dir):
        for f in sorted(files):
            if is_video_file(f):
                video_files.append(os.path.join(root, f))

    if not video_files:
        msg("ZIP mein koi video nahi mili!")
        return

    list_text = "\n".join([f"{i+1}. {os.path.basename(v)}" for i, v in enumerate(video_files[:10])])
    if len(video_files) > 10: list_text += "\n..."
    msg(f"{len(video_files)} episodes mile:\n\n{list_text}\n\nUpload shuru...")

    for i, video_path in enumerate(video_files, 1):
        fname = os.path.basename(video_path)
        fsize = os.path.getsize(video_path)/(1024*1024)
        msg(f"Episode {i}/{len(video_files)}\n{fname}\n{fsize:.1f} MB")
        jazz_drive_upload(video_path, folder_name)
        clean(video_path)
        msg(f"Episode {i}/{len(video_files)} done!")

    shutil.rmtree(extract_dir, ignore_errors=True)
    msg(f"SERIES COMPLETE!\n{len(video_files)} episodes uploaded!")

# ═══════════════════════════════════════
# 🎬 YOUTUBE VIA COLAB
# ═══════════════════════════════════════
def download_youtube_via_colab(yt_url, quality, timeout=300):
    msg(f"📡 Colab ko request bhej raha hoon...\n⏳ Max wait: {timeout//60} min")

    # Event reset karo
    colab_response["value"] = None
    colab_response["event"].clear()

    # Colab ko request bhejo
    bot.send_message(CHAT_ID, f"[YT_REQ] {quality}|{yt_url}")

    # Colab ke response ka wait karo
    got_response = colab_response["event"].wait(timeout=timeout)

    if not got_response:
        msg("⏰ Colab ne jawab nahi diya! Colab poller chalu hai?")
        return None

    response = colab_response["value"]

    if response.startswith("[YT_ERR]"):
        msg(f"❌ Colab error: {response}")
        return None

    cdn_urls = response.replace("[YT_RES] ", "").split("|||")
    cdn_urls = [u for u in cdn_urls if u.startswith("http")]

    if not cdn_urls:
        msg("❌ CDN URL empty aaya")
        return None

    msg(f"✅ CDN URL mili! Download shuru ({len(cdn_urls)} stream)...")
    return download_from_cdn(cdn_urls)

def download_from_cdn(cdn_urls):
    os.makedirs("/tmp/yt_downloads", exist_ok=True)
    output = f"/tmp/yt_downloads/yt_{int(time.time())}.mp4"

    try:
        if len(cdn_urls) >= 2:
            # Video + Audio alag — ffmpeg se merge
            cmd = ["ffmpeg", "-y",
                   "-i", cdn_urls[0],
                   "-i", cdn_urls[1],
                   "-c", "copy", output]
        else:
            cmd = ["ffmpeg", "-y", "-i", cdn_urls[0], "-c", "copy", output]

        subprocess.run(cmd, capture_output=True, timeout=3600)

        if os.path.exists(output) and os.path.getsize(output) > 1024:
            size = os.path.getsize(output) / (1024 * 1024)
            msg(f"✅ Download complete! {size:.1f} MB")
            return output
        else:
            msg("❌ ffmpeg download fail")
            return None
    except Exception as e:
        msg(f"❌ CDN download error: {str(e)[:150]}")
        return None

def process_youtube(url, quality, folder_name=""):
    msg(f"🎬 YouTube: {url[:60]}\nQuality: {quality}p")
    result = download_youtube_via_colab(url, quality)
    if result:
        sz = os.path.getsize(result) / (1024 * 1024)
        msg(f"JazzDrive upload ho raha hai... ({sz:.1f} MB)")
        jazz_drive_upload(result, folder_name)
        clean(result)
    else:
        msg("❌ YouTube download fail!\nColab poller chalu karo phir dobara bhejo.")

# ═══════════════════════════════════════
# 📎 Direct Link Process
# ═══════════════════════════════════════
def process_direct(url, folder_name=""):
    out_name = url.split("/")[-1].split("?")[0] or "file.mp4"
    out_name = safe_filename(out_name)
    if "." not in out_name: out_name += ".mp4"
    if ".m3u8" in out_name.lower():
        out_name = re.sub(r'[.]av[0-9]+', '', out_name.lower().replace(".m3u8", ".mp4"))
    out_path = f"/tmp/{out_name}"
    clean(out_path)

    msg(f"Downloading...\n{out_name[:60]}")
    result, error_msg = download_file(url, out_path)

    if not result:
        msg(f"❌ Download fail!\nReason: {error_msg}\nFresh link bhejein.")
        return

    sz = os.path.getsize(result)/(1024*1024)
    msg(f"✅ Downloaded! {sz:.1f} MB\nJazzDrive upload ho raha hai...")
    jazz_drive_upload(result, folder_name)
    clean(result)

# ═══════════════════════════════════════
# ☁️ JazzDrive Upload
# ═══════════════════════════════════════
def jazz_drive_upload(filename, folder_name=""):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 720},
            storage_state="state.json" if os.path.exists("state.json") else None
        )
        page = ctx.new_page()
        try:
            page.goto("https://cloud.jazzdrive.com.pk/#folders", wait_until="networkidle", timeout=90000)
            time.sleep(5)

            if page.locator("#msisdn").is_visible():
                msg("Session expire! Login karo...")
                ok = do_login(page, ctx)
                if not ok: msg("Login fail."); return
                page.goto("https://cloud.jazzdrive.com.pk/#folders", wait_until="networkidle", timeout=90000)
                time.sleep(5)

            # 📁 Folder navigate karein agar diya gaya ho
            if folder_name and folder_name.strip().upper() != "ROOT" and folder_name.strip() != "":
                try:
                    page.get_by_text(folder_name.strip(), exact=False).first.click(timeout=5000)
                    time.sleep(3)
                    msg(f"📁 Folder open: {folder_name}")
                except:
                    msg(f"⚠️ Folder '{folder_name}' nahi mila, root mein upload ho raha hai...")

            ctx.storage_state(path="state.json")
            abs_path = os.path.abspath(filename)

            # Upload button click (Colab wala XPath)
            for sel in ["xpath=/html/body/div/div/div[1]/div/header/div/div/button", "button:has-text('Upload')"]:
                try: page.click(sel, timeout=5000); break
                except: pass

            page.wait_for_selector("input[type='file']", state="attached")
            with page.expect_file_chooser() as fc_info:
                page.click
