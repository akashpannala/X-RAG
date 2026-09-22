# X-RAG — Static Frontend

Pixel-perfect Stitch export (NotebookLM-style dark workbench) wired to the
FastAPI backend. No build step — plain HTML + one JS file.

## Files

| File | Purpose |
|------|---------|
| `index.html` | Login (demo-user presets, API health dot) |
| `chat.html` | 3-pane workbench: Chat History · conversation · Sources |
| `app.js` | All wiring: auth, `/query`, `/documents`, `/conversations`, `/ingest` |
| `assets/` | Local logos (replaces remote googleusercontent images) |
| `stitch_pixel_perfect_page_clone/` | Raw Stitch exports (`code.html` + `screen.png`) |

## Run

```bash
# backend (postgres, port 8001)
setsid nohup .venv/bin/python -u -m backend.run > /tmp/be.out 2>&1 < /dev/null &

# frontend (port 3000)
setsid nohup python3 -m http.server 3000 --directory frontend > /tmp/fe.out 2>&1 < /dev/null &
```

Open http://localhost:3000 — API base is `http://localhost:8001` (CORS allows
localhost:3000). Any 401 clears the token and returns to the login page.

## Demo users (password `pass`)

| User | Groups | Default mode |
|------|--------|--------------|
| `luffy` | hr, public | quick |
| `admin` | hr, eng, public | quick |
| `zoro` | eng, public | deep |

## Feature map

- **Login** — `POST /auth/login`, client-side JWT decode for header avatar/groups,
  `GET /health` ping (30s poll on chat page).
- **Chat** — `POST /query` (mode = quick/deep), pending shimmer skeleton,
  `[doc#chunk]` answer citations → numbered chips; clicking a chip scrolls/flashes
  the rail row. Meta pills: mode, cache-hit (client-timed), `% supported`,
  RAG-Verified (hidden when `supported_ratio: -1`), refusal styling.
- **History** — `GET /conversations` grouped Today/Yesterday/7d, search, click to
  reload a stored thread.
- **Sources** — `GET /documents` (ACL-filtered), extension icons, chunks/size/group
  chips; upload via dropzone/attach → modal (groups + enrich) → `POST /ingest`,
  uploading row with stage labels, error row + toast on failure.
- **Sign out** — `#accountBtn` clears token.

## E2E status

`node frontend/e2e.mjs` (CDP, debug Chrome on `:9222` via
`CHROME_PATH=/opt/brave.com/brave/brave npx -y @accesslint/chrome@latest ensure`):
**27/27 passing** — login → health → session header → mode default → rail load →
upload modal → ingest (unique fixture, rail count delta) → pending skeleton →
answer + citation chips → citation→rail highlight + numbered pill → history
row/query/reload/search → cache-hit pill on repeat query → new session →
sign out → auth gate → zero console errors. Unit suite: 49 passed.
