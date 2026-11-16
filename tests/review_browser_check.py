"""Optional Chromium UI checks; install playwright separately. Synthetic data only."""
import importlib.util,json,sys,threading,tempfile
from pathlib import Path
from PIL import Image,ImageDraw
from playwright.sync_api import sync_playwright, expect
repo=Path(__file__).resolve().parents[1]
output=Path(tempfile.mkdtemp(prefix='review-browser-'))
print('Synthetic screenshots/download saved outside repo:',output)
spec=importlib.util.spec_from_file_location('review',repo/'scripts/review_server.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as t:
    root=Path(t)/'data';root.mkdir();rows=[]
    for i in range(4):
        image=Image.new('RGB',(1000,650),'#dce3dc');d=ImageDraw.Draw(image)
        d.rectangle((0,350,1000,650),fill='#b2b4b5');d.rectangle((0,300,1000,350),fill='#f4efec')
        d.rectangle((110,180,850,570),fill=['#477b88','#aa6655','#668855','#775588'][i]);d.rectangle((200,210,760,360),fill='#bcd3db')
        d.ellipse((180,510,280,610),fill='#251f21');d.ellipse((680,510,780,610),fill='#251f21')
        d.rectangle((380,430,580,490),fill='#f7d34e');d.text((410,450),'DEMO',fill='black');d.text((30,25),'SYNTHETIC IMAGE - NOT A REAL REPORT',fill='black')
        file=root/f'synthetic-{i}.png';image.save(file)
        rows.append(dict(image=file.name,image_sha256=m.digest(file),group_id=f'group-{i}',candidate_labels=[],label_state={k:'unknown' for k in m.LABELS},review_status='needs_visual_and_event_review',city_label='סיווג סינתטי בלבד',plate_text_candidate='NEVER-SURFACE'))
    candidates=Path(t)/'candidates.json';candidates.write_text(json.dumps(rows))
    server=m.ThreadingHTTPServer(('127.0.0.1',0),m.Handler);server.token='synthetic-token';server.store=m.ReviewStore(root,candidates,Path(t)/'work')
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
      with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox'])
        for width in [320,390,1024]:
          context=browser.new_context(viewport={'width':width,'height':844},device_scale_factor=1,is_mobile=width<700,has_touch=width<700)
          page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
          page.goto(f'http://127.0.0.1:{server.server_port}/#synthetic-token');page.locator('#photo').wait_for(state='visible');expect(page.locator('#photo')).to_have_attribute('width','1000')
          assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),width
          assert 'NEVER-SURFACE' not in page.locator('body').inner_text()
          page.screenshot(path=str(output / f'review-{width}-initial.png'),full_page=True)
          page.locator('#targetMode').click();canvas=page.locator('#photo');canvas.scroll_into_view_if_needed();box=canvas.bounding_box()
          (canvas.tap if width<700 else canvas.click)(position={'x':box['width']*.1,'y':box['height']*.2});(canvas.tap if width<700 else canvas.click)(position={'x':box['width']*.9,'y':box['height']*.98})
          page.locator('#plateMode').click();box=canvas.bounding_box()
          (canvas.tap if width<700 else canvas.click)(position={'x':box['width']*.38,'y':box['height']*.66});(canvas.tap if width<700 else canvas.click)(position={'x':box['width']*.58,'y':box['height']*.76})
          for k in m.LABELS:page.locator('#label-'+k).select_option('present')
          page.locator('#event').check();page.locator('#visual').check();page.locator('#reviewer').fill('Synthetic human');page.locator('#split').select_option('train');page.locator('#plateStatus').select_option('readable');page.locator('#plateText').fill('DEMO')
          page.locator('#approve').click();expect(page.locator('#message')).to_contain_text('אושרה ונשמרה')
          page.locator('#photo').scroll_into_view_if_needed();page.screenshot(path=str(output / f'review-{width}-boxes.png'))
          page.reload();expect(page.locator('#photo')).to_have_attribute('width','1000');assert page.locator('#reviewer').input_value()=='Synthetic human'
          page.locator('#plateText').fill('DEMO-EDIT');page.locator('#draft').click();expect(page.locator('#message')).to_contain_text('הטיוטה נשמרה')
          # Regression: after a valid box, an incomplete/non-finite edit must
          # clear the model box, never approve stale coordinates. Save must parse
          # controls itself, even if no input/change event has fired.
          for key,title in [('target_vehicle_box','רכב'),('plate_box','לוחית')]:
            field=page.get_by_label(title+' x2',exact=True)
            valid=field.input_value()
            for invalid in ['', '1e999', '-']:
              field.evaluate('(input,value)=>{input.value=value;}',invalid)
              page.locator('#approve').click();expect(page.locator('#message')).to_contain_text('לא נשמר')
              page.locator('#draft').click();expect(page.locator('#message')).to_contain_text('הטיוטה נשמרה')
              stored=server.store.state['reviews']['synthetic-0.png']
              assert stored[key] is None, (key,invalid,stored[key])
              assert stored['decision']=='draft'
              page.reload();expect(page.locator('#photo')).to_have_attribute('width','1000')
              assert field.input_value()==''
              # Restore all four controls without blur or synthetic change events.
              box_values=[100,130,900,640] if key=='target_vehicle_box' else [380,430,580,490]
              for coordinate,value in zip(['x1','y1','x2','y2'],box_values):
                page.get_by_label(title+' '+coordinate,exact=True).evaluate('(input,value)=>{input.value=String(value);}',value)
              page.locator('#draft').click();expect(page.locator('#message')).to_contain_text('הטיוטה נשמרה')
              assert server.store.state['reviews']['synthetic-0.png'][key]==box_values
          print('UI PASS',width,'clear/non-finite/partial box edits block approval and save null, no stale box')
          assert not errors,errors
          print('UI PASS',width,'two-tap boxes, explicit approve, reload, edit/draft, no horizontal overflow, no private OCR candidate')
          context.close()
        context=browser.new_context(viewport={'width':390,'height':844},has_touch=True,is_mobile=True,accept_downloads=True)
        page=context.new_page();page.goto(f'http://127.0.0.1:{server.server_port}/#synthetic-token');expect(page.locator('#photo')).to_have_attribute('width','1000')
        for i in range(4):
          page.locator('#jump').select_option(str(i));expect(page.locator('#identity')).to_have_text(f'synthetic-{i}.png')
          for label,value in [('רכב x1','100'),('רכב y1','130'),('רכב x2','900'),('רכב y2','640'),('לוחית x1','380'),('לוחית y1','430'),('לוחית x2','580'),('לוחית y2','490')]:
            page.get_by_label(label,exact=True).fill(value);page.get_by_label(label,exact=True).press('Tab')
          for k in m.LABELS:page.locator('#label-'+k).select_option('present' if i==0 else 'absent')
          page.locator('#event').check();page.locator('#visual').check();page.locator('#reviewer').fill('Synthetic human');page.locator('#split').select_option(['train','train','val','test'][i]);page.locator('#plateStatus').select_option('readable');page.locator('#plateText').fill('DEMO');page.locator('#approve').click();expect(page.locator('#message')).to_contain_text('אושרה ונשמרה')
        with page.expect_download() as info:page.locator('#export').click()
        download=info.value;download.save_as(str(output / 'synthetic-reviewed-output.json'))
        exported=json.loads(Path(str(output / 'synthetic-reviewed-output.json')).read_text());assert len(exported)==4;assert all(r['review_status']=='approved_visual_event_and_target' for r in exported);assert 'NEVER-SURFACE' not in json.dumps(exported)
        print('UI PASS end-to-end four reviews -> downloaded gate-compatible manifest, no private OCR candidate')
        context.close();browser.close()
    finally:
      server.shutdown();server.server_close();thread.join()
