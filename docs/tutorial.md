# Tutorial: your first cited answer

In this tutorial we will install X-RAG, start it on your machine, upload a document, and ask a
question that comes back with a **clickable citation** — a chip `[1]` you can press to see the exact
source chunk highlighted in the sidebar.

You will need: Python 3.11–3.13, Docker (for the vector store), and a
[Groq API key](https://console.groq.com/keys) (free tier is fine).

## 1. Install

```bash
git clone https://github.com/akashpannala/X-RAG.git
cd X-RAG

python3 -m venv .venv
.venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch
.venv/bin/pip install -r requirements.txt
```

The torch install is CPU-only on purpose — X-RAG does not need a GPU.

## 2. Configure

```bash
cp .env.example .env
```

Open `.env` and paste your Groq key:

```ini
LLM_API_KEY=sk-your-groq-key
```

Leave everything else at its defaults for now — SQLite for metadata and Qdrant for vectors.

## 3. Fetch the model and start Qdrant

Download the local embedding model once (~2.2 GB):

```bash
.venv/bin/hf download BAAI/bge-m3
```

Start Qdrant in Docker:

```bash
docker run -d --name xrag-qdrant -p 6333:6333 qdrant/qdrant
```

## 4. Seed users and start the API

```bash
.venv/bin/python -m backend.run seed
.venv/bin/python -m backend.run
```

The server prints its startup checks, then listens on port 8001. Verify it in another terminal:

```bash
curl http://localhost:8001/health
```

You should see:

```json
{"status":"ok","llm":"groq","vector_store":"qdrant","qdrant":"http://localhost:6333","db":"sqlite"}
```

## 5. Start the UI

```bash
python3 frontend/serve.py 3000
```

Open <http://localhost:3000> and click the **LUFFY** demo preset to log in. You get the chat shell:
composer in the middle, conversation history on the left, sources rail on the right (empty for now).

## 6. Upload a document

Press the paperclip, pick the bundled `Free Journals.pdf` from the repo root, keep the pre-checked
group chips, and confirm the upload. When ingest finishes the sources rail shows the new row —
filename, chunk count, size.

## 7. Ask a question

Type a question about the document, for example:

```text
What are free journals?
```

The answer arrives with citation chips like `[1]` inline, and the rail marks which sources were used.

## 8. Click a citation

Press a chip in the answer. The matching row in the sources rail scrolls into view and flashes —
that is X-RAG's core promise: every claim traceable to its source.

## Where to go next

- Job to do (Docker, providers, ACL, deletion, tests) → [how-to guides](how-to.md)
- Looking up an endpoint or env var → [reference](reference.md)
- Why ACL is enforced before search, how quick/deep modes differ → [explanation](explanation.md)
