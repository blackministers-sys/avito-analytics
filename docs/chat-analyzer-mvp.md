# Avito Chat Analyzer — MVP

## Product goal

Provide a standalone workspace for exporting and analyzing Avito conversations. Full account/ad business analytics is optional and is not required to use this module.

## User workflow

1. Connect each Avito account once through the supported Avito authorization flow.
2. Keep each account connection and its token lifecycle isolated.
3. Switch between already connected accounts without repeating consent on every selection.
4. Select an account and date range, then request a chat export or analysis.
5. Browse conversations, inspect individual message history, and export results.

Re-consent may be required if the user revokes access, Avito invalidates a refresh token, or the platform requires renewed authorization.

## Architecture

- **Account connections:** internal connection ID, Avito account ID, display label, encrypted access/refresh tokens, granted scopes, token expiry and connection status.
- **Collector:** read-only Messenger API client; initial history backfill followed by incremental synchronization. Never send messages or mark chats as read.
- **Storage:** normalized accounts, chats, messages and sync checkpoints. Every chat/message is scoped by internal connection ID and Avito account ID.
- **Chat Analyzer:** operates only on normalized stored messages. It must not know Client ID, Client Secret or OAuth tokens.
- **UI:** account switcher, date range, sync status, chat list, conversation detail, analysis summary and export.
- **Business Analytics integration:** optional consumer of normalized chat data; not a dependency of Chat Analyzer.

## MVP analysis

Report observable metrics and evidence:
- number of conversations and messages;
- last inbound message awaiting a reply;
- response-time sample and average, only where sender and timestamps are known;
- repeated customer questions and objections;
- possible price, availability, delivery, trust and competitor themes;
- possible purchase-intent phrases.

Every inferred reason must be labelled as a text signal, not a confirmed lost sale. A purchase-intent phrase is not a confirmed order. Unknown sender direction must not be guessed.

## Security and reliability

- Never place secrets in source control, logs, chat messages or exported reports.
- Keep application credentials server-side in deployment secret storage.
- Encrypt per-account refresh tokens at rest; restrict access to the token store.
- Validate OAuth state and redirect URI; implement refresh-token rotation safely.
- Use a persistent database and backups; ephemeral application filesystem is not sufficient.
- Add per-account sync locks, retries with backoff, rate-limit handling and resumable checkpoints.
- Keep API operations read-only.

## Known implementation state

The repository already contains a read-only client based on Client Credentials, a SQLite chat/message store and an initial full-sync service. These are scaffolding only:
- Client Credentials is not yet a multi-user account connection flow.
- OAuth Authorization Code, state validation, token exchange, refresh and encrypted token storage are not implemented.
- The current sync service is a one-account initial backfill, not a durable incremental collector.
- The current Flask app has no Chat Analyzer UI or account switcher.
- The Messenger API response schema, pagination and authorization requirements still require validation against current Avito documentation and a real authorized test account.
- Render persistent storage and background worker/scheduler are not yet configured or verified.

## Delivery order

1. Confirm Avito app status, Messenger API entitlement and supported authorization scheme.
2. Implement OAuth connection lifecycle and account registry.
3. Add persistent storage migrations and per-account incremental sync.
4. Add chat list/detail and date-range export UI.
5. Add explainable conversation analytics and tests.
6. Deploy with persistent storage and verify with one account, then a second account.
