import os, re, time, threading, queue, subprocess, requests, zipfile, telebot
import yt_dlp
from playwright.sync_api import sync_playwright

BROWSER_ARGS = ["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage", "--single-process"]
WEB_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
VIDEO_EXTS = [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts"]
ZIP_EXTS = [".zip", ".rar", ".7z", ".tar", ".gz"]
MAX_SIZE_MB = 1990

BOTS = [
    {"token": "8350099407:AAEAX6NzIykESMj50CnduDAwngfHW1ER-oM", "chat_id": 7144917062, "state_file": "state1.json"},
]

def is_youtube(url):
    return any(x in url.lower() for x in [
        "youtube.com/watch", "youtu.be/", "youtube.com/playlist",
        "youtube.com/shorts", "m.youtube.com"
    ])

def is_zip_url(link):
    return any(link.lower().endswith(ext) or ext in link.lower() for ext in ZIP_EXTS)
def is_video_file(f):
    return any(f.lower().endswith(ext) for ext in VIDEO_EXTS)
def is_m3u8(url):
    return '.m3u8' in url.lower()
def safe_filename(t):
    return re.sub(r'[\\/*?:"<>|]', '', t).strip().replace(' ', '_')[:80]
def file_ok(f, min_mb=0.5):
    return os.path.exists(f) and os.path.getsize(f)/(1024*1024) >= min_mb
def clean(f):
    if os.path.exists(f): os.remove(f)


class BotInstance:
    def __init__(self, token, chat_id, state_file):
        self.token = token
        self.chat_id = chat_id
        self.state_file = state_file
        self.bot = telebot.TeleBot(token)
        self.task_queue = queue.Queue()
        self.is_working = False
        self.worker_lock = threading.Lock()
        self.queue_paused = False
        self.ctx = {
            "state": "IDLE",
            "number": None,
            "otp": None,
            "pending_link": None,
            "pending_type": None,
            "pending_quality": "1080",
            "pending_folder": ""
        }

    def msg(self, text):
        try:
            self.bot.send_message(self.chat_id, text)
        except:
            try: self.bot.send_message(self.chat_id, re.sub(r'[*_`\[\]]', '', text))
            except: pass

    def send_photo(self, path, caption=""):
        try:
            with open(path, "rb") as f:
                self.bot.send_photo(self.chat_id, f, caption=caption)
        except: pass

    def take_screenshot(self, page, caption="📸"):
        try:
            page.screenshot(path="s.png")
            self.send_photo("s.png", caption)
            os.remove("s.png")
        except: pass

    def do_login(self, page, context):
        self.msg("LOGIN REQUIRED\n\nJazz number bhejein\nFormat: 03XXXXXXXXX")
        self.ctx["state"] = "WAITING_FOR_NUMBER"
        for _ in range(500):
            if self.ctx["state"] == "NUMBER_RECEIVED": break
            time.sleep(1)
        else:
            self.msg("Timeout! Task cancel.")
            return False
        page.locator("#msisdn").fill(self.ctx["number"])
        time.sleep(1)
        page.locator("#signinbtn").first.click()
        time.sleep(3)
        self.take_screenshot(page, "Number submit")
        self.msg("Number accept!\n\nOTP bhejein:")
        self.ctx["state"] = "WAITING_FOR_OTP"
        for _ in range(500):
            if self.ctx["state"] == "OTP_RECEIVED": break
            time.sleep(1)
        else:
            self.msg("Timeout! Task cancel.")
            return False
        for i, digit in enumerate(self.ctx["otp"].strip()[:6], 1):
            try:
                f = page.locator(f"//input[@aria-label='Digit {i}']")
                if f.is_visible(): f.fill(digit); time.sleep(0.2)
            except: pass
        time.sleep(5)
        self.take_screenshot(page, "OTP submit")
        context.storage_state(path=self.state_file)
        self.msg("LOGIN SUCCESSFUL!\n\nSession save!\nLink bhejein")
        self.ctx["state"] = "IDLE"
        return True

    def check_login_status(self):
        self.msg("Jazz Drive login check...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
            ctx = browser.new_context(viewport={"width": 1280, "height": 720},
                storage_state=self.state_file if os.path.exists(self.state_file) else None)
            page = ctx.new_page()
            try:
                page.goto("https://cloud.jazzdrive.com.pk/", wait_until="networkidle", timeout=90000)
                time.sleep(3)
                if page.locator("#msisdn").is_visible():
                    self.msg("Session expire!\nLogin karte hain...")
                    self.do_login(page, ctx)
                else:
                    self.msg("LOGIN VALID!\n\nLink bhejein!")
            except Exception as e:
                self.msg(f"Error: {str(e)[:150]}")
            finally:
                browser.close()

    def download_file(self, url, out_path):
        last_error = "Unknown"
        clean(out_path)
        if is_m3u8(url):
            if not out_path.endswith('.mp4'): out_path = out_path.rsplit('.', 1)[0] + '.mp4'
            try:
                subprocess.run(["ffmpeg", "-y", "-user_agent", WEB_UA, "-i", url, "-c", "copy", "-bsf:a", "aac_adtstoasc", out_path], capture_output=True, timeout=600)
                if file_ok(out_path): return out_path, "Success"
            except Exception as e: last_error = str(e)
            return None, last_error
        try:
            subprocess.run(["curl", "-L", "-k", "--retry", "3", "-H", f"User-Agent: {WEB_UA}", "-H", "Referer: https://www.google.com/", "-o", out_path, url], timeout=300)
            if file_ok(out_path, min_mb=0.1): return out_path, "Success"
        except Exception as e: last_error = str(e)
        clean(out_path)
        try:
            subprocess.run(["wget", "-q", "--tries=3", "--timeout=120", "--header", f"User-Agent: {WEB_UA}", "-O", out_path, url], timeout=300)
            if file_ok(out_path, min_mb=0.1): return out_path, "Success"
        except Exception as e: last_error = str(e)
        clean(out_path)
        try:
            with requests.get(url, headers={"User-Agent": WEB_UA}, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk: f.write(chunk)
            if file_ok(out_path, min_mb=0.1): return out_path, "Success"
        except Exception as e: last_error = str(e)
        return None, last_error

    def split_video(self, filepath):
        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        if size_mb <= MAX_SIZE_MB:
            return [filepath]
        self.msg(f"File {size_mb:.0f}MB — splitting...")
        base = filepath.rsplit(".", 1)[0]
        ext = filepath.rsplit(".", 1)[-1]
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", filepath],
            capture_output=True, text=True)
        try:
            total_duration = float(result.stdout.strip())
        except:
            return [filepath]
        num_parts = int(size_mb / MAX_SIZE_MB) + 1
        part_duration = total_duration / num_parts
        parts = []
        for i in range(num_parts):
            part_path = f"{base}_part{i+1}.{ext}"
            subprocess.run(["ffmpeg", "-y", "-i", filepath, "-ss", str(i * part_duration),
                "-t", str(part_duration), "-c", "copy", part_path], capture_output=True, timeout=3600)
            if os.path.exists(part_path) and os.path.getsize(part_path) > 1024:
                parts.append(part_path)
        if parts: clean(filepath)
        return parts if parts else [filepath]

    def jazz_drive_upload(self, filename, folder_name=""):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
            ctx = browser.new_context(viewport={"width": 1280, "height": 720},
                storage_state=self.state_file if os.path.exists(self.state_file) else None)
            page = ctx.new_page()
            try:
                page.goto("https://cloud.jazzdrive.com.pk/#folders", wait_until="networkidle", timeout=90000)
                time.sleep(5)
                if page.locator("#msisdn").is_visible():
                    self.msg("Session expire! Login karo...")
                    ok = self.do_login(page, ctx)
                    if not ok: self.msg("Login fail."); return
                    page.goto("https://cloud.jazzdrive.com.pk/#folders", wait_until="networkidle", timeout=90000)
                    time.sleep(5)
                if folder_name and folder_name.strip().upper() != "ROOT" and folder_name.strip() != "":
                    try:
                        page.get_by_text(folder_name.strip(), exact=False).first.click(timeout=5000)
                        time.sleep(3)
                        self.msg(f"Folder: {folder_name}")
                    except:
                        self.msg(f"Folder '{folder_name}' nahi mila, root mein upload...")
                ctx.storage_state(path=self.state_file)
                abs_path = os.path.abspath(filename)
                for sel in ["xpath=/html/body/div/div/div[1]/div/header/div/div/button", "button:has-text('Upload')"]:
                    try: page.click(sel, timeout=5000); break
                    except: pass
                page.wait_for_selector("input[type='file']", state="attached")
                with page.expect_file_chooser() as fc_info:
                    page.click("xpath=/html/body/div[2]/div[3]/div/div/form/div/div/div/div[1]")
                fc_info.value.set_files(abs_path)
                time.sleep(3)
                try:
                    yes_btn = page.get_by_text("Yes", exact=True)
                    if yes_btn.is_visible(): yes_btn.click()
                except: pass
                sz = os.path.getsize(filename) / (1024 * 1024)
                wait_sec = max(60, int(sz * 4))
                self.msg(f"Uploading {os.path.basename(filename)[:50]}... (~{wait_sec}s)")
                elapsed = 0
                upload_done = False
                while elapsed < wait_sec:
                    time.sleep(30)
                    elapsed += 30
                    try:
                        if page.locator("text=Uploads completed").is_visible():
                            self.msg(f"Upload complete! ({elapsed}s)")
                            upload_done = True
                            break
                    except: pass
                    if elapsed % 60 == 0:
                        self.take_screenshot(page, f"Progress {elapsed}s/{wait_sec}s")
                if not upload_done:
                    self.take_screenshot(page, f"Final {elapsed}s")
                ctx.storage_state(path=self.state_file)
            except Exception as e:
                self.msg(f"Upload error: {str(e)[:200]}")
            finally:
                browser.close()

    def upload_with_split(self, filepath, folder_name=""):
        parts = self.split_video(filepath)
        for i, part in enumerate(parts, 1):
            if len(parts) > 1:
                self.msg(f"Part {i}/{len(parts)} upload...")
            self.jazz_drive_upload(part, folder_name)
            clean(part)

    def process_direct(self, url, folder_name=""):
        out_name = safe_filename(url.split("/")[-1].split("?")[0] or "file.mp4")
        if "." not in out_name: out_name += ".mp4"
        out_path = f"/tmp/{out_name}"
        clean(out_path)
        self.msg(f"Downloading...\n{out_name[:60]}")
        result, error_msg = self.download_file(url, out_path)
        if not result:
            self.msg(f"Download fail!\n{error_msg}"); return
        sz = os.path.getsize(result) / (1024 * 1024)
        self.msg(f"Downloaded! {sz:.1f} MB\nUploading...")
        self.upload_with_split(result, folder_name)

    def process_zip(self, url, folder_name=""):
        import shutil
        zip_path = f"/tmp/series_{self.chat_id}.zip"
        extract_dir = f"/tmp/series_{self.chat_id}_extracted"
        clean(zip_path)
        if os.path.exists(extract_dir): shutil.rmtree(extract_dir)
        os.makedirs(extract_dir, exist_ok=True)
        self.msg("ZIP download ho raha hai...")
        result, error_msg = self.download_file(url, zip_path)
        if not result or not file_ok(zip_path):
            self.msg(f"ZIP fail!\n{error_msg}"); return
        sz = os.path.getsize(zip_path) / (1024 * 1024)
        self.msg(f"Downloaded! {sz:.1f} MB\nExtracting...")
        try:
            if zipfile.is_zipfile(zip_path):
                with zipfile.ZipFile(zip_path, "r") as zf: zf.extractall(extract_dir)
            else:
                subprocess.run(["unzip", "-o", zip_path, "-d", extract_dir], timeout=120)
        except Exception as e:
            self.msg(f"Extract fail: {str(e)[:100]}"); return
        clean(zip_path)
        video_files = []
        for root, dirs, files in os.walk(extract_dir):
            for f in sorted(files):
                if is_video_file(f): video_files.append(os.path.join(root, f))
        if not video_files:
            self.msg("ZIP mein koi video nahi!"); return
        self.msg(f"{len(video_files)} episodes mile!\nUpload shuru...")
        for i, video_path in enumerate(video_files, 1):
            fname = os.path.basename(video_path)
            fsize = os.path.getsize(video_path) / (1024 * 1024)
            self.msg(f"Episode {i}/{len(video_files)}\n{fname}\n{fsize:.1f} MB")
            self.upload_with_split(video_path, folder_name)
            self.msg(f"Episode {i}/{len(video_files)} done!")
        shutil.rmtree(extract_dir, ignore_errors=True)
        self.msg(f"SERIES COMPLETE!\n{len(video_files)} episodes uploaded!")

    def download_youtube(self, url, quality="720"):
        self.msg(f"📺 YouTube download...\nQuality: {quality}p")
        out_template = "/tmp/yt_%(title)s.%(ext)s"
        ydl_opts = {
            "format": (
                f"bestvideo[height<={quality}][ext=mp4]+"
                f"bestaudio[ext=m4a]/"
                f"best[height<={quality}][ext=mp4]/best"
            ),
            "outtmpl": out_template,
            "restrictfilenames": True,
            "noplaylist": False,
            "quiet": True,
            "no_warnings": True,
            "impersonate": "chrome",  # YouTube bot detection bypass
            "http_headers": {"User-Agent": WEB_UA},
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    self.msg("❌ YouTube info nahi mila!")
                    return None
                # Playlist
                if "entries" in info:
                    paths = []
                    for entry in info["entries"]:
                        if not entry: continue
                        base = os.path.splitext(ydl.prepare_filename(entry))[0]
                        for ext in [".mp4", ".mkv", ".webm"]:
                            if os.path.exists(base + ext):
                                paths.append(base + ext)
                                break
                    self.msg(f"✅ Playlist: {len(paths)} videos downloaded!")
                    return paths if paths else None
                # Single
                base = os.path.splitext(ydl.prepare_filename(info))[0]
                for ext in [".mp4", ".mkv", ".webm"]:
                    if os.path.exists(base + ext):
                        mb = os.path.getsize(base + ext) / 1024 / 1024
                        self.msg(f"✅ Downloaded! {os.path.basename(base+ext)} ({mb:.1f}MB)")
                        return base + ext
                self.msg("❌ File nahi mili!")
                return None
        except Exception as e:
            self.msg(f"❌ YouTube error: {str(e)[:200]}")
            return None

    def process_youtube(self, url, quality, folder_name=""):
        result = self.download_youtube(url, quality)
        if not result:
            self.msg("❌ YouTube download fail!")
            return
        # Playlist — list of files
        if isinstance(result, list):
            total = len(result)
            self.msg(f"📋 {total} videos upload shuru...")
            for i, fp in enumerate(result, 1):
                self.msg(f"🎬 {i}/{total}: {os.path.basename(fp)[:50]}")
                self.upload_with_split(fp, folder_name)
                self.msg(f"✅ {i}/{total} done!")
            self.msg(f"🎉 Playlist complete! {total} videos!")
            return
        # Single file
        sz = os.path.getsize(result) / 1024 / 1024
        self.msg(f"✅ {sz:.1f}MB\nUploading...")
        self.upload_with_split(result, folder_name)

    def worker_loop(self):
        try:
            while not self.task_queue.empty():
                while self.queue_paused:
                    time.sleep(5)
                item = self.task_queue.get()
                self.msg(f"PROCESSING...\n{item.get('link', '')[:60]}")
                try:
                    if item["type"] == "youtube":
                        self.process_youtube(item["link"], item.get("quality", "720"), item.get("folder", ""))
                    elif item["type"] == "zip":
                        self.process_zip(item["link"], item.get("folder", ""))
                    else:
                        self.process_direct(item["link"], item.get("folder", ""))
                except Exception as e:
                    self.msg(f"Error: {str(e)[:150]}")
                finally:
                    self.task_queue.task_done()
            self.msg("QUEUE COMPLETE!\n\nAgla link bhejein")
        except Exception as e:
            self.msg(f"Worker crash: {str(e)[:150]}")
        finally:
            with self.worker_lock:
                self.is_working = False

    def start_worker(self):
        with self.worker_lock:
            if not self.is_working:
                self.is_working = True
                threading.Thread(target=self.worker_loop, daemon=True).start()

    def register_handlers(self):
        bot = self.bot

        @bot.message_handler(commands=["start"])
        def welcome(m):
            if m.chat.id != self.chat_id: return
            self.msg("JAZZ DRIVE BOT\n\nDirect/ZIP/RAR link bhejein\n\n/checklogin\n/status\n/pause\n/resume\n/clear\n/cmd")

        @bot.message_handler(commands=["checklogin"])
        def cmd_check(m):
            if m.chat.id != self.chat_id: return
            threading.Thread(target=self.check_login_status, daemon=True).start()

        @bot.message_handler(commands=["status"])
        def cmd_status(m):
            if m.chat.id != self.chat_id: return
            icon = "Working" if self.is_working else "Idle"
            cookie = "Active" if os.path.exists(self.state_file) else "None"
            self.msg(f"BOT STATUS\n\nState: {icon}\nQueue: {self.task_queue.qsize()}\nSession: {cookie}")

        @bot.message_handler(commands=["pause"])
        def cmd_pause(m):
            if m.chat.id != self.chat_id: return
            self.queue_paused = True
            self.msg("Queue paused!")

        @bot.message_handler(commands=["resume"])
        def cmd_resume(m):
            if m.chat.id != self.chat_id: return
            self.queue_paused = False
            self.msg("Queue resumed!")
            self.start_worker()

        @bot.message_handler(commands=["clear"])
        def cmd_clear(m):
            if m.chat.id != self.chat_id: return
            count = self.task_queue.qsize()
            while not self.task_queue.empty():
                try: self.task_queue.get_nowait()
                except: break
            self.msg(f"Queue cleared! {count} tasks.")

        @bot.message_handler(commands=["cmd"])
        def cmd_shell(m):
            if m.chat.id != self.chat_id: return
            try:
                c = m.text.replace("/cmd ", "", 1).strip()
                out = subprocess.check_output(c, shell=True, stderr=subprocess.STDOUT).decode()
                bot.reply_to(m, out[:4000])
            except Exception as e:
                bot.reply_to(m, f"Error: {e}")

        @bot.message_handler(func=lambda m: True)
        def handle(m):
            if m.chat.id != self.chat_id: return
            text = (m.text or "").strip()

            if self.ctx["state"] == "WAITING_FOR_NUMBER":
                self.ctx["number"] = text
                self.ctx["state"] = "NUMBER_RECEIVED"
                bot.reply_to(m, "Number receive hua...")
                return

            if self.ctx["state"] == "WAITING_FOR_OTP":
                self.ctx["otp"] = text
                self.ctx["state"] = "OTP_RECEIVED"
                bot.reply_to(m, "OTP receive hua...")
                return

            if self.ctx["state"] == "WAITING_FOR_YT_QUALITY":
                q_map = {"1": "2160", "2": "1440", "3": "1080", "4": "720", "5": "480", "6": "360"}
                self.ctx["pending_quality"] = q_map.get(text.strip(), "1080")
                self.ctx["state"] = "WAITING_FOR_FOLDER"
                bot.reply_to(m, f"Quality: {self.ctx['pending_quality']}p\n\n📁 Folder name bhejein\n(ya 'root')")
                return

            if self.ctx["state"] == "WAITING_FOR_FOLDER":
                folder_name = text if text.strip().upper() != "ROOT" and text.strip() != "" else ""
                link = self.ctx["pending_link"]
                ltype = self.ctx["pending_type"]
                quality = self.ctx["pending_quality"]
                self.ctx["pending_link"] = None
                self.ctx["pending_type"] = None
                self.ctx["state"] = "IDLE"
                self.task_queue.put({"link": link, "type": ltype, "folder": folder_name, "quality": quality})
                bot.reply_to(m, f"Task add!\nFolder: {folder_name or 'Root'}\nQueue: {self.task_queue.qsize()}")
                self.start_worker()
                return

            if text.startswith("http"):
                if is_youtube(text):
                    ltype = "youtube"
                    self.ctx["pending_link"] = text
                    self.ctx["pending_type"] = ltype
                    self.ctx["state"] = "WAITING_FOR_YT_QUALITY"
                    bot.reply_to(m, "📺 YouTube link mila!\n\n🎬 Quality choose karein:\n1. 4K (2160p)\n2. 2K (1440p)\n3. Full HD (1080p)\n4. HD (720p)\n5. SD (480p)\n6. Low (360p)")
                elif is_zip_url(text):
                    ltype = "zip"
                    self.ctx["pending_link"] = text
                    self.ctx["pending_type"] = ltype
                    self.ctx["state"] = "WAITING_FOR_FOLDER"
                    bot.reply_to(m, "ZIP/RAR link mila!\n\n📁 Folder name bhejein\n(ya 'root')")
                else:
                    ltype = "direct"
                    self.ctx["pending_link"] = text
                    self.ctx["pending_type"] = ltype
                    self.ctx["state"] = "WAITING_FOR_FOLDER"
                    bot.reply_to(m, "Direct link mila!\n\n📁 Folder name bhejein\n(ya 'root')")
            else:
                bot.reply_to(m, "Link bhejein ya /start dekho")

    def run(self):
        self.register_handlers()
        self.msg("BOT ONLINE!\n\nReady!\nDirect link ya ZIP/RAR bhejein")
        self.bot.infinity_polling()


if __name__ == "__main__":
    instances = []
    threads = []
    for cfg in BOTS:
        instance = BotInstance(cfg["token"], cfg["chat_id"], cfg["state_file"])
        instances.append(instance)
        t = threading.Thread(target=instance.run, daemon=True)
        threads.append(t)
        t.start()
        time.sleep(2)

    for t in threads:
        t.join()
