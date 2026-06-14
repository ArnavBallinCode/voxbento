from __future__ import annotations


class FakeResponse:
    def __init__(self, data):
        self.data = data
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from portal.models import DBBooth, Event, Room, TranscriptSegment, TranscriptTranslation
from portal.translations.constants import TranslationProviderEnum
from portal.translations.worker import TranslationWorker


@pytest.fixture
def mock_broadcast_callback():
    return AsyncMock()


@pytest.fixture
def worker(mock_broadcast_callback):
    return TranslationWorker(broadcast_callback=mock_broadcast_callback)


@pytest.mark.anyio
class TestTranslationWorker:
    async def test_get_translation_api_key(self, worker):
        event = Event(
            encrypted_translation_openai_api_key="enc-openai",
            encrypted_openrouter_api_key="enc-or",
            encrypted_gemini_api_key="enc-gemini",
            encrypted_anthropic_api_key="enc-anthropic",
            encrypted_groq_api_key="enc-groq",
        )

        with patch("portal.translations.worker.decrypt_val", side_effect=lambda x: x.replace("enc-", "dec-")):
            assert worker._get_translation_api_key(event, TranslationProviderEnum.OPENAI.value) == "dec-openai"
            assert worker._get_translation_api_key(event, TranslationProviderEnum.OPENROUTER.value) == "dec-or"
            assert worker._get_translation_api_key(event, TranslationProviderEnum.GEMINI.value) == "dec-gemini"
            assert worker._get_translation_api_key(event, TranslationProviderEnum.ANTHROPIC.value) == "dec-anthropic"
            assert worker._get_translation_api_key(event, TranslationProviderEnum.GROQ.value) == "dec-groq"
            assert worker._get_translation_api_key(event, "unknown") is None

    async def test_call_llm_openai(self, worker):
        mock_response = FakeResponse({"choices": [{"message": {"content": "Bonjour"}}]})

        # Create a mock client class that we inject
        class MockClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def post(self, *args, **kwargs):
                self.post_args = (args, kwargs)
                return mock_response

        mock_client = MockClient()

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker._call_llm(
                TranslationProviderEnum.OPENAI.value, "gpt-4", "test-key", "Hello", "French"
            )

            assert result == "Bonjour"
            assert mock_client.post_args[0][0] == "https://api.openai.com/v1/chat/completions"
            assert mock_client.post_args[1]["headers"]["Authorization"] == "Bearer test-key"
            assert mock_client.post_args[1]["json"]["model"] == "gpt-4"
            assert mock_client.post_args[1]["json"]["messages"][1]["content"] == "Hello"

    async def test_call_llm_anthropic(self, worker):
        mock_response = FakeResponse({"content": [{"text": "Bonjour"}]})

        class MockClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def post(self, *args, **kwargs):
                self.post_args = (args, kwargs)
                return mock_response

        mock_client = MockClient()

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await worker._call_llm(
                TranslationProviderEnum.ANTHROPIC.value, "claude-3", "test-key", "Hello", "French"
            )

            assert result == "Bonjour"
            assert mock_client.post_args[0][0] == "https://api.anthropic.com/v1/messages"
            assert mock_client.post_args[1]["headers"]["x-api-key"] == "test-key"
            assert mock_client.post_args[1]["json"]["model"] == "claude-3"
            assert mock_client.post_args[1]["json"]["messages"][0]["content"] == "Hello"

    async def test_call_llm_local(self, worker):
        result = await worker._call_llm(
            TranslationProviderEnum.LOCAL.value, "local-model", "test-key", "Hello", "French"
        )
        assert result == "[French] Hello"

    async def test_translate_and_broadcast_success(self, worker, mock_broadcast_callback):
        event = Event(id=1)
        room = Room(id=1)

        mock_session_instance = AsyncMock()
        # the add method is synchronous
        mock_session_instance.add = MagicMock()
        mock_session_context = AsyncMock()
        mock_session_context.__aenter__.return_value = mock_session_instance

        with patch.object(worker, "_call_llm", new_callable=AsyncMock) as mock_call_llm:
            mock_call_llm.return_value = "Bonjour"

            with patch("portal.translations.worker.get_session", return_value=mock_session_context):
                await worker._translate_and_broadcast(
                    event, room, "openai", "gpt-4", "test-key", "fr", "French", 10, "Hello", "booth-1"
                )

                mock_call_llm.assert_called_once_with("openai", "gpt-4", "test-key", "Hello", "French")

                mock_session_instance.add.assert_called_once()
                added_translation = mock_session_instance.add.call_args[0][0]
                assert isinstance(added_translation, TranscriptTranslation)
                assert added_translation.segment_id == 10
                assert added_translation.language_code == "fr"
                assert added_translation.text == "Bonjour"

                mock_session_instance.commit.assert_called_once()

                mock_broadcast_callback.assert_called_once_with(
                    "booth-1", {"type": "translation", "language_code": "fr", "text": "Bonjour"}
                )

    async def test_translate_and_broadcast_llm_failure(self, worker, mock_broadcast_callback):
        event = Event(id=1)
        room = Room(id=1)

        with patch.object(worker, "_call_llm", new_callable=AsyncMock) as mock_call_llm:
            mock_call_llm.return_value = None  # Simulating failure

            with patch("portal.translations.worker.get_session") as mock_get_session:
                await worker._translate_and_broadcast(
                    event, room, "openai", "gpt-4", "test-key", "fr", "French", 10, "Hello", "booth-1"
                )

                mock_call_llm.assert_called_once()
                mock_get_session.assert_not_called()
                mock_broadcast_callback.assert_not_called()

    async def test_handle_translation_floor(self, worker):
        mock_session_instance = AsyncMock()
        mock_session_context = AsyncMock()
        mock_session_context.__aenter__.return_value = mock_session_instance

        # Mocks for database scalars
        segment = TranscriptSegment(id=10, booth_id=None)

        # We need a proper mock object for room to avoid sqlalchemy __setattr__ issues
        room = MagicMock()
        room.id = 1
        room.event_id = 2
        room.floor_translation_enabled = True
        room.floor_translation_provider = "openai"
        room.floor_translation_model = "gpt-4"

        mock_lang = MagicMock()
        mock_lang.language_code = "fr"
        mock_lang.language_name = "French"
        mock_lang.enabled = True

        room.translation_languages = [mock_lang]

        event = Event(id=2, encrypted_translation_openai_api_key="enc-key")

        # scalar side effects
        async def mock_scalar(stmt):
            stmt_str = str(stmt)
            if "transcript_segments" in stmt_str:
                return segment
            elif "rooms" in stmt_str:
                return room
            elif "events" in stmt_str:
                return event
            return None

        mock_session_instance.scalar.side_effect = mock_scalar

        with patch("portal.translations.worker.get_session", return_value=mock_session_context):
            with patch.object(worker, "_get_translation_api_key", return_value="dec-key"):
                with patch.object(worker, "_translate_and_broadcast", new_callable=AsyncMock) as mock_tab:
                    await worker.handle_translation(1, 10, "Hello", "booth-str")

                    mock_tab.assert_called_once_with(
                        event, room, "openai", "gpt-4", "dec-key", "fr", "French", 10, "Hello", "booth-str"
                    )
