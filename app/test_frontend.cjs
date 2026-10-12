// Code-only DOM checks with mocked API responses. No browser or network access.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {JSDOM}=require(process.env.MRP_DOM_MODULES||'jsdom');
const fixture=JSON.parse(fs.readFileSync(process.argv[2]||path.join(__dirname,'tests/fixtures/state.json'),'utf8'));
const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'static/index.html'),'utf8'),{url:'https://unit.test/',runScripts:'outside-only'});
const w=dom.window;
const errors=[];
w.addEventListener('error',e=>errors.push(e.error));
w.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
w.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');this.dispatchEvent(new w.Event('close'));};
w.print=()=>{};
let posted=[];
let sessionCsrf='test-csrf', restoreFailure=false;
w.fetch=async(url,opts={})=>{
 let body;
 if(url==='/api/session')body={csrf:sessionCsrf,user:fixture.user};
 else if(url==='/api/state')body=structuredClone(fixture);
 else if(url==='/api/logout'){sessionCsrf='new-session-csrf';body={ok:true};}
 else if(url==='/api/login'){
  if(opts.headers['X-CSRF-Token']!==sessionCsrf)return {ok:false,status:403,json:async()=>({error:'Stale CSRF'})};
  body={csrf:sessionCsrf,user:fixture.user};posted.push({url});
 }
 else if(url==='/api/restore-test'){
  if(restoreFailure)return {ok:false,status:409,json:async()=>({error:'Backup verification failed'})};
  body={result:{tables:17,views:4,routines:16,triggers:19,data_matched:true},message:'OK'};
 }
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
 check([...query('#type-filter').options].map(x=>x.value).join(',')===',NGUYEN_LIEU,THANH_PHAM','All inventory types available');
 query('#search').value='';query('#type-filter').value='NGUYEN_LIEU';query('#type-filter').dispatchEvent(new w.Event('change',{bubbles:true}));
 check([...query('#content tbody').rows].filter(r=>!r.hidden).every(r=>r.dataset.type==='NGUYEN_LIEU'),'Raw material inventory filter');
 for(const kind of ['incoming','outgoing','bom','jobs','results']){
  w.documentEditor(kind);check(query('#document-form'),'Editor '+kind);check(query('#document-form .primary[type="submit"]'),'Save button '+kind);
  check(!/demo/i.test(query('#editor').textContent),'No sample branding in editor '+kind);
  if(['incoming','outgoing','bom'].includes(kind)){check(query('.line-grid'),'First detail row '+kind);click('[data-add-line]');check(query('#lines').children.length===2,'Add detail '+kind);click('[data-remove-line]');check(query('#lines').children.length===1,'Remove detail '+kind);}
  query('#editor').close();
 }
 w.documentEditor('incoming');
 for(const [key,value] of Object.entries({MaNCC:'1',NgayChungTu:'2026-10-10'}))query(`[name="${key}"]`).value=value;
 for(const [key,value] of Object.entries({MaSP:'1',MaViTri:'1',SoLuongNhan:'10',SoLuongLoi:'0',DonGiaNhap:'1800000'}))query(`.line-grid [name="${key}"]`).value=value;
 query('.line-grid [name="KetQuaKiemTra"]').value='Đã kiểm nhận';
 query('#document-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await tick();
 const saved=posted.find(x=>x.url==='/api/documents/incoming');check(saved?.body.lines.length===1,'Receipt save payload');check(saved.body.MaNCC==='1'&&!('MaNVLap' in saved.body),'Creator not sent by UI');
 check(saved.body.lines[0].KetQuaKiemTra==='Đã kiểm nhận','Inspection note included in save payload');
 vm.runInContext("S.user.VaiTro='ADMIN'",dom.getInternalVMContext());
 for(const kind of ['products','categories','suppliers','locations','employees']){w.catalogEditor(kind);check(query('#catalog-form'),'Catalog '+kind);query('#editor').close();}
 w.accountEditor();check(query('#account-form [name="password"]').required,'New account password required');query('#editor').close();
 await nav('catalog');click('[data-catalog-tab="products"]');check(query('#category-filter'),'Advanced catalog filters');
 const search=value=>{query('#search').value=value;query('#search').dispatchEvent(new w.Event('input',{bubbles:true}));};
 const visibleRows=()=>[...query('#content tbody').rows].filter(r=>!r.hidden);
 for(const kind of ['products','suppliers']){
  click(`[data-catalog-tab="${kind}"]`);
  for(const value of ['sửa','XÓA','không có dữ liệu này']){search(value);check(visibleRows().length===0,kind+' search does not match action labels: '+value);}
  search('');check(visibleRows().length===fixture[kind].length,kind+' empty search restores all rows');
 }
 click('[data-catalog-tab="products"]');search('CPU-001');check(visibleRows().length===1,'Catalog SKU search');
 query('#type-filter').value='THANH_PHAM';query('#type-filter').dispatchEvent(new w.Event('change',{bubbles:true}));
 check(visibleRows().length===0,'Catalog keyword and type filter combine');
 query('#type-filter').value='NGUYEN_LIEU';query('#type-filter').dispatchEvent(new w.Event('change',{bubbles:true}));
 check(visibleRows().length===1,'Matching type keeps SKU result');
 query('#category-filter').value=String(fixture.products.find(p=>p.SKU==='CPU-001').MaLoai);query('#category-filter').dispatchEvent(new w.Event('change',{bubbles:true}));
 check(visibleRows().length===1,'Catalog keyword and category filter combine');
 query('#state-filter').value='HOAT_DONG';query('#state-filter').dispatchEvent(new w.Event('change',{bubbles:true}));
 check(visibleRows().length===1,'Catalog keyword and state filter combine');
 click('#content th [data-sort="0"]');check(visibleRows().length===1&&visibleRows()[0].textContent.includes('CPU-001'),'Sort preserves filtered result');
 const productName=fixture.products[0].TenSP,supplierName=fixture.suppliers[0].TenNCC;
 fixture.products[0].TenSP='Bộ sửa máy tính';fixture.suppliers[0].TenNCC='Dịch vụ Xóa dữ liệu';await w.reload();
 click('[data-catalog-tab="products"]');search('SỬA');check(visibleRows().length===1&&visibleRows()[0].textContent.includes('Bộ sửa máy tính'),'Real product name containing an action word still matches');
 click('[data-catalog-tab="suppliers"]');search('xóa');check(visibleRows().length===1&&visibleRows()[0].textContent.includes('Dịch vụ Xóa dữ liệu'),'Real supplier name containing an action word still matches');
 fixture.products[0].TenSP=productName;fixture.suppliers[0].TenNCC=supplierName;await w.reload();
 await nav('accounts');search('mật khẩu');check(visibleRows().length===0,'Account search excludes password action labels');
 vm.runInContext("S.user.VaiTro='QUAN_LY_KHO'",dom.getInternalVMContext());await nav('incoming');search('Chi tiết');check(visibleRows().length===0,'Document search excludes action labels');
 vm.runInContext("S.user.VaiTro='ADMIN'",dom.getInternalVMContext());
 await nav('backup');check(query('#backup-create'),'Backup action rendered');
 check(!/demo/i.test(query('#workspace').textContent),'Backup copy is neutral');
 vm.runInContext("S.backup='mrp_test.sql';render()",dom.getInternalVMContext());
 restoreFailure=true;click('#restore-test');await tick();query('#confirm-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await tick();
 check(!query('#restore-test').disabled&&!query('#restore-progress'),'Failed restore clears progress and allows retry');
 check(query('#toast').textContent==='Backup verification failed','Failed restore shows error');
 restoreFailure=false;click('#restore-test');await tick();query('#confirm-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await tick();
 check(query('.backup-result')?.textContent.includes('Dữ liệu khớp với bản sao lưu'),'Successful restore retry renders verification');
 await nav('accounts');check(!/demo/i.test(query('#workspace').textContent),'Account names are neutral');
 vm.runInContext("S.user.VaiTro='NHAN_VIEN'",dom.getInternalVMContext());await nav('overview');check(!query('[data-nav="report"]')&&!query('[data-nav="accounts"]'),'Employee navigation restricted');
 check(errors.length===0,'No JavaScript errors: '+errors.join(';'));
 click('#logout');await tick();check(!query('#login').hidden,'Logout shows login');
 query('#login-form [name="username"]').value='quanly';query('#login-form [name="password"]').value='Demo@12345';
 query('#login-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await tick();
 check(!query('#workspace').hidden&&posted.some(x=>x.url==='/api/login'),'Relogin obtains new CSRF without reloading');
 console.log(checks+' code-only frontend assertions passed.');
 dom.window.close();
})().catch(e=>{console.error(e);process.exitCode=1;dom.window.close();});
