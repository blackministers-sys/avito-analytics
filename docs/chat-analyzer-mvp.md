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
