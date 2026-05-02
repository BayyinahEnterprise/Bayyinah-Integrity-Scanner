# Railway volume setup for the scan counter

The scan counter (added in `bayyinah/counter.py`) writes to a SQLite
database at `/data/counter.db` by default. For the counter to persist
across deployments and restarts, the `/data` path must be backed by a
Railway Volume.

Railway does not currently support declaring volumes inside
`railway.json` or `railway.toml`; volumes are configured per service
through the dashboard or the CLI. Do this once after this PR merges.

## Dashboard steps

1. Open the project in the Railway dashboard.
2. Select the service running the FastAPI app (the one that uses
   `Procfile` / `railway.json` to launch `uvicorn api:app`).
3. Click the service, then go to **Settings** -> **Volumes**.
4. Click **Connect Volume** (or **New Volume** if none exists), give it
   a name such as `bayyinah-counter`, and set the **Mount path** to
   `/data`.
5. Click **Add** / **Attach**. Railway will redeploy the service; the
   volume is now mounted at `/data` for every subsequent build.

## CLI steps (alternative)

If you prefer the CLI, the equivalent flow is:

```bash
railway login
railway link        # link to the BayyinahEnterprise project
railway volume add  # follow the prompts; mount at /data
```

Confirm with `railway volume list` once attached.

## Required environment variables

After the volume is attached, set the following on the same service
(Settings -> Variables):

| Variable                    | Value                                   |
|-----------------------------|-----------------------------------------|
| `BAYYINAH_COUNTER_DB`       | `/data/counter.db` (optional; default)  |
| `BAYYINAH_COUNTER_SECRET`   | A long random string, generated once    |

Generate the secret with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Set it in the dashboard as `BAYYINAH_COUNTER_SECRET`. Do not rotate it
casually: rotating the secret invalidates all existing per-day IP hashes
and resets the unique-visitor count for the past day window.

## Verifying the volume is live

Once attached and the env vars are set, hit the live demo:

```bash
curl https://bayyinah.dev/demo/stats
```

Expected response (numbers will reflect actual traffic):

```json
{
  "scans": 0,
  "unique_visitors_total": 0,
  "unique_visitors_today": 0,
  "since": null,
  "as_of": "2026-05-02T00:00:00.000000+00:00"
}
```

Run a scan through the demo page, then hit `/demo/stats` again. `scans`
should now be 1 and `unique_visitors_total` should be 1.

## Behaviour without the volume

If the volume is not attached, `/data` will not exist, the counter
falls back to `/tmp/counter.db`, and a warning is logged at process
start. The counter still works but resets every time Railway restarts
or redeploys the container.
