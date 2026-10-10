// Code-only DOM checks with mocked API responses. No browser or network access.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {JSDOM}=require(process.env.MRP_DOM_MODULES||'jsdom');
const fixture=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'static/index.html'),'utf8'),{url:'https://unit.test/',runScripts:'outside-only'});
const w=dom.window;
const errors=[];
w.addEventListener('error',e=>errors.push(e.error));
w.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
w.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');this.dispatchEvent(new w.Event('close'));};
w.print=()=>{};
let posted=[];
w.fetch=async(url,opts={})=>{
 let body;
 if(url==='/api/session')body={csrf:'test-csrf',user:fixture.user};
 else if(url==='/api/state')body=structuredClone(fixture);
 else {posted.push({url,method:opts.method,body:opts.body&&JSON.parse(opts.body)});body={id:99,message:'OK'};}
 return {ok:true,status:200,json:async()=>body};
};
vm.runInContext(fs.readFileSync(path.join(__dirname,'static/app.js'),'utf8'),dom.getInternalVMContext());
const tick=async()=>{await new Promise(r=>setImmediate(r));await new Promise(r=>setImmediate(r));};
const query=s=>w.document.querySelector(s);
const click=s=>{assert.ok(query(s),s);query(s).click();};
let checks=0;
const check=(v,msg)=>{assert.ok(v,msg);checks++;};
async function nav(page){w.location.hash=page;w.dispatchEvent(new w.HashChangeEvent('hashchange'));await tick();}
(async()=>{
 await tick();check(!query('#workspace').hidden,'Authenticated shell renders');
 check(!query('#login-form [name="username"]').value&&!query('#login-form [name="password"]').value,'Login fields start empty');
 check(!/demo|Mọi chuyển động|Một kho rõ ràng/i.test(query('#login').textContent),'Login copy is neutral');
 for(const page of ['overview','inventory','incoming','outgoing','bom','jobs','results','report','ledger','catalog','guide']){
  await nav(page);check(query('#content h1'),'Page renders: '+page);
  check(!/demo/i.test(query('#workspace').textContent),'No sample branding on page: '+page);
 }
 w.detail('bom',1);check(!/demo/i.test(query('#editor').textContent),'Issued BOM detail has neutral label');query('#editor').close();
 w.detail('outgoing',2);check(!/demo/i.test(query('#editor').textContent),'Issued shipment detail has neutral label');query('#editor').close();
 await nav('inventory');query('#search').value='CPU-001';query('#search').dispatchEvent(new w.Event('input',{bubbles:true}));
 check([...query('#content tbody').rows].filter(r=>!r.hidden).length===1,'Inventory keyword filter');
 for(const kind of ['incoming','outgoing','bom','jobs','results']){
  w.documentEditor(kind);check(query('#document-form'),'Editor '+kind);check(query('#document-form .primary[type="submit"]'),'Save button '+kind);
  check(!/demo/i.test(query('#editor').textContent),'No sample branding in editor '+kind);
  if(['incoming','outgoing','bom'].includes(kind)){check(query('.line-grid'),'First detail row '+kind);click('[data-add-line]');check(query('#lines').children.length===2,'Add detail '+kind);click('[data-remove-line]');check(query('#lines').children.length===1,'Remove detail '+kind);}
  query('#editor').close();
 }
 w.documentEditor('incoming');
 for(const [key,value] of Object.entries({MaNCC:'1',NgayChungTu:'2026-10-10'}))query(`[name="${key}"]`).value=value;
 for(const [key,value] of Object.entries({MaSP:'1',MaViTri:'1',SoLuongNhan:'10',SoLuongLoi:'0',DonGiaNhap:'1800000'}))query(`.line-grid [name="${key}"]`).value=value;
 query('#document-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await tick();
 const saved=posted.find(x=>x.url==='/api/documents/incoming');check(saved?.body.lines.length===1,'Receipt save payload');check(saved.body.MaNCC==='1'&&!('MaNVLap' in saved.body),'Creator not sent by UI');
 vm.runInContext("S.user.VaiTro='ADMIN'",dom.getInternalVMContext());
 for(const kind of ['products','categories','suppliers','locations','employees']){w.catalogEditor(kind);check(query('#catalog-form'),'Catalog '+kind);query('#editor').close();}
 w.accountEditor();check(query('#account-form [name="password"]').required,'New account password required');query('#editor').close();
 await nav('catalog');click('[data-catalog-tab="products"]');check(query('#category-filter'),'Advanced catalog filters');
 await nav('backup');check(query('#backup-create'),'Backup action rendered');
 check(!/demo/i.test(query('#workspace').textContent),'Backup copy is neutral');
 await nav('accounts');check(!/demo/i.test(query('#workspace').textContent),'Account names are neutral');
 vm.runInContext("S.user.VaiTro='NHAN_VIEN'",dom.getInternalVMContext());await nav('overview');check(!query('[data-nav="report"]')&&!query('[data-nav="accounts"]'),'Employee navigation restricted');
 check(errors.length===0,'No JavaScript errors: '+errors.join(';'));
 console.log(checks+' code-only frontend assertions passed.');
 dom.window.close();
})().catch(e=>{console.error(e);process.exitCode=1;dom.window.close();});
