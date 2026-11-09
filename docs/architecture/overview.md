# Architecture overview (Phase 1)

## Components

| Component | Responsibility |
| --------- | -------------- |
| **Web app** (`frontend/`) | React SPA. Routing, server state (TanStack Query), upload with progress (XHR), PDF rendering (pdf.js through react-pdf), and user preferences in `localStorage`. |
| **API** (`backend/`) | FastAPI app factory with versioned routes under `/api/v1`, a structured error envelope, request logging with `X-Request-ID`, CORS from configuration, and health checks that include pgvector status. |
| **Database** | PostgreSQL 16 with pgvector 0.8, run by Docker Compose and managed with Alembic migrations. |
| **File storage** | Local directory (`STORAGE_DIR`). Files are named by server-generated UUIDs, the client's filename is kept as metadata only, and every path is confined to the storage root. |

## Request flow: document upload

1. The browser checks the extension, MIME type and size, then sends `multipart/form-data` (`workspace_id`, `file`) through XHR so it can report progress.
2. The API rejects the request early if `Content-Length` already exceeds the limit.
3. `services.documents.create_document` checks that the workspace exists, sanitises the display filename and validates the extension and MIME type.
4. `LocalStorage.save_pdf` streams the upload in 1 MB chunks to `<uuid>.pdf.part`, checks the `%PDF-` signature, enforces the byte limit while streaming, then renames the file atomically. It removes the partial file on any failure.
5. The metadata row is inserted with `processing_status = 'uploaded'`. If the database commit fails, the stored file is deleted.
6. The client invalidates the cached queries, so the lists and counts refresh.

Deletion runs in the opposite order: commit the database delete first, then remove the file. A failure there leaves at most an orphaned file, never a database row pointing at a missing file.

## Data model

```
workspaces 1 ──< documents
           1 ──< conversations 1 ──< messages
```

Every table uses UUID primary keys and `timestamptz` timestamps. Foreign keys use `ON DELETE CASCADE`. Status and role values are enforced by check constraints.

## Decisions

- **Ports.** The database defaults to host port **5433** so it doesn't collide with a natively installed PostgreSQL on 5432 (common on Windows developer machines).
- **One `.env` for every consumer.** This keeps variable names identical across PowerShell, bash, Compose, FastAPI and Vite.
- **Sync SQLAlchemy.** It is simpler and fast enough for a local single-user application. Route handlers are sync, so FastAPI runs them in its threadpool.
- **Honest status vocabulary.** The `uploaded` status is shown as *Stored*. *Indexed* is reserved for the Phase 2 `ready` state.
- **Bundled fonts.** The Indic fonts are bundled and scoped by `unicode-range`, so rendering is identical and offline on Windows and macOS. Using system font fallback mis-shaped Devanagari when Newsreader came first in the stack.
- **pdf.js assets.** The cmaps and standard fonts are copied into `public/pdfjs` before `dev` and `build`, so the viewer works offline.
