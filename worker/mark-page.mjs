// mark-page - tap-marking pass for images already labeled some_illegal.
// Separate module so both Worker files stay under the 400-line source cap.
// Marks are stored on the existing human label record (marks field); export
// already carries them, so the training pipeline reads one record per image.

// ===== Mark pass API =====
export async function markState(env, set, manifest, labelsFor) {
  const m = await manifest(env, set);
  const human = (await labelsFor(env, set)).human || {};
  const items = m
    .filter((it) => human[it.id] && human[it.id].verdict === "some_illegal")
    .map((it) => ({ id: it.id, url: it.url || null,
      served_url: it.url ? null : `/img/${set}/${it.id}`,
      marks: human[it.id].marks || [] }));
  return { set, total: items.length,
    marked: items.filter((it) => it.marks.length > 0).length, items };
}

export async function submitMarks(env, set, id, marks) {
  const key = `label:${set}:human:${id}`;
  const raw = await env.LABELS.get(key);
  if (!raw) return { error: `no human label for ${id} in set ${set}` };
  if (!Array.isArray(marks)) return { error: "marks must be an array of {x, y}" };
  const clean = marks
    .filter((p) => p && Number.isFinite(p.x) && Number.isFinite(p.y) && p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1)
    .slice(0, 50).map((p) => ({ x: +p.x.toFixed(4), y: +p.y.toFixed(4) }));
  const rec = JSON.parse(raw);
  rec.marks = clean;
  rec.marks_ts = new Date().toISOString();
  await env.LABELS.put(key, JSON.stringify(rec));
  return { saved: { id, marks: clean } };
}

// ===== Mark page (Hebrew RTL, phone + desktop) =====
export const MARK_PAGE = `<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>סימון רכבים חוסמים</title>
<style>
  * { box-sizing: border-box; margin: 0; }
  body { font-family: system-ui, -apple-system, sans-serif; background: #111; color: #eee;
         display: flex; flex-direction: column; align-items: center; min-height: 100vh; }
  header, #stage, #q, #btns, #nav, #msg, #kb { width: 100%; max-width: 720px; }
  header { padding: 10px 14px; font-size: 15px; background: #1c1c1e; position: sticky; top: 0; z-index: 5; }
  #bar { height: 5px; background: #333; margin-top: 8px; border-radius: 3px; overflow: hidden; }
  #fill { height: 100%; background: #ff9800; width: 0; transition: width .2s; }
  #stage { position: relative; width: fit-content; max-width: 100%; margin: 0 auto; touch-action: manipulation; }
  #photo { display: block; max-width: 100%; max-height: 62vh; margin: 0 auto; user-select: none; -webkit-user-select: none; cursor: crosshair; }
  .pin { position: absolute; width: 30px; height: 30px; margin: -15px 0 0 -15px; border-radius: 50%;
         background: rgba(255,152,0,.85); border: 2px solid #fff; pointer-events: none; }
  #q { padding: 10px 14px; font-size: 14px; color: #bbb; }
  #btns { display: flex; gap: 10px; padding: 10px 14px; }
  #save { flex: 2; font-size: 18px; padding: 16px 8px; border: 0; border-radius: 12px; background: #ef6c00; color: #fff; }
  #undo { flex: 1; font-size: 15px; padding: 16px 8px; border: 1px solid #444; border-radius: 12px; background: #1c1c1e; color: #eee; }
  #nav { display: flex; gap: 10px; padding: 0 14px 14px; }
  #nav button { flex: 1; font-size: 15px; padding: 12px; border-radius: 10px; border: 1px solid #444; background: #1c1c1e; color: #eee; }
  #msg { text-align: center; font-size: 13px; color: #7fc; min-height: 18px; padding-bottom: 10px; }
</style>
</head>
<body>
<header>
  <div>מעבר חצייה - סימון הרכבים החוסמים</div>
  <div id="bar"><div id="fill"></div></div>
  <div id="count" style="font-size:12px;color:#999;margin-top:4px"></div>
</header>
<div id="stage"><img id="photo" alt=""></div>
<div id="q">סמנו בנגיעה כל רכב שחונה על מעבר החצייה או חוסם אותו. נגיעה ליד סימון קיים מסירה אותו.</div>
<div id="btns">
  <button id="undo">ביטול סימון אחרון</button>
  <button id="save">שמור והבא</button>
</div>
<div id="nav">
  <button id="prev">הקודם</button>
  <button id="skip">דלג</button>
</div>
<div id="kb" style="text-align:center;font-size:12px;color:#666;padding-bottom:6px">מקלדת: Enter = שמור והבא, Backspace = ביטול סימון, חץ ימינה = הקודם, חץ שמאלה = דלג</div>
<div id="msg"></div>
<div id="keyform" style="display:none;position:fixed;inset:0;background:#111;padding:40px 24px;z-index:20">
  <div style="max-width:420px;margin:0 auto">
    <h1 style="font-size:20px;margin-bottom:10px">סימון רכבים</h1>
    <p style="font-size:14px;color:#bbb;margin-bottom:16px" id="keymsg">כדי להיכנס, הדביקו את המפתח שקיבלתם ולחצו כניסה.</p>
    <input id="keyin" type="text" inputmode="latin" autocapitalize="off" autocomplete="off" placeholder="המפתח" style="width:100%;font-size:17px;padding:14px;border-radius:10px;border:1px solid #444;background:#1c1c1e;color:#eee;margin-bottom:12px">
    <button id="keygo" style="width:100%;font-size:17px;padding:14px;border:0;border-radius:10px;background:#ef6c00;color:#fff">כניסה</button>
  </div>
</div>
<script>
let KEY = new URLSearchParams(location.search).get('key') || localStorage.getItem('label_key') || '';
if (KEY) localStorage.setItem('label_key', KEY);
const SET = new URLSearchParams(location.search).get('set') || 'xwalk';
const api = (p, o) => fetch(p + (p.includes('?') ? '&' : '?') + 'key=' + encodeURIComponent(KEY), o).then(r => r.json());
let items = [], idx = 0, marks = [];

function showKeyForm(msg) {
  document.getElementById('keyform').style.display = 'block';
  if (msg) document.getElementById('keymsg').textContent = msg;
  document.getElementById('keyin').focus();
}
document.getElementById('keygo').onclick = () => {
  const v = document.getElementById('keyin').value.trim();
  if (!v) return;
  KEY = v; localStorage.setItem('label_key', v);
  document.getElementById('keyform').style.display = 'none';
  boot();
};
document.getElementById('keyin').addEventListener('keydown', ev => {
  if (ev.key === 'Enter') document.getElementById('keygo').click();
});

async function boot() {
  if (!KEY) { showKeyForm(); return; }
  const d = await api('/api/mark-state?set=' + SET);
  if (d.error === 'unauthorized') {
    localStorage.removeItem('label_key'); KEY = '';
    showKeyForm('המפתח לא נכון. הדביקו שוב את המפתח מההודעה ולחצו כניסה.');
    return;
  }
  if (d.error) { document.getElementById('msg').textContent = 'שגיאה: ' + d.error; return; }
  items = d.items;
  if (!items.length) { document.getElementById('q').textContent = 'אין תמונות שמחכות לסימון.'; return; }
  idx = items.findIndex(it => !it.marks.length);
  if (idx < 0) idx = 0;
  show();
}
function show() {
  const it = items[idx]; if (!it) return;
  const img = document.getElementById('photo');
  img.src = it.url || (it.served_url + '?key=' + encodeURIComponent(KEY));
  marks = it.marks.slice();
  drawPins();
  const done = items.filter(x => x.marks.length).length;
  document.getElementById('fill').style.width = (100 * done / items.length) + '%';
  document.getElementById('count').textContent = done + ' / ' + items.length + ' סומנו';
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
async function save(next) {
  const it = items[idx];
  const r = await api('/api/mark', { method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ set: SET, id: it.id, marks }) });
  if (r.saved) {
    it.marks = r.saved.marks;
    document.getElementById('msg').textContent = 'נשמר';
    if (next) {
      const nxt = items.findIndex((x, i) => i > idx && !x.marks.length);
      idx = nxt >= 0 ? nxt : items.findIndex(x => !x.marks.length);
      if (idx < 0) { idx = items.length - 1; document.getElementById('msg').textContent = 'סיימת את כל הסימון!'; }
    }
    show();
  } else document.getElementById('msg').textContent = 'שגיאה: ' + (r.error || '?');
}
document.getElementById('save').onclick = () => save(true);
document.getElementById('undo').onclick = () => { marks.pop(); drawPins(); };
document.getElementById('prev').onclick = () => { if (idx > 0) { idx--; show(); } };
document.getElementById('skip').onclick = () => { if (idx < items.length - 1) { idx++; show(); } };
document.addEventListener('keydown', ev => {
  if (document.getElementById('keyform').style.display === 'block') return;
  if (ev.target && ev.target.tagName === 'INPUT') return;
  if (ev.key === 'Enter') save(true);
  else if (ev.key === 'Backspace') { ev.preventDefault(); marks.pop(); drawPins(); }
  else if (ev.key === 'ArrowRight') document.getElementById('prev').click();
  else if (ev.key === 'ArrowLeft') document.getElementById('skip').click();
});
boot();
</script>
</body>
</html>`;
