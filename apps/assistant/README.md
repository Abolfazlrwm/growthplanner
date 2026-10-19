# Planning assistant

Parent integration must add `apps.assistant` to `INSTALLED_APPS`, include
`path("assistant/", include("apps.assistant.urls"))` in the root URLconf, and run
`python manage.py migrate assistant`.

Endpoints (all authenticated, POST endpoints require CSRF):

- `GET /assistant/` — page and the latest user-owned conversation
- `POST /assistant/chat/` — chat JSON
- `POST /assistant/accept/` — explicit task-draft confirmation
- `POST /assistant/clear/` — deletes the requesting user's conversation history

The server reads only `MANUS_API_URL` / `MANUS_API_KEY` at runtime, with the
legacy `BUILT_IN_FORGE_API_URL` / `BUILT_IN_FORGE_API_KEY` aliases supported.
No key is rendered into HTML or JavaScript. `AI_MODEL` defaults to `gpt-6-luna`.
