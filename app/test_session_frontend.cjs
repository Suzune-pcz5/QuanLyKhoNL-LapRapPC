// Authentication changes must discard old successes, errors and form completions.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {JSDOM}=require(process.env.MRP_DOM_MODULES||'jsdom');
const fixture=JSON.parse(fs.readFileSync(process.argv[2]||path.join(__dirname,'tests/fixtures/state.json'),'utf8'));
const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'static/index.html'),'utf8'),{url:'https://unit.test/',runScripts:'outside-only'}),w=dom.window,ctx=dom.getInternalVMContext();
const $=s=>w.document.querySelector(s),state=code=>vm.runInContext(code,ctx),tick=async()=>{await new Promise(setImmediate);await new Promise(setImmediate);};
const errors=[],requests=[];let checks=0,current=structuredClone(fixture),nextState=null,nextLogin=null,nextSave=null;
const documentRequests=[];let loseDocumentResponse=false;
current.user={...fixture.user,VaiTro:'ADMIN',HoTen:'Quản trị viên'};
const check=(value,message)=>{assert.ok(value,message);checks++;};
const response=(body,status=200)=>({ok:status<400,status,json:async()=>body});
function defer(){let release,reject,started;const ready=new Promise(r=>started=r),promise=new Promise((r,j)=>{release=r;reject=j;});return {release,reject,started,ready,promise};}
w.addEventListener('error',ev=>errors.push(String(ev.error)));
w.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
w.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');this.dispatchEvent(new w.Event('close'));};
w.print=()=>{};
w.fetch=async(url,options={})=>{
 requests.push(url);
 if(url==='/api/session')return response({csrf:'test',user:current?.user||null});
 if(url==='/api/logout'){current=null;return response({ok:true});}
 if(url==='/api/login'){
  const name=JSON.parse(options.body).username;current=structuredClone(fixture);
  current.user={...fixture.user,TenDangNhap:name,HoTen:name==='admin'?'Quản trị viên':'Nhân viên lắp ráp',VaiTro:name==='admin'?'ADMIN':'NHAN_VIEN'};
  if(name!=='admin'){current.accounts=[];current.incoming=[];current.employees=current.employees.filter(e=>e.MaNV===current.user.MaNV);}
  const reply=response({csrf:'test',user:current.user});
  if(nextLogin){const pending=nextLogin;nextLogin=null;pending.reply=reply;pending.started();return pending.promise;}
  return reply;
 }
 if(url==='/api/state'){
  const reply=response(structuredClone(current));
  if(nextState){const pending=nextState;nextState=null;pending.reply=reply;pending.started();return pending.promise;}
  return reply;
 }
 if(url.startsWith('/api/catalog/')&&nextSave){const pending=nextSave;nextSave=null;pending.started();return pending.promise;}
 if(url==='/api/documents/incoming'){
  documentRequests.push({key:options.headers['Idempotency-Key'],data:JSON.parse(options.body)});
  if(loseDocumentResponse){loseDocumentResponse=false;throw new TypeError('Failed to fetch');}
  return response({id:99,replayed:documentRequests.length>1,message:'Đã lưu một phiếu.'});
 }
 throw Error('Unexpected API '+url);
};
vm.runInContext(fs.readFileSync(path.join(__dirname,'static/app.js'),'utf8'),ctx);
const submit=()=>$('#login-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
async function login(name){$('#login-form [name=username]').value=name;$('#login-form [name=password]').value='Demo@12345';submit();await tick();check(!$('#workspace').hidden,'Login completes: '+name);}
async function logout(){$('#logout').click();await tick();check(!$('#login').hidden&&$('#workspace').hidden,'Logout shows login only');}
(async()=>{
 await tick();check(!$('#workspace').hidden,'Initial authenticated shell');
 for(const outcome of ['success','unauthorized','network']){
  if(state('S.user?.VaiTro')!=='ADMIN'){await logout();await login('admin');}
  const pending=defer();nextState=pending;$('#content [data-refresh]').click();await pending.ready;
  await logout();
  if(outcome==='network')pending.reject(Error('Old network failure'));
  else pending.release(outcome==='success'?pending.reply:response({error:'Old unauthorized response'},401));
  await tick();
  check($('#workspace').hidden&&!$('#login').hidden,'Late '+outcome+' cannot undo logout');
  check(state('S.user===null&&S.data===null'),'Old data cleared: '+outcome);
  check(!$('#login-error').textContent&&!$('#toast').textContent,'Old '+outcome+' does not show an error in the next session');
 }
 for(const outcome of ['success','unauthorized','network']){
  await login('admin');const pending=defer();nextState=pending;$('#content [data-refresh]').click();await pending.ready;
  await logout();await login('nhanvien');
  if(outcome==='network')pending.reject(Error('Old network failure'));
  else pending.release(outcome==='success'?pending.reply:response({error:'Old unauthorized response'},401));
  await tick();
  check(state("S.user?.VaiTro==='NHAN_VIEN'"),'Late '+outcome+' preserves employee identity');
  check(!$('#workspace').hidden&&!$('#nav [data-nav=accounts]'),'Late '+outcome+' cannot display Admin navigation');
  check(state('S.data.accounts.length===0&&S.data.incoming.length===0'),'Late '+outcome+' cannot restore Admin data');
  check(!$('#login-error').textContent&&!$('#toast').textContent,'Late '+outcome+' is silent after account switch');
  await logout();
 }
 await login('admin');const old=defer();nextState=old;const earlier=w.reload();await old.ready;
 current.products[0].TenSP='Tên vừa cập nhật';await w.reload();old.release(old.reply);await earlier;
 check(state("S.data.products[0].TenSP==='Tên vừa cập nhật'"),'Older same-session reload cannot overwrite a newer one');
 current.inventory=[{MaViTri:1,SoLuongKhongBan:1},{MaViTri:1,SoLuongKhongBan:2},{MaViTri:3,SoLuongKhongBan:1},{MaViTri:2,SoLuongKhongBan:0}];
 state('S.data.inventory='+JSON.stringify(current.inventory));
 const wrapper=w.document.createElement('div');wrapper.innerHTML=w.overview();
 check([...wrapper.querySelectorAll('.stat')].find(x=>x.textContent.includes('Vị trí có hàng lỗi')).querySelector('strong').textContent==='2','Faulty locations are distinct, not SKU rows');
 state('S.data.inventory=[]');wrapper.innerHTML=w.overview();
 check([...wrapper.querySelectorAll('.stat')].find(x=>x.textContent.includes('Vị trí có hàng lỗi')).querySelector('strong').textContent==='0','Empty stock has zero faulty locations');
 await logout();nextLogin=defer();const pendingLogin=nextLogin;$('#login-form [name=username]').value='admin';$('#login-form [name=password]').value='Demo@12345';const count=requests.filter(x=>x==='/api/login').length;
 submit();await pendingLogin.ready;submit();await tick();check(requests.filter(x=>x==='/api/login').length===count+1,'Duplicate login submit issues one request');pendingLogin.release(pendingLogin.reply);await tick();
 // A completed save belonging to a signed-out account cannot close a new editor.
 current=structuredClone(fixture);current.user={...fixture.user,VaiTro:'ADMIN'};await w.reload();
 w.catalogEditor('suppliers');$('#catalog-form [name=TenNCC]').value='Nhà cung cấp thử';nextSave=defer();const pendingSave=nextSave;
 $('#catalog-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await pendingSave.ready;await logout();await login('nhanvien');w.documentEditor('outgoing');
 pendingSave.release(response({id:99,message:'Old save completed'}));await tick();
 check($('#editor').open&&$('#document-form')?.dataset.kind==='outgoing','Old save cannot close another account editor');
 check(!state('editorSaving'),'Old save does not leave the next account blocked');
 // The server may have committed even though fetch rejects. Keep the operation
 // and exact payload while retrying; never turn a retry into a new draft.
 $('#editor').close();current=structuredClone(fixture);current.user={...fixture.user,VaiTro:'QUAN_LY_KHO'};await w.reload();
 w.documentEditor('incoming');$('#document-form [name=MaNCC]').value='1';$('#document-form [name=GhiChu]').value='Lưu một lần';
 $('#document-form [name=MaSP]').value='1';$('#document-form [name=MaViTri]').value='1';
 loseDocumentResponse=true;$('#document-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await tick();
 check($('#editor').open,'Lost save response leaves the original form open');
 check($('#document-form').dataset.uncertain==='1','Lost response marks the save as uncertain');
 check($('#document-form [type=submit]').textContent==='Thử lại lưu','Uncertain save offers a specific retry');
 check($('#document-form .form-error').textContent.includes('Chưa xác định được kết quả lưu'),'Uncertain save is explained in Vietnamese');
 check(!$('#document-form .form-error').textContent.includes('Failed to fetch'),'Raw browser error is not displayed');
 check($('#document-form [name=GhiChu]').disabled&&$('#document-form [data-add-line]').disabled,'Uncertain payload cannot be edited');
 check(documentRequests[0].key?.length>=16,'New document carries an operation key');
 $('#document-form [name=GhiChu]').value='Tampered while disabled';
 $('#document-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await tick();
 check(documentRequests.length===2&&documentRequests[0].key===documentRequests[1].key,'Retry reuses the original operation key');
 check(JSON.stringify(documentRequests[0].data)===JSON.stringify(documentRequests[1].data),'Retry reuses the exact original payload');
 check(!$('#editor').open,'Recovered save closes after the list refresh');
 check(errors.length===0,'No unhandled JavaScript errors');
 console.log(JSON.stringify({checks,errors}));w.close();
})().catch(error=>{console.error(error);w.close();process.exitCode=1;});
