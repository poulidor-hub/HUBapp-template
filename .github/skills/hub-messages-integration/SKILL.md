---
name: hub-messages-integration
description: 'Integrate or retrofit the Hub messaging system into an app: backend M2M send via /api/messages/m2m/send, frontend SSE stream + read receipts, MessageBanner and MessageArchive UI, /hub/ proxy for HTTPS. Use for adding Hub notifications, user messages, SSE events, or porting the messaging UI into a legacy app that already has M2M.'
argument-hint: 'Scope of the integration, for example: full integration, backend send only, frontend SSE only, or HTTPS proxy fix'
---

# Hub Messages Integration

Use this skill when the task involves sending Hub user messages, wiring the SSE event stream, displaying notifications, or retrofitting the Hub messaging system into an existing app that already has working M2M.

## Architecture Recap

- Sending happens on the backend with the M2M service account.
- Receiving, displaying, and acknowledging happen on the frontend with the user's Hub token.
- The app does not store messages locally; the Hub is the source of truth.
- The full reference is [docs/HUB_MESSAGES.md](../../../docs/HUB_MESSAGES.md).

## Prerequisites Before Touching Code

- M2M is registered and `get_m2m_token()` works in [backend/hub_client.py](../../../backend/hub_client.py).
- `/api/config` exposes `hub_api_url` and `hub_frontend_url` from [backend/main.py](../../../backend/main.py).
- A user auth context exists on the frontend, see [frontend/src/context/AuthContext.jsx](../../../frontend/src/context/AuthContext.jsx).
- For HTTPS, nginx must proxy `/hub/` with SSE-friendly settings, see [nginx.conf](../../../nginx.conf) and [nginx-ssl.conf](../../../nginx-ssl.conf).

## Procedure

1. Decide the scope.
   - Full integration, backend send only, frontend SSE + UI only, or HTTPS proxy hardening.

2. Backend send path.
   - Reuse `hub_client.send_user_message(...)` from [backend/hub_client.py](../../../backend/hub_client.py) instead of writing a new HTTP call.
   - For a smoke test or admin trigger, the existing route `POST /api/tests/messages/send` lives in [backend/routes/tests.py](../../../backend/routes/tests.py).
   - For business-driven sends, call `send_user_message` from a domain route or service, not from the frontend.
   - Required outbound headers are `Authorization: Bearer <m2m_token>` and `X-Slug: <APP_SLUG>` (handled by the helper).

3. Frontend reception path.
   - Extend the existing AuthContext in [frontend/src/context/AuthContext.jsx](../../../frontend/src/context/AuthContext.jsx) to:
     - load `GET {hub_api_url}/api/messages/me` and `GET /api/messages/me/unread-count`
     - open `EventSource({hub_api_url}/api/events/stream)`
     - handle `user_message`, `user_permissions_changed`, `force_logout`, `apps_updated`
     - call `POST /api/messages/{id}/read` and `POST /api/messages/read-all`
   - Mount [frontend/src/components/MessageBanner.jsx](../../../frontend/src/components/MessageBanner.jsx) and [frontend/src/components/MessageArchive.jsx](../../../frontend/src/components/MessageArchive.jsx) from the root layout, see [frontend/src/App.jsx](../../../frontend/src/App.jsx).
   - Reuse the matching CSS blocks `message-banner*` and `message-archive*` in [frontend/src/styles/index.css](../../../frontend/src/styles/index.css).
   - Keep `lucide-react` available in [frontend/package.json](../../../frontend/package.json) if you reuse the UI as is.

4. HTTPS proxy.
   - In HTTPS mode, the frontend must call the Hub through `/hub/` to avoid mixed content and to keep SSE alive.
   - Confirm the `location /hub/` block in [nginx-ssl.conf](../../../nginx-ssl.conf) has `proxy_buffering off`, `proxy_cache off`, and a long `proxy_read_timeout` (24h is the template default).
   - The frontend already switches to `${origin}/hub` automatically through [frontend/src/config.js](../../../frontend/src/config.js) and [frontend/src/context/ConfigContext.jsx](../../../frontend/src/context/ConfigContext.jsx); preserve that behavior.

5. Verify end to end.
   - Trigger the smoke test endpoint: `curl -X POST -H "Authorization: Bearer $TOKEN_ADMIN" http://localhost:9045/api/tests/messages/send`.
   - Check that MessageBanner shows the message immediately and MessageArchive lists it.
   - Confirm read receipts via the network tab (`POST /api/messages/{id}/read`).
   - In HTTPS, verify the SSE call goes through `/hub/api/events/stream` and stays open.

## Guardrails

- Do not reimplement message storage locally; the Hub owns the data.
- Do not call `/api/messages/m2m/send` from the frontend; it is M2M only.
- Do not strip `proxy_buffering off` from the `/hub/` location, it breaks SSE silently.
- Be aware that in the template `unreadMessages` actually holds the full archive; the real unread indicator is `unreadCount` and the live banner state is `activeMessages`.
