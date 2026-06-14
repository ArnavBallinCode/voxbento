import asyncio
import os
import signal
import subprocess
import urllib.parse

from playwright.async_api import async_playwright


def setup_pulseaudio(event_slug, pulse_socket, sink_name):
    pulse_dir = f"/tmp/pulse-dir-{event_slug}"
    os.makedirs(pulse_dir, exist_ok=True)

    subprocess.run(["pkill", "-f", f"ffmpeg.*{event_slug}"], stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-f", f"pulseaudio.*{event_slug}"], stderr=subprocess.DEVNULL)
    if os.path.exists(pulse_socket):
        try:
            os.remove(pulse_socket)
        except OSError:
            pass

    pulse_proc = subprocess.Popen(
        [
            "pulseaudio",
            "--daemonize=no",
            "--exit-idle-time=-1",
            "--disallow-exit",
            "-n",
            "-L",
            f"module-native-protocol-unix auth-anonymous=1 socket={pulse_socket}",
            "-L",
            f"module-null-sink sink_name={sink_name}",
            "-L",
            "module-always-sink",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return pulse_proc


async def launch_browser(pw, env, jitsi_url):
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
            "--disable-dev-shm-usage",
        ],
    )

    context = await browser.new_context(permissions=["microphone", "camera"], ignore_https_errors=True)

    page = await context.new_page()
    page.on("console", lambda m: print(f"Browser: {m.text}"))
    page.on("pageerror", lambda err: print(f"Browser Error: {err}"))

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

    return browser


async def start_ffmpeg(sink_name, event_slug, mediamtx_rtsp_base, env):
    ffmpeg_proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-f",
        "pulse",
        "-i",
        f"{sink_name}.monitor",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "libopus",
        "-b:a",
        "32k",
        "-vbr",
        "on",
        "-compression_level",
        "10",
        "-application",
        "lowdelay",
        "-f",
        "rtsp",
        "-rtsp_transport",
        "tcp",
        f"{mediamtx_rtsp_base}/{event_slug}/floor",
        env=env,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return ffmpeg_proc


async def cleanup_resources(ffmpeg_proc, browser, pw, pulse_proc, pulse_socket):
    if ffmpeg_proc is not None and ffmpeg_proc.returncode is None:
        ffmpeg_proc.terminate()
        try:
            await ffmpeg_proc.wait()
        except Exception:
            pass
    if browser is not None:
        await browser.close()
    if pw is not None:
        await pw.stop()
    if pulse_proc is not None and pulse_proc.poll() is None:
        pulse_proc.terminate()
    if os.path.exists(pulse_socket):
        try:
            os.remove(pulse_socket)
        except OSError:
            pass


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

    if not event_slug or not jitsi_url or not mediamtx_rtsp_base:
        print("Missing required environment variables.")
        return

    pulse_socket = f"/tmp/pulse-{event_slug}.sock"
    sink_name = f"sink_{event_slug}"

    pulse_proc = setup_pulseaudio(event_slug, pulse_socket, sink_name)

    pw = None
    browser = None
    ffmpeg_proc = None

    try:
        await asyncio.sleep(2)

        env = os.environ.copy()
        env["PULSE_SERVER"] = f"unix:{pulse_socket}"

        pw = await async_playwright().start()
        browser = await launch_browser(pw, env, jitsi_url)
        ffmpeg_proc = await start_ffmpeg(sink_name, event_slug, mediamtx_rtsp_base, env)

        await ffmpeg_proc.wait()

    except asyncio.CancelledError:
        print("run_capture cancelled")
    finally:
        await cleanup_resources(ffmpeg_proc, browser, pw, pulse_proc, pulse_socket)


if __name__ == "__main__":
    asyncio.run(run_capture())
