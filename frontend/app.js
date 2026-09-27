"use strict";
/* X-RAG workbench — vanilla wiring for the Stitch static export.
   Pages: index.html (login), chat.html (3-pane workbench). */

const API = (location.hostname === "localhost" || location.hostname === "127.0.0.1")
  ? "http://localhost:8001"
  : location.origin;
const TOKEN_KEY = "xrag.token";

const SUGGESTIONS = [
  "What is the procedure for submitting internet expense receipts?",
  "Which vendors are approved for ergonomic office chairs?",
  "Can contractor employees claim the home office stipend?",
  "What does our vacation policy allow?",
];

/* ---------------- auth ---------------- */

function decodeToken(token) {
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    if (!payload.sub || (payload.exp && payload.exp * 1000 < Date.now())) return null;
    return {
      id: payload.sub,
      username: payload.username || "",
      groups: payload.groups || [],
    };
  } catch {
    return null;
  }
}

const getToken = () => localStorage.getItem(TOKEN_KEY);
const clearToken = () => localStorage.removeItem(TOKEN_KEY);

function defaultMode(groups) {
  if (groups.includes("hr")) return "quick";
  if (groups.includes("eng")) return "deep";
  return "quick";
}

async function api(path, opts = {}) {
  const headers = Object.assign({}, opts.headers);
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(API + path, Object.assign({}, opts, { headers }));
  if (res.status === 401 && location.pathname.indexOf("index.html") === -1 && location.pathname !== "/") {
    clearToken();
    location.href = "index.html";
    throw new Error("session expired");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json();
}

/* ---------------- toasts ---------------- */

function toast(msg, kind = "ok") {
  const box = document.getElementById("toasts");
  if (!box) return;
  const el = document.createElement("div");
  const tone =
    kind === "err"
      ? "border-[#ba1a1a]/50 bg-[#3b1513] text-[#ffb4ab]"
      : "border-white/[0.1] bg-[#1e1f20] text-[#e3e3e3]";
  el.className = `xrag-enter rounded-xl border px-4 py-2.5 text-xs shadow-xl backdrop-blur ${tone}`;
  el.textContent = msg;
  box.appendChild(el);
  setTimeout(() => {
    el.style.transition = "opacity .2s";
    el.style.opacity = "0";
    setTimeout(() => el.remove(), 220);
  }, kind === "err" ? 6000 : 3500);
}

/* ---------------- health ---------------- */

async function pingHealth(labelEl, dotEl, textFn) {
  try {
    const r = await fetch(API + "/health");
    if (!r.ok) throw new Error("bad");
    await r.json();
    if (labelEl) labelEl.textContent = textFn(true);
    if (dotEl) dotEl.style.background = "#8ab4f8";
    return true;
  } catch {
    if (labelEl) labelEl.textContent = textFn(false);
    if (dotEl) dotEl.style.background = "#f28b82";
    return false;
  }
}

/* ---------------- login page ---------------- */

function initLogin() {
  if (getToken() && decodeToken(getToken())) {
    location.href = "chat.html";
    return;
  }
  const form = document.getElementById("loginForm");
  const errBox = document.getElementById("loginError");
  const submitBtn = document.getElementById("submitBtn");
  const submitLabel = document.getElementById("submitLabel");
  const submitIcon = document.getElementById("submitIcon");

  document.querySelectorAll("[data-demo-user]").forEach((b) => {
    b.addEventListener("click", () => {
      document.getElementById("username").value = b.dataset.demoUser;
      document.getElementById("password").value = "password";
      document.getElementById("password").focus();
    });
  });

  const toggleBtn = document.getElementById("togglePasswordBtn");
  toggleBtn.addEventListener("click", () => {
    const pw = document.getElementById("password");
    const show = pw.type === "password";
    pw.type = show ? "text" : "password";
    document.getElementById("passwordIcon").textContent = show ? "visibility" : "visibility_off";
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errBox.classList.add("hidden");
    submitBtn.disabled = true;
    submitIcon.textContent = "progress_activity";
    submitIcon.classList.add("animate-spin");
    submitLabel.textContent = "Authenticating…";
    try {
      const r = await fetch(API + "/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: document.getElementById("username").value.trim(),
          password: document.getElementById("password").value,
        }),
      });
      if (!r.ok) {
        const detail = (await r.json().catch(() => ({}))).detail;
        throw new Error(detail === "bad credentials" ? "Bad username or password." : detail || "Sign in failed");
      }
      const data = await r.json();
      localStorage.setItem(TOKEN_KEY, data.access_token);
      submitIcon.classList.remove("animate-spin");
      submitIcon.textContent = "verified_user";
      submitLabel.textContent = "Access Granted";
      setTimeout(() => (location.href = "chat.html"), 350);
    } catch (err) {
      errBox.textContent = err.message || "Sign in failed";
      errBox.classList.remove("hidden");
      submitBtn.disabled = false;
      submitIcon.classList.remove("animate-spin");
      submitIcon.textContent = "vpn_key";
      submitLabel.textContent = "Sign In to Workspace";
    }
  });
}

/* ---------------- chat page: state ---------------- */

let session = null;
let mode = "quick";
let sending = false;
let docs = [];
let historyRows = [];
let activeHistoryId = null;
let pendingFile = null;
let lastUploadGroups = null;
let lastCiteMap = new Map(); // filename -> [n]

/* ---------------- chat page: boot ---------------- */

function initChat() {
  const token = getToken();
  session = token ? decodeToken(token) : null;
  if (!session) {
    location.href = "index.html";
    return;
  }
  mode = defaultMode(session.groups);

  document.getElementById("userName").textContent = session.username;
  document.getElementById("userAvatar").textContent = (session.username[0] || "?").toUpperCase();
  document.getElementById("userGroups").innerHTML = session.groups
    .map(
      (g) =>
        `<span class="font-mono text-[9px] px-1 py-0.5 rounded bg-[#282a2c] text-[#9aa0a6] leading-none">${esc(g)}</span>`
    )
    .join("");

  document.getElementById("accountBtn").addEventListener("click", () => {
    clearToken();
    location.href = "index.html";
  });

  setMode(mode);

  document.getElementById("modeQuick").addEventListener("click", () => setMode("quick"));
  document.getElementById("modeDeep").addEventListener("click", () => setMode("deep"));
  document.getElementById("btnSend").addEventListener("click", triggerSend);
  document.getElementById("btnNew").addEventListener("click", newSession);
  document.getElementById("btnAddDoc").addEventListener("click", () => fileInput.click());
  document.getElementById("btnAttach").addEventListener("click", () => fileInput.click());

  const composer = document.getElementById("composerInput");
  composer.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      triggerSend();
    }
  });
  composer.addEventListener("input", () => {
    composer.style.height = "auto";
    composer.style.height = Math.min(composer.scrollHeight, 144) + "px";
  });

  document.getElementById("historySearch").addEventListener("input", () => renderHistory(historyRows));
  document.getElementById("srcSearch").addEventListener("input", () => renderDocs(docs));

  wireUpload();
  renderEmpty();
  refreshDocs();
  refreshHistory();

  pingHealth(
    document.getElementById("healthLabel"),
    document.getElementById("healthDot"),
    (ok) => (ok ? "/healthy" : "/down")
  );
  setInterval(
    () =>
      pingHealth(
        document.getElementById("healthLabel"),
        document.getElementById("healthDot"),
        (ok) => (ok ? "/healthy" : "/down")
      ),
    30000
  );
}

/* ---------------- chat: rendering ---------------- */

const esc = (s) =>
  String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

const CHIPS_CITED =
  "inline-flex items-center justify-center min-w-[22px] h-5 px-1.5 ml-1 rounded-full bg-[#a8c7fa]/20 text-[#a8c7fa] hover:bg-[#a8c7fa] hover:text-[#041e49] font-mono text-[11px] font-semibold transition-all duration-150 align-baseline cursor-pointer border border-[#a8c7fa]/30";

function renderEmpty() {
  const stream = document.getElementById("chatStream");
  stream.innerHTML = `
    <div class="w-full max-w-[760px] mx-auto flex flex-col gap-5">
      <div class="flex flex-col gap-3 pt-6 pb-2">
        <span class="font-mono text-[10px] text-[#757b82] uppercase tracking-wider pl-1 font-semibold">Suggested inquiries</span>
        <div class="flex flex-wrap gap-2">
          ${SUGGESTIONS.map(
            (s) => `
        <button class="px-3.5 py-2 rounded-full bg-[#1e1f20] hover:bg-[#282a2c] text-[#e3e3e3] text-xs text-left transition-all flex items-center gap-1.5" data-suggest="${esc(s)}" type="button">
          <span class="material-symbols-outlined text-[16px] text-[#a8c7fa]">add_circle</span>
          <span>${esc(s)}</span>
        </button>`).join("")}
        </div>
      </div>
    </div>`;
  stream.querySelectorAll("[data-suggest]").forEach((b) =>
    b.addEventListener("click", () => populatePrompt(b.dataset.suggest))
  );
}

function userTurnHTML(text) {
  const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return `
  <div class="flex flex-col items-start gap-1.5 w-full xrag-enter">
    <div class="flex items-center gap-2 text-[#9aa0a6] px-1">
      <span class="text-xs font-medium text-[#e3e3e3]">${esc(session.username)}</span>
      <span class="text-xs">•</span>
      <span class="font-mono text-[11px] text-[#757b82]">${now}</span>
    </div>
    <div class="w-full max-w-[85%] p-4 rounded-3xl bg-[#1e1f20] border border-white/[0.06] shadow-sm">
      <p class="text-[15px] text-[#e3e3e3] leading-relaxed">${esc(text)}</p>
    </div>
  </div>`;
}

function assistantHeaderHTML(chip) {
  return `
  <div class="flex items-center gap-2 px-1">
    <div class="w-5 h-5 rounded-full bg-[#a8c7fa]/20 flex items-center justify-center text-[#a8c7fa]">
      <span class="material-symbols-outlined text-[14px]">bolt</span>
    </div>
    <span class="text-xs font-semibold text-[#a8c7fa]">X-RAG Synthesizer</span>
    ${chip || ""}
  </div>`;
}

function pendingHTML() {
  return `
  <div class="flex flex-col items-start gap-2 w-full xrag-enter" id="pendingBlock">
    ${assistantHeaderHTML(
      `<span class="font-mono text-[10px] bg-[#282a2c] text-[#a8c7fa] px-2 py-0.5 rounded-full font-medium border border-white/[0.05]">Synthesizing response…</span>`
    )}
    <div class="w-full p-6 rounded-[24px] bg-[#1e1f20] border border-white/[0.08] shadow-lg flex flex-col gap-3" aria-busy="true">
      <div class="xrag-shimmer h-3.5 w-[92%]"></div>
      <div class="xrag-shimmer h-3.5 w-[97%]"></div>
      <div class="xrag-shimmer h-3.5 w-[88%]"></div>
      <div class="xrag-shimmer h-3.5 w-[62%]"></div>
      <div class="flex gap-2 pt-2">
        <div class="xrag-shimmer h-5 w-16"></div>
        <div class="xrag-shimmer h-5 w-16"></div>
      </div>
    </div>
  </div>`;
}

function markdownLite(text) {
  const paras = esc(text).split(/\n{2,}/);
  return paras
    .map((p) => {
      let html = p
        .replace(/\*\*(.+?)\*\*/g, "<strong class='font-medium text-white'>$1</strong>")
        .replace(/\n/g, "<br/>");
      return `<p class="my-1">${html}</p>`;
    })
    .join("");
}

function citeDocOf(c) {
  return String(c).replace(/^\[|\]$/g, "").replace(/^doc#/, "").split("#")[0];
}

function inlineCitations(html, citeList) {
  const map = new Map();
  for (const c of citeList || []) {
    const doc = citeDocOf(c);
    if (doc && !map.has(doc)) map.set(doc, map.size + 1);
  }
  const used = new Map(map);
  // chunk -> doc from server citations, so a bare [doc#N] placeholder can be resolved
  const chunkDoc = new Map();
  for (const c of citeList || []) {
    const s = String(c).replace(/^\[|\]$/g, "").replace(/^doc#/, "");
    const i = s.lastIndexOf("#");
    if (i > 0 && !chunkDoc.has(s.slice(i + 1))) chunkDoc.set(s.slice(i + 1), s.slice(0, i));
  }
  const chip = (doc, chunk) => {
    if (!map.has(doc)) map.set(doc, map.size + 1);
    used.set(doc, map.get(doc));
    const c = chunk ? ` data-chunk="${esc(chunk)}"` : "";
    const t = chunk ? ` • chunk ${esc(chunk)}` : "";
    return `<button class="${CHIPS_CITED}" data-cite="${esc(doc)}"${c} title="Source: ${esc(doc)}${t}" type="button">[${map.get(doc)}]</button>`;
  };
  // model is inconsistent: [name#chunk] (names may contain spaces), [doc#name#chunk],
  // groups [name#18, name#19], [doc#name#19, #20], full-width 【name#19】, bare [doc#N], plain [n]
  const out = html.replace(/[[【][^\]】<]*[\]】]/g, (whole) => {
    const inner = whole.slice(1, -1);
    const parts = [];
    const seen = new Set();
    let lastDoc = null;
    let handled = false;
    for (let seg of inner.split(",")) {
      seg = seg.trim();
      if (seg === "doc#chunk") {
        handled = true;
        continue; // echoed instruction, not a citation
      }
      let m;
      if (/^#\d+$/.test(seg)) {
        m = lastDoc && [lastDoc, seg.slice(1)];
      } else if ((m = seg.match(/^(?:doc#)?(.+)#(\d+)$/))) {
        let doc = m[1].trim();
        if (doc === "doc") doc = chunkDoc.get(m[2]) || (map.size === 1 ? [...map.keys()][0] : "");
        if (!doc) continue;
        lastDoc = doc;
        m = [doc, m[2]];
      } else continue;
      if (m && !seen.has(m[0])) {
        seen.add(m[0]);
        parts.push(chip(m[0], m[1]));
      }
    }
    if (parts.length) return parts.join("");
    if (handled) return "";
    const plain = inner.trim();
    if (/^\d+$/.test(plain)) {
      const n = parseInt(plain, 10);
      const doc = [...map.entries()].find(([, v]) => v === n)?.[0];
      if (doc) {
        used.set(doc, n);
        return `<button class="${CHIPS_CITED}" data-cite="${esc(doc)}" title="Source: ${esc(
          doc
        )}" type="button">[${n}]</button>`;
      }
    }
    return whole;
  });
  lastCiteMap = used;
  return out;
}

function verificationHTML(verif) {
  const ratio = verif && typeof verif.supported_ratio === "number" ? verif.supported_ratio : -1;
  if (ratio < 0) return { pill: "", chip: "" };
  const pct = Math.round(ratio * 100);
  const good = ratio >= 0.6;
  const pill = `
    <div class="flex items-center gap-1 px-2.5 py-0.5 rounded-full font-mono text-[11px] font-semibold border ${
      good
        ? "bg-[#a8c7fa]/15 text-[#a8c7fa] border-[#a8c7fa]/20"
        : "bg-[#f59e0b]/15 text-[#fbbf24] border-[#f59e0b]/30"
    }">
      <span class="material-symbols-outlined text-[13px]">verified</span>
      <span>${pct}% supported</span>
    </div>`;
  const chip = good
    ? `<span class="font-mono text-[10px] bg-[#282a2c] text-[#a8c7fa] px-2 py-0.5 rounded-full font-medium border border-white/[0.05]">RAG Verified</span>`
    : `<span class="font-mono text-[10px] bg-[#282a2c] text-[#fbbf24] px-2 py-0.5 rounded-full font-medium border border-white/[0.05]">Partially Grounded</span>`;
  return { pill, chip };
}

function answerHTML({ answer, citations, mode: m, cache_hit, verification, latencyMs }) {
  const isRefusal = /^I can't answer that/.test(answer);
  const ver = verificationHTML(isRefusal ? null : verification);
  const chip = isRefusal
    ? `<span class="font-mono text-[10px] bg-[#282a2c] text-[#ffb4ab] px-2 py-0.5 rounded-full font-medium border border-white/[0.05]">No Grounding</span>`
    : ver.chip;

  let body = inlineCitations(markdownLite(answer), citations);
  if (!body.includes("data-cite=") && lastCiteMap.size) {
    // answer text carries no usable inline refs — give it a Sources row anyway
    body += `
      <div class="mt-3 pt-3 border-t border-white/[0.06] flex items-center gap-2 flex-wrap" data-sources-row>
        <span class="font-mono text-[10px] text-[#757b82] uppercase tracking-wider font-semibold">Sources</span>
        ${[...lastCiteMap.entries()]
          .map(
            ([doc, n]) =>
              `<button class="${CHIPS_CITED}" data-cite="${esc(doc)}" title="Source: ${esc(doc)}" type="button">[${n}]</button>`
          )
          .join("")}
      </div>`;
  }
  const modePill = `
    <div class="flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-[#282a2c] text-[#9aa0a6] font-mono text-[11px] border border-white/[0.05]">
      <span class="material-symbols-outlined text-[13px] text-[#a8c7fa]">${m === "deep" ? "psychology" : "bolt"}</span>
      <span>${m === "deep" ? "Deep Mode" : "Quick Mode"}</span>
    </div>`;
  const cachePill = cache_hit
    ? `<div class="flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-[#282a2c] text-[#9aa0a6] font-mono text-[11px] font-medium border border-white/[0.05]">
        <span class="material-symbols-outlined text-[13px] text-[#a8c7fa]">cached</span>
        <span>Cache Hit (${latencyMs}ms)</span>
      </div>`
    : "";

  const followups = isRefusal
    ? ""
    : `
    <div class="w-full mt-1 flex flex-col gap-2">
      <span class="font-mono text-[10px] text-[#757b82] uppercase tracking-wider pl-1 font-semibold">Suggested inquiries</span>
      <div class="flex flex-wrap gap-2">
        ${SUGGESTIONS.slice(0, 3)
          .map(
            (s) => `
        <button class="px-3.5 py-2 rounded-full bg-[#1e1f20] hover:bg-[#282a2c] text-[#e3e3e3] text-xs text-left transition-all flex items-center gap-1.5" data-suggest="${esc(s)}" type="button">
          <span class="material-symbols-outlined text-[16px] text-[#a8c7fa]">add_circle</span>
          <span>${esc(s)}</span>
        </button>`).join("")}
      </div>
    </div>`;

  return `
  <div class="flex flex-col items-start gap-2 w-full xrag-enter">
    ${assistantHeaderHTML(chip)}
    <div class="w-full p-6 rounded-[24px] bg-[#1e1f20] border border-white/[0.08] shadow-lg flex flex-col gap-4">
      <div class="text-[15px] leading-relaxed ${isRefusal ? "text-[#9aa0a6] italic" : "text-[#e3e3e3]"}" data-answer>${body}</div>
      <div class="pt-3 mt-1 flex flex-wrap items-center justify-between gap-2 bg-[#18191a]/80 -mx-6 -mb-6 px-6 py-3 rounded-b-[24px] border-t border-white/[0.06]">
        <div class="flex flex-wrap items-center gap-2">
          ${modePill}
          ${cachePill}
          ${ver.pill}
        </div>
        <div class="flex items-center gap-1 text-[#9aa0a6]">
          <button class="p-1.5 rounded-full hover:bg-[#282a2c] hover:text-[#e3e3e3] transition-colors" data-copy title="Copy answer" type="button">
            <span class="material-symbols-outlined text-[18px]">content_copy</span>
          </button>
          <button class="p-1.5 rounded-full hover:bg-[#282a2c] hover:text-[#e3e3e3] transition-colors" data-fb="up" title="Accurate answer" type="button">
            <span class="material-symbols-outlined text-[18px]">thumb_up</span>
          </button>
          <button class="p-1.5 rounded-full hover:bg-[#282a2c] hover:text-[#e3e3e3] transition-colors" data-fb="down" title="Report discrepancy" type="button">
            <span class="material-symbols-outlined text-[18px]">thumb_down</span>
          </button>
        </div>
      </div>
    </div>
    ${followups}
  </div>`;
}

function wireAnswerActions(root, plainAnswer) {
  root.querySelectorAll("[data-suggest]").forEach((b) =>
    b.addEventListener("click", () => populatePrompt(b.dataset.suggest))
  );
  root.querySelectorAll("[data-cite]").forEach((b) =>
    b.addEventListener("click", () => highlightCite(b.dataset.cite))
  );
  const copyBtn = root.querySelector("[data-copy]");
  if (copyBtn)
    copyBtn.addEventListener("click", () => {
      navigator.clipboard.writeText(plainAnswer).then(
        () => toast("Answer copied"),
        () => toast("Clipboard unavailable", "err")
      );
    });
  root.querySelectorAll("[data-fb]").forEach((b) =>
    b.addEventListener("click", () => {
      b.classList.toggle("text-[#a8c7fa]");
      toast(b.dataset.fb === "up" ? "Marked as accurate" : "Feedback recorded");
    })
  );
}

function scrollStream() {
  const s = document.getElementById("chatStream");
  s.scrollTop = s.scrollHeight;
}

function appendHTML(html) {
  const wrap = document.createElement("div");
  wrap.innerHTML = html.trim();
  const el = wrap.firstElementChild;
  document.getElementById("chatStream").appendChild(el);
  scrollStream();
  return el;
}

function populatePrompt(text) {
  const composer = document.getElementById("composerInput");
  composer.value = text;
  composer.focus();
  composer.dispatchEvent(new Event("input"));
}

function newSession() {
  activeHistoryId = null;
  lastCiteMap = new Map();
  const stream = document.getElementById("chatStream");
  delete stream.dataset.live;
  renderEmpty();
  renderHistory(historyRows);
  renderDocs(docs);
}

/* ---------------- send ---------------- */

async function triggerSend() {
  const composer = document.getElementById("composerInput");
  const text = composer.value.trim();
  if (!text || sending) return;
  sending = true;
  document.getElementById("btnSend").style.opacity = "0.5";

  if (!document.getElementById("chatStream").dataset.live) {
    // first message of a fresh session: drop empty-state suggestions
    document.getElementById("chatStream").dataset.live = "1";
    document.getElementById("chatStream").innerHTML = "";
  }

  composer.value = "";
  composer.style.height = "auto";
  appendHTML(userTurnHTML(text));
  appendHTML(pendingHTML());

  const t0 = Date.now();
  try {
    const res = await api("/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: text, top_k: 5, mode }),
    });
    const ms = Date.now() - t0;
    document.getElementById("pendingBlock")?.remove();
    const el = appendHTML(answerHTML({ ...res, latencyMs: ms }));
    wireAnswerActions(el, res.answer);
    markRailCited(res.citations || []);
    refreshHistory();
  } catch (err) {
    document.getElementById("pendingBlock")?.remove();
    appendHTML(`
      <div class="w-full p-4 rounded-[24px] bg-[#1e1f20] border border-[#ba1a1a]/40 text-[#ffb4ab] text-sm xrag-enter">
        Query failed: ${esc(err.message)}
      </div>`);
    toast(err.message, "err");
  } finally {
    sending = false;
    document.getElementById("btnSend").style.opacity = "1";
    scrollStream();
  }
}

/* ---------------- sources rail ---------------- */

const EXT_META = {
  pdf: { icon: "picture_as_pdf", box: "bg-red-950/60 text-red-400 border-red-900/40" },
  docx: { icon: "article", box: "bg-blue-950/60 text-[#a8c7fa] border-blue-900/40" },
  pptx: { icon: "slideshow", box: "bg-orange-950/60 text-orange-300 border-orange-900/40" },
  csv: { icon: "table_view", box: "bg-emerald-950/60 text-emerald-300 border-emerald-900/40" },
  md: { icon: "code", box: "bg-[#282a2c] text-[#9aa0a6]" },
  txt: { icon: "description", box: "bg-[#282a2c] text-[#9aa0a6]" },
  png: { icon: "image", box: "bg-purple-950/60 text-purple-300 border-purple-900/40" },
  jpg: { icon: "image", box: "bg-purple-950/60 text-purple-300 border-purple-900/40" },
  jpeg: { icon: "image", box: "bg-purple-950/60 text-purple-300 border-purple-900/40" },
};

function extOf(name) {
  return (name.split(".").pop() || "").toLowerCase();
}

function fmtSize(bytes) {
  if (bytes == null) return "";
  if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + " MB";
  if (bytes >= 1024) return Math.round(bytes / 1024) + " KB";
  return bytes + " B";
}

function stemOf(name) {
  return String(name).replace(/\.[^.]+$/, "");
}

// citations carry the doc stem ("vacation_policy") while the rail keys on the
// uploaded filename ("vacation_policy.md") — match either.
function citeMatches(key, filename) {
  return key === filename || key === stemOf(filename);
}

function docRowHTML(d) {
  const meta = EXT_META[extOf(d.filename)] || { icon: "draft", box: "bg-[#282a2c] text-[#9aa0a6]" };
  const entry = [...lastCiteMap.entries()].find(([k]) => citeMatches(k, d.filename));
  const cited = !!entry;
  const n = entry ? entry[1] : 0;
  const size = fmtSize(d.size_bytes);
  return `
  <article class="group relative p-3 rounded-2xl transition-all duration-200 cursor-pointer shadow-sm ${
    cited ? "bg-[#282a2c] hover:bg-[#303236]" : "bg-[#1e1f20] hover:bg-[#282a2c]"
  }" id="doc-${esc(d.filename)}" data-filename="${esc(d.filename)}" tabindex="0">
    ${cited ? `<div class="absolute left-0 top-3 bottom-3 w-1 bg-[#a8c7fa] rounded-r-full"></div>` : ""}
    <div class="flex items-start justify-between gap-2 ${cited ? "pl-1" : ""}">
      <div class="flex items-start gap-2.5 min-w-0">
        <div class="p-1.5 rounded-lg ${meta.box} shrink-0 mt-0.5 border border-transparent">
          <span class="material-symbols-outlined text-[18px]">${meta.icon}</span>
        </div>
        <div class="min-w-0 flex flex-col">
          <h3 class="text-xs font-medium ${
            cited ? "text-[#e3e3e3] group-hover:text-[#a8c7fa]" : "text-[#9aa0a6] group-hover:text-[#e3e3e3]"
          } truncate transition-colors" title="${esc(d.filename)}">${esc(d.filename)}</h3>
          <span class="font-mono text-[10px] ${cited ? "text-[#9aa0a6]" : "text-[#757b82]"} mt-0.5">${d.chunks} chunks${
    size ? " • " + size : ""
  }</span>
        </div>
      </div>
      <div class="flex items-center gap-1 shrink-0">
        ${
          cited
            ? `<span class="inline-flex items-center justify-center h-5 px-1.5 rounded-full bg-[#a8c7fa] text-[#041e49] font-mono text-[10px] font-bold shadow-sm">[${n}]</span>`
            : ""
        }
        <button type="button" class="p-1 rounded-lg text-[#9aa0a6] hover:text-[#ff8a80] hover:bg-[#282a2c] opacity-0 group-hover:opacity-100 focus:opacity-100 transition-all" data-del="${esc(d.filename)}" title="Delete document" aria-label="Delete ${esc(d.filename)}">
          <span class="material-symbols-outlined text-[16px]">delete</span>
        </button>
      </div>
    </div>
    <div class="mt-2.5 flex items-center ${cited ? "justify-between pl-1" : "gap-1"}">
      <div class="flex items-center gap-1 flex-wrap">
        ${d.allowed_groups
          .map(
            (g) =>
              `<span class="font-mono text-[9px] px-1.5 py-0.5 rounded-full ${
                cited ? "bg-[#1e1f20] text-[#9aa0a6] border border-white/[0.05]" : "bg-[#282a2c] text-[#757b82]"
              }">${esc(g)}</span>`
          )
          .join("")}
      </div>
    </div>
  </article>`;
}

function renderDocs(list) {
  docs = list;
  const q = (document.getElementById("srcSearch")?.value || "").toLowerCase();
  const visible = docs.filter((d) => d.filename.toLowerCase().includes(q));
  document.getElementById("srcCount").textContent = `${docs.length} active`;
  const box = document.getElementById("srcList");
  if (!visible.length) {
    box.innerHTML = `
    <div class="flex flex-col items-center justify-center text-center gap-2 py-10 px-4">
      <span class="material-symbols-outlined text-[28px] text-[#757b82]">folder_off</span>
      <span class="text-xs font-medium text-[#9aa0a6]">${docs.length ? "No matches" : "No sources yet"}</span>
      <span class="font-mono text-[10px] text-[#757b82]">${docs.length ? "" : "Add PDFs, DOCX, CSV, MD or images"}</span>
    </div>`;
    return;
  }
  box.innerHTML = visible.map(docRowHTML).join("");
  box.querySelectorAll("[data-filename]").forEach((el) => {
    el.addEventListener("click", () => selectDoc(el.dataset.filename));
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter") selectDoc(el.dataset.filename);
    });
  });
  box.querySelectorAll("[data-del]").forEach((btn) => {
    btn.addEventListener("keydown", (e) => e.stopPropagation());
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const name = btn.dataset.del;
      if (!confirm(`Delete ${name}? Vectors, indexes and the source file are removed for everyone who can see it.`)) return;
      btn.disabled = true;
      try {
        await api(`/documents/${encodeURIComponent(name)}`, { method: "DELETE" });
        toast(`${name} deleted`);
        await refreshDocs();
        removeCiteChips(name); // answers in view must not keep chips for a deleted doc
      } catch (err) {
        toast(err.message || String(err), "err");
        btn.disabled = false;
      }
    });
  });
}

function railRowFor(docname) {
  return [...document.querySelectorAll("#srcList [data-filename]")].find((el) =>
    citeMatches(docname, el.dataset.filename)
  );
}

function selectDoc(filename) {
  const row = railRowFor(filename);
  document.querySelectorAll("#srcList [data-filename]").forEach((el) => {
    const on = el === row;
    el.classList.toggle("bg-[#282a2c]", on);
  });
  const meta = docs.find((d) => citeMatches(filename, d.filename));
  if (meta)
    toast(`${meta.filename} · ${meta.chunks} chunks · ${meta.allowed_groups.join(", ")}`);
}

function removeCiteChips(filename) {
  document.querySelectorAll("#chatStream [data-cite]").forEach((chip) => {
    if (citeMatches(chip.dataset.cite, filename)) chip.remove();
  });
  document.querySelectorAll("#chatStream [data-sources-row]").forEach((row) => {
    if (!row.querySelector("[data-cite]")) row.remove();
  });
}

function highlightCite(docname) {
  const row = railRowFor(docname);
  if (!row) {
    toast(`Source ${docname} not in your accessible set`, "err");
    return;
  }
  row.scrollIntoView({ behavior: "smooth", block: "center" });
  row.classList.remove("xrag-flash");
  void row.offsetWidth;
  row.classList.add("xrag-flash");
  selectDoc(docname);
}

function markRailCited(citations) {
  lastCiteMap = new Map();
  for (const c of citations) {
    const doc = citeDocOf(c);
    if (doc && !lastCiteMap.has(doc)) lastCiteMap.set(doc, lastCiteMap.size + 1);
  }
  renderDocs(docs);
}

async function refreshDocs() {
  try {
    renderDocs(await api("/documents"));
  } catch (err) {
    toast("Failed to load sources: " + err.message, "err");
  }
}

/* ---------------- history ---------------- */

function groupOfDay(isoLike) {
  const d = new Date(String(isoLike).replace(" ", "T"));
  if (isNaN(d)) return "Earlier";
  const now = new Date();
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = (day(now) - day(d)) / 86400000;
  if (diff <= 0) return "Today";
  if (diff === 1) return "Yesterday";
  if (diff <= 7) return "Previous 7 Days";
  return "Earlier";
}

function renderHistory(rows) {
  historyRows = rows;
  const q = (document.getElementById("historySearch")?.value || "").toLowerCase();
  const visible = rows.filter((r) => (r.query || "").toLowerCase().includes(q));
  const box = document.getElementById("historyList");
  if (!visible.length) {
    box.innerHTML = `
    <div class="flex flex-col items-center text-center gap-2 py-8 px-3">
      <span class="material-symbols-outlined text-[24px] text-[#757b82]">forum</span>
      <span class="font-mono text-[10px] text-[#757b82]">${rows.length ? "No matches" : "No conversations yet"}</span>
    </div>`;
    return;
  }
  const groups = new Map();
  for (const r of visible) {
    const g = groupOfDay(r.created_at);
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g).push(r);
  }
  const order = ["Today", "Yesterday", "Previous 7 Days", "Earlier"];
  let html = "";
  for (const g of order) {
    const items = groups.get(g);
    if (!items) continue;
    html += `<div class="space-y-1"><div class="px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-[#757b82] font-semibold">${g}</div>`;
    for (const r of items) {
      const active = r.id === activeHistoryId;
      const when = new Date(String(r.created_at).replace(" ", "T"));
      const time = isNaN(when)
        ? ""
        : when.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      html += `
      <div class="group relative flex items-start gap-2.5 p-2.5 rounded-2xl cursor-pointer transition-all ${
        active
          ? "bg-[#282a2c] text-[#e3e3e3] shadow-sm"
          : "hover:bg-[#282a2c]/60 text-[#9aa0a6] hover:text-[#e3e3e3]"
      }" data-conv="${r.id}" tabindex="0">
        <span class="material-symbols-outlined text-[18px] mt-0.5 shrink-0 ${
          active ? "text-[#a8c7fa]" : "text-[#757b82] group-hover:text-[#a8c7fa]"
        }">${active ? "chat_bubble" : "forum"}</span>
        <div class="min-w-0 flex-1">
          <p class="text-xs font-medium truncate leading-snug ${
            active ? "text-[#e3e3e3]" : "group-hover:text-[#e3e3e3]"
          }">${esc(r.query)}</p>
          <div class="flex items-center gap-1.5 mt-0.5">
            ${
              r.citations && r.citations.length
                ? `<span class="font-mono text-[10px] text-[#a8c7fa]">${r.citations.length} citation${
                    r.citations.length > 1 ? "s" : ""
                  }</span><span class="text-[#757b82] text-[10px]">•</span>`
                : ""
            }
            <span class="font-mono text-[10px] text-[#9aa0a6]">${time}</span>
          </div>
        </div>
        <div class="flex items-center gap-1 shrink-0 mt-0.5">
          <button type="button" class="p-1 rounded-lg text-[#757b82] hover:text-[#ff8a80] hover:bg-[#282a2c] opacity-0 group-hover:opacity-100 focus:opacity-100 transition-all" data-delconv="${r.id}" title="Delete chat" aria-label="Delete chat">
            <span class="material-symbols-outlined text-[16px]">delete</span>
          </button>
          ${active ? `<div class="w-1.5 h-1.5 rounded-full bg-[#a8c7fa] shrink-0"></div>` : ""}
        </div>
      </div>`;
    }
    html += `</div>`;
  }
  box.innerHTML = html;
  box.querySelectorAll("[data-conv]").forEach((el) => {
    const load = () => loadConversation(Number(el.dataset.conv));
    el.addEventListener("click", load);
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter") load();
    });
  });
  box.querySelectorAll("[data-delconv]").forEach((btn) => {
    btn.addEventListener("keydown", (e) => e.stopPropagation());
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const id = Number(btn.dataset.delconv);
      if (!confirm("Delete this chat? This cannot be undone.")) return;
      btn.disabled = true;
      try {
        await api(`/conversations/${id}`, { method: "DELETE" });
        toast("Chat deleted");
        if (activeHistoryId === id) newSession();
        await refreshHistory();
      } catch (err) {
        toast(err.message || String(err), "err");
        btn.disabled = false;
      }
    });
  });
}

function loadConversation(id) {
  const row = historyRows.find((r) => r.id === id);
  if (!row) return;
  activeHistoryId = id;
  document.getElementById("chatStream").dataset.live = "1";
  const stream = document.getElementById("chatStream");
  stream.innerHTML = "";
  stream.insertAdjacentHTML("beforeend", userTurnHTML(row.query));
  const el = appendHTML(
    answerHTML({
      answer: row.answer,
      citations: row.citations || [],
      mode: row.mode,
      cache_hit: false,
      verification: { supported_ratio: -1 },
      latencyMs: 0,
    })
  );
  wireAnswerActions(el, row.answer);
  markRailCited(row.citations || []);
  renderHistory(historyRows);
}

async function refreshHistory() {
  try {
    renderHistory(await api("/conversations"));
  } catch (err) {
    /* non-fatal: rail shows empty */
  }
}

/* ---------------- upload ---------------- */

function wireUpload() {
  const fileInput = document.getElementById("fileInput");
  const dropzone = document.getElementById("dropzone");
  const modal = document.getElementById("uploadModal");

  const open = () => fileInput.click();
  dropzone.addEventListener("click", open);
  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      open();
    }
  });
  ["dragover", "dragenter"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      dropzone.classList.add("border-[#a8c7fa]/60", "bg-[#18191a]");
    })
  );
  ["dragleave", "drop"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      dropzone.classList.remove("border-[#a8c7fa]/60", "bg-[#18191a]");
    })
  );
  dropzone.addEventListener("drop", (e) => {
    const f = e.dataTransfer?.files?.[0];
    if (f) openUpload(f);
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files[0]) openUpload(fileInput.files[0]);
    fileInput.value = "";
  });

  document.getElementById("uploadCancel").addEventListener("click", closeUpload);
  document.getElementById("uploadCancelIcon").addEventListener("click", closeUpload);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeUpload();
  });
  document.getElementById("uploadGroups").addEventListener("change", updateGroupsSummary);
  document.getElementById("uploadConfirm").addEventListener("click", confirmUpload);
}

function knownGroups() {
  const set = new Set(["public", "hr", "eng"]);
  (session.groups || []).forEach((g) => set.add(g));
  return [...set];
}

function selectedUploadGroups() {
  return [...document.querySelectorAll("#uploadGroups input:checked")].map((i) => i.value);
}

function updateGroupsSummary() {
  const el = document.getElementById("uploadGroupsSummary");
  if (!el) return;
  const g = selectedUploadGroups();
  el.textContent = g.length ? `Visible to: ${g.join(", ")}` : "No group selected — pick at least one";
  el.style.color = g.length ? "" : "#ffb4ab";
}

function openUpload(file) {
  pendingFile = file;
  document.getElementById("uploadFileName").textContent = file.name;
  const pre =
    lastUploadGroups && lastUploadGroups.length
      ? lastUploadGroups
      : session.groups.length
        ? session.groups
        : ["public"];
  document.getElementById("uploadGroups").innerHTML = knownGroups()
    .map((g) => {
      const on = pre.includes(g);
      return `
      <label class="cursor-pointer">
        <input type="checkbox" class="peer sr-only" value="${esc(g)}" ${on ? "checked" : ""}/>
        <span class="inline-flex items-center px-2.5 py-1 rounded-full font-mono text-[11px] border transition-all peer-checked:bg-[#a8c7fa]/15 peer-checked:text-[#a8c7fa] peer-checked:border-[#a8c7fa]/40 bg-[#131314] text-[#9aa0a6] border-white/[0.08] hover:border-[#a8c7fa]/40">${esc(
          g
        )}</span>
      </label>`;
    })
    .join("");
  const modal = document.getElementById("uploadModal");
  modal.classList.remove("hidden");
  modal.classList.add("flex");
  updateGroupsSummary();
}

function closeUpload() {
  pendingFile = null;
  const modal = document.getElementById("uploadModal");
  modal.classList.add("hidden");
  modal.classList.remove("flex");
}

function uploadRowHTML(id, filename) {
  return `
  <article class="p-3 rounded-2xl bg-[#1e1f20] flex flex-col gap-2" id="${id}">
    <div class="flex items-center gap-2.5">
      <div class="p-1.5 rounded-lg bg-[#282a2c] text-[#a8c7fa]">
        <span class="material-symbols-outlined text-[18px] animate-spin">progress_activity</span>
      </div>
      <div class="min-w-0 flex-1">
        <h3 class="text-xs font-medium text-[#e3e3e3] truncate">${esc(filename)}</h3>
        <span class="font-mono text-[10px] text-[#9aa0a6]" data-stage>Uploading…</span>
      </div>
    </div>
    <div class="h-1 rounded-full bg-[#131314] overflow-hidden">
      <div class="h-full w-1/3 bg-[#a8c7fa] rounded-full" style="animation: xragShimmer 1.2s linear infinite; background: linear-gradient(90deg,#1a6c81,#a8c7fa,#1a6c81); background-size:200px 100%"></div>
    </div>
  </article>`;
}

async function confirmUpload() {
  if (!pendingFile) return closeUpload();
  const file = pendingFile;
  const groups = [...document.querySelectorAll("#uploadGroups input:checked")].map((i) => i.value);
  const enrich = document.getElementById("enrichChk").checked;
  if (!groups.length) {
    toast("Pick at least one access group", "err");
    return;
  }
  lastUploadGroups = groups;
  closeUpload();

  const rowId = "uploading-row";
  const box = document.getElementById("srcList");
  box.insertAdjacentHTML("afterbegin", uploadRowHTML(rowId, file.name));
  const t0 = Date.now();
  const stageEl = () => document.querySelector(`#${rowId} [data-stage]`);
  const timer = setInterval(() => {
    const s = Math.round((Date.now() - t0) / 1000);
    if (stageEl()) stageEl().textContent = `Indexing… ${s}s`;
  }, 1000);

  try {
    const fd = new FormData();
    fd.append("f", file, file.name);
    const qs = `?allowed_groups=${encodeURIComponent(groups.join(","))}&enrich=${enrich}`;
    const headers = { Authorization: `Bearer ${getToken()}` };
    const res = await fetch(API + "/ingest" + qs, { method: "POST", headers, body: fd });
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
      throw new Error(detail);
    }
    const data = await res.json();
    clearInterval(timer);
    toast(`${data.filename} indexed · ${data.chunks} chunks · ${groups.join(", ")}`);
    document.getElementById(rowId)?.remove();
    await refreshDocs();
  } catch (err) {
    clearInterval(timer);
    const row = document.getElementById(rowId);
    if (row) {
      row.className = "p-3 rounded-2xl bg-[#1e1f20] border border-[#ba1a1a]/40 flex flex-col gap-1";
      row.innerHTML = `
        <div class="flex items-center gap-2 text-[#ffb4ab]">
          <span class="material-symbols-outlined text-[18px]">error</span>
          <span class="text-xs font-medium">${esc(file.name)}</span>
        </div>
        <span class="font-mono text-[10px] text-[#ffb4ab]">${esc(err.message)}</span>`;
    }
    toast("Ingest failed: " + err.message, "err");
  }
}

/* ---------------- mode ---------------- */

function setMode(m) {
  mode = m;
  const q = document.getElementById("modeQuick");
  const d = document.getElementById("modeDeep");
  const on = "px-3 py-1 rounded-full font-mono text-[11px] font-semibold bg-[#282a2c] text-[#a8c7fa] shadow-sm transition-all flex items-center gap-1";
  const off = "px-3 py-1 rounded-full font-mono text-[11px] font-medium text-[#9aa0a6] hover:text-[#e3e3e3] transition-all flex items-center gap-1";
  q.className = m === "quick" ? on : off;
  d.className = m === "deep" ? on : off;
}

/* ---------------- boot ---------------- */

window.addEventListener("DOMContentLoaded", () => {
  if (document.getElementById("loginForm")) initLogin();
  else if (document.getElementById("chatStream")) initChat();
});
