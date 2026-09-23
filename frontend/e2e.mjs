// X-RAG static frontend E2E via CDP (debug chrome on :9222)
// usage: ensure chrome on :9222 (CHROME_PATH=... npx -y @accesslint/chrome@latest ensure), then `node e2e.mjs`
import fs from "node:fs";

const CDP_PORT = 9222;
const BASE = "http://localhost:3000";
const FIXTURE = `# Vacation Policy (HR Handbook 2026)

## Accrual
Full-time employees accrue 1.5 days of paid vacation per month (18 days per year).
New hires may use vacation after completing the 90-day probation period.

## Requesting time off
Submit requests at least 14 days in advance through the HR portal.
Requests are approved by your people manager based on team coverage.

## Carryover
Up to 5 unused days carry over into the next calendar year.
Unused days beyond the carryover limit expire on January 31.
`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let msgId = 0;
const pending = new Map();
const consoleErrors = [];
let ws;

function send(method, params = {}) {
  const id = ++msgId;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    setTimeout(() => {
      if (pending.has(id)) {
        pending.delete(id);
        reject(new Error("CDP timeout: " + method));
      }
    }, 30000);
  });
}

async function evalJs(expression) {
  const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error("eval failed: " + JSON.stringify(r.exceptionDetails.exception?.description || r.exceptionDetails));
  return r.result.value;
}

async function waitFor(expression, timeoutMs = 30000, label = expression) {
  const t0 = Date.now();
  for (;;) {
    let v;
    try { v = await evalJs(expression); } catch { v = false; }
    if (v) return v;
    if (Date.now() - t0 > timeoutMs) throw new Error("timeout waiting for: " + label);
    await sleep(300);
  }
}

const results = [];
function check(name, ok, extra = "") {
  results.push({ name, ok });
  console.log((ok ? "PASS" : "FAIL") + "  " + name + (extra ? "  [" + extra + "]" : ""));
  if (!ok) process.exitCode = 1;
}

async function main() {
  const stamp = Date.now().toString(36);
  const uploadFile = `/tmp/opencode/vacation_e2e_${stamp}.md`;
  const uploadBase = uploadFile.split("/").pop();
  fs.writeFileSync(uploadFile, FIXTURE);
  // close leftover page tabs from prior runs
  const old = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`).then((r) => r.json()).catch(() => []);
  for (const t of old) {
    if (t.type === "page") await fetch(`http://127.0.0.1:${CDP_PORT}/json/close/${t.id}`).catch(() => {});
  }
  // open tab
  const tab = await fetch(`http://127.0.0.1:${CDP_PORT}/json/new?${encodeURIComponent(BASE + "/index.html")}`, { method: "PUT" }).then((r) => r.json());
  ws = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) {
      const { resolve, reject } = pending.get(m.id);
      pending.delete(m.id);
      m.error ? reject(new Error(m.error.message)) : resolve(m.result);
    } else if (m.method === "Runtime.exceptionThrown") {
      consoleErrors.push(m.params.exceptionDetails.exception?.description || "exception");
    } else if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error") {
      consoleErrors.push(m.params.args.map((a) => a.value || a.description).join(" "));
    }
  };
  await send("Page.enable");
  await send("Runtime.enable");
  await send("DOM.enable");
  // python http.server sends no Cache-Control — Chrome would heuristically cache
  // app.js across runs and test stale JS. Always bypass cache in tests.
  await send("Network.enable");
  await send("Network.setCacheDisabled", { cacheDisabled: true });

  // start clean: navigate first (tab may be about:blank), then drop any token
  await send("Page.navigate", { url: BASE + "/index.html" });
  await waitFor(`location.origin === ${JSON.stringify(BASE)}`, 15000, "tab on origin");
  await evalJs(`localStorage.removeItem("xrag.token"); "ok"`);
  await send("Page.navigate", { url: BASE + "/index.html" });

  // ---- 1. login page ----
  await waitFor(`!!document.getElementById("loginForm")`, 15000, "login form");
  check("login page renders", true);
  const gh = await evalJs(`document.querySelector('a[href*="github.com"]')?.href || ""`);
  check("login github link", gh.includes("github.com/akashpannala/X-RAG"), gh);

  await evalJs(`document.querySelector('[data-demo-user="LUFFY"]').click()`);
  const filled = await evalJs(`document.getElementById("username").value + "/" + document.getElementById("password").value`);
  check("demo preset fills form", filled === "LUFFY/password", filled);

  await evalJs(`document.getElementById("loginForm").dispatchEvent(new Event("submit",{cancelable:true,bubbles:true}))`);
  await waitFor(`location.href.includes("chat.html")`, 20000, "redirect to chat");
  check("login redirects to chat.html", true);

  // ---- 2. chat shell ----
  await waitFor(`!!document.getElementById("chatStream") && !!document.getElementById("srcList")`, 15000, "chat shell");
  const who = await evalJs(`document.getElementById("userName").textContent`);
  check("session header shows user", who === "LUFFY", who);
  const modeActive = await evalJs(`document.getElementById("modeQuick").className.includes("bg-[#282a2c]")`);
  check("default mode = quick (hr group)", modeActive === true);
  const hl = await waitFor(`document.getElementById("healthLabel").textContent`, 15000, "health label");
  check("chat health pill", hl.includes("healthy"), hl);
  const ghChat = await evalJs(`[...document.querySelectorAll('a[href*="github.com"]')].length`);
  check("chat github link", ghChat > 0, ghChat + " links");

  // existing docs in rail — wait until renderDocs ran (row or empty-state, not the HTML placeholder)
  await waitFor(`document.querySelector("#srcList article") || document.getElementById("srcList").textContent.includes("No sources yet") || document.getElementById("srcList").textContent.includes("No matches")`, 15000, "rail rendered");
  const count1 = await evalJs(`document.getElementById("srcCount").textContent`);
  check("sources rail loads documents", /\d+ active/.test(count1), count1);

  // ---- 3. upload ----
  const inputEl = await send("Runtime.evaluate", { expression: `document.getElementById("fileInput")` });
  await send("DOM.setFileInputFiles", { files: [uploadFile], objectId: inputEl.result.objectId });
  await evalJs(`document.getElementById("fileInput").dispatchEvent(new Event("change",{bubbles:true}))`);
  await waitFor(`!document.getElementById("uploadModal").classList.contains("hidden")`, 8000, "upload modal");
  const fname = await evalJs(`document.getElementById("uploadFileName").textContent`);
  check("upload modal opens with filename", fname === uploadBase, fname);
  const groupsChecked = await evalJs(`[...document.querySelectorAll("#uploadGroups input:checked")].map(i=>i.value).join(",")`);
  check("group chips prechecked from session", groupsChecked.split(",").length > 0, groupsChecked);

  await evalJs(`document.getElementById("uploadConfirm").click()`);
  // row only appears after POST /ingest responds and the rail refreshes
  await waitFor(`!!document.querySelector('#srcList [data-filename="${uploadBase}"]')`, 90000, "new doc row after ingest");
  check("ingest completes and rail refreshes", true);
  const count2 = await evalJs(`document.getElementById("srcCount").textContent`);
  check("rail count grew by one", parseInt(count2, 10) === parseInt(count1, 10) + 1, `${count1} -> ${count2}`);

  // ---- 4. ask ----
  await evalJs(`(() => {
    const c = document.getElementById("composerInput");
    c.value = "What does our vacation policy allow?";
    c.dispatchEvent(new Event("input",{bubbles:true}));
  })()`);
  await evalJs(`document.getElementById("btnSend").click()`);
  await waitFor(`!!document.getElementById("pendingBlock")`, 5000, "pending skeleton");
  check("pending skeleton shows", true);
  await waitFor(`!document.getElementById("pendingBlock") && !!document.querySelector("#chatStream [data-copy]")`, 90000, "answer card");
  const answerText = await evalJs(`document.querySelector("#chatStream [data-answer]").textContent`);
  check("answer rendered", answerText.length > 40, answerText.slice(0, 80));

  const citationCount = await evalJs(`document.querySelectorAll("#chatStream [data-cite]").length`);
  check("citation chips present", citationCount > 0, citationCount + " chips");

  const metaPills = await evalJs(`[...document.querySelectorAll("#chatStream [data-copy]")].length`);
  check("answer action bar present", metaPills === 1);

  // citation click highlights rail
  if (citationCount > 0) {
    const citeDoc = await evalJs(`document.querySelector("#chatStream [data-cite]").dataset.cite`);
    await evalJs(`document.querySelector("#chatStream [data-cite]").click()`);
    await sleep(600);
    const flashed = await evalJs(`!!document.querySelector("#srcList article.xrag-flash")`);
    check("citation click highlights rail row", flashed === true, "doc=" + citeDoc);
    const railCited = await evalJs(`[...document.querySelectorAll("#srcList article")].some(a => /\\[\\d+\\]/.test(a.textContent))`);
    check("rail shows numbered cited pill", railCited === true);
  }

  // ---- 5. history ----
  await waitFor(`document.querySelectorAll("#historyList [data-conv]").length > 0`, 20000, "history row");
  check("history pane shows new conversation", true);
  const histQ = await evalJs(`document.querySelector("#historyList [data-conv] p").textContent`);
  check("history item has query", histQ.includes("vacation policy"), histQ);

  // load conversation from history
  await evalJs(`document.querySelector("#historyList [data-conv]").click()`);
  await sleep(800);
  const reloaded = await evalJs(`document.querySelectorAll("#chatStream [data-copy]").length`);
  check("clicking history reloads the thread", reloaded >= 1);

  // search filter
  await evalJs(`(() => { const el = document.getElementById("historySearch"); el.value = "vac"; el.dispatchEvent(new Event("input", { bubbles: true })); })()`);
  await sleep(300);
  const filtered = await evalJs(`document.querySelectorAll("#historyList [data-conv]").length`);
  await evalJs(`(() => { const el = document.getElementById("historySearch"); el.value = ""; el.dispatchEvent(new Event("input", { bubbles: true })); })()`);
  check("history search filters", filtered >= 1);

  // ---- 6b. repeat query hits the answer cache ----
  await evalJs(`(() => { const c = document.getElementById("composerInput"); c.value = "What does our vacation policy allow?"; c.dispatchEvent(new Event("input", { bubbles: true })); })()`);
  await evalJs(`document.getElementById("btnSend").click()`);
  await waitFor(`document.querySelectorAll("#chatStream [data-answer]").length >= 2`, 60000, "cached answer card");
  const cachePill = await evalJs(`[...document.querySelectorAll("#chatStream div")].some(d => d.textContent.includes("Cache Hit"))`);
  check("cache-hit pill on repeat query", cachePill === true);

  // ---- 6. new session clears ----
  await evalJs(`document.getElementById("btnNew").click()`);
  await sleep(300);
  const emptyState = await evalJs(`document.querySelectorAll("#chatStream [data-suggest]").length`);
  check("new session restores empty state", emptyState === 4, emptyState + " suggestions");

  // ---- 7. sign out ----
  await evalJs(`document.getElementById("accountBtn").click()`);
  await waitFor(`location.href.includes("index.html")`, 15000, "sign out redirect");
  check("sign out returns to login", true);

  // ---- 8. auth gate: chat with no token ----
  await evalJs(`localStorage.removeItem("xrag.token"); location.href="chat.html"`);
  await waitFor(`location.href.includes("index.html")`, 15000, "auth gate");
  check("chat page redirects without token", true);

  check("no console errors", consoleErrors.length === 0, consoleErrors.slice(0, 3).join(" | "));

  const failed = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - failed}/${results.length} passed`);
  process.exit(failed ? 1 : 0);
}

main().catch((e) => { console.error("E2E error:", e.message); process.exit(2); });
