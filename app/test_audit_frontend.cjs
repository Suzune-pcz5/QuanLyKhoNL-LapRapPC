// Form boundaries and report races, including dates outside the current quarter.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {JSDOM}=require(process.env.MRP_DOM_MODULES||'jsdom');
const fixture=JSON.parse(fs.readFileSync(process.argv[2]||path.join(__dirname,'tests/fixtures/state.json'),'utf8'));
fixture.user.VaiTro='ADMIN';
const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'static/index.html'),'utf8'),{url:'https://unit.test/',runScripts:'outside-only'}),w=dom.window,ctx=dom.getInternalVMContext();
const $=s=>w.document.querySelector(s),tick=async()=>{await new Promise(setImmediate);await new Promise(setImmediate);};
const errors=[],requests=[],savedReceipts=[];let waitReport=null,checks=0,shortageRequests=0,freshState=null;
const check=(value,message)=>{assert.ok(value,message);checks++;};
w.addEventListener('error',ev=>errors.push(String(ev.error)));
w.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
w.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');this.dispatchEvent(new w.Event('close'));};
w.print=()=>{};
w.fetch=async (url,options)=>{
 let body;
 if(url==='/api/session')body={csrf:'test',user:fixture.user};
 else if(url==='/api/state')body=structuredClone(freshState||fixture);
 else if(url.startsWith('/api/report?')){const query=new URLSearchParams(url.split('?')[1]);requests.push(query.toString());if(waitReport)await waitReport;body={start:query.get('from'),end:query.get('to'),rows:[]};}
 else if(url==='/api/jobs/99/shortage-report'){
  assert.equal(options.method,'POST');assert.deepEqual(JSON.parse(options.body),{});shortageRequests++;
  body={report:{ThoiDiem:'2026-11-19 10:00:00',lines:[{SKU:'CPU-001',SoLuongThieu:4}]},message:'Đã báo thiếu linh kiện cho quản lý kho.'};
 }
 else if(url==='/api/documents/incoming'){
  assert.equal(options.method,'POST');savedReceipts.push(JSON.parse(options.body));
  body={id:99,message:'Đã lưu nháp.'};
 }
 else throw Error('Unexpected API '+url);
 return {ok:true,status:200,json:async()=>body};
};
vm.runInContext(fs.readFileSync(path.join(__dirname,'static/app.js'),'utf8'),ctx);
const state=code=>vm.runInContext(code,ctx);
const change=(selector,value)=>{const input=$(selector);input.value=value;input.dispatchEvent(new w.Event('change',{bubbles:true}));};
async function nav(page){const changed=new Promise(resolve=>w.addEventListener('hashchange',resolve,{once:true}));w.location.hash='#'+page;await changed;await tick();}
(async()=>{
 await tick();
 w.documentEditor('incoming');
 check($('[name=GhiChu]').maxLength===255,'Receipt notes agree with DB/API limit');
 check($('[name=KetQuaKiemTra]').maxLength===255,'Inspection limit');
 check($('[name=SoLuongNhan]').min==='1','Positive receipt quantity');
 check($('[name=SoLuongLoi]').min==='0','Zero faulty quantity allowed');
 check($('[name=SoLuongNhan]').max==='2147483647','Integer upper bound');
 $('[name=SoLuongNhan]').value='0';check(!$('[name=SoLuongNhan]').checkValidity(),'Native validation rejects zero receipt');
 $('[name=NgayChungTu]').value='0001-01-01';check(!$('[name=NgayChungTu]').checkValidity(),'Native date range');
 $('#editor').close();
 for(const [kind,name,max] of [['products','SKU',50],['products','TenSP',200],['products','MoTa',500],['categories','MoTa',255],['suppliers','TenNCC',150],['suppliers','SoDienThoai',20],['employees','HoTen',100],['locations','MaViTriHienThi',50]]){
  w.catalogEditor(kind);check($(`[name=${name}]`).maxLength===max,`${kind}/${name} maximum`);$('#editor').close();
 }
 w.catalogEditor('products');check($('[name=DonViTinh]').value==='cái','Accented default unit');$('#editor').close();
 w.accountEditor();check($('#account-form [name=password]').minLength===8&&$('#account-form [name=password]').maxLength===255,'Password length range');$('#editor').close();
 w.documentEditor('bom');check($('[name=PhienBan]').min==='1'&&$('[name=DinhMuc]').min==='1','Positive BOM quantities');$('#editor').close();
 w.documentEditor('results');check($('[name=SoLuongDat]').min==='0'&&$('[name=SoLuongLoi]').min==='0','Partial results may individually be zero');$('#editor').close();
 state("S.user.VaiTro='QUAN_LY_KHO'");await nav('report');
 for(const [day,quarter,tomorrow] of [['2026-01-31',1,'2026-02-01'],['2026-04-01',2,'2026-04-02'],['2026-07-01',3,'2026-07-02'],['2026-12-31',4,'2027-01-01'],['2028-02-29',1,'2028-03-01']]){
  state(`S.data.now='${day} 12:00:00'`);w.render();
  check(Number($('#report-quarter').value)===quarter,'Quarter follows '+day);
  check($('#report-to').value===tomorrow,'Custom interval includes '+day);
 }
 change('#period','quarter');check(!$('#report-quarter').disabled&&$('#report-month').disabled,'Quarter activates only relevant inputs');
 await w.runReport();check(state('S.report')!==null,'Report is exportable after successful query');
 change('#report-type','NGUYEN_LIEU');check(state('S.report')===null,'Changing filter invalidates CSV/print query');
 check($('#report-results').textContent.includes('Bộ lọc đã thay đổi'),'Old results cleared with explanation');
 $('#csv-export').click();await tick();check($('#toast').textContent.includes('Xem báo cáo'),'CSV cannot silently use previous filters');
 let release;waitReport=new Promise(resolve=>release=resolve);const pending=w.runReport();
 change('#report-location','1');release();await pending;waitReport=null;
 check(state('S.report')===null,'Late response cannot restore obsolete report');
 await w.runReport();check(state("S.report.get('location')")==='1','New result has current filter');
 change('#period','custom');$('#report-year').value='';check($('#report-year').disabled&&$('#year-label').hidden,'Custom dates do not validate hidden year');
 check(!$('#report-from').disabled&&$('#report-from').required&&!$('#report-to').disabled,'Custom dates are enabled and required');
 waitReport=new Promise(resolve=>release=resolve);const navigation=w.runReport();await nav('overview');release();await navigation;waitReport=null;
 check(state('S.report')===null&&$('#content h1').textContent==='Tổng quan kho','Report response cannot overwrite another page');
 w.documentEditor('outgoing',null,{LoaiXuat:'THANH_PHAM'});$('[name=MaSP]').value='3';change('[name=LoaiXuat]','CAP_PHAT');
 check($('[name=MaSP]').value==='','Changing outgoing type clears incompatible lines');
 check([...$('[name=MaSP]').options].every(o=>!o.value||['1','2','4'].includes(o.value)),'Allocation only offers materials');
 $('#editor').close();
 state(`
  S.user.VaiTro='NHAN_VIEN'; S.user.MaNV=2;
  S.data.jobs.push({MaYC:99,MaNVNhan:2,MaBOM:1,SoLuongYeuCau:40,accepted:0,pending:0,
    TrangThai:'DA_GIAO',DaNhanViec:1,materials:[],needs:[
      {MaSPLinhKien:1,SKU:'CPU-001',SoLuongCan:40,SoLuongThieu:4}
    ]});
 `);
 await nav('jobs');$('[data-allocate="99"]').click();
 check(!$('#allocation-shortage').hidden&&!$('#report-shortage').hidden,'Shortage action is inside the allocation dialog');
 check($('#allocation-shortage').textContent.includes('CPU-001 thiếu'),'Shortage alert identifies the SKU');
 $('#report-shortage').click();await tick();
 check(shortageRequests===1&&$('#report-shortage').hidden,'Report sends once and hides the action');
 check($('#allocation-shortage').textContent.includes('Đã báo thiếu cho quản lý kho'),'Employee sees acknowledgement');
 check(!$('[data-replenish-job]'),'Employee has no receipt action');
 $('#editor').close();
 state("S.user.VaiTro='QUAN_LY_KHO'; S.user.MaNV=1");
 await nav('overview');
 check($('#content').textContent.includes('CPU-001 thiếu 4'),'Manager sees current shortage on Overview');
 $('[data-detail="jobs"][data-id="99"]').click();
 check($('#editor').textContent.includes('CPU-001 thiếu 4'),'Job detail preserves the reported amount');
 $('#editor').close();
 freshState=JSON.parse(state('JSON.stringify(S.data)'));
 const freshJob=freshState.jobs.find(j=>j.MaYC===99);
 freshJob.needs[0].SoLuongThieu=2;
 freshJob.needs.push(
  {MaSPLinhKien:2,SKU:'RAM-001',SoLuongThieu:6},
  {MaSPLinhKien:4,SKU:'OTHER',SoLuongThieu:0}
 );
 $('[data-replenish-job="99"]').click();await tick();
 const form=$('#document-form');
 check(form?.dataset.kind==='incoming'&&!form.dataset.id,'Shortage opens the standard new receipt form');
 check([...form.querySelectorAll('[name=MaSP]')].map(x=>x.value).join(',')==='1,2','Only missing products are preselected');
 check([...form.querySelectorAll('[name=SoLuongNhan]')].map(x=>x.value).join(',')==='2,6','Receipt uses refreshed quantities');
 check(form.elements.GhiChu.value.includes('YC-099'),'Receipt note identifies the assembly job');
 check(!form.elements.MaNCC.value&&[...form.querySelectorAll('[name=MaViTri]')].every(x=>!x.value),'Supplier and locations require explicit selection');
 check(!savedReceipts.length,'Opening the receipt makes no write');
 form.elements.MaNCC.value='1';
 form.querySelectorAll('[name=MaViTri]').forEach(x=>x.value='1');
 form.querySelector('[name=SoLuongNhan]').value='1';
 form.querySelector('[type=submit]').click();await tick();
 check(savedReceipts.length===1&&savedReceipts[0].lines.map(x=>x.SoLuongNhan).join(',')==='1,6','Saving uses the actual quantities entered in the standard form');
 check($('[data-replenish-job="99"]'),'Draft alone does not clear the shortage');

 freshState.products.find(item=>item.MaSP===1).TrangThai='NGUNG';
 $('[data-replenish-job="99"]').click();await tick();
 check($('#document-form [name=MaSP]').value==='2'&&$('#modal-body .hint').textContent.includes('CPU-001'),'Inactive SKU is called out while eligible SKU is prefilled');
 $('#editor').close();
 freshJob.needs.forEach(item=>{item.SoLuongThieu=0;});
 $('[data-replenish-job="99"]').click();await tick();
 check(!$('#editor').open&&savedReceipts.length===1,'Replenishment in another session prevents a stale prefilled receipt');
 check(!$('#content').textContent.includes('HIỆN CÒN THIẾU'),'Replenished job leaves the manager queue');
 check(errors.length===0,'No unhandled JS errors');
 console.log(JSON.stringify({checks,requests:requests.length,errors}));w.close();
})().catch(error=>{console.error(error);w.close();process.exitCode=1;});
