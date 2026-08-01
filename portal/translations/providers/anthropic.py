import logging

import httpx

from portal.translations.providers.base import TranslationProvider

logger = logging.getLogger(__name__)


class AnthropicProvider(TranslationProvider):
    async def translate(
        self,
        provider_name: str,
        text: str,
        target_lang_name: str,
        target_lang_code: str,
        model: str,
        api_key: str | None,
    ) -> str | None:
        if not api_key:
            return None

        system_prompt = f"You are a professional interpreter. Translate the following text into {target_lang_name}. Output ONLY the translated text, nothing else."
        timeout = httpx.Timeout(10.0)

        import portal.globals as pg

        try:
            client = pg.get_http_client()
            res = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                json={
                    "model": model,
                    "max_tokens": 1024,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": text}],
                },
                timeout=timeout,
            )
            res.raise_for_status()
            return res.json()["content"][0]["text"].strip()
        except Exception as e:
            logger.error(f"Anthropic translation failed for {target_lang_name}: {e}")
            return None
