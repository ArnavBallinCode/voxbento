import asyncio
import logging
import numpy as np
import io
import wave
import httpx
import json
import threading
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

# --- Local Model Caching ---
_current_model_size = None
_current_model = None
_model_lock = threading.Lock()

def get_model(model_size: str):
    global _current_model_size, _current_model
    if _current_model_size == model_size and _current_model is not None:
        return _current_model
    with _model_lock:
        if _current_model_size != model_size:
            logger.info(f"Loading faster-whisper model: {model_size}")
            if _current_model is not None:
                del _current_model
                import gc
                gc.collect()
            _current_model = WhisperModel(model_size, device="cpu", compute_type="int8")
            _current_model_size = model_size
    return _current_model

# --- Audio Utilities ---
def pcm_to_wav(pcm_data: bytes, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buf.getvalue()

# --- Providers ---
class TranscriptionProvider:
    async def process_chunk(self, chunk: bytes, language_code: str, model_variant: str, api_key: str | None) -> str:
        raise NotImplementedError

class LocalProvider(TranscriptionProvider):
    async def process_chunk(self, chunk: bytes, language_code: str, model_variant: str, api_key: str | None) -> str:
        audio_data = np.frombuffer(chunk, np.int16).astype(np.float32) / 32768.0
        return await asyncio.to_thread(self._run_inference, audio_data, language_code, model_variant)
        
    def _run_inference(self, audio_data: np.ndarray, language_code: str, model_size: str) -> str:
        model = get_model(model_size)
        segments, _ = model.transcribe(audio_data, beam_size=5, vad_filter=True, language=language_code)
        text = " ".join(segment.text for segment in segments)
        return text.strip()

class OpenAIProvider(TranscriptionProvider):
    async def process_chunk(self, chunk: bytes, language_code: str, model_variant: str, api_key: str | None) -> str:
        if not api_key:
            logger.error("OpenAI API key missing")
            return ""
        
        wav_data = pcm_to_wav(chunk)
        headers = {"Authorization": f"Bearer {api_key}"}
        files = {
            "file": ("audio.wav", wav_data, "audio/wav"),
        }
        data = {
            "model": model_variant,
            "language": language_code
        }
        
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post("https://api.openai.com/v1/audio/transcriptions", headers=headers, files=files, data=data, timeout=10.0)
                if resp.status_code == 200:
                    return resp.json().get("text", "").strip()
                else:
                    logger.error(f"OpenAI error: {resp.text}")
            except Exception as e:
                logger.error(f"OpenAI request failed: {e}")
        return ""

class DeepgramProvider(TranscriptionProvider):
    async def process_chunk(self, chunk: bytes, language_code: str, model_variant: str, api_key: str | None) -> str:
        if not api_key:
            logger.error("Deepgram API key missing")
            return ""
            
        headers = {
            "Authorization": f"Token {api_key}",
            "Content-Type": "audio/raw; encoding=linear16; sample_rate=16000; channels=1"
        }
        
        url = f"https://api.deepgram.com/v1/listen?model={model_variant}&language={language_code}"
        
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, headers=headers, content=chunk, timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json()
                    try:
                        return data["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
                    except (KeyError, IndexError):
                        pass
                else:
                    logger.error(f"Deepgram error: {resp.text}")
            except Exception as e:
                logger.error(f"Deepgram request failed: {e}")
        return ""

class NVIDIAProvider(TranscriptionProvider):
    async def process_chunk(self, chunk: bytes, language_code: str, model_variant: str, api_key: str | None) -> str:
        if not api_key:
            logger.error("NVIDIA API key missing")
            return ""
            
        wav_data = pcm_to_wav(chunk)
        headers = {"Authorization": f"Bearer {api_key}"}
        
        async with httpx.AsyncClient() as client:
            try:
                files = {"file": ("audio.wav", wav_data, "audio/wav")}
                # Placeholder NVIDIA parakeet NVCF endpoint
                url = "https://api.nvcf.nvidia.com/v2/nvcf/pexec/functions/ea20e3ad-2868-4a56-b0ff-94b1ef86e1cd"
                resp = await client.post(url, headers=headers, files=files, timeout=10.0)
                if resp.status_code == 200:
                    # In a real scenario, map NVIDIA's specific JSON structure
                    return str(resp.json()) 
            except Exception as e:
                logger.error(f"NVIDIA request failed: {e}")
        return ""

PROVIDERS = {
    'local': LocalProvider(),
    'openai': OpenAIProvider(),
    'deepgram': DeepgramProvider(),
    'nvidia': NVIDIAProvider(),
}

# --- Worker ---
active_workers: dict[str, asyncio.Task] = {}
active_processes: dict[str, asyncio.subprocess.Process] = {}

async def transcription_worker(event_slug: str, language_code: str, booth_id: str, broadcast_callback, provider_name: str, model_size: str, api_key: str | None):
    logger.info(f"Starting {provider_name} transcription worker for booth {booth_id}")
    rtsp_url = f"rtsp://mediamtx:8554/{event_slug}/{language_code}"
    
    provider = PROVIDERS.get(provider_name, PROVIDERS['local'])
    
    cmd = [
        "ffmpeg",
        "-rtsp_transport", "tcp",
        "-i", rtsp_url,
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        "-"
    ]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL
    )
    active_processes[booth_id] = process
    
    try:
        chunk_size_bytes = 16000 * 2 * 3 # 3 seconds
        
        while True:
            chunk = await process.stdout.readexactly(chunk_size_bytes)
            if not chunk:
                break
                
            text = await provider.process_chunk(chunk, language_code, model_size, api_key)
            
            if text:
                logger.debug(f"[{booth_id}] Transcribed: {text}")
                await broadcast_callback(booth_id, text)
                
    except asyncio.IncompleteReadError:
        logger.warning(f"[{booth_id}] ffmpeg stream ended abruptly.")
    except asyncio.CancelledError:
        logger.info(f"[{booth_id}] Transcription worker cancelled.")
        raise
    except Exception as e:
        logger.error(f"[{booth_id}] Transcription error: {e}")
    finally:
        if process.returncode is None:
            try:
                process.terminate()
                await process.wait()
            except ProcessLookupError:
                pass
        active_processes.pop(booth_id, None)
        active_workers.pop(booth_id, None)
        logger.info(f"[{booth_id}] Transcription worker exited.")

async def start_transcription_worker(event_slug: str, language_code: str, booth_id: str, broadcast_callback, provider: str, model_size: str, api_key: str | None = None):
    if booth_id in active_workers:
        logger.warning(f"Transcription worker for {booth_id} is already running.")
        return
        
    task = asyncio.create_task(transcription_worker(event_slug, language_code, booth_id, broadcast_callback, provider, model_size, api_key))
    active_workers[booth_id] = task

async def stop_transcription_worker(booth_id: str):
    task = active_workers.get(booth_id)
    if task:
        task.cancel()
        try:
            await task
        except Exception as e:
            logger.debug(f"Task finished with exception: {e}")
    
    process = active_processes.get(booth_id)
    if process and process.returncode is None:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
