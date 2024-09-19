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
  const [showPw, setShowPw] = useState(false);
  const [upGroups, setUpGroups] = useState("public");
  const [upFile, setUpFile] = useState<File | null>(null);
  const [upMsg, setUpMsg] = useState("");
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
      setMsgs([]);
      setInput("");
      setError("");
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
            <div style={{ position: "relative" }}>
              <input
                className="field"
                type={showPw ? "text" : "password"}
                placeholder="Password"
                value={login.p}
                onChange={(e) => setLogin({ ...login, p: e.target.value })}
                autoComplete="current-password"
                style={{ paddingRight: "2.6rem" }}
              />
              <button
                type="button"
                aria-label={showPw ? "Hide password" : "Show password"}
                aria-pressed={showPw}
                onClick={() => setShowPw((v) => !v)}
                style={{
                  position: "absolute",
                  right: "0.4rem",
                  top: "50%",
                  transform: "translateY(-50%)",
                  background: "transparent",
                  border: 0,
                  color: "var(--ink-dim)",
                  cursor: "pointer",
                  padding: "0.3rem",
                  lineHeight: 0,
                }}
              >
                {showPw ? (
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24" />
                    <path d="M10.73 5.08A10.4 10.4 0 0 1 12 5c7 0 10 7 10 7a13.2 13.2 0 0 1-1.67 2.68" />
                    <path d="M6.61 6.61A13.5 13.5 0 0 0 2 12s3 7 10 7a9.7 9.7 0 0 0 5.39-1.61" />
                    <line x1="2" x2="22" y1="2" y2="22" />
                  </svg>
                ) : (
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                )}
              </button>
            </div>
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
            <h2>Documents</h2>
            <p className="muted">Upload restricted to allowed groups. Department isolation enforced at retrieval.</p>
          </div>
        </aside>
      </div>
    </main>
  );
}
