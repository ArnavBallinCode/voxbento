from __future__ import annotations

import logging

import httpx

from portal.translations.constants import OPENAI_COMPATIBLE_ENDPOINTS
from portal.translations.providers.base import TranslationProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(TranslationProvider):
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

        endpoint = OPENAI_COMPATIBLE_ENDPOINTS.get(provider_name)
        if not endpoint:
            logger.error(f"Endpoint not found for provider {provider_name}")
            return None

        system_prompt = f"You are a professional interpreter. Translate the following {source_lang_name} text into {target_lang_name}. Output ONLY the translated text, nothing else."
        timeout = httpx.Timeout(10.0)

        import portal.globals as pg

        try:
            client = pg.get_http_client()
            res = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": text}],
                },
                timeout=timeout,
            )
            res.raise_for_status()
            return res.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"OpenAI translation failed for {target_lang_name}: {e}")
            return None
