// photo-labeler - human + bot image labeling for municipal photo training data.
// One Worker: Hebrew RTL labeling web page + hosted MCP (Streamable HTTP) + KV label store.
// Labels are keyed per source (human/grok) and never overwrite each other.
// Crosswalk photos are private: served from KV only with the bearer key.
// Mapillary images are CC BY-SA, plates pre-blurred by Mapillary, loaded from their CDN.
import { MARK_PAGE, markState, submitMarks } from "./mark-page.mjs";
const PROTOCOL = "2024-11-05";
// ===== Label sets and verdict vocabulary =====
const SETS = {
  legalpark: {
    title: "חנייה חוקית (כחול-לבן) - 109 מועמדים",
    question: "האם הרכבים בתמונה חונים חוקית ליד שפה כחול-לבנה?",
    mark_hint: "סמן בנגיעה כל רכב שחונה שלא חוקי",
    verdicts: [
      ["all_legal", "כולם חוקי"],
      ["some_illegal", "חלק לא חוקי"],
      ["none_legal", "אף אחד לא חוקי"],
      ["unsure", "לא בטוח"],
    ],
  },
  xwalk: {
    title: "מעבר חצייה - 159 מועמדים",
    question: "האם יש מעבר חצייה בתמונה? האם רכב חונה עליו / חוסם אותו?",
    mark_hint: "סמן בנגיעה כל רכב שחונה על מעבר החצייה או חוסם אותו",
    verdicts: [
      ["all_legal", "יש מעבר חצייה, אין רכב חוסם"],
      ["some_illegal", "יש רכב חוסם את המעבר"],
      ["none_legal", "אין מעבר חצייה בתמונה"],
      ["unsure", "לא בטוח"],
    ],
  },
};
const SOURCES = ["human", "grok"];
const BOT_SOURCES = SOURCES.filter((s) => s !== "human");

// ===== HTTP helpers and bearer auth =====
const json = (o, init = {}) =>
  new Response(JSON.stringify(o), { ...init, headers: { "content-type": "application/json; charset=utf-8", ...(init.headers || {}) } });
const unauthorized = () => json({ error: "unauthorized" }, { status: 401 });

function okAuth(req, env, url) {
  const h = req.headers.get("authorization") || "";
  if (h === `Bearer ${env.LABEL_KEY}`) return true;
  // Query key is for the browser page only; bots must use the Authorization header.
  if (url.pathname === "/mcp" || url.pathname === "/api/export") return false;
  return url.searchParams.get("key") === env.LABEL_KEY;
}

// ===== KV store access =====
async function manifest(env, set) {
  const raw = await env.LABELS.get(`manifest:${set}`);
  return raw ? JSON.parse(raw) : [];
}

async function labelsFor(env, set) {
  const out = {}; // source -> { id: label }
  for (const src of SOURCES) {
    out[src] = {};
    let cursor;
    do {
      const l = await env.LABELS.list({ prefix: `label:${set}:${src}:`, cursor });
      for (const k of l.keys) {
        const v = await env.LABELS.get(k.name);
        if (v) out[src][k.name.split(":").pop()] = JSON.parse(v);
      }
      cursor = l.list_complete ? undefined : l.cursor;
    } while (cursor);
  }
  return out;
}

// ===== Label workflow =====
async function nextUnlabeled(env, set, source) {
  const m = await manifest(env, set);
  const labels = await labelsFor(env, set);
  const mine = labels[source] || {};
  const item = m.find((it) => !mine[it.id]);
  if (!item) return null;
  return { set, id: item.id, image_url: item.url || null,
    served_url: item.url ? null : `/img/${set}/${item.id}`,
    remaining: m.filter((it) => !mine[it.id]).length, total: m.length };
}

async function submitLabel(env, set, source, id, verdict, marks) {
  const m = await manifest(env, set);
  if (!m.some((it) => it.id === id)) return { error: `unknown id ${id} in set ${set}` };
  if (!SOURCES.includes(source)) return { error: `source must be one of ${SOURCES.join("/")}` };
  const valid = SETS[set].verdicts.map((v) => v[0]);
  if (!valid.includes(verdict)) return { error: `verdict must be one of ${valid.join("/")}` };
  const cleanMarks = Array.isArray(marks)
    ? marks.filter((p) => p && Number.isFinite(p.x) && Number.isFinite(p.y) && p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1)
        .slice(0, 50).map((p) => ({ x: +p.x.toFixed(4), y: +p.y.toFixed(4) }))
    : [];
  const rec = { set, id, source, verdict, marks: cleanMarks, ts: new Date().toISOString() };
  await env.LABELS.put(`label:${set}:${source}:${id}`, JSON.stringify(rec));
  return { saved: rec };
}

async function progress(env) {
  const out = {};
  for (const set of Object.keys(SETS)) {
    const m = await manifest(env, set);
    const labels = await labelsFor(env, set);
    out[set] = { total: m.length };
    for (const src of SOURCES) out[set][src] = { labeled: Object.keys(labels[src]).length };
  }
  return out;
}

// ===== MCP tool surface =====
const TOOLS = [
  { name: "get_next_unlabeled",
    description: "Get the next image awaiting a label from a set, for your source identity. Returns id, image_url (fetch with the same bearer key) and remaining count.",
    inputSchema: { type: "object", properties: {
      set: { type: "string", enum: Object.keys(SETS) },
      source: { type: "string", enum: BOT_SOURCES, description: "Your identity: bots must use their own name, never 'human'." } },
      required: ["set", "source"] } },
  { name: "submit_label",
    description: "Submit a label for one image. verdict is the per-image call; marks are normalized (0-1) points on each offending car (empty if none). Stored under your source; never overwrites another source.",
    inputSchema: { type: "object", properties: {
      set: { type: "string", enum: Object.keys(SETS) },
      id: { type: "string" },
      verdict: { type: "string", enum: ["all_legal", "some_illegal", "none_legal", "unsure"] },
      marks: { type: "array", items: { type: "object", properties: { x: { type: "number" }, y: { type: "number" } }, required: ["x", "y"] } },
      source: { type: "string", enum: BOT_SOURCES } },
      required: ["set", "id", "verdict", "source"] } },
  { name: "get_progress",
    description: "Labeling progress per set and per source (human vs bot counts stay separate).",
    inputSchema: { type: "object", properties: {} } },
];

async function callTool(env, name, args = {}) {
  if (args.source === "human") return { error: "MCP callers must not use source 'human'" };
  if (name === "get_next_unlabeled") {
    if (!SETS[args.set]) return { error: "unknown set" };
    const n = await nextUnlabeled(env, args.set, args.source || "grok");
    return n || { done: true };
  }
  if (name === "submit_label") return submitLabel(env, args.set, args.source || "grok", args.id, args.verdict, args.marks);
  if (name === "get_progress") return progress(env);
  return { error: `unknown tool ${name}` };
}

// ===== MCP transport (Streamable HTTP, stateless) =====
async function handleMcp(req, env) {
  let msg;
  try { msg = await req.json(); } catch { return json({ error: "bad json" }, { status: 400 }); }
  const { id, method, params } = msg;
  const reply = (result) => json({ jsonrpc: "2.0", id, result });
  const err = (code, message) => json({ jsonrpc: "2.0", id, error: { code, message } });
  if (method === "initialize") return reply({ protocolVersion: PROTOCOL,
    capabilities: { tools: {} }, serverInfo: { name: "photo-labeler", version: "0.2.0" } });
  if (method === "notifications/initialized" || method === "ping") return new Response(null, { status: 202 });
  if (method === "tools/list") return reply({ tools: TOOLS });
  if (method === "tools/call") {
    const result = await callTool(env, params?.name, params?.arguments);
    return reply({ content: [{ type: "text", text: JSON.stringify(result) }] });
  }
  return err(-32601, "method not found");
}

// ===== Web page (Hebrew RTL labeling UI) =====
const PAGE = `<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>סיווג תמונות</title>
<style>
  * { box-sizing: border-box; margin: 0; }
  body { font-family: system-ui, -apple-system, sans-serif; background: #111; color: #eee;
         display: flex; flex-direction: column; align-items: center; min-height: 100vh; }
  header, #stage, #q, #hint, #btns, #nav, #msg, #kb { width: 100%; max-width: 720px; }
  header { padding: 10px 14px; font-size: 15px; background: #1c1c1e; position: sticky; top: 0; z-index: 5; }
  #bar { height: 5px; background: #333; margin-top: 8px; border-radius: 3px; overflow: hidden; }
  #fill { height: 100%; background: #4caf50; width: 0; transition: width .2s; }
  #stage { position: relative; width: fit-content; max-width: 100%; margin: 0 auto; touch-action: manipulation; }
  #photo { display: block; max-width: 100%; max-height: 62vh; margin: 0 auto; user-select: none; -webkit-user-select: none; }
  .pin { position: absolute; width: 30px; height: 30px; margin: -15px 0 0 -15px; border-radius: 50%;
         background: rgba(255,59,48,.85); border: 2px solid #fff; pointer-events: none; }
  #q { padding: 10px 14px; font-size: 14px; color: #bbb; }
  #hint { padding: 0 14px 8px; font-size: 13px; color: #888; }
  #btns { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; padding: 10px 14px; }
  #btns button { font-size: 17px; padding: 16px 8px; border: 0; border-radius: 12px; color: #fff; }
  .v0 { background: #2e7d32; } .v1 { background: #c62828; } .v2 { background: #6d4c41; } .v3 { background: #546e7a; }
  #nav { display: flex; gap: 10px; padding: 0 14px 14px; }
  #nav button { flex: 1; font-size: 15px; padding: 12px; border-radius: 10px; border: 1px solid #444; background: #1c1c1e; color: #eee; }
  #export { background: #0a5640 !important; }
  #msg { text-align: center; font-size: 13px; color: #7fc; min-height: 18px; padding-bottom: 10px; }
</style>
</head>
<body>
<header>
  <div id="title"></div>
  <div id="bar"><div id="fill"></div></div>
  <div id="count" style="font-size:12px;color:#999;margin-top:4px"></div>
</header>
<div id="stage"><img id="photo" alt=""></div>
<div id="q"></div>
<div id="hint"></div>
<div id="btns"></div>
<div id="nav">
  <button id="prev">הקודם</button>
  <button id="skip">דלג</button>
  <button id="export">ייצא תוצאות</button>
</div>
<div id="kb" style="text-align:center;font-size:12px;color:#666;padding-bottom:6px">מקלדת: 1-4 לסיווג, חץ ימינה = הקודם, חץ שמאלה = דלג</div>
<div id="msg"></div>
<div id="keyform" style="display:none;position:fixed;inset:0;background:#111;padding:40px 24px;z-index:20">
  <div style="max-width:420px;margin:0 auto">
    <h1 style="font-size:20px;margin-bottom:10px">סיווג תמונות</h1>
    <p style="font-size:14px;color:#bbb;margin-bottom:16px" id="keymsg">כדי להיכנס, הדביקו את המפתח שקיבלתם ולחצו כניסה.</p>
    <input id="keyin" type="text" inputmode="latin" autocapitalize="off" autocomplete="off" placeholder="המפתח" style="width:100%;font-size:17px;padding:14px;border-radius:10px;border:1px solid #444;background:#1c1c1e;color:#eee;margin-bottom:12px">
    <button id="keygo" style="width:100%;font-size:17px;padding:14px;border:0;border-radius:10px;background:#2e7d32;color:#fff">כניסה</button>
  </div>
</div>
<script>
let KEY = new URLSearchParams(location.search).get('key') || localStorage.getItem('label_key') || '';
if (KEY) localStorage.setItem('label_key', KEY);
const SET = new URLSearchParams(location.search).get('set') || 'legalpark';
const api = (p, o) => fetch(p + (p.includes('?') ? '&' : '?') + 'key=' + encodeURIComponent(KEY), o).then(r => r.json());
let man = [], idx = 0, labels = {}, marks = [];

function showKeyForm(msg) {
  const f = document.getElementById('keyform');
  f.style.display = 'block';
  if (msg) document.getElementById('keymsg').textContent = msg;
  document.getElementById('keyin').focus();
}
document.getElementById('keygo').onclick = () => {
  const v = document.getElementById('keyin').value.trim();
  if (!v) return;
  KEY = v;
  localStorage.setItem('label_key', v);
  document.getElementById('keyform').style.display = 'none';
  boot();
};
document.getElementById('keyin').addEventListener('keydown', ev => {
  if (ev.key === 'Enter') document.getElementById('keygo').click();
});

async function boot() {
  if (!KEY) { showKeyForm(); return; }
  const d = await api('/api/state?set=' + SET);
  if (d.error === 'unauthorized') {
    localStorage.removeItem('label_key'); KEY = '';
    showKeyForm('המפתח לא נכון. הדביקו שוב את המפתח מההודעה ולחצו כניסה.');
    return;
  }
  if (d.error) { document.getElementById('msg').textContent = 'שגיאה: ' + d.error; return; }
  man = d.manifest; labels = d.labels;
  document.getElementById('title').textContent = d.title;
  document.getElementById('q').textContent = d.question;
  document.getElementById('hint').textContent = d.mark_hint;
  const btns = document.getElementById('btns');
  d.verdicts.forEach(([val, he], i) => {
    const b = document.createElement('button');
    b.textContent = he; b.className = 'v' + i;
    b.onclick = () => save(val);
    btns.appendChild(b);
  });
  idx = man.findIndex(it => !labels[it.id]);
  if (idx < 0) idx = 0;
  show();
}
function show() {
  const it = man[idx]; if (!it) return;
  const img = document.getElementById('photo');
  img.src = it.url || ('/img/' + SET + '/' + it.id + '?key=' + encodeURIComponent(KEY));
  const rec = labels[it.id];
  marks = rec && rec.marks ? rec.marks.slice() : [];
  drawPins();
  const done = Object.keys(labels).length;
  document.getElementById('fill').style.width = (100 * done / man.length) + '%';
  document.getElementById('count').textContent = done + ' / ' + man.length + ' מסווגים' + (rec ? ' (סווג: שמור)' : '');
  document.getElementById('msg').textContent = '';
}
function drawPins() {
  document.querySelectorAll('.pin').forEach(p => p.remove());
  const st = document.getElementById('stage');
  for (const m of marks) {
    const d = document.createElement('div');
    d.className = 'pin';
    d.style.left = (m.x * 100) + '%'; d.style.top = (m.y * 100) + '%';
    st.appendChild(d);
  }
}
document.getElementById('stage').addEventListener('click', ev => {
  const r = ev.currentTarget.getBoundingClientRect();
  const x = (ev.clientX - r.left) / r.width, y = (ev.clientY - r.top) / r.height;
  const near = marks.findIndex(m => Math.hypot((m.x - x) * r.width, (m.y - y) * r.height) < 24);
  if (near >= 0) marks.splice(near, 1); else marks.push({ x, y });
  drawPins();
});
async function save(verdict) {
  const it = man[idx];
  const r = await api('/api/label', { method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ set: SET, id: it.id, verdict, marks, source: 'human' }) });
  if (r.saved) {
    labels[it.id] = r.saved;
    document.getElementById('msg').textContent = 'נשמר';
    const nxt = man.findIndex((x, i) => i > idx && !labels[x.id]);
    idx = nxt >= 0 ? nxt : man.findIndex(x => !labels[x.id]);
    if (idx < 0) { idx = man.length - 1; document.getElementById('msg').textContent = 'סיימת את כל הסט!'; }
    show();
  } else document.getElementById('msg').textContent = 'שגיאה: ' + (r.error || '?');
}
document.getElementById('prev').onclick = () => { if (idx > 0) { idx--; show(); } };
document.getElementById('skip').onclick = () => { if (idx < man.length - 1) { idx++; show(); } };
document.addEventListener('keydown', ev => {
  if (document.getElementById('keyform').style.display === 'block') return;
  if (ev.target && ev.target.tagName === 'INPUT') return;
  const bs = document.getElementById('btns').children;
  if (ev.key >= '1' && ev.key <= '4' && bs[+ev.key - 1]) bs[+ev.key - 1].click();
  else if (ev.key === 'ArrowRight') document.getElementById('prev').click();
  else if (ev.key === 'ArrowLeft') document.getElementById('skip').click();
});
document.getElementById('export').onclick = async () => {
  const d = await api('/api/export?set=' + SET);
  const blob = new Blob([JSON.stringify(d, null, 1)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'labels-' + SET + '.json';
  a.click();
};
boot();
</script>
</body>
</html>`;

// ===== Worker entry point =====
export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const path = url.pathname;

    // The labeling page is served without auth: it asks for the key in the
    // browser and stores it in localStorage. API, MCP and images stay authed.
    if (path === "/" || path === "/index.html")
      return new Response(PAGE, { headers: { "content-type": "text/html; charset=utf-8" } });
    if (path === "/mark")
      return new Response(MARK_PAGE, { headers: { "content-type": "text/html; charset=utf-8" } });

    if (!okAuth(req, env, url)) return unauthorized();

    if (path === "/mcp" && req.method === "POST") return handleMcp(req, env);
    if (path === "/mcp") return new Response("POST only", { status: 405 });

    if (path.startsWith("/img/")) {
      const [, , set, id] = path.split("/");
      const m = await manifest(env, set);
      const it = m.find((x) => x.id === id);
      if (!it) return json({ error: "not found" }, { status: 404 });
      if (it.url) return Response.redirect(it.url, 302);
      const obj = await env.LABELS.get(`img:${set}:${id}`, { type: "arrayBuffer" });
      if (!obj) return json({ error: "image not stored" }, { status: 404 });
      return new Response(obj, { headers: { "content-type": "image/jpeg", "cache-control": "private, max-age=3600" } });
    }

    if (path === "/api/state") {
      const set = url.searchParams.get("set") || "legalpark";
      if (!SETS[set]) return json({ error: "unknown set" });
      const m = await manifest(env, set);
      const labels = (await labelsFor(env, set)).human || {};
      return json({ title: SETS[set].title, question: SETS[set].question, mark_hint: SETS[set].mark_hint,
        verdicts: SETS[set].verdicts, manifest: m, labels });
    }

    if (path === "/api/label" && req.method === "POST") {
      let b; try { b = await req.json(); } catch { return json({ error: "bad json" }, { status: 400 }); }
      return json(await submitLabel(env, b.set, "human", b.id, b.verdict, b.marks));
    }

    if (path === "/api/export") {
      const set = url.searchParams.get("set") || "legalpark";
      const labels = await labelsFor(env, set);
      return json({ set, exported: new Date().toISOString(), by_source: labels });
    }

    if (path === "/api/progress") return json(await progress(env));

    if (path === "/api/mark-state") {
      const set = url.searchParams.get("set") || "xwalk";
      if (!SETS[set]) return json({ error: "unknown set" });
      return json(await markState(env, set, manifest, labelsFor));
    }

    if (path === "/api/mark" && req.method === "POST") {
      let b; try { b = await req.json(); } catch { return json({ error: "bad json" }, { status: 400 }); }
      if (!SETS[b.set]) return json({ error: "unknown set" });
      return json(await submitMarks(env, b.set, b.id, b.marks));
    }

    return json({ error: "not found" }, { status: 404 });
  },
};
