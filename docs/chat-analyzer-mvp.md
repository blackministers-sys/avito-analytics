# Avito Chat Analyzer — MVP

## Product goal

Provide a standalone workspace for collecting and analyzing Avito conversations across multiple accounts, including accounts without Messenger API entitlement where a user-authorized browser export is available. Chat analysis must not depend on Client ID, Client Secret or OAuth tokens.

## Agreed collection strategy: hybrid

Use two independent ingestion paths that produce the same normalized message format:

1. **Browser-assisted export (primary fallback):** the user opens Avito in their normal browser session and explicitly starts an export for the selected account, chats and date range. The first MVP may accept a JSON export from an existing exporter; after its format is inspected, build our own browser extension only if needed.
2. **Official Messenger API (optional):** use it for accounts whose category/subscription and authorization permit access. Do not require this route for every account.

The browser-assisted path must use only content the signed-in user can access in the normal Avito interface and explicit user action. Do not extract passwords, cookies, session tokens or hidden credentials; do not call undocumented private endpoints, bypass access controls, or automate sending/deleting/reading messages. Respect Avito terms and applicable privacy requirements. If compliant collection from the rendered interface is not technically or contractually available, use a user-generated export/import instead.

## Important operating limitation

A browser export requires an active browser session and the user's computer at export time. It cannot continuously sync while the computer is off. After import, storage and analytics run on the server independently. Background incremental updates while the computer is off are possible only through an authorized server-side source (for example, official API/webhooks where available). Otherwise the user repeats the export periodically.

## User workflow

1. Add an internal account record with a display name; no API credentials are required for a browser-import account.
2. Open the corresponding Avito account in the browser.
3. Select chats/date range and explicitly export accessible conversation data.
4. Upload the export to the server (or send it from an authenticated browser extension to an authenticated upload endpoint).
5. Normalize, deduplicate and store chats/messages under the internal account ID.
6. Analyze the imported history, browse chats and export reports.
7. Repeat export when new data is needed, unless official API sync is available.

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

The repository already contains a read-only client based on Client Credentials, a SQLite chat/message store, an initial full-sync service and an analyzer for manually uploaded exports. These are scaffolding only: OAuth multi-account lifecycle is not implemented; the current sync service is a one-account initial backfill; the Flask app has no Chat Analyzer UI or account switcher; the browser-export JSON format has not yet been inspected; no browser extension has been implemented or reviewed for Avito terms/compliance; Render persistent storage and background worker/scheduler are not configured or verified.

## Delivery order

1. Obtain a sanitized sample JSON from the existing browser exporter and document its schema.
2. Implement and test a secure JSON import adapter, internal account registry and idempotent normalization.
3. Add import UI, chat list/detail and analysis for imported data.
4. Decide whether a custom browser extension is needed; if so, limit it to explicit user-initiated collection of user-visible authorized content and verify compliance before release.
5. Keep official API integration as an optional connector for accounts with entitlement.
6. Deploy with persistent storage and verify imports with two separate Avito accounts.
