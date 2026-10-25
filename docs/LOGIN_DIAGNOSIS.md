# Login diagnosis and local administrator recovery

## Finding for this checkout

The Visor form in `frontend/app.js` sends `POST /api/auth/login` as same-origin JSON with `username` and `password`. A backend rejection is HTTP 401 with the sanitized detail `Invalid credentials`; the form displays that response. This message is produced for an unknown/inactive account or a failed password verification. Network, CSRF, and server failures have different responses or browser errors.

The local API at `http://127.0.0.1:8000` responded to `/api/health` with `ok`; `/api/auth/session` returned `authenticated: false`. The shell resolves `DATABASE_URL` to `sqlite:///./.data/vigilon.db` with a process-level override present. From the repository root, that is the repository's `.data/vigilon.db`; the relative URL would resolve elsewhere if a service starts from a different working directory. Read-only inspection of this target found schema revision `0005_map_revision`, two user records, one active administrator, and Argon2 hashes. The username selected by the current bootstrap configuration matches an existing active account.

The password in the current local configuration does **not** verify against that existing account's stored Argon2 hash. The comparison was made in process and emitted only a boolean; no password or hash was printed. `bootstrap-admin` is create-only (`backend/app/db.py`): changing `VIGILON_ADMIN_PASSWORD` does not update an existing account. This makes the configuration password mismatch a confirmed cause if that configured password was used for the reported login. The actual password entered in the user's browser and the database selected by the already-running API process could not be observed safely, so the reported attempt is not attributed with certainty to that value or database. The API health route intentionally does not expose its database target.

The runtime API accepts login failures as 401, and the UI maps 401 login responses directly to the displayed message. An isolated API regression verified correct-password login, incorrect-password rejection, session identity, permitted page access, role denial, logout, and unauthenticated access rejection. The user's operational account was not changed or claimed as recovered.

## Safe recovery

The local recovery command changes only the password hash of the existing, active administrator whose username exactly matches `VIGILON_ADMIN_USERNAME`. It refuses missing, inactive, non-admin, or differently named accounts. It prints a sanitized target, requires the operator to type that database target exactly and then confirm the account name, and collects the new password twice through a hidden prompt. Passwords are never command-line arguments or logged. It does not create an account or change cameras, plans, incidents, keys, or evidence.

From the repository root in PowerShell, after confirming that this shell's `.env` and `DATABASE_URL` target the same database as the API and worker:

```powershell
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m app.commands reset-admin-password
```

The username comes from the `.env`-loaded `VIGILON_ADMIN_USERNAME` (default `admin`). The command prints the SQLite path or a redacted database target before asking for confirmation. It enforces a 12-character minimum and uses Argon2. Do not run it until the target has been checked; the diagnosis above did not execute this command against operational data.

Session cookies are signed, stateless tokens with an eight-hour expiry and there is no session revocation store. A password reset therefore does not invalidate already issued sessions; they expire normally. Restart the API and worker only if their inherited database/configuration environment needs correction, and ensure both use the intended database, signing key, and encryption key. Do not use bootstrap as a password-reset tool, delete/reseed the database, rotate keys, or disable authentication.

## Evidence limits

- The current shell's effective database target and account metadata were inspected read-only. The live API process's environment is not exposed by the health endpoint, so its exact database URL remains unverified.
- No operational login attempt was replayed, and no actual user password was requested, logged, or tested.
- Local browser automation was blocked because the shared Playwright Chrome profile was already in use and the browser inventory exposed no isolated browser surface. API/session behavior was tested with disposable SQLite accounts instead.
- Use only the matching API/worker checkout and environment. The local application is normally served at `http://127.0.0.1:8000`.
