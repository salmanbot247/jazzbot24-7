import os, re, time, threading, queue, subprocess, requests, zipfile, telebot
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

BROWSER_ARGS = ["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage", "--single-process"]
WEB_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
VIDEO_EXTS = [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts"]
ZIP_EXTS = [".zip", ".rar", ".7z", ".tar", ".gz"]
MAX_SIZE_MB = 1990

BOTS = [
    {"token": "8350099407:AAEAX6NzIykESMj50CnduDAwngfHW1ER-oM", "chat_id": 7144917062, "state_file": "state1.json"},
]

# ─── Helpers ────────────────────────────────────────────────────────────────

def is_zip_url(link):
    return any(link.lower().endswith(ext) or ext in link.lower() for ext in ZIP_EXTS)

def is_video_file(f):
    return any(f.lower().endswith(ext) for ext in VIDEO_EXTS)

def is_m3u8(url):
    return '.m3u8' in url.lower()

def safe_filename(t):
    return re.sub(r'[\\/*?:"<>|]', '', t).strip().replace(' ', '_')[:80]

def file_ok(f, min_mb=0.5):
    return os.path.exists(f) and os.path.getsize(f) / (1024 * 1024) >= min_mb

def clean(f):
    if f and os.path.exists(f):
        os.remove(f)

def get_referers(url):
    try:
        parsed = urlparse(url)
        domain_referer = f"{parsed.scheme}://{parsed.netloc}/"
    except:
        domain_referer = "https://www.google.com/"
    return [
        domain_referer,
        "https://www.google.com/",
        "https://www.facebook.com/",
        "",
    ]

def get_filename_from_url(url):
    try:
        path = urlparse(url).path
        name = path.split("/")[-1].split("?")[0]
        name = requests.utils.unquote(name)
        name = safe_filename(name)
        if "." not in name or len(name) < 3:
            name = "video.mp4"
        return name
    except:
        return "video.mp4"


# ─── Bot Instance ────────────────────────────────────────────────────────────

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
            "pending_folder": ""
        }

    def msg(self, text):
        try:
            self.bot.send_message(self.chat_id, text)
        except:
            try:
                self.bot.send_message(self.chat_id, re.sub(r'[*_`\[\]]', '', text))
            except:
                pass

    def send_photo(self, path, caption=""):
        try:
            with open(path, "rb") as f:
                self.bot.send_photo(self.chat_id, f, caption=caption)
        except:
            pass

    def take_screenshot(self, page, caption="📸"):
        try:
            page.screenshot(path="s.png")
            self.send_photo("s.png", caption)
            os.remove("s.png")
        except:
            pass

    # ─── Login ──────────────────────────────────────────────────────────────

    def do_login(self, page, context):
        self.msg("LOGIN REQUIRED\n\nJazz number bhejein\nFormat: 03XXXXXXXXX")
        self.ctx["state"] = "WAITING_FOR_NUMBER"
        for _ in range(500):
            if self.ctx["state"] == "NUMBER_RECEIVED":
                break
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
            if self.ctx["state"] == "OTP_RECEIVED":
                break
            time.sleep(1)
        else:
            self.msg("Timeout! Task cancel.")
            return False
        for i, digit in enumerate(self.ctx["otp"].strip()[:6], 1):
            try:
                f = page.locator(f"//input[@aria-label='Digit {i}']")
                if f.is_visible():
                    f.fill(digit)
                    time.sleep(0.2)
            except:
                pass
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
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 720},
                storage_state=self.state_file if os.path.exists(self.state_file) else None
            )
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

    # ─── Download ───────────────────────────────────────────────────────────

    def download_file(self, url, out_path):
        last_error = "Unknown"
        clean(out_path)
        referers = get_referers(url)

        if is_m3u8(url):
            if not out_path.endswith('.mp4'):
                out_path = out_path.rsplit('.', 1)[0] + '.mp4'
            for referer in referers[:2]:
                clean(out_path)
                try:
                    cmd = ["ffmpeg", "-y"]
                    if referer:
                        cmd += ["-headers", f"Referer: {referer}\r\nUser-Agent: {WEB_UA}\r\n"]
                    else:
                        cmd += ["-user_agent", WEB_UA]
                    cmd += ["-i", url, "-c", "copy", "-bsf:a", "aac_adtstoasc", out_path]
                    subprocess.run(cmd, capture_output=True, timeout=600)
                    if file_ok(out_path):
                        return out_path, "Success"
                except Exception as e:
                    last_error = str(e)
            return None, f"M3U8 fail: {last_error}"

        try:
            import yt_dlp
            tmp_template = out_path.rsplit('.', 1)[0] + '.%(ext)s'
            ydl_opts = {
                "outtmpl": tmp_template,
                "quiet": True,
                "no_warnings": True,
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "merge_output_format": "mp4",
                "http_headers": {
                    "User-Agent": WEB_UA,
                    "Referer": referers[0],
                    "Origin": referers[0].rstrip("/"),
                },
                "socket_timeout": 30,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            base = out_path.rsplit('.', 1)[0]
            for ext in VIDEO_EXTS:
                candidate = base + ext
                if file_ok(candidate, min_mb=0.1):
                    return candidate, "Success"
            if file_ok(out_path, min_mb=0.1):
                return out_path, "Success"
        except Exception as e:
            last_error = f"yt-dlp: {str(e)[:100]}"

        for referer in referers:
            clean(out_path)
            try:
                cmd = [
                    "aria2c", "-x", "16", "-s", "16", "-k", "1M",
                    "--max-tries=3", "--retry-wait=5", "--allow-overwrite=true",
                    f"--user-agent={WEB_UA}",
                    "-d", os.path.dirname(out_path) or "/tmp",
                    "-o", os.path.basename(out_path),
                ]
                if referer:
                    cmd += [f"--referer={referer}", f"--header=Origin: {referer.rstrip('/')}"]
                cmd.append(url)
                result = subprocess.run(cmd, capture_output=True, timeout=600)
                if file_ok(out_path, min_mb=0.1):
                    return out_path, "Success"
                last_error = f"aria2c [{referer[:30]}]: " + result.stderr.decode()[:100]
            except Exception as e:
                last_error = f"aria2c: {str(e)[:100]}"

        for referer in referers:
            clean(out_path)
            try:
                cmd = [
                    "curl", "-L", "-k", "--retry", "3", "--retry-delay", "3",
                    "--connect-timeout", "30", "-H", f"User-Agent: {WEB_UA}",
                    "-o", out_path,
                ]
                if referer:
                    cmd += ["-H", f"Referer: {referer}", "-H", f"Origin: {referer.rstrip('/')}"]
                cmd.append(url)
                subprocess.run(cmd, timeout=600)
                if file_ok(out_path, min_mb=0.1):
                    return out_path, "Success"
            except Exception as e:
                last_error = f"curl [{referer[:30]}]: {str(e)[:100]}"

        for referer in referers[:2]:
            clean(out_path)
            try:
                cmd = [
                    "wget", "-q", "--tries=3", "--timeout=120",
                    f"--user-agent={WEB_UA}", "-O", out_path,
                ]
                if referer:
                    cmd += [f"--referer={referer}"]
                cmd.append(url)
                subprocess.run(cmd, timeout=600)
                if file_ok(out_path, min_mb=0.1):
                    return out_path, "Success"
            except Exception as e:
                last_error = f"wget: {str(e)[:100]}"

        for referer in referers:
            clean(out_path)
            try:
                hdrs = {"User-Agent": WEB_UA}
                if referer:
                    hdrs["Referer"] = referer
                    hdrs["Origin"] = referer.rstrip("/")
                with requests.get(url, headers=hdrs, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    with open(out_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                if file_ok(out_path, min_mb=0.1):
                    return out_path, "Success"
            except Exception as e:
                last_error = f"requests [{referer[:30]}]: {str(e)[:100]}"

        return None, last_error

    # ─── Video Split ─────────────────────────────────────────────────────────

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
            capture_output=True, text=True
        )
        try:
            total_duration = float(result.stdout.strip())
        except:
            return [filepath]
        num_parts = int(size_mb / MAX_SIZE_MB) + 1
        part_duration = total_duration / num_parts
        parts = []
        for i in range(num_parts):
            part_path = f"{base}_part{i+1}.{ext}"
            subprocess.run(
                ["ffmpeg", "-y", "-i", filepath,
                 "-ss", str(i * part_duration), "-t", str(part_duration),
                 "-c", "copy", part_path],
                capture_output=True, timeout=3600
            )
            if os.path.exists(part_path) and os.path.getsize(part_path) > 1024:
                parts.append(part_path)
        if parts:
            clean(filepath)
        return parts if parts else [filepath]

    # ─── Jazz Drive Upload ────────────────────────────────────────────────────

    def jazz_drive_upload(self, filename, folder_name=""):
        """Upload file to JazzDrive. Returns uploaded filename (for share link lookup)."""
        uploaded_name = os.path.basename(filename)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 720},
                storage_state=self.state_file if os.path.exists(self.state_file) else None
            )
            page = ctx.new_page()
            try:
                page.goto("https://cloud.jazzdrive.com.pk/#folders", wait_until="networkidle", timeout=90000)
                time.sleep(5)
                if page.locator("#msisdn").is_visible():
                    self.msg("Session expire! Login karo...")
                    ok = self.do_login(page, ctx)
                    if not ok:
                        self.msg("Login fail.")
                        return None
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
                    try:
                        page.click(sel, timeout=5000)
                        break
                    except:
                        pass

                page.wait_for_selector("input[type='file']", state="attached")
                with page.expect_file_chooser() as fc_info:
                    page.click("xpath=/html/body/div[2]/div[3]/div/div/form/div/div/div/div[1]")
                fc_info.value.set_files(abs_path)
                time.sleep(3)

                try:
                    yes_btn = page.get_by_text("Yes", exact=True)
                    if yes_btn.is_visible():
                        yes_btn.click()
                except:
                    pass

                sz = os.path.getsize(filename) / (1024 * 1024)
                wait_sec = max(60, int(sz * 4))
                self.msg(f"Uploading {uploaded_name[:50]}... (~{wait_sec}s)")

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
                    except:
                        pass
                    if elapsed % 60 == 0:
                        self.take_screenshot(page, f"Progress {elapsed}s/{wait_sec}s")

                if not upload_done:
                    self.take_screenshot(page, f"Final {elapsed}s")

                # ── [NEW] Get share link ──────────────────────────────────
                share_link = self._get_share_link_from_page(page, uploaded_name)
                if share_link:
                    self.msg(f"Share link:\n{share_link}")
                else:
                    # Try fresh page load to find the file
                    time.sleep(3)
                    share_link = self._get_share_link_fresh(ctx, uploaded_name, folder_name)
                    if share_link:
                        self.msg(f"Share link:\n{share_link}")
                    else:
                        self.msg("Share link nahi mila (manually check karo)")

                ctx.storage_state(path=self.state_file)
                return uploaded_name

            except Exception as e:
                self.msg(f"Upload error: {str(e)[:200]}")
                return None
            finally:
                browser.close()

    # ─── [NEW] Share Link Helpers ─────────────────────────────────────────────

    def _get_share_link_from_page(self, page, filename):
        """
        Try to get share link on the current upload page.
        JazzDrive typically shows files in a list — we hover/right-click
        the file and look for a Share option.
        """
        try:
            time.sleep(3)
            # Dismiss any upload dialog first
            for dismiss in ["button:has-text('Close')", "button:has-text('Done')", ".modal-close"]:
                try:
                    btn = page.locator(dismiss)
                    if btn.is_visible(timeout=2000):
                        btn.click()
                        time.sleep(1)
                        break
                except:
                    pass

            # Find file row by filename (partial match)
            name_without_ext = filename.rsplit(".", 1)[0][:30]
            file_row = None
            for selector in [
                f"text={name_without_ext}",
                f"[title*='{name_without_ext}']",
                f"td:has-text('{name_without_ext}')",
            ]:
                try:
                    el = page.locator(selector).first
                    if el.is_visible(timeout=3000):
                        file_row = el
                        break
                except:
                    pass

            if not file_row:
                return None

            file_row.hover()
            time.sleep(1)

            # Look for options/more button near the file
            for opt_sel in [
                "button[aria-label*='more' i]",
                "button[aria-label*='option' i]",
                "[class*='more'] button",
                "button[title*='more' i]",
                ".file-action",
                "button svg",                 # icon button
            ]:
                try:
                    btn = page.locator(opt_sel).first
                    if btn.is_visible(timeout=2000):
                        btn.click()
                        time.sleep(1)
                        break
                except:
                    pass

            # Click Share
            for share_sel in [
                "text=Share",
                "text=share",
                "[aria-label*='share' i]",
                "button:has-text('Share')",
            ]:
                try:
                    s = page.locator(share_sel).first
                    if s.is_visible(timeout=3000):
                        s.click()
                        time.sleep(2)
                        break
                except:
                    pass

            # Extract link from input/textarea/clipboard dialog
            return self._extract_link_from_dialog(page)

        except Exception as e:
            return None

    def _get_share_link_fresh(self, ctx, filename, folder_name=""):
        """
        Open a fresh page, navigate to folder, find file, get share link.
        Called as fallback if upload-page approach failed.
        """
        page = ctx.new_page()
        try:
            page.goto("https://cloud.jazzdrive.com.pk/#folders", wait_until="networkidle", timeout=60000)
            time.sleep(4)

            if folder_name and folder_name.strip().upper() != "ROOT":
                try:
                    page.get_by_text(folder_name.strip(), exact=False).first.click(timeout=5000)
                    time.sleep(3)
                except:
                    pass

            return self._get_share_link_from_page(page, filename)
        except:
            return None
        finally:
            page.close()

    def _extract_link_from_dialog(self, page):
        """
        After clicking Share, extract the URL from whatever dialog appears.
        Tries input fields, textareas, and visible link text.
        """
        try:
            time.sleep(2)
            # Input with http URL
            for inp_sel in ["input[type='text']", "input[readonly]", "textarea"]:
                try:
                    inputs = page.locator(inp_sel).all()
                    for inp in inputs:
                        if inp.is_visible(timeout=1000):
                            val = inp.input_value()
                            if val and val.startswith("http"):
                                return val
                except:
                    pass

            # Anchor tags with share-like URLs
            try:
                links = page.locator("a[href*='share'], a[href*='cloud.jazz']").all()
                for a in links:
                    href = a.get_attribute("href")
                    if href and href.startswith("http"):
                        return href
            except:
                pass

            # Any visible text that looks like a URL
            try:
                body_text = page.inner_text("body")
                urls = re.findall(r'https://[^\s"\'<>]+', body_text)
                for u in urls:
                    if "share" in u.lower() or "jazz" in u.lower():
                        return u
            except:
                pass

        except:
            pass
        return None

    # ─── Upload with Split ────────────────────────────────────────────────────

    def upload_with_split(self, filepath, folder_name=""):
        parts = self.split_video(filepath)
        for i, part in enumerate(parts, 1):
            if len(parts) > 1:
                self.msg(f"Part {i}/{len(parts)} upload...")
            self.jazz_drive_upload(part, folder_name)
            clean(part)

    # ─── Task Processors ──────────────────────────────────────────────────────

    def process_direct(self, url, folder_name=""):
        out_name = get_filename_from_url(url)
        out_path = f"/tmp/{out_name}"
        clean(out_path)
        self.msg(f"Downloading...\n{out_name[:60]}")
        result, error_msg = self.download_file(url, out_path)
        if not result:
            self.msg(f"Download fail!\n{error_msg[:200]}")
            if "403" in error_msg or "Forbidden" in error_msg.lower():
                self.msg(
                    "⚠️ 403 Error — Possible causes:\n"
                    "1. URL IP-locked hai (Jazz IP se generate hua)\n"
                    "   GitHub ka alag IP hai, isliye fail\n"
                    "2. URL expire ho gaya ho\n"
                    "3. Site ne GitHub block kiya ho\n\n"
                    "Try: Fresh link generate karo aur turant bhejo"
                )
            return
        sz = os.path.getsize(result) / (1024 * 1024)
        self.msg(f"Downloaded! {sz:.1f} MB\nUploading...")
        self.upload_with_split(result, folder_name)

    def process_zip(self, url, folder_name=""):
        """
        Download a ZIP/RAR (or any archive URL), extract all videos,
        upload each one. Works with /season command too (no .zip needed in URL).
        """
        import shutil
        zip_path = f"/tmp/series_{self.chat_id}.zip"
        extract_dir = f"/tmp/series_{self.chat_id}_extracted"
        clean(zip_path)
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        os.makedirs(extract_dir, exist_ok=True)

        self.msg("ZIP/Archive download ho raha hai...")
        result, error_msg = self.download_file(url, zip_path)
        if not result or not file_ok(zip_path):
            self.msg(f"Download fail!\n{error_msg[:200]}")
            return

        sz = os.path.getsize(zip_path) / (1024 * 1024)
        self.msg(f"Downloaded! {sz:.1f} MB\nExtracting...")

        extracted = False
        # Try zipfile first
        try:
            if zipfile.is_zipfile(zip_path):
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(extract_dir)
                extracted = True
        except Exception as e:
            pass

        # Try unzip CLI
        if not extracted:
            try:
                r = subprocess.run(["unzip", "-o", zip_path, "-d", extract_dir], timeout=300)
                extracted = (r.returncode == 0)
            except:
                pass

        # Try 7z (RAR, 7z, tar, gz etc.)
        if not extracted:
            try:
                r = subprocess.run(["7z", "x", zip_path, f"-o{extract_dir}", "-y"], timeout=300)
                extracted = (r.returncode == 0)
            except:
                pass

        if not extracted:
            self.msg("Extract fail! 7z, unzip sab try hua.")
            return

        clean(zip_path)

        # Gather all video files sorted by name (episode order)
        video_files = []
        for root, dirs, files in os.walk(extract_dir):
            dirs.sort()
            for f in sorted(files):
                if is_video_file(f):
                    video_files.append(os.path.join(root, f))

        if not video_files:
            self.msg("Archive mein koi video nahi mili!")
            shutil.rmtree(extract_dir, ignore_errors=True)
            return

        self.msg(f"{len(video_files)} episodes mile!\nUpload shuru...")

        for i, video_path in enumerate(video_files, 1):
            fname = os.path.basename(video_path)
            fsize = os.path.getsize(video_path) / (1024 * 1024)
            self.msg(f"Episode {i}/{len(video_files)}\n{fname}\n{fsize:.1f} MB")
            self.upload_with_split(video_path, folder_name)
            self.msg(f"Episode {i}/{len(video_files)} done!")

        shutil.rmtree(extract_dir, ignore_errors=True)
        self.msg(f"SEASON COMPLETE!\n{len(video_files)} episodes upload ho gaye!")

    # ─── Worker ──────────────────────────────────────────────────────────────

    def worker_loop(self):
        try:
            while not self.task_queue.empty():
                while self.queue_paused:
                    time.sleep(5)
                item = self.task_queue.get()
                self.msg(f"PROCESSING...\n{item.get('link', '')[:80]}")
                try:
                    if item["type"] == "zip":
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

    # ─── Handlers ────────────────────────────────────────────────────────────

    def register_handlers(self):
        bot = self.bot

        @bot.message_handler(commands=["start"])
        def welcome(m):
            if m.chat.id != self.chat_id:
                return
            self.msg(
                "JAZZ DRIVE BOT\n\n"
                "Kya bhej sakte ho:\n"
                "• Direct link (mp4, mkv, ts...)\n"
                "• M3U8/HLS link\n"
                "• ZIP/RAR link (auto-detect)\n\n"
                "Commands:\n"
                "/checklogin\n"
                "/status\n"
                "/season <url>  ← Poora season ek baar\n"
                "/pause\n"
                "/resume\n"
                "/clear\n"
                "/cmd <bash>"
            )

        @bot.message_handler(commands=["checklogin"])
        def cmd_check(m):
            if m.chat.id != self.chat_id:
                return
            threading.Thread(target=self.check_login_status, daemon=True).start()

        @bot.message_handler(commands=["status"])
        def cmd_status(m):
            if m.chat.id != self.chat_id:
                return
            icon = "Working" if self.is_working else "Idle"
            cookie = "Active" if os.path.exists(self.state_file) else "None"
            paused = "YES" if self.queue_paused else "No"
            self.msg(
                f"BOT STATUS\n\n"
                f"State: {icon}\n"
                f"Queue: {self.task_queue.qsize()}\n"
                f"Paused: {paused}\n"
                f"Session: {cookie}"
            )

        @bot.message_handler(commands=["pause"])
        def cmd_pause(m):
            if m.chat.id != self.chat_id:
                return
            self.queue_paused = True
            self.msg("Queue paused!")

        @bot.message_handler(commands=["resume"])
        def cmd_resume(m):
            if m.chat.id != self.chat_id:
                return
            self.queue_paused = False
            self.msg("Queue resumed!")
            self.start_worker()

        @bot.message_handler(commands=["clear"])
        def cmd_clear(m):
            if m.chat.id != self.chat_id:
                return
            count = self.task_queue.qsize()
            while not self.task_queue.empty():
                try:
                    self.task_queue.get_nowait()
                except:
                    break
            self.msg(f"Queue cleared! {count} tasks remove.")

        # ── [NEW] /season command ─────────────────────────────────────────────
        @bot.message_handler(commands=["season"])
        def cmd_season(m):
            if m.chat.id != self.chat_id:
                return
            parts = m.text.split(None, 1)
            if len(parts) < 2 or not parts[1].strip().startswith("http"):
                bot.reply_to(
                    m,
                    "Format:\n/season <url>\n\n"
                    "Example:\n/season https://example.com/DragonBallZ_S01.zip\n\n"
                    "URL mein .zip extension zarori nahi\n"
                    "Bot khud extract karke sab upload karega"
                )
                return
            url = parts[1].strip()
            self.ctx["pending_link"] = url
            self.ctx["pending_type"] = "zip"
            self.ctx["state"] = "WAITING_FOR_FOLDER"
            bot.reply_to(m, "Season pack link mila!\n\nFolder name bhejein\n(ya 'root' type karo)")

        @bot.message_handler(commands=["cmd"])
        def cmd_shell(m):
            if m.chat.id != self.chat_id:
                return
            try:
                c = m.text.replace("/cmd ", "", 1).strip()
                out = subprocess.check_output(c, shell=True, stderr=subprocess.STDOUT).decode()
                bot.reply_to(m, out[:4000])
            except Exception as e:
                bot.reply_to(m, f"Error: {e}")

        @bot.message_handler(func=lambda m: True)
        def handle(m):
            if m.chat.id != self.chat_id:
                return
            text = (m.text or "").strip()

            # ── Login states ──
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

            # ── Folder selection ──
            if self.ctx["state"] == "WAITING_FOR_FOLDER":
                folder_name = "" if text.strip().upper() in ("ROOT", "") else text.strip()
                link = self.ctx["pending_link"]
                ltype = self.ctx["pending_type"]
                self.ctx.update({"pending_link": None, "pending_type": None, "state": "IDLE"})
                self.task_queue.put({"link": link, "type": ltype, "folder": folder_name})
                bot.reply_to(m, f"Task add!\nFolder: {folder_name or 'Root'}\nQueue: {self.task_queue.qsize()}")
                self.start_worker()
                return

            # ── New link ──
            if text.startswith("http"):
                if is_zip_url(text):
                    ltype = "zip"
                    hint = "ZIP/RAR link mila!"
                elif is_m3u8(text):
                    ltype = "direct"
                    hint = "M3U8/HLS link mila!"
                else:
                    ltype = "direct"
                    hint = "Direct link mila!"

                self.ctx["pending_link"] = text
                self.ctx["pending_type"] = ltype
                self.ctx["state"] = "WAITING_FOR_FOLDER"
                bot.reply_to(m, f"{hint}\n\nFolder name bhejein\n(ya 'root')")
            else:
                bot.reply_to(m, "Link bhejein ya /start dekho")

    def run(self):
        self.register_handlers()
        self.msg("BOT ONLINE!\n\nDirect / M3U8 / ZIP / /season link bhejein")
        self.bot.infinity_polling()


# ─── Main ─────────────────────────────────────────────────────────────────────

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
