from __future__ import annotations

from unittest.mock import patch

import pytest

from portal.translations.providers.local import LocalProvider


@pytest.mark.anyio
async def test_local_provider_translate_success():
    provider = LocalProvider()
    with patch.object(provider, "_run_inference", return_value="Bonjour") as mock_inference:
        result = await provider.translate(
            provider_name="local",
            text="Hello",
            target_lang_name="French",
            target_lang_code="fr",
            source_lang_name="English",
            model="nllb-200-distilled-600M",
            api_key=None,
        )
        assert result == "Bonjour"
        mock_inference.assert_called_once_with("Hello", "eng_Latn", "fra_Latn", "nllb-200-distilled-600M")


@pytest.mark.anyio
async def test_local_provider_translate_invalid_language():
    provider = LocalProvider()
    result = await provider.translate(
        provider_name="local",
        text="Hello",
        target_lang_name="UnknownLanguage",
        target_lang_code="xx",
        source_lang_name="English",
        model="nllb-200-distilled-600M",
        api_key=None,
    )
    assert result is None
