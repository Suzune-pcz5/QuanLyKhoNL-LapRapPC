// Exercise delayed/failed refreshes and the confirmation dialogs without a network.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {JSDOM}=require(process.env.MRP_DOM_MODULES||'jsdom');
const fixture=JSON.parse(fs.readFileSync(process.argv[2]||path.join(__dirname,'tests/fixtures/state.json'),'utf8'));
fixture.user.VaiTro='ADMIN';
const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'static/index.html'),'utf8'),{url:'https://unit.test/',runScripts:'outside-only'}),w=dom.window;
const query=s=>w.document.querySelector(s),context=dom.getInternalVMContext(),errors=[],posted=[];
let holdState=null,failState=false,nextEmployee=100,holdWrite=null,failWrite=false;
w.addEventListener('error',ev=>errors.push(ev.error));
w.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
w.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');this.dispatchEvent(new w.Event('close'));};
w.fetch=async(url,opts={})=>{
 let body;
 if(url==='/api/session')body={csrf:'test',user:fixture.user};
 else if(url==='/api/state'){
  if(holdState)await holdState;
  if(failState)return {ok:false,status:503,json:async()=>({error:'Không tải được danh sách'})};
  body=structuredClone(fixture);
 }else{
  const data=opts.body?JSON.parse(opts.body):{};posted.push({url,data});
  if(url==='/api/catalog/employees'){
   if(holdWrite)await holdWrite;
   if(failWrite)return {ok:false,status:409,json:async()=>({error:'Không lưu được dữ liệu thử'})};
   const id=nextEmployee++;fixture.employees.push({MaNV:id,...data});body={id,message:'Đã lưu nhân viên.'};
  }else body={id:101,message:'OK'};
 }
 return {ok:true,status:200,json:async()=>body};
};
vm.runInContext(fs.readFileSync(path.join(__dirname,'static/app.js'),'utf8'),context);
const tick=async()=>{await new Promise(resolve=>setImmediate(resolve));await new Promise(resolve=>setImmediate(resolve));};
const submit=form=>form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
let checks=0;
const check=(value,message)=>{assert.ok(value,message);checks++;};
function newEmployee(name){w.catalogEditor('employees');query('[name=HoTen]').value=name;return query('#catalog-form');}
async function cancelConfirmation(){query('#confirmation').close();await tick();}
(async()=>{
 await tick();
 let writeRelease;holdWrite=new Promise(resolve=>writeRelease=resolve);failWrite=true;
 const writing=newEmployee('Giữ nội dung khi lưu chậm');submit(writing);await tick();
 check(query('[name=HoTen]').disabled,'Input is frozen while the write itself is pending');
 check(query('#editor [data-close]').disabled,'Pending write cannot be closed');
 holdWrite=null;writeRelease();await tick();failWrite=false;
 check(!query('[name=HoTen]').disabled,'Failed write restores editable input');
 check(query('[name=HoTen]').value==='Giữ nội dung khi lưu chậm','Failed write preserves entered text');
 query('#editor').close();posted.length=0;
 let release;holdState=new Promise(resolve=>release=resolve);
 const delayed=newEmployee('Nhân viên tải chậm');submit(delayed);await tick();
 check(query('#editor').open,'Editor stays open until refresh completes');
 check(query('#editor').getAttribute('aria-busy')==='true','Editor announces pending save/refresh');
 check(query('#editor [data-close]').disabled,'Cannot close while refresh is pending');
 const cancel=new w.Event('cancel',{cancelable:true});query('#editor').dispatchEvent(cancel);
 check(cancel.defaultPrevented,'Escape cannot bypass synchronization');
 assert.throws(()=>w.accountEditor(),/Đang lưu/);checks++;
 submit(delayed);await tick();check(posted.filter(x=>x.url==='/api/catalog/employees').length===1,'Repeated submit cannot create duplicate employee');
 holdState=null;release();await tick();
 check(!query('#editor').open,'Editor closes after refreshed data arrives');
 w.accountEditor();check([...query('[name=MaNV]').options].some(o=>o.value==='100'),'New employee immediately available in account form');query('#editor').close();

 failState=true;const failed=newEmployee('Nhân viên lỗi làm mới');submit(failed);await tick();
 check(query('#editor').open&&failed.dataset.saved==='1','Successful write is remembered when refresh fails');
 check(query('.form-error').textContent.includes('Đã lưu thành công'),'Refresh failure is distinguished from save failure');
 check(query('#catalog-form button[type=submit]').textContent==='Tải lại dữ liệu','Offers refresh retry');
 check(query('[name=HoTen]').disabled,'Persisted input cannot be edited and accidentally resubmitted');
 submit(failed);await tick();check(posted.filter(x=>x.url==='/api/catalog/employees').length===2,'Failed refresh retry sends no duplicate POST');
 failState=false;submit(failed);await tick();
 check(!query('#editor').open,'Refresh retry completes save flow');
 w.accountEditor();check([...query('[name=MaNV]').options].some(o=>o.value==='101'),'Retry refresh includes the saved employee');query('#editor').close();

 failState=true;submit(newEmployee('Nhân viên đóng sau lỗi'));await tick();query('#editor').close();
 assert.throws(()=>w.accountEditor(),/Nhấn Làm mới/);checks++;
 failState=false;await w.reload();w.accountEditor();check([...query('[name=MaNV]').options].some(o=>o.value==='102'),'Page refresh unblocks new forms with current data');query('#editor').close();

 fixture.suppliers[0].TenNCC='NCC <img src=x onerror=alert(1)>';
 fixture.incoming.push({MaPN:99,TrangThai:'NHAP',LoaiNhap:'NCC',MaNCC:fixture.suppliers[0].MaNCC,lines:[{MaSP:2,MaViTri:1,SoLuongNhan:20,SoLuongLoi:2}]});
 const commit=w.transition('incoming',99,'commit');await tick();
 const incoming=query('#confirm-details').textContent;
 check(incoming.includes('PN-099')&&incoming.includes('RAM-001')&&incoming.includes('LK-A1'),'Receipt confirmation identifies document/SKU/location');
 check(incoming.includes('+20')&&incoming.includes('+2')&&incoming.includes('+18'),'Receipt confirmation separates physical/faulty/available changes');
 check(incoming.includes('<img src=x')&&!query('#confirm-details img'),'Supplier content is escaped');
 await cancelConfirmation();await commit;check(!posted.some(x=>x.url.includes('/api/actions/')),'Cancel confirmation does not call an action');
 const commitAgain=w.transition('incoming',99,'commit');await tick();submit(query('#confirm-form'));await commitAgain;
 check(posted.filter(x=>x.url==='/api/actions/incoming/99/commit').length===1,'Confirmed commit calls the expected document action once');
 fixture.incoming.find(r=>r.MaPN===99).TrangThai='DA_GHI_NHAN';
 await assert.rejects(w.transition('incoming',99,'commit'),/đã đổi trạng thái/);checks++;
 check(!query('#confirmation').open&&posted.filter(x=>x.url==='/api/actions/incoming/99/commit').length===1,'Stale action cannot display a misleading stock increment or send another POST');
 fixture.incoming.find(r=>r.MaPN===99).TrangThai='NHAP';
 let releaseAction;holdState=new Promise(resolve=>releaseAction=resolve);const pendingAction=w.transition('incoming',99,'commit');await tick();
 await assert.rejects(w.transition('incoming',99,'commit'),/Đang kiểm tra/);checks++;
 holdState=null;releaseAction();await tick();await cancelConfirmation();await pendingAction;

 fixture.outgoing.push({MaPX:99,LoaiXuat:'THANH_PHAM',TenNguoiNhan:'Bộ phận <script>alert(1)</script>',lines:[{MaSP:3,MaViTri:2,SoLuongXuat:2}]});
 await w.reload();w.confirmAction('Duyệt xuất','',false,w.stockConfirmation('outgoing',99));
 check(query('#confirm-details').textContent.includes('Bộ phận <script>')&&!query('#confirm-details script'),'Recipient content is escaped and visible');
 check(query('#confirm-details').textContent.includes('TP-A1')&&query('#confirm-details').textContent.includes('-2'),'Shipment confirmation identifies location and deduction');await cancelConfirmation();
 fixture.jobs.push({MaYC:99,MaBOM:1,MaNVNhan:2});
 fixture.outgoing.push({MaPX:100,LoaiXuat:'CAP_PHAT',MaYCLapRap:99,MaNVLap:2,lines:[{MaSP:1,MaViTri:1,SoLuongXuat:3},{MaSP:2,MaViTri:1,SoLuongXuat:6}]});
 fixture.results.push({MaKQ:99,MaYC:99,MaNVLap:2,SoLuongDat:2,SoLuongLoi:1,MaViTriDat:2,MaViTriLoi:3});await w.reload();
 w.confirmAction('Cấp vật liệu','',false,w.stockConfirmation('outgoing',100));
 check(query('#confirm-details').textContent.includes('YC-99')&&query('#confirm-details').textContent.includes(fixture.employees.find(n=>n.MaNV===2).HoTen),'Allocation confirmation names the employee and job');
 check(query('#confirm-details .stock-summary').children.length===2,'Allocation shows each component separately');await cancelConfirmation();
 w.confirmAction('Tiếp nhận','',false,w.stockConfirmation('results',99));
 check(query('#confirm-details').textContent.includes('PC-001')&&query('#confirm-details').textContent.includes('TP-A1')&&query('#confirm-details').textContent.includes('LOI-A1'),'Result confirmation identifies finished product and both locations');
 check(query('#confirm-details .stock-summary').children.length===2,'Good and faulty result quantities remain separate');await cancelConfirmation();
 w.confirmAction('Xóa nháp','Xác nhận');check(query('#confirm-details').hidden&&!query('#confirm-details').textContent,'Generic confirmation clears previous document details');await cancelConfirmation();
 check(errors.length===0,'No unhandled JavaScript errors');console.log(checks+' PRD frontend assertions passed.');dom.window.close();
})().catch(error=>{console.error(error.stack);process.exitCode=1;dom.window.close();});
