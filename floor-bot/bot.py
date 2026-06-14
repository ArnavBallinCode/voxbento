import asyncio
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("floor-bot")

class SubprocessManager:
    def __init__(self):
        self.rooms = {}  # Dict[str, asyncio.subprocess.Process]
        self.lock = asyncio.Lock()
        self.loop = None

    async def start_room(self, event_slug: str, jitsi_url: str, mediamtx_rtsp_base: str):
        async with self.lock:
            if event_slug in self.rooms:
                await self.stop_room_locked(event_slug)

            logger.info(f"Starting subprocess for event: {event_slug}")
            env = os.environ.copy()
            env["BOT_EVENT_SLUG"] = event_slug
            env["BOT_JITSI_URL"] = jitsi_url
            env["BOT_MEDIAMTX_RTSP_BASE"] = mediamtx_rtsp_base

            cmd = [
                "python", "-u", "-c",
                """
import asyncio
import os
import signal
import subprocess
from playwright.async_api import async_playwright

async def run_capture():
    loop = asyncio.get_running_loop()
    main_task = asyncio.current_task()

    def signal_handler():
        print("Received terminate signal, shutting down...")
        if main_task:
            main_task.cancel()

    loop.add_signal_handler(signal.SIGTERM, signal_handler)
    loop.add_signal_handler(signal.SIGINT, signal_handler)

    event_slug = os.environ.get("BOT_EVENT_SLUG")
    jitsi_url = os.environ.get("BOT_JITSI_URL")
    mediamtx_rtsp_base = os.environ.get("BOT_MEDIAMTX_RTSP_BASE")

    pulse_socket = f"/tmp/pulse-{event_slug}.sock"
    pulse_dir = f"/tmp/pulse-dir-{event_slug}"

    os.makedirs(pulse_dir, exist_ok=True)
    sink_name = f"sink_{event_slug}"

    subprocess.run(["pkill", "-f", f"ffmpeg.*{event_slug}"], stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-f", f"pulseaudio.*{event_slug}"], stderr=subprocess.DEVNULL)
    if os.path.exists(pulse_socket):
        try:
            os.remove(pulse_socket)
        except OSError:
            pass

    pulse_proc = subprocess.Popen([
        "pulseaudio",
        "--daemonize=no",
        "--exit-idle-time=-1",
        "--disallow-exit",
        "-n",
        "-L", f"module-native-protocol-unix auth-anonymous=1 socket={pulse_socket}",
        "-L", f"module-null-sink sink_name={sink_name}",
        "-L", "module-always-sink"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    pw = None
    browser = None
    ffmpeg_proc = None

    try:
        await asyncio.sleep(2)

        env = os.environ.copy()
        env["PULSE_SERVER"] = f"unix:{pulse_socket}"

        pw = await async_playwright().start()

        browser = await pw.chromium.launch(
            headless=True,
            env=env,
            ignore_default_args=["--mute-audio"],
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                "--disable-gesture-requirement-for-media-playback",
                "--ignore-certificate-errors",
                "--unsafely-treat-insecure-origin-as-secure=https://jitsi-web",
                "--autoplay-policy=no-user-gesture-required",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        context = await browser.new_context(
            permissions=["microphone", "camera"],
            ignore_https_errors=True
        )

        page = await context.new_page()
        page.on("console", lambda m: print(f"Browser: {m.text}"))
        page.on("pageerror", lambda err: print(f"Browser Error: {err}"))

        import urllib.parse
        display_name = urllib.parse.quote('"VoxBento FloorBot"')

        join_url = (
            f"{jitsi_url}"
            f"#config.startWithAudioMuted=false"
            f"&config.startWithVideoMuted=true"
            f"&config.prejoinPageEnabled=false"
            f"&config.disableDeepLinking=true"
            f"&config.p2p.enabled=false"
            f"&config.requireDisplayName=false"
            f"&userInfo.displayName={display_name}"
        )

        print(f"Joining: {join_url}")
        await page.goto(join_url)

        await asyncio.sleep(5)

        try:
            await page.click("div[aria-label='Join meeting']", timeout=5000)
            print("Clicked Join Meeting dialog")
        except Exception:
            pass

        ffmpeg_proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y",
            "-f", "pulse",
            "-i", f"{sink_name}.monitor",
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "libopus",
            "-b:a", "32k",
            "-vbr", "on",
            "-compression_level", "10",
            "-application", "lowdelay",
            "-f", "rtsp",
            "-rtsp_transport", "tcp",
            f"{mediamtx_rtsp_base}/{event_slug}/floor",
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )

        await ffmpeg_proc.wait()

    except asyncio.CancelledError:
        print("run_capture cancelled")
    finally:
        if ffmpeg_proc is not None and ffmpeg_proc.returncode is None:
            ffmpeg_proc.terminate()
            try:
                await ffmpeg_proc.wait()
            except:
                pass
        if browser is not None:
            await browser.close()
        if pw is not None:
            await pw.stop()
        if pulse_proc.poll() is None:
            pulse_proc.terminate()
        if os.path.exists(pulse_socket):
            try:
                os.remove(pulse_socket)
            except OSError:
                pass

asyncio.run(run_capture())
"""
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )

            async def log_stream(stream, prefix):
                async for line in stream:
                    line_decoded = line.decode('utf-8', errors='replace').strip()
                    if line_decoded:
                        logger.info(f"{prefix}: {line_decoded}")

            t1 = asyncio.create_task(log_stream(proc.stdout, f"bot[{event_slug}] stdout"))
            t2 = asyncio.create_task(log_stream(proc.stderr, f"bot[{event_slug}] stderr"))

            # Keep strong references to prevent garbage collection
            if not hasattr(self, 'log_tasks'):
                self.log_tasks = set()
            self.log_tasks.add(t1)
            self.log_tasks.add(t2)
            t1.add_done_callback(self.log_tasks.discard)
            t2.add_done_callback(self.log_tasks.discard)

            self.rooms[event_slug] = proc

    async def stop_room_locked(self, event_slug: str):
        if event_slug in self.rooms:
            logger.info(f"Terminating subprocess for {event_slug}")
            proc = self.rooms[event_slug]
            if proc.returncode is None:
                proc.terminate()
                try:
                    await proc.wait()
                except Exception:
                    pass
            del self.rooms[event_slug]

    async def stop_room(self, event_slug: str):
        async with self.lock:
            await self.stop_room_locked(event_slug)

manager = SubprocessManager()

class RequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        try:
            req = json.loads(post_data.decode('utf-8'))
        except json.JSONDecodeError:
            self.send_error(400, "Bad Request: Invalid JSON")
            return

        if self.path == '/start':
            event_slug = req.get("event_slug")
            jitsi_url = req.get("jitsi_url")
            mediamtx_rtsp_base = req.get("mediamtx_rtsp_base")
            if not all([event_slug, jitsi_url, mediamtx_rtsp_base]):
                self.send_error(400, "Missing parameters")
                return
            future = asyncio.run_coroutine_threadsafe(
                manager.start_room(event_slug, jitsi_url, mediamtx_rtsp_base),
                manager.loop
            )
            future.result() # Wait for the coroutine to finish
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started", "event_slug": event_slug}).encode())

        elif self.path == '/stop':
            event_slug = req.get("event_slug")
            if not event_slug:
                self.send_error(400, "Missing event_slug")
                return
            future = asyncio.run_coroutine_threadsafe(
                manager.stop_room(event_slug),
                manager.loop
            )
            future.result()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "stopped", "event_slug": event_slug}).encode())
        else:
            self.send_error(404, "Not Found")

    def do_GET(self):
        if self.path == '/status':
            async def get_status():
                status = {}
                async with manager.lock:
                    for event_slug, proc in manager.rooms.items():
                        if proc.returncode is not None:
                            status[event_slug] = {"state": "dead", "exit_code": proc.returncode}
                        else:
                            status[event_slug] = {"state": "healthy", "pid": proc.pid}
                return status
            future = asyncio.run_coroutine_threadsafe(get_status(), manager.loop)
            status = future.result()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"active_rooms": status}).encode())
        else:
            self.send_error(404, "Not Found")

def run_server():
    server_address = ('0.0.0.0', 8080)  # nosec B104
    httpd = HTTPServer(server_address, RequestHandler)
    logger.info("Starting floor-bot on port 8080...")
    try:
        httpd.serve_forever()
    except Exception as e:
        logger.error(f"HTTP server error: {e}")
    finally:
        httpd.server_close()

async def main():
    manager.loop = asyncio.get_running_loop()
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        for slug in list(manager.rooms.keys()):
            await manager.stop_room(slug)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
