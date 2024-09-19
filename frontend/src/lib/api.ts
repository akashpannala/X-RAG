/* Typed wrapper over the FastAPI backend. Token lives in localStorage. */
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export type Role = { id: number; username: string; groups: string[] };

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("offline_rag_token");
}

export function setToken(t: string | null) {
  if (typeof window === "undefined") return;
  if (t) localStorage.setItem("offline_rag_token", t);
  else localStorage.removeItem("offline_rag_token");
}

async function req(path: string, init: RequestInit = {}, auth = true) {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (auth) {
    const t = getToken();
    if (!t) throw new Error("Not signed in. Sign in first.");
    headers["Authorization"] = `Bearer ${t}`;
  }
  const r = await fetch(`${BASE}${path}`, { ...init, headers });
  if (r.status === 401) {
    setToken(null);
    throw new Error("Session expired or invalid. Sign in again.");
  }
  if (!r.ok) {
    const body = await r.text();
    throw new Error(`Request failed (${r.status}): ${body.slice(0, 200)}`);
  }
  return r.json();
}

export const api = {
  health: () => req("/health", {}, false),
  login: async (username: string, password: string) => {
    const r = await req(
      "/auth/login",
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) },
      false,
    );
    setToken(r.access_token);
    return r;
  },
  register: (username: string, password: string, groups: string[]) =>
    req("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, groups }),
    }, false),
  ingest: (file: File, allowedGroups: string, enrich: boolean) => {
    const fd = new FormData();
    fd.append("f", file);
    return req(`/ingest?allowed_groups=${encodeURIComponent(allowedGroups)}&enrich=${enrich}`, {
      method: "POST",
      body: fd,
    });
  },
  query: (query: string, mode: string | null, top_k = 5) =>
    req("/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, top_k, mode }),
    }),
};

export function decodeRole(token: string): Role | null {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return { id: Number(payload.sub), username: payload.username, groups: payload.groups ?? [] };
  } catch {
    return null;
  }
}
