from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from portal.transcription.worker import active_processes, active_workers, stop_transcription_worker


class MockTask:
    def __init__(self):
        self.cancel_called = False
        self.awaited = False
        self.raise_exc = None
        self.raise_cancel = False

    def cancel(self):
        self.cancel_called = True

    def __await__(self):
        self.awaited = True

        async def _await_logic():
            if self.raise_cancel:
                raise asyncio.CancelledError()
            if self.raise_exc:
                raise self.raise_exc
            return

        return _await_logic().__await__()


@pytest.fixture(autouse=True)
def clean_state():
    """Ensure a clean state for active_workers and active_processes before and after each test."""
    active_workers.clear()
    active_processes.clear()
    yield
    active_workers.clear()
    active_processes.clear()


@pytest.mark.anyio
async def test_stop_transcription_worker_happy_path():
    booth_id = "test-booth-1"

    mock_process = MagicMock()
    mock_process.returncode = None

    mock_task = MockTask()
    mock_stderr_task = MagicMock()

    active_processes[booth_id] = mock_process
    active_workers[booth_id] = {
        "task": mock_task,
        "provider": "openai",
        "model_size": "large",
        "stderr_task": mock_stderr_task,
    }

    await stop_transcription_worker(booth_id)

    # Assert process is terminated
    mock_process.terminate.assert_called_once()

    # Assert tasks are cancelled
    mock_stderr_task.cancel.assert_called_once()
    assert mock_task.cancel_called
    assert mock_task.awaited

    # Assert state is cleaned
    assert booth_id not in active_processes
    assert booth_id not in active_workers


@pytest.mark.anyio
async def test_stop_transcription_worker_non_existent_booth():
    booth_id = "non-existent-booth"

    # Calling on non-existent booth should not raise an exception
    await stop_transcription_worker(booth_id)


@pytest.mark.anyio
async def test_stop_transcription_worker_process_already_exited():
    booth_id = "test-booth-2"

    mock_process = MagicMock()
    mock_process.returncode = 0  # Not None, so it has exited

    mock_task = MockTask()

    active_processes[booth_id] = mock_process
    active_workers[booth_id] = {"task": mock_task, "provider": "openai", "stderr_task": None}

    await stop_transcription_worker(booth_id)

    # Assert process.terminate() is NOT called since it already exited
    mock_process.terminate.assert_not_called()
    assert mock_task.cancel_called


@pytest.mark.anyio
async def test_stop_transcription_worker_process_lookup_error():
    booth_id = "test-booth-3"

    mock_process = MagicMock()
    mock_process.returncode = None
    mock_process.terminate.side_effect = ProcessLookupError("Process not found")

    mock_task = MockTask()

    active_processes[booth_id] = mock_process
    active_workers[booth_id] = {"task": mock_task, "provider": "openai", "stderr_task": None}

    # Should handle ProcessLookupError gracefully
    await stop_transcription_worker(booth_id)

    mock_process.terminate.assert_called_once()
    assert mock_task.cancel_called


@pytest.mark.anyio
@patch("portal.transcription.providers.local.decrement_model_ref")
async def test_stop_transcription_worker_local_provider(mock_decrement):
    booth_id = "test-booth-local"

    mock_process = MagicMock()
    mock_process.returncode = None
    mock_task = MockTask()

    active_processes[booth_id] = mock_process
    active_workers[booth_id] = {"task": mock_task, "provider": "local", "model_size": "tiny", "stderr_task": None}

    await stop_transcription_worker(booth_id)

    # Verify local model ref count was decremented
    mock_decrement.assert_called_once_with("tiny")


@pytest.mark.anyio
@patch("portal.transcription.worker.logger")
async def test_stop_transcription_worker_task_exception(mock_logger):
    booth_id = "test-booth-ex"

    mock_process = MagicMock()
    mock_process.returncode = None

    mock_task = MockTask()
    mock_task.raise_exc = RuntimeError("Unexpected failure")

    active_processes[booth_id] = mock_process
    active_workers[booth_id] = {"task": mock_task, "provider": "openai", "stderr_task": None}

    # Should not bubble up the exception
    await stop_transcription_worker(booth_id)

    # Logger should have recorded the exception
    mock_logger.error.assert_called_once()
    assert "Task finished with exception" in mock_logger.error.call_args[0][0]


@pytest.mark.anyio
async def test_stop_transcription_worker_cancelled_error_ignored():
    booth_id = "test-booth-cancelled"

    mock_process = MagicMock()
    mock_process.returncode = None

    mock_task = MockTask()
    mock_task.raise_cancel = True

    active_processes[booth_id] = mock_process
    active_workers[booth_id] = {"task": mock_task, "provider": "openai", "stderr_task": None}

    # Should not bubble up the exception, and should not log it as an error
    with patch("portal.transcription.worker.logger.error") as mock_logger_error:
        await stop_transcription_worker(booth_id)
        mock_logger_error.assert_not_called()
