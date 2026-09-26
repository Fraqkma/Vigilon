# Architecture

Vigilon is a small modular application with an API process and one separately run ingestion worker. Compose runs FastAPI, the worker, PostgreSQL, and an Nginx frontend. The local Windows demo runs the same Python API/worker against SQLite when Docker is unavailable.

```text
Authorized RTSP / local media / synthetic source
                    │
          per-source reader thread
       bounded one-frame replace-oldest queue
                    │
     simulated detector → duration/rule check
                    │
PostgreSQL: sources, rules, incidents, history, notifications, lease
                    │
   snapshot-only evidence volume + latest JPEG volume
                    │
    authenticated API ← same-origin operator frontend
```

Each source has an isolated reader thread. A read timeout or decoder failure closes and reconnects only that source with 1–30 second exponential backoff. A one-element queue drops the stale queued image when producers run ahead. File EOF is treated as a disconnect; reopening the file replays it from the beginning. Reader threads are daemonized and their decoder is configured with OpenCV FFmpeg open/read timeouts; shutdown joins each reader for at most six seconds.

The API and worker do not share process memory. For preview, the worker writes a generated JPEG first, then atomically replaces a small JSON manifest naming that immutable frame file. The API reads the manifest and serves that JPEG after authentication. The handoff keeps only the three most recent JPEGs per source to tolerate a reader racing a manifest update. Incident snapshots are copied from the triggering frame before the next frame can replace the handoff. Frames are not stored in PostgreSQL.

The worker claims the singleton `worker_lease` row for 15 seconds, refreshes it continuously, and releases it at shutdown. A second worker exits if the lease is fresh. A crashed worker stops refreshing the lease; ownership becomes available after expiry. API source changes are observed by polling the database, and a changed source configuration replaces its reader without restarting the API.

The simulated detector returns typed geometry and event metadata for generated obstruction, person-down, and smoke/fire scenes. The worker applies the rule minimum duration and cooldown, deduplicates continuing observations into an active incident, and does not reopen a resolved event on each frame. A later recurrence after cooldown may create a new incident. Manual resolution records an operator decision; it does not claim the scene cleared. Real detector implementations are currently unavailable.

Database schema changes are Alembic migrations. Run the explicit `migrate` command before bootstrap, API, or worker. The initial migration creates durable models for users, camera/source configuration, rules, incidents, append-only transitions, in-app notifications, and worker ownership. Alembic upgrade was verified on a clean SQLite database. SQLite is a local development path; Compose uses PostgreSQL, which was not available for verification because Docker is missing in the environment.

Evidence storage is snapshot-only. Files use random names outside the public frontend directory and are served through role-authenticated API routes. Cleanup is an explicit command today; expired file references remain in incident history with `evidence_expired=true`.
