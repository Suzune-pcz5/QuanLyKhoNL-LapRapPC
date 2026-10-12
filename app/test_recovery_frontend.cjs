// Recovery when the authentication owner disappears or an uncertain save is rejected.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {JSDOM}=require(process.env.MRP_DOM_MODULES||'jsdom');
const fixture=JSON.parse(fs.readFileSync(process.argv[2]||path.join(__dirname,'tests/fixtures/state.json'),'utf8'));
const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'static/index.html'),'utf8'),{url:'https://unit.test/',runScripts:'outside-only'}),w=dom.window,ctx=dom.getInternalVMContext();
const $=s=>w.document.querySelector(s),state=code=>vm.runInContext(code,ctx),tick=async()=>{await new Promise(setImmediate);await new Promise(setImmediate);};
const errors=[],saves=[],replies=[];let checks=0,user=null,sessionFailure=false,sessionGate=null,lockTail=Promise.resolve();
const check=(value,label)=>{assert.ok(value,label);checks++;},response=(body,status=200)=>({ok:status<400,status,json:async()=>body});
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};}
Object.defineProperty(w.navigator,'locks',{value:{request:(_name,action)=>{const task=lockTail.then(action);lockTail=task.catch(()=>{});return task;}}});
w.addEventListener('error',ev=>errors.push(String(ev.error)));
w.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
w.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');this.dispatchEvent(new w.Event('close'));};
w.fetch=async(url,options={})=>{
 if(url==='/api/session'){
  if(sessionGate){const gate=sessionGate;sessionGate=null;gate.started.resolve();await gate.release.promise;}
  if(sessionFailure){sessionFailure=false;throw new TypeError('Failed to fetch');}
  return response({csrf:'test',user});
 }
 if(url==='/api/state')return response({...structuredClone(fixture),user});
 if(url==='/api/login'){user={...fixture.user,VaiTro:'QUAN_LY_KHO'};return response({csrf:'test',user});}
 if(url==='/api/logout'){user=null;return response({ok:true});}
 if(url==='/api/documents/incoming'){
  saves.push({key:options.headers['Idempotency-Key'],data:JSON.parse(options.body)});
  const reply=replies.shift();assert.ok(reply,'Document request must have an expected reply');
  if(reply==='network')throw new TypeError('Failed to fetch');
  if(reply==='malformed')return {ok:true,status:200,json:async()=>{throw new SyntaxError('Invalid JSON');}};
  return response(reply.body||{id:99,message:'Đã lưu.'},reply.status||200);
 }
 throw Error('Unexpected API '+url);
};
vm.runInContext(fs.readFileSync(path.join(__dirname,'static/app.js'),'utf8'),ctx);
function authEvent(phase){const key='kho.authChanged',value=JSON.stringify({phase,id:w.crypto.randomUUID()});w.localStorage.setItem(key,value);w.dispatchEvent(new w.StorageEvent('storage',{key,newValue:value}));}
const submit=async()=>{$('#document-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await tick();};
function receipt(){w.documentEditor('incoming');$('[name=MaNCC]').value='1';$('[name=MaSP]').value='1';$('[name=MaViTri]').value='1';$('[name=SoLuongNhan]').value='1';$('[name=SoLuongLoi]').value='2';}
(async()=>{
 await tick();check(!$('#login-form [type=submit]').disabled,'Bootstrap permits login');
 if(process.argv.includes('--auth-only')||!process.argv.includes('--form-only')){
  // The other tab held the lock, announced start, then vanished without done.
  const owner=deferred(),started=deferred();const held=w.navigator.locks.request('kho.auth',async()=>{started.resolve();await owner.promise;});await started.promise;
  authEvent('start');await tick();check($('#login-form [type=submit]').disabled,'Login stays disabled while the other tab owns the lock');
  owner.resolve();await held;await tick();check(!$('#login-form [type=submit]').disabled&&!state('loginPending'),'Owner disappearance recovers login without a done event or reload');
  // Two notifications must not enable login while a session read is still queued.
  sessionGate={started:deferred(),release:deferred()};const gate=sessionGate;
  authEvent('start');await gate.started.promise;authEvent('done');await tick();check($('#login-form [type=submit]').disabled,'Pending session synchronization keeps login disabled');
  gate.release.resolve();await tick();check(!$('#login-form [type=submit]').disabled&&!state('loginPending'),'All queued synchronization completes before login is enabled');
  sessionFailure=true;authEvent('start');await tick();check(!$('#login-form [type=submit]').disabled&&!state('loginPending'),'Failed session refresh does not trap login');
  check($('#login-error').textContent.includes('Không thể tải dữ liệu'),'Failed session refresh displays Vietnamese feedback');
 }
 if(!process.argv.includes('--auth-only')){
  $('#login-form [name=username]').value='quanly';$('#login-form [name=password]').value='Demo@12345';$('#login-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await tick();check(!$('#workspace').hidden,'Login works after synchronization recovery');
  receipt();$('[name=NgayChungTu]').disabled=true;replies.push('network',{status:400,body:{error:'Số lỗi không được lớn hơn số thực nhận.'}},{status:200});
  await submit();check($('[name=SoLuongLoi]').disabled&&$('#document-form').dataset.uncertain==='1','Lost response freezes the payload');const first=saves.at(-1);
  await submit();check(!$('[name=SoLuongLoi]').disabled&&!$('[name=SoLuongNhan]').disabled,'Definite validation rejection unlocks quantity inputs');
  check(!$('[data-add-line]').disabled,'Definite rejection unlocks line editing');check($('[name=NgayChungTu]').disabled,'Originally disabled fields remain disabled');
  check(!$('#document-form').dataset.uncertain&&$('#document-form [type=submit]').textContent==='Lưu nháp','Definite rejection restores normal save');
  check($('#document-form .form-error').textContent==='Số lỗi không được lớn hơn số thực nhận.','Validation feedback no longer claims an uncertain result');
  check(saves.at(-1).key===first.key&&JSON.stringify(saves.at(-1).data)===JSON.stringify(first.data),'Validation retry still sends the original operation and payload');
  $('[name=SoLuongLoi]').value='0';await submit();check(saves.at(-1).key!==first.key&&saves.at(-1).data.lines[0].SoLuongLoi==='0','Corrected save uses a new operation and edited payload');check(!$('#editor').open,'Corrected save completes without reopening the form');
  for(const status of [409,500]){
   receipt();replies.push({status,body:{error:'Chưa xác nhận được thao tác.'}},{status:200});await submit();const unavailable=saves.at(-1);
   check($('[name=SoLuongLoi]').disabled&&$('#document-form').dataset.uncertain==='1','Initial HTTP '+status+' preserves a potentially committed save');
   check(!$('#document-form .form-error').textContent.includes('do mất kết nối'),'HTTP '+status+' is not mislabeled as a lost connection');
   await submit();check(saves.at(-1).key===unavailable.key&&!$('#editor').open,'Initial HTTP '+status+' retry reuses the operation');
  }
  for(const status of [409,500]){
   receipt();replies.push('network',{status,body:{error:'Đã từ chối và rollback.',save_not_committed:true}},{status:200});await submit();const rejected=saves.at(-1);await submit();
   check(!$('[name=SoLuongLoi]').disabled,'Confirmed rollback '+status+' unlocks input');
   check($('#document-form [type=submit]').textContent==='Lưu nháp','Confirmed rollback '+status+' restores Save draft');
   check($('#document-form .form-error').textContent==='Đã từ chối và rollback.','Confirmed rollback '+status+' shows definite feedback');
   $('[name=SoLuongLoi]').value='0';await submit();check(saves.at(-1).key!==rejected.key,'Confirmed rollback '+status+' starts a new corrected operation');
  }
  // An unavailable backend or operation conflict cannot prove that the first save failed.
  for(const [reply,label] of [[{status:500,body:{error:'Lỗi máy chủ.'}},'HTTP 500'],[{status:409,body:{error:'Lần lưu trước đang xử lý.'}},'HTTP 409'],['malformed','Malformed response']]){
   receipt();replies.push('network',reply,{status:200});await submit();const original=saves.at(-1);await submit();
   check($('[name=SoLuongLoi]').disabled&&$('#document-form').dataset.uncertain==='1',label+' preserves the uncertain payload');
   check($('#document-form [type=submit]').textContent==='Thử lại lưu',label+' keeps retry available');
   await submit();check(saves.at(-1).key===original.key&&JSON.stringify(saves.at(-1).data)===JSON.stringify(original.data),label+' recovery reuses the original operation');
   check(!$('#editor').open,label+' recovery completes');
  }
 }
 check(errors.length===0,'No unhandled JavaScript errors');console.log(JSON.stringify({checks,errors}));w.close();
})().catch(error=>{console.error(error);w.close();process.exitCode=1;});
