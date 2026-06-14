import json
import logging
import os
import subprocess  # nosec B404
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("floor-bot")


class SubprocessManager:
    def __init__(self):
        self.rooms: Dict[str, subprocess.Popen] = {}
        self.lock = threading.Lock()

    def start_room(self, event_slug: str, jitsi_url: str, mediamtx_rtsp_base: str):
        with self.lock:
            if event_slug in self.rooms:
                self.stop_room_locked(event_slug)

            logger.info(f"Starting subprocess for event: {event_slug}")
            env = os.environ.copy()
            env["BOT_EVENT_SLUG"] = event_slug
            env["BOT_JITSI_URL"] = jitsi_url
            env["BOT_MEDIAMTX_RTSP_BASE"] = mediamtx_rtsp_base

            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capture.py")
            cmd = ["python", "-u", script_path]

            proc = subprocess.Popen(  # nosec B603
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, env=env
            )

            def log_stream(stream, prefix):
                for line in iter(stream.readline, ""):
                    logger.info(f"{prefix}: {line.strip()}")

            threading.Thread(target=log_stream, args=(proc.stdout, f"bot[{event_slug}] stdout"), daemon=True).start()
            threading.Thread(target=log_stream, args=(proc.stderr, f"bot[{event_slug}] stderr"), daemon=True).start()

            self.rooms[event_slug] = proc

    def stop_room_locked(self, event_slug: str):
        if event_slug in self.rooms:
            logger.info(f"Terminating subprocess for {event_slug}")
            proc = self.rooms[event_slug]
            if proc.poll() is None:
                proc.terminate()
            del self.rooms[event_slug]

    def stop_room(self, event_slug: str):
        with self.lock:
            self.stop_room_locked(event_slug)


manager = SubprocessManager()


class RequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        try:
            req = json.loads(post_data.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(400, "Bad Request: Invalid JSON")
            return

        if self.path == "/start":
            event_slug = req.get("event_slug")
            jitsi_url = req.get("jitsi_url")
            mediamtx_rtsp_base = req.get("mediamtx_rtsp_base")
            if not all([event_slug, jitsi_url, mediamtx_rtsp_base]):
                self.send_error(400, "Missing parameters")
                return
            manager.start_room(event_slug, jitsi_url, mediamtx_rtsp_base)
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started", "event_slug": event_slug}).encode())

        elif self.path == "/stop":
            event_slug = req.get("event_slug")
            if not event_slug:
                self.send_error(400, "Missing event_slug")
                return
            manager.stop_room(event_slug)
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "stopped", "event_slug": event_slug}).encode())
        else:
            self.send_error(404, "Not Found")

    def do_GET(self):
        if self.path == "/status":
            status = {}
            with manager.lock:
                for event_slug, proc in manager.rooms.items():
                    if proc.poll() is not None:
                        status[event_slug] = {"state": "dead", "exit_code": proc.returncode}
                    else:
                        status[event_slug] = {"state": "healthy", "pid": proc.pid}
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"active_rooms": status}).encode())
        else:
            self.send_error(404, "Not Found")


if __name__ == "__main__":
    server_address = ("0.0.0.0", 8080)  # nosec B104
    httpd = HTTPServer(server_address, RequestHandler)
    logger.info("Starting floor-bot on port 8080...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for slug in list(manager.rooms.keys()):
            manager.stop_room(slug)
        httpd.server_close()
