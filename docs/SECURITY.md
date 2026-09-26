# Security and data handling

Vigilon is intended for a trusted local property network. Compose binds the browser service to loopback, does not publish PostgreSQL, and uses same-origin API proxying. Do not expose it to the public internet without a separate deployment security review, HTTPS termination, network policy, and account lifecycle controls.

Passwords use Argon2id through `argon2-cffi`. The signed session cookie is HTTP-only, SameSite Strict, bounded to eight hours, and can use `Secure` through `VIGILON_COOKIE_SECURE=true`. Mutating requests reject a mismatched `Origin`; browsers also enforce the SameSite policy. Admin routes manage source and rules; operators can review preview/evidence and transition incidents. There is no password reset or user-management UI; admin user creation is an authenticated API operation.

Source URLs/credentials are encrypted with Fernet. `VIGILON_ENCRYPTION_KEY` must be generated externally by local setup and backed up securely. Losing it prevents source credential recovery. Do not log request bodies or include connection URLs in errors. The API response models omit encrypted fields.

Only authorized `rtsp`/`rtsps` URLs are accepted. Worker validation limits resolved addresses to configured CIDRs, denies common unrelated service ports, sets FFmpeg open/read timeouts, and never invokes a shell. Local video paths must resolve under `VIGILON_MEDIA_DIR`. Do not broaden these rules into an arbitrary URL or filesystem proxy.

Preview, evidence, and incident APIs require authentication. Evidence uses generated filenames and path containment checks; no public evidence directory is mounted. Snapshots contain sensitive property imagery. Configure filesystem/database backups and retention to match local policy. `python -m app.retention` removes snapshots after `VIGILON_RETENTION_DAYS` and keeps an expired evidence marker plus audit history. The command is not yet scheduled automatically.

Generated fixtures and all incidents derived from them carry a `SIMULATED` marker. Never silently feed simulated events from real sources. The in-app notification table is durable; no external notifier reports delivery.
