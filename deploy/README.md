# Deploy — No Docker

All via `.env` providers. One repo, no `docker compose`.

## Local (laptop)

```bash
python3 -m venv .venv && .venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch
.venv/bin/pip install -r requirements.txt
cp .env.example .env  # set GROQ_API_KEY or OLLAMA_URL
# Qdrant native (no Docker)
curl -L https://github.com/qdrant/qdrant/releases/latest/download/qdrant-aarch64-unknown-linux-gnu.tar.gz | tar xz -C /usr/local/bin
mkdir -p data/qdrant_storage data/kuzu data/uploads data/logs
qdrant --storage-path data/qdrant_storage &
.venv/bin/python -m backend.run seed
.venv/bin/python -m backend.run
cd frontend && npm ci && npm run build && npm run start -- -p 3000 -H 0.0.0.0
```

## SSH / Oracle VPS (laptop stays fast)

```bash
# On VPS run the same steps above, then:
sudo apt install nginx certbot -y
# systemd: /etc/systemd/system/xrag-qdrant.service  ExecStart=/usr/local/bin/qdrant --storage-path /home/ubuntu/X-RAG/data/qdrant_storage
#          /etc/systemd/system/xrag-api.service     WorkingDirectory=/home/ubuntu/X-RAG  ExecStart=/home/ubuntu/X-RAG/.venv/bin/python -m backend.run  EnvironmentFile=/home/ubuntu/X-RAG/.env  Restart=always
sudo systemctl enable --now xrag-qdrant xrag-api
# Caddy/Nginx proxy api.<domain> -> 127.0.0.1:8001
# On laptop, tunnel instead of running models:
ssh -L 6333:localhost:6333 -L 11434:localhost:11434 ubuntu@<vps-ip> -N &
# .env: QDRANT_URL=http://localhost:6333  OLLAMA_URL=http://localhost:11434  LLM_PROVIDER=ollama
```

## Online (hosted APIs)

```ini
LLM_PROVIDER=groq
GROQ_API_KEY=...
DATABASE_URL=postgresql://...supabase...
VECTOR_STORE_PROVIDER=qdrant  # QDRANT_URL=https://xxx.qdrant.io  QDRANT_API_KEY=...
QUEUE_PROVIDER=upstash        # UPSTASH_REDIS_REST_URL=https://...
EMBED_PROVIDER=choreo         # EMBED_URL=https://...choreoapps.dev/embed
```

See `SPEC.md` §2–4 and `.env.example` for all providers. L22 (Redis/Langfuse/ClickHouse) removed Sep-15 — rewrite will reuse the same `.env` keys.
