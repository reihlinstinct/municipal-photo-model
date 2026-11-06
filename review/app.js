'use strict';
const $ = id => document.getElementById(id);
let token = location.hash.slice(1) || sessionStorage.getItem('review-token') || '';
if (token) sessionStorage.setItem('review-token', token);
history.replaceState(null, '', location.pathname);
let data, index = 0, review, picture, blobURL, mode = null, corner = null, dirty = false, busy = false;
const names = {sidewalk_parking:'חניה על מדרכה',red_white:'אדום־לבן',crosswalk_obstruction:'הפרעה למעבר חציה'};
const errors = {"Unauthorized": "הכתובת אינה מורשית. יש לפתוח את כתובת ההפעלה המלאה.", "Stale page. Reload before saving; no data overwritten": "העמוד אינו מעודכן. יש לטעון מחדש לפני שמירה; שום מידע לא נדרס.", "Invalid pixel xyxy box": "תיבת הסימון אינה תקינה. יש לבדוק את ארבע הקואורדינטות ואת גבולות התמונה.", "Human reviewer, visual and event checks required": "צריך שם סוקר/ת ואישור בדיקה של התמונה ושל אירוע הדיווח.", "Confirm municipality category from source evidence": "יש לאשר את סיווג העירייה מול מקור הדיווח.", "Target vehicle box and split required": "צריך לסמן את רכב היעד ולבחור חלוקת קבוצה.", "Resolve all labels, including negatives": "צריך לבחור קיים או לא קיים לכל סוג הפרעה.", "Review plate or mark unreadable/not visible": "צריך לבדוק את הלוחית ולציין אם היא קריאה, לא קריאה או לא נראית.", "Visible plate needs a box": "לוחית נראית דורשת תיבת סימון.", "Readable plate needs text": "יש להזין את הטקסט שנראה על הלוחית הקריאה.", "Do not invent text for an unreadable or invisible plate": "כשהלוחית אינה קריאה או לא נראית, יש להשאיר את הטקסט ריק.", "Plate box must be inside the target vehicle box": "תיבת הלוחית צריכה להיות בתוך תיבת רכב היעד.", "Invisible plate cannot have a box": "כשהלוחית לא נראית, יש למחוק את תיבת הלוחית.", "Exclusion reason required": "יש לציין סיבה להוצאה מהאימון.", "Every image must be approved or explicitly excluded before export": "לפני ייצוא צריך לאשר או להוציא מהאימון כל תמונה.", "Image changed since review started": "קובץ תמונה השתנה מאז תחילת הסקירה. אין לייצא לפני בירור.", "Group leakage: assign the same split to every image in a group": "קבוצת תמונות חולקה לכמה חלקים. יש לבחור אותה חלוקה לכל תמונות הקבוצה.", "Non-empty train, val and test groups required": "צריך קבוצות נפרדות ולא ריקות לאימון, לכיול ולבדיקה.", "Training requires positive and negative examples for each class": "באימון צריכות להיות דוגמאות חיוביות ושליליות לכל סוג הפרעה.", "Source group data is missing; repair candidates before approval": "חסרים נתוני קבוצה במקור. יש לתקן את נתוני המקור לפני אישור.", "Invalid label state": "ערך סיווג אינו תקין.", "Invalid plate status": "מצב הלוחית אינו תקין.", "Invalid text": "אחד משדות הטקסט אינו תקין או ארוך מדי.", "Unexpected review fields": "הסקירה מכילה שדות לא צפויים. יש לטעון מחדש."};
function message(text, error=false) { $('message').textContent=text; $('message').className=error?'error':''; }
async function request(path, body) {
  const response = await fetch(path,{method:body===undefined?'GET':'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
  if (!response.ok) { let detail; try { detail=(await response.json()).error; } catch (_) {} throw new Error(errors[detail] || detail || 'שגיאה בחיבור המקומי'); }
  return response;
}
function defaults(row) {
  return {label_state:Object.fromEntries(data.labels.map(k=>[k,'unknown'])),target_vehicle_box:null,plate_box:null,plate_text:'',municipal_category:typeof row.municipal_category==='string'?row.municipal_category:(typeof row.city_label==='string'?row.city_label:''),plate_status:'unknown',split:'unassigned',reviewer:'',event_checked:false,visual_checked:false,notes:'',exclusion_reason:''};
}
function parseBox(numbers) {
  const values=[...numbers.querySelectorAll('input')].map(input=>{
    const text=input.value.trim();
    return text!=='' && input.validity.valid && Number.isFinite(input.valueAsNumber)?input.valueAsNumber:null;
  });
  return values.length===4 && values.every(value=>value!==null)?values:null;
}
function readForm() {
  for(const key of ['target_vehicle_box','plate_box']) {
    review[key]=parseBox(document.querySelector(`[data-box="${key}"]`));
  }
  review.municipal_category=$('municipal').value; review.plate_text=$('plateText').value;
  review.plate_status=$('plateStatus').value; review.split=$('split').value; review.reviewer=$('reviewer').value;
  review.event_checked=$('event').checked; review.visual_checked=$('visual').checked;
  review.notes=$('notes').value; review.exclusion_reason=$('reason').value;
  for(const k of data.labels) review.label_state[k]=$('label-'+k).value;
  const outgoing=structuredClone(review);delete outgoing.decision;delete outgoing.reviewed_at;return outgoing;
}
function coordinates() {
  $('coordinates').replaceChildren();
  for(const [key,title] of [['target_vehicle_box','רכב'],['plate_box','לוחית']]) {
    const section=document.createElement('div'); section.className='boxrow';
    const heading=document.createElement('strong'); heading.textContent=title+(review[key]?'':' · ללא תיבה'); section.append(heading);
    const numbers=document.createElement('div'); numbers.className='numbers'; numbers.dataset.box=key;
    ['x1','y1','x2','y2'].forEach((coordinate,j)=>{
      const label=document.createElement('label'); label.textContent=coordinate;
      const input=document.createElement('input'); input.type='number'; input.min='0'; input.step='1'; input.value=review[key]?.[j]??'';
      input.setAttribute('aria-label',title+' '+coordinate);
      input.addEventListener('input',()=>{
        review[key]=parseBox(numbers);
        dirty=true; draw();
      }); label.append(input); numbers.append(label);
    }); section.append(numbers);
    const clear=document.createElement('button'); clear.textContent='מחיקת תיבת '+title;
    clear.onclick=()=>{review[key]=null;dirty=true;coordinates();draw();}; section.append(clear); $('coordinates').append(section);
  }
}
function draw() {
  if(!picture) return;
  const c=$('photo'), ctx=c.getContext('2d'); c.width=picture.naturalWidth; c.height=picture.naturalHeight;
  ctx.drawImage(picture,0,0);
  for(const [key,color] of [['target_vehicle_box','#007d68'],['plate_box','#a84c00']]) {
    const b=review[key]; if(!b) continue;
    ctx.strokeStyle=color; ctx.lineWidth=Math.max(3,c.width/180); ctx.strokeRect(b[0],b[1],b[2]-b[0],b[3]-b[1]);
  }
  if(corner) {ctx.fillStyle='#ed313e';ctx.beginPath();ctx.arc(corner[0],corner[1],Math.max(5,c.width/90),0,2*Math.PI);ctx.fill();}
}
function setMode(next) {
  mode=next;corner=null;
  $('targetMode').setAttribute('aria-pressed',String(mode==='target_vehicle_box'));
  $('plateMode').setAttribute('aria-pressed',String(mode==='plate_box'));
  $('drawHelp').textContent=mode?'נגיעה ראשונה בפינה אחת, נגיעה שנייה בפינה הנגדית. להגדלה משתמשים במחוון לפני הסימון.':'לסימון תיבה: בוחרים רכב או לוחית ואז נוגעים בשתי פינות נגדיות.';
  draw();
}
async function show(next) {
  if (busy || (dirty && !confirm('יש שינויים שלא נשמרו. לעבור בלי לשמור?'))) return;
  busy=true;
  try {
    const response=await request('/api/image/'+next), blob=await response.blob();
    const newURL=URL.createObjectURL(blob); const image=new Image();
    try {image.src=newURL; await image.decode();} catch(error) {URL.revokeObjectURL(newURL);throw error;}
    if(blobURL) URL.revokeObjectURL(blobURL);blobURL=newURL;picture=image;index=next;
    const row=data.rows[index]; review=structuredClone(data.state.reviews[row.image]||defaults(row)); dirty=false;
    $('position').textContent=`${index+1} / ${data.rows.length}`; $('identity').textContent=row.image;
    $('source').textContent=JSON.stringify(row,null,2); $('group').value=row.group_id;
    for(const [id,key] of [['municipal','municipal_category'],['plateText','plate_text'],['plateStatus','plate_status'],['split','split'],['reviewer','reviewer'],['notes','notes'],['reason','exclusion_reason']]) $(id).value=review[key]||'';
    $('event').checked=!!review.event_checked; $('visual').checked=!!review.visual_checked;
    $('labels').replaceChildren();
    for(const k of data.labels) {
      const label=document.createElement('label'); label.className='labelrow'; label.textContent=names[k];
      const select=document.createElement('select'); select.id='label-'+k;
      for(const [value,title] of [['unknown','לא ידוע / לא נבדק'],['present','קיים'],['absent','לא קיים']]) {const option=new Option(title,value);select.add(option);}
      select.value=review.label_state[k]; select.onchange=()=>{dirty=true;};label.append(select);$('labels').append(label);
    }
    $('jump').value=String(index);$('prev').disabled=index===0;$('next').disabled=index===data.rows.length-1;
    $('zoom').value='1';$('photo').style.width='100%'; coordinates();setMode(null);
    const counts=Object.values(data.state.reviews).reduce((a,r)=>{a[r.decision]=(a[r.decision]||0)+1;return a;},{});
    $('progress').textContent=`אושרו: ${counts.approved||0} · הוצאו: ${counts.excluded||0} · טיוטות: ${counts.draft||0}`;
    message(review.decision==='approved'?'התמונה אושרה. שינוי דורש שמירה מחדש.':review.decision==='excluded'?'התמונה הוצאה מהאימון.':'התמונה ממתינה לסקירה.');
  } catch(error) {message(error.message,true);} finally {busy=false;}
}
async function save(decision) {
  if(busy) return;busy=true;
  try {
    data.state=await (await request('/api/save',{revision:data.state.revision,index,review:readForm(),decision})).json();dirty=false;
    message(decision==='approved'?'התמונה אושרה ונשמרה במחשב.':decision==='excluded'?'התמונה הוצאה מהאימון ונשמרה הסיבה.':'הטיוטה נשמרה במחשב.');
    const counts=Object.values(data.state.reviews).reduce((a,r)=>{a[r.decision]=(a[r.decision]||0)+1;return a;},{});
    $('progress').textContent=`אושרו: ${counts.approved||0} · הוצאו: ${counts.excluded||0} · טיוטות: ${counts.draft||0}`;
  } catch(error) {message('לא נשמר: '+error.message,true);} finally {busy=false;}
}
$('photo').addEventListener('click',event=>{
  if(!mode||!picture) return;
  const bounds=$('photo').getBoundingClientRect();
  const point=[Math.round((event.clientX-bounds.left)/bounds.width*picture.naturalWidth),Math.round((event.clientY-bounds.top)/bounds.height*picture.naturalHeight)];
  if(!corner) {corner=point;draw();return;}
  if(point[0]===corner[0]||point[1]===corner[1]) {message('צריך שתי פינות שיוצרות שטח, לא קו.',true);return;}
  review[mode]=[Math.min(point[0],corner[0]),Math.min(point[1],corner[1]),Math.max(point[0],corner[0]),Math.max(point[1],corner[1])];
  dirty=true;coordinates();setMode(null);
});
$('targetMode').onclick=()=>setMode('target_vehicle_box');$('plateMode').onclick=()=>setMode('plate_box');$('cancelMode').onclick=()=>setMode(null);
$('zoom').oninput=()=>{$('photo').style.width=(Number($('zoom').value)*100)+'%';};
$('prev').onclick=()=>show(index-1);$('next').onclick=()=>show(index+1);$('jump').onchange=()=>{const next=Number($('jump').value);$('jump').value=String(index);show(next);};
$('draft').onclick=()=>save('draft');$('approve').onclick=()=>save('approved');$('exclude').onclick=()=>save('excluded');
$('app').addEventListener('input',event=>{if(!['zoom','jump'].includes(event.target.id)) dirty=true;});
window.addEventListener('beforeunload',event=>{if(dirty) {event.preventDefault();event.returnValue='';}});
$('export').onclick=async()=>{
  if(busy) return;
  if(dirty) {message('יש שינויים לא שמורים. יש לשמור לפני הייצוא.',true);return;}
  busy=true;
  try {
    const response=await request('/api/export',{}), blob=await response.blob();const url=URL.createObjectURL(blob);
    const a=document.createElement('a');a.href=url;a.download='manifest.reviewed.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);
    message('הייצוא נשמר גם בתיקיית העבודה במחשב. לא הועלה דבר לקאגל.');
  } catch(error) {message('הייצוא חסום: '+error.message,true);}finally {busy=false;}
};
(async()=>{
  try {
    data=await (await request('/api/data')).json();
    for(let i=0;i<data.rows.length;i++) $('jump').add(new Option(`${i+1} · ${data.rows[i].image}`,String(i)));
    $('app').hidden=false;await show(0);
  } catch(error) {message('לא ניתן לפתוח: '+error.message+'. יש לפתוח את הכתובת הפרטית שהודפסה עם הפעלת הכלי.',true);}
})();
