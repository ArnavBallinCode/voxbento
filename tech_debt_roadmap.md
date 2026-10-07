# Technical Debt Audit Report
## 1. Executive Summary

This report identifies technical debt across the codebase and outlines a prioritized roadmap for improvements. The findings are based on static analysis tools (Vulture for dead code, Radon for cyclomatic complexity), reviewing `.agents/context/TECHNICAL_DEBT_REPORT.md`, and manual codebase inspection.

## 2. High-Priority Issues (Do This First)

### 2.1 Overly Complex Functions (Refactoring Required)
Several functions have extremely high cyclomatic complexity (Cyclomatic Complexity > 20) and are likely hard to test, maintain, and prone to bugs. These require refactoring (splitting into smaller helper functions, extracting logic).
* `portal/auth.py:resolve_ws_auth` (Complexity: 37) - Handles authentication logic for WebSockets with multiple nested checks and edge cases.
* `portal/routers/admin.py:admin_edit_room` (Complexity: 32) - Massive handler for room editing with multiple conditional form sections (general, relay, transcription, translation).
* `portal/routers/admin.py:admin_event_api_settings_post` (Complexity: 30) - Handles setting multiple API keys with repetitive `clear_*` and `update_*` logic.
* `portal/routers/listener.py:_embed_listener_impl` (Complexity: 30) - Complicated setup logic for embedding the listener page.
* `portal/translations/worker.py:TranslationWorker.handle_translation` (Complexity: 26) - Handles translation loop logic, likely with many edge cases for chunking/API errors.
* `portal/database.py:upsert_room` (Complexity: 25) - Complex room upsert logic.

### 2.2 Critical Security and Reliability Gaps
* **Missing Rate Limiting:** `/register`, `/login`, and `/admin/login` lack rate limiting (TD-08), exposing the system to brute-force attacks.
* **CSRF Protection:** Missing on admin form routes (`POST /admin/*`) (TD-02).
* **WebSocket Reconnection:** No proper reconnection handling on the server, leading to "ghost participants" when network drops (TD-11).
* **State Persistence:** `BoothRegistry` state is entirely in-memory, causing active interpreters to drop on portal restart (TD-03).

## 3. Medium-Priority Issues

### 3.1 Dead Code and Unused Logic
Vulture identified several unused pieces of code that should be removed to reduce cognitive load:
* **Unused Admin/Identity Logic:** `booth_id_to_mediamtx_path` and `mediamtx_path_to_booth_id` in `portal/booth_identity.py`.
* **Unused State Variables:** Many unused variables/attributes in `portal/booth_state.py` (e.g., `updated_at`, `joined_at`, `message_id`, `sender_name`, `sent_at`, `is_active_interpreter`, `set_ingest_status`).
* **Unused Config Variables:** `model_config`, `port`, `effective_mediamtx_internal_base`, `validate_production_secrets`, `supertonic_base_url` in `portal/config.py`.
* **Unused Database Helpers:** `set_sqlite_pragma` in `portal/database.py`.
* **Unused Auth Logic:** `verify_bearer` in `portal/auth.py`.

### 3.2 Inconsistent Abstractions & Architectural Issues
* **Process-Global Caches:** `_created_paths` in `portal/routers/api.py` is an uninvalidated process-global cache (TD-05). It should be replaced with a robust check or invalidation strategy upon MediaMTX unreachability.
* **Legacy Routes:** `GET /interpreter/{booth_id}` is legacy and should be removed (TD-10) in favor of the structured `/interpreter/{event_slug}/{language_code}`.
* **Shared Admin Password:** `ADMIN_PASSWORD` allows bypass of proper per-user admin accounts (TD-04). This pattern should be deprecated entirely.

### 3.3 Duplicated/Repetitive Logic
* **API Key Management:** `admin_event_api_settings_post` has repetitive `if clear_* ... elif *_api_key ...` logic that should be abstracted into a generic configuration updater.

## 4. Low-Priority Issues

* **Alembic Revisions:** Migration files use manual sequential integer prefixes (001-008) instead of Alembic's hex IDs (TD-09).
* **Hardcoded Limits:** `MAX_TOTAL_WORKERS` in `portal/transcription/worker.py` is hardcoded to 10 (TD-06). Move this to `Settings` in `portal/config.py`.
* **Missing Tests:** Several crucial logic paths lack tests: WebSocket token scope validation, CaptionAggregator finalization logic, Fernet key rotation, `set_active_interpreter` permissions, and admin panel route auth guards.
* **Documentation Drift:** `docs/how-it-works.mdx` needs updates to reflect the DB state and new transcription subsystem.

## 5. Prioritized Roadmap of Improvements

### Phase 1: Security & Stability (Immediate)
1. Add rate limiting (e.g., using `slowapi`) to `/register`, `/login`, and `/admin/login`.
2. Implement CSRF protection (double-submit cookies or token) on admin `POST` routes.
3. Remove the fallback shared `ADMIN_PASSWORD` mechanism in `portal/auth.py`.
4. Fix server-side WebSocket reconnection to prevent "ghost participants" on transient drops.

### Phase 2: Refactoring Complex Handlers (Next 2-4 Weeks)
1. **Refactor `resolve_ws_auth`:** Extract token validation logic and role checking into separate helper functions.
2. **Refactor Admin Settings:** Abstract the repetitive API key update/clear logic in `admin_event_api_settings_post` into a reusable dictionary/mapping loop.
3. **Refactor `admin_edit_room`:** Break down the form processing by section (e.g., `_process_general_section`, `_process_transcription_section`).
4. **Refactor Translation and Transcription Workers:** Extract logic inside `TranslationWorker.handle_translation` and `TranscriptionWorkerSession._run_loop` to reduce complexity and improve testability.

### Phase 3: Cleanup & Dead Code Removal (Ongoing)
1. Delete unused properties/methods identified by Vulture (e.g., in `booth_identity.py`, `booth_state.py`, `config.py`).
2. Remove legacy route `/interpreter/{booth_id}` and corresponding old logic.
3. Move `MAX_TOTAL_WORKERS` to `portal/config.py`.
4. Write missing tests for critical paths (WebSocket auth, `CaptionAggregator`).

### Phase 4: Architectural Enhancements (Long-Term)
1. Replace in-memory `BoothRegistry` state with Redis or database-backed state persistence for failover safety.
2. Implement proper cache invalidation for `_created_paths` interacting with MediaMTX.
3. Update Alembic configuration to generate random hex revision IDs for future migrations.
