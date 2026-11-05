# Avito Chat Analyzer — MVP

## Product goal
Provide a standalone workspace for collecting and analyzing Avito conversations across multiple accounts, including accounts without Messenger API entitlement where a user-authorized browser export is available. Chat analysis must not depend on Client ID, Client Secret or OAuth tokens.

## Agreed collection strategy: hybrid

Use two independent ingestion paths that produce the same normalized message format:

1. **Browser-assisted export:** explicit user-initiated export from content visible in the normal Avito interface. The first implementation is a deliberately limited Chrome extension prototype that exports only text explicitly selected by the user.
2. **Official Messenger API (optional):** use it for accounts whose category/subscription and authorization permit access. Do not require this route for every account.

The browser-assisted path must use only content the signed-in user can access in the normal Avito interface and explicit user action. Do not extract passwords, cookies, session tokens or hidden credentials; do not call undocumented private endpoints, bypass access controls, or automate sending/deleting/reading messages. Respect Avito terms and applicable privacy requirements. If compliant collection from the rendered interface is not technically or contractually available, use a user-generated export/import instead.

## Chrome extension prototype — v0.1.0

Location: `browser-extension/` on branch `feature/chat-analyzer-mvp`.

Implemented:
- Chrome Manifest V3 popup with account label and optional date range.
- User explicitly selects visible chat text and presses the export button.
- Extension reads only `window.getSelection()` from the active Avito tab.
- Generates a versioned JSON file locally.
- No cookies, passwords, tokens, internal endpoints, background polling, message actions or server upload.

Known limitations:
- It exports only the selected text, not all chats or full conversation history.
- It does not reliably split messages, identify authors or recover timestamps.
- It does not upload to the server; this is a local prototype and has not been tested against a live Avito chat.
- The JSON schema is provisional and must be reconciled with a real, sanitized sample before implementing a robust importer.

## Important operating limitation

A browser export requires an active browser session and the user's computer at export time. It cannot continuously sync while the computer is off. After import, storage and analytics run on the server independently. Background incremental updates while the computer is off are possible only through an authorized server-side source (for example, official API/webhooks where available). Otherwise the user repeats the export periodically.

## User workflow — current prototype

1. Install the unpacked extension from `browser-extension/` using `chrome://extensions` and Developer mode.
2. Open the relevant Avito conversation in the normal browser session.
3. Select the visible message text manually.
4. Open the extension, enter an account label and optional date range, then generate JSON.
5. Inspect and sanitize the JSON before sharing it for schema validation.

The future workflow may add structured message parsing and authenticated upload only after the rendered UI structure, attribution accuracy, privacy requirements and Avito rules have been checked.

## Architecture

- **Account registry:** internal account ID, label, collection mode (browser import or official API), source account identifier when available, last import/sync time and status.
- **Browser exporter/import adapter:** explicit user-initiated export; versioned JSON schema; no credentials/session material in the exported file.
- **Official API collector:** separate optional read-only path for eligible accounts.
- **Normalization layer:** maps both sources to one schema for accounts, chats, messages, timestamps, sender direction, attachments metadata and source provenance.
- **Storage:** persistent database; unique message identity scoped by account and chat; import batches and checkpoints for idempotency.
- **Chat Analyzer:** operates only on normalized stored messages. It must not know Client ID, Client Secret or OAuth tokens.
- **UI:** account switcher, import/upload, date range, import status, chat list, conversation detail, analysis summary and export.
- **Background processing:** server handles normalization and analytics after upload; scheduled API sync only for eligible official-API connections.
- **Business Analytics integration:** optional consumer of normalized chat data; not a dependency of Chat Analyzer.

## MVP analysis

Report observable metrics and evidence: conversation/message counts; last inbound message awaiting a reply; response-time sample and average only where sender and timestamps are known; repeated customer questions and objections; possible price, availability, delivery, trust and competitor themes; possible purchase-intent phrases.

Every inferred reason must be labelled as a text signal, not a confirmed lost sale. A purchase-intent phrase is not a confirmed order. Unknown sender direction must not be guessed.

## Security and reliability

- Never place secrets in source control, logs, chat messages or exported reports.
- Do not collect or transmit browser cookies, passwords, access tokens or other session credentials.
- Keep uploads authenticated, size-limited, validated and associated with the selected internal account.
- Treat imported message content as private customer data; restrict access and define retention/deletion controls before production.
- Encrypt server-side API refresh tokens at rest for official API connections.
- Use a persistent database and backups; ephemeral application filesystem is not sufficient.
- Make imports idempotent; retain source filename, schema version, import time and error report.
- Keep all automated API operations read-only.

## Known implementation state

The repository contains a read-only client based on Client Credentials, a SQLite chat/message store, an initial full-sync service and an analyzer for manually uploaded exports. The Chrome extension v0.1.0 now exists as a local-selection export prototype. OAuth multi-account lifecycle is not implemented; the current sync service is a one-account initial backfill; the Flask app has no Chat Analyzer UI or account switcher; extension output has not been validated against real chat data; Render persistent storage and background worker/scheduler are not configured or verified. No production deployment has been performed for this prototype.

## Delivery order

1. Install and test the local extension on one Avito account with a non-sensitive test conversation.
2. Review the generated JSON and define the normalized schema using a sanitized real sample.
3. Implement and test a secure JSON import adapter, internal account registry and idempotent normalization.
4. Add import UI, chat list/detail and analysis for imported data.
5. Decide whether structured browser extraction is feasible and compliant; if so, validate DOM selectors and sender/timestamp attribution before implementation.
6. Keep official API integration as an optional connector for accounts with entitlement.
7. Deploy with persistent storage and verify imports with two separate Avito accounts.


## Automatic collection work — 2026-11-05

The user's required workflow is now explicit: choose an account and date interval, start one operation, and have the system collect all accessible conversations/messages in that interval and produce an analysis report. Manual text selection is not an acceptable product workflow; v0.1.0 is only a proof of extension installation and local file generation.

### Source feasibility

- The existing chat_analytics/avito_client.py already contains read-only calls for account self, chat listing (Messenger v2) and message history (Messenger v3).
- The official Messenger API is the most reliable automated source where the account has entitlement. The read operations are GET /messenger/v2/accounts/{user_id}/chats and GET /messenger/v3/accounts/{user_id}/chats/{chat_id}/messages/. Do not call write operations such as send, mark-read or delete.
- API availability depends on the account's category/subscription and approved application access. Confirm entitlement per account before promising server-side automatic collection.
- For accounts without API entitlement, a browser-assisted path remains an investigation, not an implemented capability. Before coding selectors, inspect the live rendered chat-list and chat-detail UI and validate message boundaries, sender attribution, timestamps, pagination, lazy loading and Avito terms. Never use private endpoints, cookies, tokens or access-control bypasses. If a compliant full-history UI export is not feasible, use a user-generated export/import.

### Normalized message contract

Added chat_analytics/normalization.py with schema version 1.0. It maps explicit source field paths into: internal account ID, conversation ID, message ID, UTC timestamp (or null), sender type (customer/seller/unknown), text, attachment metadata and source provenance. Unknown sender direction is preserved as unknown; numeric timestamps require source-specific explicit conversion. Tests are in tests/test_chat_normalization.py.

### Next implementation steps

1. Run CI/unit tests for the normalization contract.
2. Extend the official API sync to accept a date interval, persist only matching messages while retaining idempotent message IDs, and report coverage/partial failures.
3. Add a secure server-side account registry and authenticated sync trigger; secrets stay in server environment variables and never in the extension.
4. Add report endpoints/UI for chat counts, message counts, reply latency (only when sender/time are known), unanswered inbound messages and text-based objection signals.
5. Separately inspect a live Avito chat UI before deciding whether a compliant browser collector can replace manual selection for non-API accounts.

### Current product truth

Automatic all-chat collection is not yet delivered. The installed Chrome extension remains v0.1.0 and only exports manually selected text. The new normalization layer is a backend foundation, not an end-to-end collector. No production deployment or merge to main has been made.


### Date-scoped API sync foundation — 2026-11-05

The read-only sync service now accepts optional date_from/date_to bounds, supports ISO timestamps and Unix seconds/milliseconds in API message records, applies an inclusive calendar-date range, and returns counts for fetched, stored, out-of-range and unknown-timestamp messages. When a date filter is active, messages with unknown timestamps are excluded rather than guessed. Important limitation: the current API still enumerates chats and fetches each chat's message pages before filtering locally; server-side date-range query optimization has not been verified. Added unit tests for period parsing and timestamp handling in tests/test_chat_sync_period.py. CI execution has not yet been observed.


### Verification — 2026-11-05

GitHub Actions run 72 for commit bf4dd76 completed successfully. The job `test-data-validation` passed, including the Python test step and the JavaScript filters/sorting test step. This confirms the repository test workflow passed for the normalization and date-filtering changes present at that commit. The subsequent documentation-only commits do not change runtime code.


## Browser UI diagnostics — extension v0.2.0 — 2026-11-05

The user supplied screenshots of the Avito message list and an open conversation. The list UI visibly presents buyer name, listing title/price, last-message preview/time and labels such as waiting-for-reply/active-interest. The conversation UI distinguishes inbound/outbound bubbles and displays message times and delivery/read indicators. Screenshots establish the visible product structure but not DOM selectors, pagination or loading behavior.

The extension was updated to v0.2.0 with an explicit local diagnostic action. On each screen, it records only visible DOM structural metadata: tag/class signatures, repeated-element counts, presence (not values) of ARIA attributes, data-attribute names, child counts and bounding rectangles. It does not read or save message text, names, aria-label values, links, form values, cookies or network data; it does not upload anything. User should run it once on the chat list and once inside an open conversation and provide both JSON files.

This is a diagnostic step, not an automatic chat collector. After reviewing the two sanitized diagnostics, identify candidate repeated chat-row/message elements and decide whether a compliant UI-driven collection path is feasible. Do not automate navigation/history collection until selectors, pagination/lazy loading and sender/timestamp attribution can be validated.


## One-click period analysis implementation — 2026-11-05

The selected workflow is a server-side one-click run: open /chat-analyzer, enter the protected access key and date range, run the official Messenger API collector, then render a period report. The Chrome extension is not required for the official API route.

Implemented in feature/chat-analyzer-mvp:
- chat_analytics/store.py: query stored messages by inclusive date range (internally UTC, end-exclusive).
- chat_analytics/sync_service.py: read-only list chats and retrieve message histories; persist complete accessible histories to preserve conversation context; count messages inside the selected interval; collect per-chat failures and return partial status instead of aborting all remaining chats.
- chat_analytics/report.py: period report with chat/message counts, customer/seller/unknown sender counts, last sender/message, awaiting-reply signal, average first response where author and timestamps are available, and customer text-topic signals.
- chat_analytics/api.py: protected POST /api/chat-analyzer/sync plus /chat-analyzer page. Requires CHAT_ANALYZER_ACCESS_KEY and AVITO_CLIENT_ID / AVITO_CLIENT_SECRET in server environment. Access key is sent in an HTTP header, not query string. No secrets belong in GitHub or chat.
- app.py registers the API blueprint.
- tests/test_chat_report.py added. CI for report and full-history sync changes passed (workflow run 85); run 86 is checking Flask registration/API changes.

Important constraints before production: the official API entitlement and credentials are not verified for the LEONA account; current collector uses the repository's existing Messenger endpoint assumptions and must be tested against a real authorized account. The request runs synchronously, so large accounts may exceed web-worker timeouts; a persistent background job worker is a later reliability requirement. The extension v0.2.0 is diagnostic only and is not the official API workflow. No merge to main or deploy has been made.
