/* OFFLINE-RAG console: sign in, upload with groups, ask with Quick/Deep toggle. */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, decodeRole, getToken, setToken, type Role } from "@/lib/api";

type Msg = {
  kind: "q" | "a";
  text: string;
  cites?: string[];
  mode?: string;
  cacheHit?: boolean;
};

const CITE_RE = /(\[[^\]\[]+#\d+\])/g;

function Cited({ text }: { text: string }) {
  const parts = text.split(CITE_RE);
  return (
    <>
      {parts.map((p, i) =>
        CITE_RE.test(p) || /^\[.+#\d+\]$/.test(p) ? (
          <span className="cite" key={i}>
            {p}
          </span>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  );
}

export default function Home() {
  const [token, setTok] = useState<string | null>(null);
  const [role, setRole] = useState<Role | null>(null);
  const [health, setHealth] = useState<string>("checking");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<"auto" | "quick" | "deep">("auto");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [login, setLogin] = useState({ u: "", p: "" });
  const [upGroups, setUpGroups] = useState("public");
  const [upFile, setUpFile] = useState<File | null>(null);
  const [upMsg, setUpMsg] = useState("");
  const [evalOut, setEvalOut] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = getToken();
    if (t) {
      const r = decodeRole(t);
      if (r) {
        setTok(t);
        setRole(r);
      } else setToken(null);
    }
    api
      .health()
      .then((h) => setHealth(`online · ${h.llm}`))
      .catch(() => setHealth("backend unreachable"));
  }, []);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  const signIn = useCallback(async () => {
    setError("");
    try {
      const r = await api.login(login.u, login.p);
      const t: string = r.access_token;
      setTok(t);
      setRole(decodeRole(t));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign in failed.");
    }
  }, [login]);

  const ask = useCallback(async () => {
    const q = input.trim();
    if (!q || busy) return;
    setError("");
    setBusy(true);
    setMsgs((m) => [...m, { kind: "q", text: q }]);
    setInput("");
    try {
      const r = await api.query(q, mode === "auto" ? null : mode);
      setMsgs((m) => [...m, { kind: "a", text: r.answer, cites: r.citations, mode: r.mode, cacheHit: r.cache_hit }]);
    } catch (e) {
      setMsgs((m) => [...m, { kind: "a", text: e instanceof Error ? e.message : "Query failed." }]);
    } finally {
      setBusy(false);
    }
  }, [input, busy, mode]);

  const upload = useCallback(async () => {
    if (!upFile) return;
    setUpMsg("Uploading and indexing…");
    try {
      const r = await api.ingest(upFile, upGroups, true);
      setUpMsg(`Indexed ${r.filename}: ${r.chunks} chunks.`);
    } catch (e) {
      setUpMsg(e instanceof Error ? e.message : "Upload failed.");
    }
  }, [upFile, upGroups]);

  const runEval = useCallback(async () => {
    setEvalOut("Scoring…");
    try {
      const r = await api.ragas(20);
      setEvalOut(JSON.stringify(r, null, 2));
    } catch (e) {
      setEvalOut(e instanceof Error ? e.message : "Eval failed.");
    }
  }, []);

  if (!token || !role) {
    return (
      <main className="layout">
        <div className="login-wrap rise">
          <p className="brand">
            OFFLINE-<em>RAG</em>
          </p>
          <p className="muted">Ask your documents. Cited answers, department isolation, fully offline.</p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              signIn();
            }}
          >
            <input
              className="field"
              placeholder="Username"
              value={login.u}
              onChange={(e) => setLogin({ ...login, u: e.target.value })}
              autoComplete="username"
            />
            <input
              className="field"
              type="password"
              placeholder="Password"
              value={login.p}
              onChange={(e) => setLogin({ ...login, p: e.target.value })}
              autoComplete="current-password"
            />
            <button className="btn" type="submit">
              Sign in
            </button>
          </form>
          {error && <p className="error">{error}</p>}
          <p className="hint">Seeded accounts: admin, hr_amy, eng_bob. Backend: {health}.</p>
        </div>
      </main>
    );
  }

  return (
    <main className="layout">
      <div className="topbar rise">
        <p className="brand">
          OFFLINE-<em>RAG</em>
        </p>
        <div className="statusline">
          <span>
            <span className={`dot ${health.startsWith("online") ? "ok" : "bad"}`} />
            {health}
          </span>
          <span>{role.username}</span>
          <span className="muted">{role.groups.join(", ")}</span>
          <button
            className="btn-ghost btn"
            style={{ padding: "0.3rem 0.8rem" }}
            onClick={() => {
              setToken(null);
              setTok(null);
              setRole(null);
              setMsgs([]);
            }}
          >
            Sign out
          </button>
        </div>
      </div>

      <div className="split">
        <section className="rise rise-1">
          <div className="row" style={{ marginBottom: "0.8rem" }}>
            <div className="toggle" role="group" aria-label="Retrieval depth">
              {(["auto", "quick", "deep"] as const).map((m) => (
                <button key={m} aria-pressed={mode === m} onClick={() => setMode(m)}>
                  {m === "auto" ? "Auto" : m === "quick" ? "Quick" : "Deep"}
                </button>
              ))}
            </div>
            <span className="muted">Auto follows your groups{mode !== "auto" ? ` · overriding with ${mode}` : ""}.</span>
          </div>

          <div className="thread">
            {msgs.length === 0 && (
              <div className="empty">No questions yet. Ask about an uploaded document — answers arrive with [doc#chunk] citations.</div>
            )}
            {msgs.map((m, i) => (
              <div className="card msg" key={i}>
                <div className={m.kind === "q" ? "msg q" : "msg a"}>
                  <Cited text={m.text} />
                </div>
                {m.kind === "a" && (m.mode || m.cacheHit) && (
                  <div className="meta">
                    {m.mode && <span className={`mode-badge ${m.mode === "deep" ? "deep" : ""}`}>{m.mode}</span>}
                    {m.cacheHit && <span>served from cache</span>}
                  </div>
                )}
              </div>
            ))}
            <div ref={bottom} />
          </div>

          <div className="composer">
            <input
              className="field"
              placeholder="Ask a question…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") ask();
              }}
            />
            <button className="btn" onClick={ask} disabled={busy || !input.trim()}>
              {busy ? "Asking…" : "Ask"}
            </button>
          </div>
          {error && <p className="error">{error}</p>}
        </section>

        <aside className="side rise rise-2">
          <div className="card">
            <h2>Upload document</h2>
            <div className="row" style={{ marginBottom: "0.6rem" }}>
              <input type="file" onChange={(e) => setUpFile(e.target.files?.[0] ?? null)} accept=".pdf,.docx,.pptx,.csv,.md,.txt" />
            </div>
            <div className="row" style={{ marginBottom: "0.6rem" }}>
              <input
                className="field"
                placeholder="Allowed groups (comma separated)"
                value={upGroups}
                onChange={(e) => setUpGroups(e.target.value)}
              />
            </div>
            <button className="btn" onClick={upload} disabled={!upFile}>
              Upload and index
            </button>
            {upMsg && <p className="muted">{upMsg}</p>}
          </div>

          <div className="card">
            <h2>Answer quality</h2>
            <p className="muted">Background faithfulness scores, aggregated offline.</p>
            <button className="btn-ghost btn" onClick={runEval}>
              Score recent answers
            </button>
            {evalOut && (
              <pre className="muted" style={{ whiteSpace: "pre-wrap", fontSize: "0.8rem" }}>
                {evalOut}
              </pre>
            )}
          </div>
        </aside>
      </div>
    </main>
  );
}
