const groups = {
  users: ['User','NV','KH'],
  products: ['LoaiSP','SP','VI_TRI_KHO','TON_KHO'],
  documents: ['NCC','PNH','CTPNH','HD','CTHD'],
  inventory: ['KIEM_KE','CT_KIEM_KE'],
  promotions: ['CTKM','KMTheoHD','KMTheoVoucher','KMTheoSP'],
};
const names = {
  User:'Tài khoản',NV:'Nhân viên',KH:'Khách hàng',LoaiSP:'Loại sản phẩm',
  SP:'Sản phẩm',NCC:'Nhà cung cấp',PNH:'Phiếu nhập hàng',CTPNH:'Chi tiết phiếu nhập',
  VI_TRI_KHO:'Vị trí kho',TON_KHO:'Tồn kho',HD:'Hóa đơn bán hàng',CTHD:'Chi tiết hóa đơn',
  KIEM_KE:'Phiếu kiểm kê',CT_KIEM_KE:'Chi tiết kiểm kê',CTKM:'Chương trình khuyến mãi',
  KMTheoHD:'KM theo hóa đơn',KMTheoVoucher:'KM theo voucher',KMTheoSP:'KM theo sản phẩm',
};
let csrf = '', user = null, columns = {}, activeTable = '', currentRows = [], editing = null;
const $ = id => document.getElementById(id);
function canWrite(table){ return !!user?.permissions?.write?.includes(table); }
function escapeHtml(s) {return String(s ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));}
async function api(url, opts = {}, retryLogin = true) {
  const response = await fetch(url, {cache:'no-store',...opts, headers:{'Content-Type':'application/json',...(opts.headers||{}),'X-CSRF-Token':csrf}});
  const body = await response.json();
  if(response.status===403 && body.code==='CSRF_EXPIRED' && url==='/api/login' && retryLogin){
    const fresh=await api('/api/session');csrf=fresh.csrf;
    return api(url,opts,false);
  }
  if (!response.ok) throw new Error(body.error || 'Không thể tải dữ liệu');
  return body;
}
function message(s, error=false){$('message').textContent=s;$('message').style.color=error?'#c03946':'#3a764a';}
function showLogin(){ $('app').hidden=true;$('login-screen').hidden=false; }
async function boot(){
  try {
    const result = await api('/api/bootstrap'); csrf = result.csrf; user = result.user;
    if (user) await enter(result); else showLogin();
  } catch(e) { $('login-error').textContent=e.message;showLogin(); }
}
async function enter(initial=null){
  const result=initial || await api('/api/bootstrap');
  csrf=result.csrf;user=result.user;
  if(!user){showLogin();return;}
  $('login-screen').hidden=true;$('app').hidden=false;
  $('current-user').textContent=`${user.HoTen} · ${user.role}`;
  $('brand-sections').textContent=user.role==='ADMIN_CNPM'?'SẢN PHẨM · BÁN HÀNG':'SẢN PHẨM · BÁN HÀNG · KHO';
  $('caption-products').textContent=user.role==='ADMIN_CNPM'?'SẢN PHẨM':'SẢN PHẨM & KHO';
  columns=result.tables;
  for (const [group,tables] of Object.entries(groups)){
    const el=$('group-'+group);el.innerHTML='';
    for(const table of tables) if(columns[table]){
      const btn=document.createElement('button');btn.className='nav-item';
      btn.dataset.table=table;btn.textContent=names[table]||table;
      el.appendChild(btn);
    }
    el.hidden=!el.children.length;
    el.previousElementSibling.hidden=el.hidden;
  }
  await choose('',result.overview);
}
async function choose(table,initialOverview=null){
  activeTable=table;message('');
  document.querySelectorAll('[data-table]').forEach(el=>el.classList.toggle('selected',el.dataset.table===table));
  $('page-title').textContent=table?names[table]||table:'Tổng quan';
  $('page-subtitle').textContent=table?`Bảng ${table} · Dữ liệu trong MySQL`:'Các mục quản lý được cấp quyền';
  $('add-btn').hidden=!table || !canWrite(table);
  if (!table){
    const data=initialOverview ?? await api('/api/overview');
    const cards=Object.entries('products' in data?{SP:data.products}:data).map(([key,n])=>`<div class="card stat">${escapeHtml(names[key]||key)}<strong>${n}</strong></div>`).join('');
    $('main-content').innerHTML=`<div class="stats">${cards}</div><h2 class="section-title">Quản lý cửa hàng</h2><div class="card">Chọn mục bên trái để xem và quản lý dữ liệu theo quyền của tài khoản.</div>`;
    return;
  }
  try {
    const result=await api('/api/data/'+table);currentRows=result.rows;
    renderTable(table,result.rows,result.count);
  } catch(e){message(e.message,true);}
}
function renderTable(table,data,count){
  const cols=columns[table].filter(c=>c.name!=='pass');
  $('main-content').innerHTML=`<div class="table-toolbar"><input id="filter-input" placeholder="Tìm trong bảng..." aria-label="Tìm dữ liệu"><span>${count} bản ghi</span></div><div class="table-wrap"><table><thead><tr>${cols.map(c=>`<th>${escapeHtml(c.name)}</th>`).join('')}${canWrite(table)?'<th>Thao tác</th>':''}</tr></thead><tbody id="table-body"></tbody></table></div><div class="table-footer">Hiển thị tối đa 100 bản ghi. Khóa chính được bảo toàn khi cập nhật.</div>`;
  const paint=rows=>{
    const body=$('table-body');body.replaceChildren();
    if(!rows.length){const tr=body.insertRow();const td=tr.insertCell();td.className='empty';td.colSpan=cols.length+(canWrite(table)?1:0);td.textContent='Chưa có dữ liệu';return;}
    for(const row of rows){
      const tr=body.insertRow();
      for(const col of cols){const td=tr.insertCell();td.textContent=String(row[col.name]??'—');td.title=td.textContent;}
      if(canWrite(table)){
        const td=tr.insertCell();const wrap=document.createElement('div');wrap.className='table-actions';
        if(table==='User' && user.role==='ADMIN_CNPM' && (Number(row.UserID)===1 || row.role==='ADMIN')){td.textContent='Admin toàn quyền';continue;}
        const edit=document.createElement('button');edit.textContent='Sửa';edit.onclick=()=>openForm(row);
        const del=document.createElement('button');del.textContent='Xóa';del.className='danger';del.onclick=()=>removeRow(row);
        wrap.append(edit,del);td.appendChild(wrap);
      }
    }
  };
  paint(data);
  $('filter-input').addEventListener('input',event=>paint(data.filter(row=>Object.values(row).some(v=>String(v??'').toLowerCase().includes(event.target.value.toLowerCase())))));
}
function isAuto(col){return String(col.extra).includes('auto_increment');}
function isPrimary(col){return col.column_key==='PRI';}
function controlType(col){
  if(['date'].includes(col.data_type))return 'date';
  if(['datetime','timestamp'].includes(col.data_type))return 'datetime-local';
  if(['int','bigint','smallint','tinyint','decimal','float','double'].includes(col.data_type))return 'number';
  return col.name==='pass'?'password':'text';
}
function openForm(row=null){
  editing=row;
  $('form-caption').textContent=activeTable;
  $('form-title').textContent=(row?'Sửa':'Thêm')+' '+(names[activeTable]||activeTable);
  const grid=$('form-fields');grid.replaceChildren();
  for(const col of columns[activeTable]){
    if(isAuto(col)||row&&isPrimary(col))continue;
    const label=document.createElement('label');label.textContent=col.name;
    const input=document.createElement('input');input.name=col.name;input.type=controlType(col);
    if(input.type==='number')input.step=col.data_type==='decimal'?'0.01':'1';
    if(row&&col.name!=='pass'&&row[col.name]!==null&&row[col.name]!==undefined){
      const val=String(row[col.name]);input.value=input.type==='datetime-local'?val.replace(' ','T').slice(0,16):val;
    }
    if(col.name==='pass'&&row)input.placeholder='Để trống nếu không đổi';
    const hint=document.createElement('small');hint.textContent=isPrimary(col)?'Khóa chính':col.nullable==='YES'?'Có thể để trống':'';
    label.append(input,hint);grid.appendChild(label);
  }
  $('record-dialog').showModal();
}
function closeForm(){$('record-dialog').close();}
function keyOf(row){
  const result={};for(const col of columns[activeTable])if(isPrimary(col))result[col.name]=row[col.name];
  return result;
}
async function removeRow(row){
  if(!confirm('Xóa bản ghi trong '+activeTable+'? Những bản ghi đang được tham chiếu sẽ bị MySQL từ chối.'))return;
  try {await api('/api/data/'+activeTable,{method:'DELETE',body:JSON.stringify({key:keyOf(row)})});await choose(activeTable);message('Đã xóa bản ghi');}
  catch(e){message(e.message,true);}
}
$('record-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const values={};
  for(const input of $('record-form').querySelectorAll('[name]')){
    const col=columns[activeTable].find(c=>c.name===input.name);
    const raw=input.value.trim();
    if(raw===''&&editing&&input.name==='pass')continue;
    if(raw===''){
      if(!editing)continue;
      values[input.name]=col.nullable==='YES'?null:raw;
    }else values[input.name]=raw;
  }
  try{
    const body=editing?{key:keyOf(editing),values}:values;
    await api('/api/data/'+activeTable,{method:editing?'PUT':'POST',body:JSON.stringify(body)});
    closeForm();await choose(activeTable);message('Đã lưu dữ liệu');
  }catch(e){alert(e.message);}
});
$('login-form').addEventListener('submit',async e=>{
  e.preventDefault();const form=new FormData(e.target);
  const button=e.target.querySelector('button[type="submit"]');
  if(button.disabled)return;
  button.disabled=true;$('login-error').textContent='';
  try{
    await initialBoot;
    const fresh=await api('/api/session');csrf=fresh.csrf;
    const result=await api('/api/login',{method:'POST',body:JSON.stringify({userID:form.get('userID'),password:form.get('password')})});
    csrf=result.csrf;user=result.user;await enter();
  }catch(err){$('login-error').textContent=err.message;}
  finally{button.disabled=false;}
});
$('app').addEventListener('click',e=>{const el=e.target.closest('[data-table]');if(el)choose(el.dataset.table);});
$('add-btn').onclick=()=>openForm();
$('close-dialog').onclick=closeForm;
$('cancel-dialog').onclick=closeForm;
$('logout-btn').onclick=async()=>{try{const result=await api('/api/logout',{method:'POST'});user=null;csrf=result.csrf;showLogin();}catch(e){message(e.message,true);}};
const initialBoot=boot();
