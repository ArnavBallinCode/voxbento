# Repository Documentation Audit Report

## Updated Files
- `docs/how-it-works.mdx`: Fixed incorrect reference to `/ws/translations/{channel_id}` by pointing to `/ws/captions/{channel_id}`.
- `CONTRIBUTING.md`: Fixed alembic commands to correctly use `uv run`. Added missing `MediaMTX RTSP` port (`8554`) to the ports table.
- `docs/api/websocket/captions.mdx`: Added missing documentation for `translation` events broadcast over the captions WebSocket endpoint.

## New Files
- `.cursor/rules.md`: Agent configuration file to point to canonical project rules.
- `.windsurf/rules.md`: Agent configuration file to point to canonical project rules.
- `CLAUDE.md`: Agent configuration file to point to canonical project rules.

## Removed Content
- `.agents/context/architecutre.md`: Removed obsolete empty typo file that was not utilized.

## Key Findings
- **Translation Pipeline State**: The translation feature broadcasts payloads directly over `/ws/captions/{channel_id}` as `"type": "translation"` rather than a separate websocket, which was poorly documented in architecture overview and entirely missing in API docs.
- **`CONTRIBUTING.md` Drift**: Commands were outdated due to the transition to `uv` and missed a critical system port (`8554` for RTSP ingestion).
- **Agents.md Linkage**: Popular agent environments (Cursor, Windsurf, Claude) did not have local pointer files, risking context drift.

## Remaining Gaps
- `fastapi_app.py` is documented in `TECHNICAL_DEBT_REPORT.md` as needing a split; currently the single monolith continues to present a challenge for understanding but remains comprehensively documented in `ROUTE_MAP.md`.
- No separate translation websocket was found to exist despite mentions in older architectural assumptions, standardizing on `/ws/captions/` as the single event source.

## Documentation Health Assessment
- **Accuracy**: 4/5 (Greatly improved, but translation logic complexity suggests potential for future edge case discovery).
- **Completeness**: 5/5 (Covered all core systems based on recent migrations and current `fastapi_app.py` state).
- **Onboarding Quality**: 5/5 (Agent and developer bootstrapping files accurately point to context files).
- **Agent Context Quality**: 5/5 (Central `agents.md` is strictly enforced and directly cross-referenced).
- **Maintainability**: 4/5 (Robust, but dependent on manual cross-updating when introducing endpoints to the monolithic app file).

### Recommendations
1. Ensure API documentation is enforced in CI PR reviews.
2. Consider standardizing WebSocket payload formats into a central JSON Schema file to automatically generate documentation.
