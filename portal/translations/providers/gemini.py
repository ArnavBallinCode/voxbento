import logging

import httpx

from portal.translations.providers.base import TranslationProvider

logger = logging.getLogger(__name__)


class GeminiProvider(TranslationProvider):
    async def translate(
        self,
        provider_name: str,
        text: str,
        target_lang_name: str,
        target_lang_code: str,
        source_lang_name: str,
        model: str,
        api_key: str | None,
    ) -> str | None:
        if not api_key:
            return None

        system_prompt = f"You are a professional interpreter. Translate the following {source_lang_name} text into {target_lang_name}. Output ONLY the translated text, nothing else."
        timeout = httpx.Timeout(10.0)

        import portal.globals as pg

        try:
            client = pg.get_http_client()
            res = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": api_key},
                json={
                    "systemInstruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"parts": [{"text": text}]}],
                },
                timeout=timeout,
            )
            res.raise_for_status()
            return res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            logger.error(f"Gemini translation failed for {target_lang_name}: {e}")
            return None
