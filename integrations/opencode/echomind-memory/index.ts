/**
 * EchoMind long-term memory for OpenCode — dual V1/V2 plugin.
 *
 * The default export is the object form OpenCode supports for both APIs:
 *   • V1 (OpenCode <= 1.19.x V1 loader) calls `server(input)` and uses the
 *     returned hooks (`chat.message`, `experimental.chat.system.transform`,
 *     `event`, `experimental.session.compacting`).
 *   • V2 (documented `@opencode/plugin` API) reads `id` + `setup(ctx)` and
 *     ignores `server()`.
 *
 * It has no runtime dependency on either plugin package, so the same directory
 * loads on V1 and V2. All memory work is delegated to the local EchoMind HTTP
 * service, which owns ranking, storage, dedup and reflection.
 *
 * Environment:
 *   ECHOMIND_URL          default http://127.0.0.1:8005
 *   ECHOMIND_API_KEY      optional X-API-Key
 *   ECHOMIND_HOOK_PROJECT override project scope (default: basename(directory))
 *   ECHOMIND_HOOK_USER    override user id (default: EchoMind default_user)
 *   ECHOMIND_HOOK_PROFILE override profile (default: default)
 */

type AnyRec = Record<string, any>;

const ENV: AnyRec = ((globalThis as any).process?.env) || {};
const BASE_URL = String(ENV.ECHOMIND_URL || "http://127.0.0.1:8005").replace(/\/+$/, "");
const API_KEY = String(ENV.ECHOMIND_API_KEY || "");
const HOOK_USER = String(ENV.ECHOMIND_HOOK_USER || "");
const HOOK_PROFILE = String(ENV.ECHOMIND_HOOK_PROFILE || "default");
const HOOK_PROJECT = String(ENV.ECHOMIND_HOOK_PROJECT || "");

/** Session-scoped recalled block, consumed once by the next model request. */
const recallCache = new Map<string, string>();

/** Last message id already persisted, per session (delta storage). */
const lastStored = new Map<string, string>();

let lastWarnAt = 0;
function warnThrottled(message: string): void {
  const now = Date.now();
  if (now - lastWarnAt < 60_000) return;
  lastWarnAt = now;
  try {
    console.warn(`[echomind] ${message}`);
  } catch {
    // no console available
  }
}

async function postJSON(path: string, body: AnyRec, timeoutMs = 8000): Promise<AnyRec> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!res.ok) {
      warnThrottled(`hook ${path} returned HTTP ${res.status}`);
      return {};
    }
    const data = await res.json();
    return data && typeof data === "object" ? (data as AnyRec) : {};
  } catch (err) {
    warnThrottled(`hook ${path} unreachable: ${(err as any)?.name || err}`);
    return {};
  } finally {
    clearTimeout(timer);
  }
}

function basePayload(sessionID: string, directory: string): AnyRec {
  return {
    session_id: sessionID || "",
    user_id: HOOK_USER || undefined,
    profile: HOOK_PROFILE,
    // Only send an explicit project when the user configured one; otherwise
    // leave it empty so the server's hooks.project / default_project applies.
    project: HOOK_PROJECT || undefined,
    cwd: directory || undefined,
  };
}

async function recall(query: string, sessionID: string, directory: string): Promise<string> {
  if (!query || !query.trim()) return "";
  const data = await postJSON("/api/hooks/opencode", {
    action: "recall",
    query,
    ...basePayload(sessionID, directory),
  }, 2000);
  return typeof data.context === "string" ? data.context : "";
}

async function briefing(sessionID: string, directory: string): Promise<string> {
  const data = await postJSON("/api/hooks/opencode", {
    action: "briefing",
    ...basePayload(sessionID, directory),
  }, 3000);
  return typeof data.context === "string" ? data.context : "";
}

async function storeMessages(
  messages: AnyRec[],
  sessionID: string,
  directory: string,
  turn?: string,
): Promise<AnyRec> {
  if (!messages || !messages.length) return {};
  const res = await postJSON("/api/hooks/opencode", {
    action: "store",
    turn: turn || undefined,
    messages,
    extract_knowledge: false,
    ...basePayload(sessionID, directory),
  });
  const status = typeof res.status === "string" ? res.status : "";
  if (status === "stored" || status === "duplicate") {
    const lastId = turn || messages[messages.length - 1]?.id;
    if (lastId) lastStored.set(sessionID, String(lastId));
  }
  return res;
}

/** Messages added since the last successfully stored turn. */
function unseenMessages(messages: AnyRec[], sessionID: string): AnyRec[] {
  const lastId = lastStored.get(sessionID);
  if (!lastId) return messages;
  const idx = messages.findIndex((m) => String(m.id || "") === lastId);
  if (idx < 0) return messages;
  return messages.slice(idx + 1);
}

function textFromParts(parts: any[]): string {
  if (!Array.isArray(parts)) return "";
  return parts
    .filter((p) => p && p.type === "text" && typeof p.text === "string")
    .map((p) => p.text)
    .join("\n");
}

/** Normalize OpenCode message objects to {role, content, id}. */
function normalizeClientMessages(list: any[]): AnyRec[] {
  if (!Array.isArray(list)) return [];
  const out: AnyRec[] = [];
  for (const item of list) {
    if (!item || typeof item !== "object") continue;
    const info = item.info && typeof item.info === "object" ? item.info : {};
    const role = item.role || info.role;
    if (role !== "user" && role !== "assistant") continue;
    let content = item.content;
    if (typeof content !== "string") content = textFromParts(item.parts);
    if (typeof content !== "string" || !content.trim()) continue;
    out.push({
      role,
      content: content.trim().slice(0, 4000),
      id: String(info.id || item.id || ""),
    });
  }
  return out.slice(-30);
}

/** Read a session transcript through whichever client shape is available. */
async function readSessionMessages(client: any, sessionID: string): Promise<AnyRec[]> {
  if (!client || !sessionID) return [];
  const attempts = [
    () => client.session?.messages({ path: { id: sessionID }, query: { limit: 30 } }),
    () => client.session?.messages({ sessionID }),
    () => client.session?.messages({ id: sessionID }),
  ];
  for (const attempt of attempts) {
    try {
      const res = await attempt();
      const list = Array.isArray(res) ? res : res?.data;
      if (Array.isArray(list) && list.length) return normalizeClientMessages(list);
    } catch {
      // try the next shape
    }
  }
  return [];
}

// ── V2 API (documented @opencode/plugin) ──────────────────────────────────

async function setup(ctx: any): Promise<() => void> {
  // The V2 API is not present in the 1.19.x loader. Stay inert rather than
  // throwing when a V1 host happens to call setup().
  if (typeof ctx?.session?.hook !== "function"
      || typeof ctx?.event?.subscribe !== "function") {
    warnThrottled("V2 plugin API not available; V1 hook path is used");
    return () => {};
  }
  const directory = String(ctx?.location?.directory || ctx?.location?.project?.directory || "");
  const controller = new AbortController();

  await ctx.session.hook("prompt", async (event: any) => {
    const sessionID = String(event?.sessionID || event?.session?.id || "default");
    const text = String(event?.prompt?.text || "");
    const block = await recall(text, sessionID, directory);
    if (block) recallCache.set(sessionID, block);
  });

  await ctx.session.hook("context", (event: any) => {
    const sessionID = String(event?.sessionID || event?.session?.id || "default");
    const block = recallCache.get(sessionID);
    if (!block) return;
    if (Array.isArray(event.system)) {
      // Match the array's own element type instead of guessing.
      const first = event.system.find((entry: any) => entry !== undefined);
      if (first === undefined || typeof first === "string") {
        event.system.push(block);
      } else {
        event.system.push({ type: "text", text: block });
      }
    }
    recallCache.delete(sessionID);
  });

  await ctx.session.hook("compaction", async (event: any) => {
    const sessionID = String(event?.sessionID || "default");
    const messages = normalizeClientMessages(event?.messages || []);
    if (!messages.length) return;
    const lastId = messages[messages.length - 1]?.id || "";
    // Same turn key as session.idle, so the server dedupes the snapshot.
    await storeMessages(unseenMessages(messages, sessionID), sessionID, directory,
                        lastId || undefined);
  });

  void (async () => {
    try {
      for await (const event of ctx.event.subscribe({
        types: ["session.idle"],
        signal: controller.signal,
      })) {
        const sessionID = String(event?.properties?.sessionID || event?.sessionID || "");
        if (!sessionID) continue;
        const messages = await readSessionMessages(ctx, sessionID);
        if (!messages.length) continue;
        const lastId = messages[messages.length - 1]?.id || "";
        await storeMessages(unseenMessages(messages, sessionID), sessionID, directory,
                            lastId || undefined);
      }
    } catch {
      // subscription aborted or transport closed — plugin stays inert
    }
  })();

  return () => controller.abort();
}

// ── V1 API (OpenCode <= 1.19.x V1 loader) ─────────────────────────────────

async function server(input: any = {}): Promise<AnyRec> {
  const client = input?.client;
  const directory = String(input?.directory || "");

  return {
    "chat.message": async (event: any, output: any) => {
      const sessionID = String(event?.sessionID || "default");
      const text = textFromParts(output?.parts || []);
      const block = await recall(text, sessionID, directory);
      if (block) recallCache.set(sessionID, block);
    },

    "experimental.chat.system.transform": async (event: any, output: any) => {
      const sessionID = String(event?.sessionID || "default");
      const block = recallCache.get(sessionID);
      if (!block) return;
      if (Array.isArray(output?.system)) output.system.push(block);
      recallCache.delete(sessionID);
    },

    event: async ({ event }: any) => {
      if (!event || event.type !== "session.idle") return;
      const sessionID = String(event?.properties?.sessionID || "");
      if (!sessionID) return;
      const messages = await readSessionMessages(client, sessionID);
      if (!messages.length) return;
      const lastId = messages[messages.length - 1]?.id || "";
      await storeMessages(unseenMessages(messages, sessionID), sessionID, directory,
                          lastId || undefined);
    },

    "experimental.session.compacting": async (event: any) => {
      const sessionID = String(event?.sessionID || "");
      if (!sessionID) return;
      const messages = await readSessionMessages(client, sessionID);
      if (!messages.length) return;
      const lastId = messages[messages.length - 1]?.id || "";
      await storeMessages(unseenMessages(messages, sessionID), sessionID, directory,
                          lastId || undefined);
    },
  };
}

// Default export: V2 reads { id, setup }, V1 calls server().
export default {
  id: "echomind.memory",
  setup,
  server,
};

// Also export the briefing helper for callers/tests that want a session-start
// block outside the hook flow.
export { briefing, recall };
