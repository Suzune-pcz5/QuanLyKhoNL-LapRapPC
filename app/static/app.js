'use strict';
const $ = s => document.querySelector(s);
const S = {csrf:'',user:null,data:null,page:'overview',catalog:'products',report:null,backup:null,needsSync:false};
let reportRequest=0;
let authVersion=0,reloadRequest=0,loginPending=true;
class StaleRequestError extends Error{}
class NetworkError extends Error{}
class ApiError extends Error{constructor(message,status,saveNotCommitted=false){super(message);this.status=status;this.saveNotCommitted=saveNotCommitted;}}
function invalidateAuth(){authVersion++;reloadRequest++;reportRequest++;}
const authEventKey='kho.authChanged';
let pendingAuth=0;
function announceAuth(phase){try{localStorage.setItem(authEventKey,JSON.stringify({phase,id:crypto.randomUUID()}));}catch{}}
async function authLock(action,announce=false){
 const run=async()=>{if(announce)announceAuth('start');try{return await action();}finally{if(announce)announceAuth('done');}};
 pendingAuth++;loginPending=true;$('#login-form [type="submit"]').disabled=true;
 try{return await (navigator.locks?.request?navigator.locks.request('kho.auth',run):run());}
 finally{loginPending=--pendingAuth>0;$('#login-form [type="submit"]').disabled=loginPending;}
}
async function syncSession(){
 return authLock(async()=>{invalidateAuth();const x=await api('/api/session');S.csrf=x.csrf;S.user=x.user;if(S.user)await reload();else showLogin();});
}
window.addEventListener('storage',async ev=>{
 if(ev.key!==authEventKey||!ev.newValue||ev.newValue!==localStorage.getItem(authEventKey))return;
 try{
  const event=JSON.parse(ev.newValue);
  if(!['start','done'].includes(event.phase))return;
  if(event.phase==='start')showLogin();
  // Waiting for the shared lock also recovers when the owner closes before done.
  await syncSession();$('#login-error').textContent='';
 }catch(error){if(!(error instanceof StaleRequestError)){$('#login-error').textContent=error.message;}}
});
const e = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = v => Number(v || 0).toLocaleString('vi-VN');
const roleNames = {ADMIN:'Quản trị viên',QUAN_LY_KHO:'Quản lý kho',NHAN_VIEN:'Nhân viên lắp ráp'};
const labels = {NHAP:'Bản nháp',DA_GHI_NHAN:'Đã nhập kho',CHO_DUYET:'Chờ duyệt',DA_THUC_HIEN:'Đã xuất kho',TU_CHOI:'Từ chối',HUY:'Đã hủy',DANG_AP_DUNG:'Đang áp dụng',NGUNG:'Ngừng sử dụng',DA_GIAO:'Đã giao việc',DA_CAP_VAT_LIEU:'Đã cấp vật liệu',DANG_LAP_RAP:'Đang lắp ráp',HOAN_THANH:'Hoàn thành',CHO_TIEP_NHAN:'Chờ tiếp nhận',DA_TIEP_NHAN:'Đã tiếp nhận',HOAT_DONG:'Hoạt động',KHOA:'Đã khóa',DANG_LAM:'Đang làm',NGUNG_LAM:'Ngừng làm'};
const badge = state => `<span class="badge ${['DA_GHI_NHAN','DA_THUC_HIEN','HOAN_THANH','DA_TIEP_NHAN','HOAT_DONG','DANG_AP_DUNG','DANG_LAM'].includes(state)?'green':['CHO_DUYET','CHO_TIEP_NHAN'].includes(state)?'yellow':['TU_CHOI','HUY','KHOA','NGUNG','NGUNG_LAM'].includes(state)?'red':'blue'}">${e(labels[state] || state)}</span>`;
const kindText = x => x==='NGUYEN_LIEU'?'Nguyên liệu':'Thành phẩm';
const formatDate = v => v ? String(v).replace('T',' ').slice(0,16) : '—';
const docDefs = {
 incoming:{title:'Nhập kho',one:'phiếu nhập',key:'MaPN',prefix:'PN',role:'QUAN_LY_KHO',desc:'Ghi nhận nguyên liệu thực nhận từ nhà cung cấp.'},
 outgoing:{title:'Xuất kho',one:'phiếu xuất',key:'MaPX',prefix:'PX',role:'NHAN_VIEN',desc:'Đề nghị, xét duyệt và bàn giao vật liệu hoặc thành phẩm.'},
 bom:{title:'Công thức BOM',one:'BOM',key:'MaBOM',prefix:'BOM',role:'QUAN_LY_KHO',desc:'Công thức một cấp, quản lý theo phiên bản.'},
 jobs:{title:'Yêu cầu lắp ráp',one:'yêu cầu',key:'MaYC',prefix:'YC',role:'QUAN_LY_KHO',desc:'Giao việc, chốt định mức và theo dõi tiến độ lắp ráp.'},
 results:{title:'Kết quả lắp ráp',one:'kết quả',key:'MaKQ',prefix:'KQ',role:'NHAN_VIEN',desc:'Ghi nhận PC đạt/lỗi và tiếp nhận thành phẩm vào kho.'}
};
const pages = [
 ['overview','Tổng quan','◫','KHO HÀNG'],['inventory','Tồn kho','▦'],['incoming','Nhập kho','↙'],['outgoing','Xuất kho','↗'],
 ['bom','Công thức BOM','⌘','LẮP RÁP'],['jobs','Yêu cầu lắp ráp','▤'],['results','Kết quả lắp ráp','◇'],
 ['report','Báo cáo kho','▥','QUẢN TRỊ'],['ledger','Lịch sử biến động','↺'],['catalog','Danh mục','▧'],['accounts','Tài khoản','♙'],['backup','Sao lưu dữ liệu','⇩'],['guide','Hướng dẫn sử dụng','?']
];
function allowed(page){
 if(!S.user)return false;
 if(['accounts','backup'].includes(page))return S.user.VaiTro==='ADMIN';
 if(page==='report')return S.user.VaiTro==='QUAN_LY_KHO';
 if(['incoming','ledger'].includes(page))return S.user.VaiTro!=='NHAN_VIEN';
 return true;
}
async function api(url, method='GET', data, headers={}){
 const version=authVersion;
 let res,b;
 try{res=await fetch(url,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':S.csrf,...headers},body:data===undefined?undefined:JSON.stringify(data)});b=await res.json();}
 catch(error){if(version!==authVersion)throw new StaleRequestError();throw new NetworkError(method==='GET'?'Không thể tải dữ liệu. Kiểm tra kết nối và thử lại.':'Chưa xác định được kết quả thao tác do mất kết nối. Kiểm tra kết nối và làm mới dữ liệu.');}
 if(version!==authVersion)throw new StaleRequestError();
 if(!res.ok){if(res.status===401 && S.user){S.user=null;showLogin();}throw new ApiError(b.error||'Không thể kết nối backend.',res.status,b.save_not_committed===true);}
 return b;
}
let toastTimer;
function toast(message,error=false){$('#toast').hidden=false;$('#toast').className='toast'+(error?' error':'');$('#toast').textContent=message;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,6000);}
let sidebarCollapsed=false;
try{sidebarCollapsed=localStorage.getItem('kho.sidebarCollapsed')==='1';}catch{}
const mobileSidebar=()=>window.matchMedia?.('(max-width:760px)').matches??window.innerWidth<=760;
function syncSidebar(){
 const mobile=mobileSidebar(),visible=mobile?$('.sidebar').classList.contains('open'):!sidebarCollapsed;
 $('#workspace').classList.toggle('sidebar-collapsed',sidebarCollapsed);
 $('.sidebar').toggleAttribute('inert',!visible);$('.sidebar').setAttribute('aria-hidden',String(!visible));
 $('#menu-backdrop').hidden=!(mobile&&visible);
 $('#mobile-menu').setAttribute('aria-expanded',String(visible));
 $('#mobile-menu').setAttribute('aria-label',visible?'Ẩn thanh điều hướng':'Hiện thanh điều hướng');
 $('#mobile-menu').title=visible?'Ẩn thanh điều hướng':'Hiện thanh điều hướng';
}
function setMenu(open){
 if(!open&&mobileSidebar()&&$('.sidebar').contains(document.activeElement))$('#mobile-menu').focus({preventScroll:true});
 $('.sidebar').classList.toggle('open',open);syncSidebar();
}
function toggleSidebar(){
 if(mobileSidebar())setMenu(!$('.sidebar').classList.contains('open'));
 else{
  sidebarCollapsed=!sidebarCollapsed;
  try{localStorage.setItem('kho.sidebarCollapsed',sidebarCollapsed?'1':'0');}catch{}
  syncSidebar();
 }
}
function showLogin(){invalidateAuth();S.user=null;S.data=null;S.report=null;S.backup=null;S.needsSync=false;transitionPending=false;editorBusy(false);setMenu(false);$('#login').hidden=false;$('#workspace').hidden=true;$('#login-form [name="password"]').value='';document.querySelectorAll('dialog[open]').forEach(x=>x.close());}
async function reload(){const request=++reloadRequest,data=await api('/api/state');if(request!==reloadRequest)return false;S.data=data;S.user=data.user;S.needsSync=false;render();return true;}
function shell(){
 $('#login').hidden=true;$('#workspace').hidden=false;
 $('#user-name').textContent=S.user.HoTen;$('#user-role').textContent=roleNames[S.user.VaiTro];$('#avatar').textContent=S.user.HoTen.split(' ').slice(-2).map(w=>w[0]).join('').toUpperCase();
 const navScroll=$('#nav').scrollTop;
 $('#nav').innerHTML=pages.filter(p=>allowed(p[0])).map(([id,title,icon,group])=>`${group?`<div class="nav-group">${group}</div>`:''}<button data-nav="${id}" class="${S.page===id?'active':''}"><span class="nav-icon">${icon}</span>${title}</button>`).join('');
 $('#nav').scrollTop=navScroll;syncSidebar();
 $('#crumb').textContent=pages.find(p=>p[0]===S.page)?.[1]||'Tổng quan';
 $('#sync-time').textContent='Đồng bộ '+formatDate(S.data.now);
}
function head(title,desc,actions='',tag='QUẢN LÝ KHO'){return `<div class="page-head"><div><span class="eyebrow">${tag}</span><h1>${title}</h1><p>${desc}</p></div><div class="head-actions">${actions}<button data-refresh>↻ Làm mới</button></div></div>`;}
function panel(title,body,sub=''){return `<section class="panel"><div class="panel-head"><h3>${title}</h3>${sub}</div>${body}</section>`;}
function table(columns,data,empty='Chưa có dữ liệu.',rowAttrs=()=> ''){
 return `<div class="table-scroll"><table><thead><tr>${columns.map(([title],i)=>`<th><button data-sort="${i}">${title}</button></th>`).join('')}</tr></thead><tbody>${data.length?data.map(r=>`<tr ${rowAttrs(r)}>${columns.map(([,fn])=>`<td>${fn(r)}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${columns.length}" class="empty">${empty}</td></tr>`}</tbody></table></div>`;
}
const getProduct = id => S.data.products.find(p=>p.MaSP==id);
const getEmployee = id => S.data.employees.find(p=>p.MaNV==id)?.HoTen || `Nhân viên #${id}`;
const getLocation = id => S.data.locations.find(p=>p.MaViTri==id)?.MaViTriHienThi || '—';
// Keep issued document contents stored as-is; shorten only the original seed labels for display.
const bomName = r => r?.MaBOM===1 && r.TenCauHinh==='Cau hinh PC demo' ? 'Cấu hình PC · 1 CPU + 2 RAM' : r?.TenCauHinh;
const recipientName = r => r?.MaPX===2 && r.TenNguoiNhan==='Bo phan ban hang demo' ? 'Bộ phận bán hàng' : r?.TenNguoiNhan;
function productCell(id){const p=getProduct(id);return `<div class="product-cell"><span class="product-icon">${p?.LoaiMatHang==='THANH_PHAM'?'▣':'▥'}</span><div><strong>${e(p?.TenSP||'Sản phẩm #'+id)}</strong><small>${e(p?.SKU)}</small></div></div>`;}
function toolbar(extra='',hint='Tìm kiếm theo mã hoặc tên'){return `<div class="toolbar"><input id="search" type="search" placeholder="⌕  ${hint}" aria-label="Tìm kiếm">${extra}<small>Nhấn tiêu đề cột để sắp xếp ↕</small></div>`;}
function inventoryTable(data){return table([['SẢN PHẨM',r=>productCell(r.MaSP)],['LOẠI HÀNG',r=>`<span class="badge">${kindText(r.LoaiMatHang)}</span>`],['VỊ TRÍ',r=>e(r.MaViTriHienThi)],['THỰC TẾ',r=>`<span class="number">${num(r.SoLuongThucTe)}</span>`],['KHÔNG BÁN',r=>`<span class="number ${r.SoLuongKhongBan?'danger':''}">${num(r.SoLuongKhongBan)}</span>`],['KHẢ DỤNG',r=>`<span class="number" style="color:var(--teal)">${num(r.SoLuongKhaDung)}</span>`],['ĐƠN VỊ',r=>e(r.DonViTinh)],['TÌNH TRẠNG',r=>r.ViTriTrangThai==='NGUNG'||r.SanPhamTrangThai==='NGUNG'?badge('NGUNG'):r.SoLuongKhaDung?badge('HOAT_DONG'):'<span class="badge yellow">Hết hàng tốt</span>']],data,'Kho chưa có số dư.',r=>`data-type="${r.LoaiMatHang}" data-location="${r.MaViTri}"`);}
function overview(){
 const d=S.data;const pending=d.outgoing.filter(r=>r.TrangThai==='CHO_DUYET').length+d.results.filter(r=>r.TrangThai==='CHO_TIEP_NHAN').length;
 const busy=d.jobs.filter(r=>!['HUY','HOAN_THANH','NHAP'].includes(r.TrangThai)).length;
 const stats=[['SKU trong danh mục',d.products.length,'Nguyên liệu và PC thành phẩm','▦'],['Chứng từ chờ xử lý',pending,'Phiếu xuất và kết quả lắp ráp','◷'],['Yêu cầu đang thực hiện',busy,'Theo dõi từ giao việc đến hoàn thành','⌘'],['Vị trí có hàng lỗi',new Set(d.inventory.filter(r=>r.SoLuongKhongBan>0).map(r=>r.MaViTri)).size,'Hàng lỗi không được cấp hoặc xuất','◇']];
 const act=S.user.VaiTro==='QUAN_LY_KHO'?'<button class="primary" data-new="incoming">＋ Tạo phiếu nhập</button>':S.user.VaiTro==='NHAN_VIEN'?'<button class="primary" data-new="outgoing">＋ Đề nghị xuất</button>':'<button class="primary" data-nav="accounts">Quản lý tài khoản →</button>';
 const activity=d.ledger.slice(0,5).map(r=>`<div class="activity-item"><span class="activity-icon">${r.DeltaThucTe>0?'↙':'↗'}</span><div><strong>${e(r.SKU)} · ${e({NHAP_NCC:'Nhập NCC',NHAP_THANH_PHAM:'Nhận PC',CAP_PHAT:'Cấp vật liệu',XUAT_THANH_PHAM:'Xuất PC'}[r.LoaiBienDong])}</strong><small>${e(getLocation(r.MaViTri))} · ${formatDate(r.ThoiDiem)}</small></div><span class="delta" style="color:${r.DeltaThucTe>0?'var(--teal)':'var(--orange)'}">${r.DeltaThucTe>0?'+':''}${num(r.DeltaThucTe)}</span></div>`).join('');
 return head('Tổng quan kho','Tồn kho, chứng từ và tiến độ lắp ráp.',act)+`<div class="stats">${stats.map(([l,n,h,i])=>`<div class="stat"><div class="stat-top"><small>${l}</small><span class="stat-icon">${i}</span></div><strong>${num(n)}</strong><p>${h}</p></div>`).join('')}</div>`+`<div class="dashboard-grid">${panel('Tồn kho hiện tại',inventoryTable(d.inventory),'<button class="link-button" data-nav="inventory">Xem tất cả →</button>')}${panel('Biến động gần đây',`<div class="activity">${activity||'<p class="empty">Chưa có biến động được phép xem.</p>'}</div>`)}</div>`;
}
function inventory(){return head('Tồn kho','Số dư theo SKU và vị trí. Khả dụng = thực tế − không bán.')+panel('Danh sách tồn',toolbar(`<select id="type-filter" aria-label="Loại hàng"><option value="">Tất cả loại hàng</option><option value="NGUYEN_LIEU">Nguyên liệu</option><option value="THANH_PHAM">Thành phẩm</option></select><select id="location-filter" aria-label="Vị trí"><option value="">Tất cả vị trí</option>${S.data.locations.map(l=>`<option value="${l.MaViTri}">${e(l.MaViTriHienThi)}</option>`).join('')}</select>`)+inventoryTable(S.data.inventory),`<small>${S.data.inventory.length} số dư · không cộng gộp khác đơn vị</small>`);}
function actionButtons(kind,r){
 const d=docDefs[kind],id=r[d.key],role=S.user.VaiTro,own=(r[kind==='jobs'?'MaNVNhan':'MaNVLap']===S.user.MaNV),draftOwner=r[kind==='jobs'?'MaNVGiao':'MaNVLap']===S.user.MaNV;
 let html=`<button data-detail="${kind}" data-id="${id}">Chi tiết</button>`;
 const a=(action,label)=>`<button data-action="${action}" data-kind="${kind}" data-id="${id}" ${['approve','accept','commit','publish','assign'].includes(action)?'class="primary"':''}>${label}</button>`;
 if(r.TrangThai==='NHAP' && role===d.role && draftOwner){html+=`<button data-edit="${kind}" data-id="${id}">Sửa</button>`;html+=a({incoming:'commit',outgoing:'send',bom:'publish',jobs:'assign',results:'send'}[kind],{incoming:'Chốt nhập',outgoing:'Gửi duyệt',bom:'Ban hành',jobs:'Giao việc',results:'Gửi kết quả'}[kind]);}
 if(kind==='outgoing'&&r.TrangThai==='CHO_DUYET'&&role==='QUAN_LY_KHO')html+=a('approve','Duyệt xuất')+a('reject','Từ chối');
 if(kind==='results'&&r.TrangThai==='CHO_TIEP_NHAN'&&role==='QUAN_LY_KHO')html+=a('accept','Tiếp nhận')+a('reject','Từ chối');
 if(kind==='jobs'&&r.TrangThai==='DA_GIAO'&&role==='NHAN_VIEN'&&own){if(!r.DaNhanViec)html+=a('receive','Nhận việc');else html+=`<button data-allocate="${id}">Đề nghị cấp</button>`;}
 if(kind==='jobs'&&['DA_CAP_VAT_LIEU','DANG_LAP_RAP'].includes(r.TrangThai)&&role==='NHAN_VIEN'&&own)html+=`<button data-result-job="${id}">Ghi kết quả</button>`;
 if(kind==='jobs'&&['NHAP','DA_GIAO'].includes(r.TrangThai)&&role==='QUAN_LY_KHO')html+=a('cancel','Hủy yêu cầu');
 return `<div class="action-cell">${html}</div>`;
}
function documents(kind){
 const d=docDefs[kind],list=S.data[kind];let columns=[['MÃ',r=>`<strong>${d.prefix}-${String(r[d.key]).padStart(3,'0')}</strong>`]];
 if(kind==='incoming')columns.push(['NGUỒN',r=>r.LoaiNhap==='NCC'?e(S.data.suppliers.find(n=>n.MaNCC==r.MaNCC)?.TenNCC):`Lắp ráp KQ-${r.MaNguonKetQua}`],['SỐ DÒNG',r=>num(r.lines.length)],['NGÀY CHỨNG TỪ',r=>formatDate(r.NgayChungTu)]);
 if(kind==='outgoing')columns.push(['LOẠI',r=>r.LoaiXuat==='CAP_PHAT'?'Cấp nguyên liệu':'Xuất thành phẩm'],['NGƯỜI NHẬN / VIỆC',r=>e(recipientName(r)||'YC-'+r.MaYCLapRap)],['NGƯỜI LẬP',r=>e(getEmployee(r.MaNVLap))]);
 if(kind==='bom')columns.push(['CẤU HÌNH',r=>`<strong>${e(bomName(r))}</strong><br><small>${e(getProduct(r.MaSPThanhPham)?.SKU)}</small>`],['PHIÊN BẢN',r=>'V'+r.PhienBan],['NGUYÊN LIỆU',r=>num(r.lines.length)]);
 if(kind==='jobs')columns.push(['CÔNG THỨC',r=>e(bomName(S.data.bom.find(b=>b.MaBOM==r.MaBOM)))],['NHÂN VIÊN',r=>e(getEmployee(r.MaNVNhan))],['TIẾN ĐỘ',r=>`${num(r.accepted)} / ${num(r.SoLuongYeuCau)} PC<div class="progress"><span style="width:${Math.min(100,100*r.accepted/r.SoLuongYeuCau)}%"></span></div><small>${num(r.pending)} chờ tiếp nhận</small>`],['NHẬN VIỆC',r=>r.DaNhanViec?'Đã nhận':'Chưa nhận']);
 if(kind==='results')columns.push(['YÊU CẦU',r=>'YC-'+r.MaYC],['NGƯỜI LẬP',r=>e(getEmployee(r.MaNVLap))],['ĐẠT',r=>`<span class="number">${num(r.SoLuongDat)}</span>`],['LỖI',r=>`<span class="number danger">${num(r.SoLuongLoi)}</span>`]);
 columns.push(['TRẠNG THÁI',r=>badge(r.TrangThai)],['THAO TÁC',r=>actionButtons(kind,r)]);
 return head(d.title,d.desc,S.user.VaiTro===d.role?`<button class="primary" data-new="${kind}">＋ Tạo ${d.one}</button>`:'')+panel(d.title,toolbar(`<select id="state-filter" aria-label="Trạng thái"><option value="">Tất cả trạng thái</option>${[...new Set(list.map(r=>r.TrangThai))].map(s=>`<option value="${s}">${e(labels[s])}</option>`).join('')}</select>`)+table(columns,list,'Chưa có chứng từ. Tạo bản nháp để bắt đầu.',r=>`data-state="${r.TrangThai}"`),`<small>${list.length} chứng từ</small>`);
}
function ledger(){return head('Lịch sử biến động','Mỗi dòng nhập hoặc xuất ghi một biến động. Lịch sử chỉ được xem.')+panel('Nhật ký kho',toolbar()+table([['THỜI ĐIỂM',r=>formatDate(r.ThoiDiem)],['SKU',r=>e(r.SKU)],['VỊ TRÍ',r=>e(r.MaViTriHienThi)],['NGHIỆP VỤ',r=>e({NHAP_NCC:'Nhập nguyên liệu',NHAP_THANH_PHAM:'Nhận thành phẩm',CAP_PHAT:'Cấp vật liệu',XUAT_THANH_PHAM:'Xuất thành phẩm'}[r.LoaiBienDong])],['THỰC TẾ ±',r=>`<span class="number">${r.DeltaThucTe>0?'+':''}${num(r.DeltaThucTe)}</span>`],['LỖI ±',r=>num(r.DeltaKhongBan)],['NGƯỜI GHI NHẬN',r=>e(r.HoTen)],['NGUỒN',r=>r.MaCTPN?'Dòng nhập #'+r.MaCTPN:'Dòng xuất #'+r.MaCTPX]],S.data.ledger));}
const catalogDefs={products:['Sản phẩm','MaSP'],categories:['Loại sản phẩm','MaLoai'],suppliers:['Nhà cung cấp','MaNCC'],locations:['Vị trí kho','MaViTri'],employees:['Nhân viên','MaNV']};
function catalog(){
 const kind=S.catalog,def=catalogDefs[kind];let cols;
 if(kind==='products')cols=[['SẢN PHẨM',r=>productCell(r.MaSP)],['LOẠI',r=>kindText(r.LoaiMatHang)],['PHÂN NHÓM',r=>e(S.data.categories.find(c=>c.MaLoai==r.MaLoai)?.TenLoai)],['ĐƠN VỊ',r=>e(r.DonViTinh)]];
 if(kind==='categories')cols=[['MÃ',r=>r.MaLoai],['TÊN',r=>e(r.TenLoai)],['MÔ TẢ',r=>e(r.MoTa)]];
 if(kind==='suppliers')cols=[['NHÀ CUNG CẤP',r=>e(r.TenNCC)],['ĐIỆN THOẠI',r=>e(r.SoDienThoai)],['ĐỊA CHỈ',r=>e(r.DiaChi)]];
 if(kind==='locations')cols=[['VỊ TRÍ',r=>e(r.MaViTriHienThi)],['KHU VỰC',r=>e(r.KhuVuc)],['KỆ / TẦNG',r=>e((r.Ke||'—')+' / '+(r.Tang||'—'))]];
 if(kind==='employees')cols=[['NHÂN VIÊN',r=>e(r.HoTen)],['CHỨC VỤ',r=>e(r.ChucVu)],['ĐIỆN THOẠI',r=>e(r.SoDienThoai)]];
 if(kind!=='categories')cols.push(['TRẠNG THÁI',r=>badge(r.TrangThai)]);
 if(S.user.VaiTro==='ADMIN')cols.push(['THAO TÁC',r=>`<div class="action-cell"><button data-catalog-edit="${kind}" data-id="${r[def[1]]}">Sửa</button><button data-catalog-delete="${kind}" data-id="${r[def[1]]}" class="danger">Xóa</button></div>`]);
 let filters='';
 if(kind==='products')filters+=`<select id="type-filter" aria-label="Loại mặt hàng"><option value="">Tất cả loại hàng</option><option value="NGUYEN_LIEU">Nguyên liệu</option><option value="THANH_PHAM">Thành phẩm</option></select><select id="category-filter" aria-label="Nhóm sản phẩm"><option value="">Tất cả nhóm</option>${S.data.categories.map(c=>`<option value="${c.MaLoai}">${e(c.TenLoai)}</option>`).join('')}</select>`;
 if(kind!=='categories')filters+=`<select id="state-filter" aria-label="Trạng thái"><option value="">Tất cả trạng thái</option>${[...new Set(S.data[kind].map(r=>r.TrangThai))].map(v=>`<option value="${v}">${e(labels[v])}</option>`).join('')}</select>`;
 return head('Danh mục','Tìm kiếm nâng cao bằng từ khóa kết hợp bộ lọc; sắp xếp bằng tiêu đề cột.',S.user.VaiTro==='ADMIN'?`<button class="primary" data-catalog-new="${kind}">＋ Thêm ${def[0].toLowerCase()}</button>`:'')+`<div class="tabs">${Object.entries(catalogDefs).map(([k,v])=>`<button data-catalog-tab="${k}" class="${k===kind?'selected':''}">${v[0]}</button>`).join('')}</div>`+panel(def[0],toolbar(filters)+table(cols,S.data[kind],'Chưa có dữ liệu.',r=>`data-type="${e(r.LoaiMatHang)}" data-category="${e(r.MaLoai)}" data-state="${e(r.TrangThai)}"`));
}
function accounts(){return head('Tài khoản & quyền','Mỗi tài khoản có một vai trò. Khóa tài khoản để giữ chứng từ lịch sử.','<button class="primary" data-account-new>＋ Thêm tài khoản</button>')+panel('Danh sách tài khoản',toolbar()+table([['TÊN ĐĂNG NHẬP',r=>`<strong>${e(r.TenDangNhap)}</strong>`],['NHÂN VIÊN',r=>e(getEmployee(r.MaNV))],['VAI TRÒ',r=>e(roleNames[r.VaiTro])],['TRẠNG THÁI',r=>badge(r.TrangThai)],['THAO TÁC',r=>`<div class="action-cell"><button data-account-edit="${r.MaTK}">Sửa / đổi mật khẩu</button><button data-account-delete="${r.MaTK}" class="danger">Xóa</button></div>`]],S.data.accounts));}
function report(){
 const today=String(S.data.now).slice(0,10),year=today.slice(0,4),month=today.slice(5,7);
 const quarter=Math.ceil(Number(month)/3),tomorrow=new Date(Date.UTC(Number(year),Number(month)-1,Number(today.slice(8,10))+1)).toISOString().slice(0,10);
 return head('Báo cáo kho','Tồn đầu + nhập − xuất = tồn cuối. Theo thời điểm chốt, UTC+7.','<button data-print>In báo cáo</button><button class="primary" id="csv-export">↓ Xuất CSV</button>')+panel('Chọn kỳ báo cáo',`<form id="report-form" class="panel-body period-fields"><label>Kỳ<select id="period"><option value="month">Tháng</option><option value="quarter">Quý</option><option value="year">Năm</option><option value="custom">Tùy chọn</option></select></label><label id="year-label">Năm<input id="report-year" type="number" min="2000" max="2100" value="${year}" required></label><label id="month-label">Tháng<input id="report-month" type="number" min="1" max="12" value="${Number(month)}" required></label><label id="quarter-label" hidden>Quý<select id="report-quarter" disabled>${['I','II','III','IV'].map((v,i)=>`<option value="${i+1}" ${i+1===quarter?'selected':''}>${v}</option>`).join('')}</select></label><label id="from-label" hidden>Từ ngày<input id="report-from" type="date" min="1000-01-01" max="9999-12-31" value="${year}-${month}-01" required disabled></label><label id="to-label" hidden>Đến ngày (không gồm)<input id="report-to" type="date" min="1000-01-01" max="9999-12-31" value="${tomorrow}" required disabled></label><label>Loại hàng<select id="report-type"><option value="">Tất cả</option><option value="NGUYEN_LIEU">Nguyên liệu</option><option value="THANH_PHAM">Thành phẩm</option></select></label><label>Vị trí<select id="report-location"><option value="">Tất cả</option>${S.data.locations.map(l=>`<option value="${l.MaViTri}">${e(l.MaViTriHienThi)}</option>`).join('')}</select></label><button type="submit" class="primary">Xem báo cáo</button></form>`)+`<div id="report-results"><div class="panel empty">Chọn kỳ và nhấn “Xem báo cáo”.</div></div>`;
}
function backupPage(){return head('Sao lưu dữ liệu','Tạo bản sao lưu và kiểm tra khả năng khôi phục.')+panel('Sao lưu & khôi phục',`<div class="panel-body"><div class="hint">Khôi phục thử tạo cơ sở dữ liệu riêng để kiểm tra bản sao lưu. Dữ liệu đang sử dụng được giữ nguyên.</div><div class="head-actions"><button class="primary" id="backup-create">↓ Tạo bản sao lưu</button><button id="restore-test" ${S.backup?'':'disabled'}>Kiểm chứng khôi phục</button></div><div id="backup-results" style="margin-top:20px">${S.backup?`<p>Bản sao lưu: <a href="/api/backups/${e(S.backup)}">${e(S.backup)}</a></p>`:''}</div></div>`);}
function guide(){const steps=[['Nhập kho','Quản lý kho chọn Nhập kho → Tạo phiếu nhập, điền nhà cung cấp và các dòng nguyên liệu. Lưu nháp, kiểm tra số thực nhận và số lỗi rồi Chốt nhập.'],['Giao việc lắp ráp','Quản lý kho chọn Yêu cầu lắp ráp → Tạo yêu cầu, chọn BOM, số lượng và nhân viên rồi Giao việc.'],['Nhận việc và đề nghị cấp','Nhân viên chọn Yêu cầu lắp ráp → Nhận việc → Đề nghị cấp. Chọn vị trí kho hoặc dùng Gợi ý phân bổ, lưu nháp rồi Gửi duyệt.'],['Duyệt xuất nguyên liệu','Quản lý kho chọn Xuất kho, kiểm tra đề nghị rồi Duyệt xuất hoặc Từ chối. Phiếu chỉ được duyệt khi đủ tồn khả dụng.'],['Ghi kết quả lắp ráp','Nhân viên chọn yêu cầu đã được cấp vật liệu → Ghi kết quả, điền số đạt, số lỗi và vị trí nhận rồi Gửi kết quả.'],['Tiếp nhận thành phẩm','Quản lý kho chọn Kết quả lắp ráp → Tiếp nhận hoặc Từ chối. Kết quả được tiếp nhận sẽ nhập thành phẩm vào kho.'],['Xuất thành phẩm','Nhân viên tạo phiếu xuất thành phẩm, chọn sản phẩm, vị trí và bộ phận nhận rồi Gửi duyệt. Quản lý kho kiểm tra và Duyệt xuất.'],['Báo cáo kho','Quản lý kho chọn Báo cáo kho, chọn kỳ và bộ lọc rồi Xem báo cáo. Có thể in hoặc xuất CSV.'],['Tài khoản và sao lưu','Quản trị viên quản lý danh mục, tài khoản và bản sao lưu.']];return head('Hướng dẫn sử dụng','Các bước thao tác theo vai trò.')+panel('Quy trình kho và lắp ráp',`<div class="panel-body">${steps.map(([t,p],i)=>`<div class="guide-step"><b>${i+1}</b><div><h3>${t}</h3><p>${p}</p></div></div>`).join('')}</div>`);}
function render(){
 if(!S.user||!S.data)return;
 S.page=location.hash.slice(1)||'overview';if(!allowed(S.page)||!pages.some(p=>p[0]===S.page))S.page='overview';shell();
 S.report=null;reportRequest++;
 $('#content').innerHTML=docDefs[S.page]?documents(S.page):({overview,inventory,ledger,catalog,accounts,report,backup:backupPage,guide}[S.page]||overview)();
}
function filterTable(){
 const q=($('#search')?.value||'').toLocaleLowerCase('vi');
 const type=$('#type-filter')?.value,loc=$('#location-filter')?.value,state=$('#state-filter')?.value,category=$('#category-filter')?.value;
 $('#content').querySelectorAll('tbody tr').forEach(r=>{
  const text=[...r.cells].filter(c=>!c.querySelector('.action-cell')).map(c=>c.textContent).join(' ').toLocaleLowerCase('vi');
  r.hidden=!(text.includes(q)&&(!type||r.dataset.type===type)&&(!loc||r.dataset.location===loc)&&(!state||r.dataset.state===state)&&(!category||r.dataset.category===category));
 });
}
function options(items,key,fn,current,placeholder='Chọn…'){return `<option value="">${placeholder}</option>`+items.map(r=>`<option value="${e(r[key])}" ${r[key]==current?'selected':''}>${e(fn(r))}</option>`).join('');}
function field(name,label,type='text',value='',items=null,required=true,wide=false,limit=null){
 const lengths={SKU:50,TenSP:200,DonViTinh:20,TenNCC:150,MaViTriHienThi:50,HoTen:100,TenLoai:100,SoDienThoai:20,ChucVu:50,KhuVuc:50,Ke:50,Tang:50,TenCauHinh:200,TenNguoiNhan:150,TenDangNhap:100};
 const max=limit??lengths[name]??(type==='textarea'?500:255);
 const rules=type==='number'?`step="1" min="${['SoLuongDat','SoLuongLoi'].includes(name)?0:1}" max="2147483647"`:['date','datetime-local'].includes(type)?`min="1000-01-01${type==='datetime-local'?'T00:00':''}" max="9999-12-31${type==='datetime-local'?'T23:59':''}"`:`maxlength="${max}" ${type==='password'?'minlength="8" autocomplete="new-password"':''}`;
 let input=items?`<select name="${name}" ${required?'required':''}>${items}</select>`:type==='textarea'?`<textarea name="${name}" rows="2" maxlength="${max}" ${required?'required':''}>${e(value)}</textarea>`:`<input name="${name}" type="${type}" value="${e(value)}" ${required?'required':''} ${rules}>`;
 return `<label class="${wide?'wide':''}" data-field="${name}">${label}${input}</label>`;
}
const activeList = key => S.data[key].filter(r=>!r.TrangThai||['HOAT_DONG','DANG_LAM'].includes(r.TrangThai));
const productOptions = (type,current) => options(activeList('products').filter(p=>p.LoaiMatHang===type),'MaSP',p=>`${p.SKU} · ${p.TenSP}`,current);
const locationOptions = current => options(activeList('locations'),'MaViTri',p=>p.MaViTriHienThi,current);
function lineHtml(kind,r={}){
 const type=kind==='outgoing'&&$('#document-form [name="LoaiXuat"]')?.value==='THANH_PHAM'?'THANH_PHAM':'NGUYEN_LIEU';
 const pkey=kind==='bom'?'MaSPLinhKien':'MaSP';
 let html=field(pkey,'Sản phẩm','select','',productOptions(type,r[pkey]));
 if(kind!=='bom')html+=field('MaViTri','Vị trí','select','',locationOptions(r.MaViTri));
 if(kind==='incoming')html+=field('SoLuongNhan','Thực nhận','number',r.SoLuongNhan??1)+field('SoLuongLoi','Số lỗi','number',r.SoLuongLoi??0)+`<label>Giá mua<input name="DonGiaNhap" type="number" min="0" max="9999999999999.99" step="0.01" value="${e(r.DonGiaNhap??0)}" required></label>`+field('KetQuaKiemTra','Kết quả kiểm nhận','text',r.KetQuaKiemTra,null,false);
 if(kind==='outgoing')html+=field('SoLuongXuat','Số xuất','number',r.SoLuongXuat??1);
 if(kind==='bom')html+=field('DinhMuc','Định mức','number',r.DinhMuc??1);
 return `<div class="line-grid ${kind}">${html}<button type="button" class="remove-line" data-remove-line aria-label="Xóa dòng">✕</button></div>`;
}
let editorSaving=false;
function openModal(title,body,tag='CHỨNG TỪ KHO'){if(editorSaving)throw Error('Đang lưu và cập nhật dữ liệu. Vui lòng chờ.');if(S.needsSync)throw Error('Dữ liệu đã lưu nhưng danh sách chưa cập nhật. Nhấn Làm mới trước khi mở form.');$('#modal-title').textContent=title;$('#modal-eyebrow').textContent=tag;$('#modal-body').innerHTML=body;if(!$('#editor').open)$('#editor').showModal();}
$('#editor').addEventListener('cancel',ev=>{if(editorSaving)ev.preventDefault();});
function editorBusy(busy){
 editorSaving=busy;$('#editor').setAttribute('aria-busy',String(busy));
 $('#editor').querySelectorAll('button,input,select,textarea').forEach(el=>{
  // Preserve the original disabled state until an uncertain save is resolved.
  if(busy){el.dataset.beforeBusy??=String(el.disabled);el.disabled=true;}
  else{const form=el.closest('form');el.disabled=el.dataset.beforeBusy==='true'||(el.tagName!=='BUTTON'&&form?.dataset.saved==='1')||(form?.dataset.uncertain==='1'&&!el.matches('[type="submit"],[data-close]'));if(form?.dataset.uncertain!=='1')delete el.dataset.beforeBusy;}
 });
}
function documentEditor(kind,ident=null,preset={}){
 const def=docDefs[kind],r=ident?S.data[kind].find(x=>x[def.key]==ident):preset;let fields='';
 if(kind==='incoming')fields=field('MaNCC','Nhà cung cấp','select','',options(activeList('suppliers'),'MaNCC',x=>x.TenNCC,r.MaNCC))+field('NgayChungTu','Ngày chứng từ','date',r.NgayChungTu||String(S.data.now).slice(0,10))+field('GhiChu','Ghi chú','textarea',r.GhiChu,null,false,true,255);
 if(kind==='outgoing')fields=field('LoaiXuat','Loại xuất','select','',`<option value="CAP_PHAT" ${r.LoaiXuat==='CAP_PHAT'?'selected':''}>Cấp nguyên liệu</option><option value="THANH_PHAM" ${r.LoaiXuat!=='CAP_PHAT'?'selected':''}>Xuất thành phẩm</option>`)+field('MaYCLapRap','Yêu cầu lắp ráp','select','',options(S.data.jobs.filter(j=>j.TrangThai==='DA_GIAO'&&j.DaNhanViec),'MaYC',j=>`YC-${j.MaYC} · ${j.SoLuongYeuCau} PC`,r.MaYCLapRap),false)+field('TenNguoiNhan','Người / bộ phận nhận','text',r.TenNguoiNhan,null,false)+field('GhiChu','Ghi chú','textarea',r.GhiChu,null,false);
 if(kind==='bom')fields=field('MaSPThanhPham','PC thành phẩm','select','',productOptions('THANH_PHAM',r.MaSPThanhPham))+field('PhienBan','Phiên bản','number',r.PhienBan||Math.max(0,...S.data.bom.map(b=>b.PhienBan))+1)+field('TenCauHinh','Tên cấu hình','text',r.TenCauHinh,null,true,true);
 if(kind==='jobs')fields=field('MaBOM','BOM đang áp dụng','select','',options(S.data.bom.filter(b=>b.TrangThai==='DANG_AP_DUNG'),'MaBOM',b=>`${bomName(b)} · V${b.PhienBan}`,r.MaBOM))+field('SoLuongYeuCau','Số PC cần lắp','number',r.SoLuongYeuCau||3)+field('MaNVNhan','Nhân viên được giao','select','',options(S.data.employees.filter(n=>n.VaiTro==='NHAN_VIEN'&&n.TaiKhoanTrangThai==='HOAT_DONG'&&n.TrangThai==='DANG_LAM'),'MaNV',n=>n.HoTen,r.MaNVNhan))+field('HanMongMuon','Hạn mong muốn (UTC+7)','datetime-local',(r.HanMongMuon||'').replace(' ','T'),null,false);
 if(kind==='results')fields=(!ident?field('MaYC','Yêu cầu đã cấp vật liệu','select','',options(S.data.jobs.filter(j=>['DA_CAP_VAT_LIEU','DANG_LAP_RAP'].includes(j.TrangThai)),'MaYC',j=>`YC-${j.MaYC} · còn ${j.SoLuongYeuCau-j.accepted} PC`,r.MaYC)): '')+field('SoLuongDat','PC đạt','number',r.SoLuongDat??1)+field('SoLuongLoi','PC lỗi','number',r.SoLuongLoi??0)+field('MaViTriDat','Vị trí thành phẩm đạt','select','',locationOptions(r.MaViTriDat||2),false)+field('MaViTriLoi','Vị trí thành phẩm lỗi','select','',locationOptions(r.MaViTriLoi||3),false)+field('GhiChu','Ghi chú','textarea',r.GhiChu,null,false,true);
 openModal(`${ident?'Sửa':'Tạo'} ${def.one}${ident?' #'+ident:''}`,`<form id="document-form" data-kind="${kind}" data-id="${ident||''}"><div class="dialog-content"><div class="form-grid">${fields}</div>${['incoming','outgoing','bom'].includes(kind)?`<div class="section-label">CHI TIẾT ${kind==='bom'?'ĐỊNH MỨC':'HÀNG HÓA'}</div><div id="lines"></div><div class="head-actions"><button type="button" data-add-line="${kind}">＋ Thêm dòng</button>${kind==='outgoing'?'<button type="button" id="suggest-allocation">Gợi ý phân bổ</button>':''}</div>`:''}<div class="hint">Lưu nháp chưa thay đổi tồn. Sau khi gửi/chốt, chứng từ được khóa. ${kind==='results'?'Tổng đạt + lỗi đã tiếp nhận không vượt số PC được giao.':kind==='bom'?'Định mức là số nguyên dương cho một PC.':'Chỉ chọn sản phẩm và vị trí đang hoạt động.'}</div><div class="form-error" role="alert"></div></div><div class="dialog-actions">${ident?`<button type="button" class="danger" data-delete-doc="${kind}" data-id="${ident}">Xóa nháp</button>`:''}<button type="button" data-close="editor">Quay lại</button><button class="primary" type="submit">Lưu nháp</button></div></form>`);
 if($('#lines'))$('#lines').innerHTML=(r.lines?.length?r.lines:[{}]).map(x=>lineHtml(kind,x)).join('');
 if(kind==='outgoing')toggleOutgoing();
}
function toggleOutgoing(){const cap=$('#document-form [name="LoaiXuat"]').value==='CAP_PHAT';document.querySelector('[data-field="MaYCLapRap"]').hidden=!cap;document.querySelector('[data-field="TenNguoiNhan"]').hidden=cap;$('#document-form [name="MaYCLapRap"]').required=cap;$('#document-form [name="TenNguoiNhan"]').required=!cap;$('#suggest-allocation').hidden=!cap;}
function allocation(){
 const id=$('#document-form [name="MaYCLapRap"]').value,job=S.data.jobs.find(j=>j.MaYC==id);if(!job)throw Error('Chọn yêu cầu đã nhận việc trước.');
 const lines=[];const missing=[];
 for(const need of job.needs){let left=need.SoLuongCan;for(const row of S.data.inventory.filter(r=>r.MaSP===need.MaSPLinhKien&&r.ViTriTrangThai==='HOAT_DONG'&&r.SanPhamTrangThai==='HOAT_DONG')){const qty=Math.min(left,row.SoLuongKhaDung);if(qty>0)lines.push({MaSP:row.MaSP,MaViTri:row.MaViTri,SoLuongXuat:qty});left-=qty;if(!left)break;}if(left)missing.push(`${need.SKU}: thiếu ${left}`);}
 if(missing.length)throw Error(missing.join('; ')+'. Nhờ quản lý bổ sung nhập kho.');
 $('#lines').innerHTML=lines.map(r=>lineHtml('outgoing',r)).join('');toast('Đã phân bổ đủ nhu cầu từ các vị trí hoạt động. Kiểm tra trước khi gửi.');
}
function detail(kind,id){
 const d=docDefs[kind],r=S.data[kind].find(x=>x[d.key]==id);let data=[];
 if(!r)return;
 const title=`${d.title} · ${d.prefix}-${String(id).padStart(3,'0')}`;
 data.push(['Trạng thái',badge(r.TrangThai)],['Người lập / giao',e(getEmployee(r.MaNVLap||r.MaNVGiao))]);
 if(kind==='incoming')data.push(['Nguồn',e(r.LoaiNhap)],['Ngày chứng từ',formatDate(r.NgayChungTu)],['Thời điểm ghi nhận',formatDate(r.ThoiDiemGhiNhan)]);
 if(kind==='outgoing')data.push(['Loại',r.LoaiXuat==='CAP_PHAT'?'Cấp nguyên liệu':'Xuất thành phẩm'],['Nguồn / người nhận',e(recipientName(r)||'YC-'+r.MaYCLapRap)],['Người duyệt',r.MaNVDuyet?e(getEmployee(r.MaNVDuyet)):'—'],['Thực hiện',formatDate(r.ThoiDiemThucHien)]);
 if(kind==='bom')data.push(['Cấu hình',e(bomName(r))],['Phiên bản','V'+r.PhienBan],['Ban hành',formatDate(r.NgayBanHanh)]);
 if(kind==='jobs')data.push(['Số PC',num(r.SoLuongYeuCau)],['Nhân viên',e(getEmployee(r.MaNVNhan))],['Đã tiếp nhận',num(r.accepted)],['Chờ tiếp nhận',num(r.pending)],['Hạn',formatDate(r.HanMongMuon)]);
 if(kind==='results')data.push(['Yêu cầu','YC-'+r.MaYC],['Đạt',num(r.SoLuongDat)+' · '+e(getLocation(r.MaViTriDat))],['Lỗi',num(r.SoLuongLoi)+' · '+e(getLocation(r.MaViTriLoi))],['Tiếp nhận',formatDate(r.ThoiDiemTiepNhan)]);
 if(r.GhiChu||r.LyDoTuChoi||r.LyDoHuy)data.push(['Ghi chú / lý do',e(r.LyDoTuChoi||r.LyDoHuy||r.GhiChu)]);
 let body='';
 if(r.lines){let cols=[['SẢN PHẨM',x=>productCell(x.MaSP||x.MaSPLinhKien)]];if(kind!=='bom')cols.push(['VỊ TRÍ',x=>e(getLocation(x.MaViTri))]);if(kind==='incoming')cols.push(['NHẬN',x=>num(x.SoLuongNhan)],['LỖI',x=>num(x.SoLuongLoi)],['GIÁ MUA',x=>x.DonGiaNhap===null?'Chưa tính giá thành':num(x.DonGiaNhap)],['KIỂM NHẬN',x=>e(x.KetQuaKiemTra)||'—']);if(kind==='outgoing')cols.push(['XUẤT',x=>num(x.SoLuongXuat)]);if(kind==='bom')cols.push(['ĐỊNH MỨC / PC',x=>num(x.DinhMuc)]);body+=table(cols,r.lines);}
 if(kind==='jobs'){body+=`<h3>Nhu cầu chốt và vật liệu tại khu lắp ráp</h3>`+table([['NGUYÊN LIỆU',x=>productCell(x.MaSPLinhKien)],['ĐỊNH MỨC',x=>num(x.DinhMucChot)],['CẦN',x=>num(x.SoLuongCan)],['ĐÃ CẤP',x=>num(x.SoLuongDaCap)],['CÓ THỂ CẤP TỪ KHO',x=>num(x.SoLuongKhaDung)],['THIẾU',x=>num(x.SoLuongThieu)]],r.needs)+table([['NGUYÊN LIỆU',x=>e(getProduct(x.MaSPLinhKien)?.SKU)],['ĐÃ DÙNG',x=>num(x.SoLuongDaDung)],['CÒN Ở LẮP RÁP',x=>num(x.SoLuongCon)]],r.materials)+`<div class="hint">Số có thể cấp chỉ tính sản phẩm và vị trí đang hoạt động. Kết quả chờ tiếp nhận chưa trừ vật liệu dẫn xuất.</div>`;}
 openModal(title,`<div class="dialog-content"><dl class="detail-grid">${data.map(([k,v])=>`<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl>${body}</div><div class="dialog-actions"><button data-close="editor">Đóng</button><button data-print class="primary">In chứng từ</button></div>`,'CHI TIẾT & ĐỐI CHIẾU');
}
function catalogEditor(kind,id=null){
 const [name,key]=catalogDefs[kind],r=id?S.data[kind].find(x=>x[key]==id):{};let f='';
 if(kind==='products')f=field('SKU','SKU','text',r.SKU)+field('TenSP','Tên sản phẩm','text',r.TenSP)+field('MaLoai','Phân nhóm','select','',options(S.data.categories,'MaLoai',x=>x.TenLoai,r.MaLoai))+field('LoaiMatHang','Loại hàng','select','',`<option value="NGUYEN_LIEU">Nguyên liệu</option><option value="THANH_PHAM" ${r.LoaiMatHang==='THANH_PHAM'?'selected':''}>Thành phẩm</option>`)+field('DonViTinh','Đơn vị tính','text',r.DonViTinh||'cái')+field('MoTa','Mô tả','textarea',r.MoTa,null,false);
 if(kind==='categories')f=field('TenLoai','Tên loại','text',r.TenLoai)+field('MoTa','Mô tả','textarea',r.MoTa,null,false,false,255);
 if(kind==='suppliers')f=field('TenNCC','Tên nhà cung cấp','text',r.TenNCC)+field('SoDienThoai','Điện thoại','text',r.SoDienThoai,null,false)+field('DiaChi','Địa chỉ','text',r.DiaChi,null,false,true);
 if(kind==='locations')f=field('MaViTriHienThi','Mã vị trí','text',r.MaViTriHienThi)+field('KhuVuc','Khu vực','text',r.KhuVuc,null,false)+field('Ke','Kệ','text',r.Ke,null,false)+field('Tang','Tầng','text',r.Tang,null,false);
 if(kind==='employees')f=field('HoTen','Họ tên','text',r.HoTen)+field('ChucVu','Chức vụ','text',r.ChucVu,null,false)+field('SoDienThoai','Điện thoại','text',r.SoDienThoai,null,false);
 if(kind!=='categories')f+=field('TrangThai','Trạng thái','select','',options((kind==='employees'?['DANG_LAM','NGUNG_LAM']:['HOAT_DONG','NGUNG']).map(x=>({v:x})),'v',x=>labels[x.v],r.TrangThai|| (kind==='employees'?'DANG_LAM':'HOAT_DONG')));
 openModal(`${id?'Sửa':'Thêm'} ${name.toLowerCase()}`,`<form id="catalog-form" data-kind="${kind}" data-id="${id||''}"><div class="dialog-content"><div class="form-grid">${f}</div><div class="hint">${kind==='products'?'Sản phẩm đã có chứng từ giữ nguyên SKU, loại hàng và đơn vị tính. ':''}${kind==='categories'?'Loại sản phẩm đã được dùng không thể xóa.':kind==='employees'?'Nhân viên còn việc đang xử lý cần hoàn thành hoặc hủy yêu cầu hợp lệ trước khi ngừng làm.':'Đối tượng đã được dùng nên ngừng sử dụng thay vì xóa.'}</div><div class="form-error" role="alert"></div></div><div class="dialog-actions"><button type="button" data-close="editor">Quay lại</button><button class="primary" type="submit">Lưu</button></div></form>`,'DANH MỤC');
}
function accountEditor(id=null){const r=id?S.data.accounts.find(a=>a.MaTK==id):{};let f=id?`<div class="hint wide">Tài khoản: <strong>${e(r.TenDangNhap)}</strong> · ${e(getEmployee(r.MaNV))}</div>`:field('MaNV','Nhân viên','select','',options(activeList('employees').filter(n=>!n.MaTK),'MaNV',n=>n.HoTen))+field('TenDangNhap','Tên đăng nhập');f+=field('VaiTro','Vai trò','select','',options(Object.keys(roleNames).map(v=>({v})),'v',r=>roleNames[r.v],r.VaiTro||'NHAN_VIEN'))+field('TrangThai','Trạng thái','select','',`<option value="HOAT_DONG">Hoạt động</option><option value="KHOA" ${r.TrangThai==='KHOA'?'selected':''}>Khóa</option>`)+field('password',id?'Mật khẩu mới (để trống nếu giữ nguyên)':'Mật khẩu (ít nhất 8 ký tự)','password','',null,!id,true);openModal(id?'Sửa tài khoản':'Thêm tài khoản',`<form id="account-form" data-id="${id||''}"><div class="dialog-content"><div class="form-grid">${f}</div><div class="form-error" role="alert"></div></div><div class="dialog-actions"><button type="button" data-close="editor">Quay lại</button><button type="submit" class="primary">Lưu tài khoản</button></div></form>`,'QUẢN TRỊ TÀI KHOẢN');}
let confirmResolve;
function confirmAction(title,message,reason=false,summary=''){$('#confirm-title').textContent=title;$('#confirm-message').textContent=message;$('#confirm-details').innerHTML=summary;$('#confirm-details').hidden=!summary;$('#confirmation').classList.toggle('with-details',!!summary);$('#reason-label').hidden=!reason;$('#reason-label textarea').required=reason;$('#reason-label textarea').value='';$('#confirmation').showModal();return new Promise(resolve=>confirmResolve=resolve);}
$('#confirm-form').addEventListener('submit',ev=>{ev.preventDefault();const reason=$('#reason-label textarea').value;confirmResolve?.({reason});confirmResolve=null;$('#confirmation').close();});
$('#confirmation').addEventListener('close',()=>{confirmResolve?.(null);confirmResolve=null;});
function stockConfirmation(kind,id){
 const def=docDefs[kind],r=S.data[kind].find(x=>x[def.key]==id);if(!r)throw Error('Chứng từ không còn trong danh sách. Nhấn Làm mới để kiểm tra.');
 const rows=[];let source='';
 if(kind==='incoming'){
  source=r.LoaiNhap==='NCC'?'Nhà cung cấp: '+(S.data.suppliers.find(n=>n.MaNCC==r.MaNCC)?.TenNCC||'#'+r.MaNCC):'Nguồn lắp ráp: KQ-'+r.MaNguonKetQua;
  for(const line of r.lines)rows.push({...line,physical:Number(line.SoLuongNhan),faulty:Number(line.SoLuongLoi)});
 }else if(kind==='outgoing'){
  const job=S.data.jobs.find(j=>j.MaYC==r.MaYCLapRap);
  source=r.LoaiXuat==='CAP_PHAT'?`Người nhận: ${getEmployee(job?.MaNVNhan||r.MaNVLap)} · YC-${r.MaYCLapRap}`:'Người / bộ phận nhận: '+r.TenNguoiNhan;
  for(const line of r.lines)rows.push({...line,physical:-Number(line.SoLuongXuat),faulty:0});
 }else{
  const job=S.data.jobs.find(j=>j.MaYC==r.MaYC),bom=S.data.bom.find(b=>b.MaBOM==job?.MaBOM);if(!bom)throw Error('Chưa tải đủ thông tin thành phẩm. Nhấn Làm mới để kiểm tra.');
  source=`Người giao: ${getEmployee(r.MaNVLap)} · YC-${r.MaYC}`;
  if(Number(r.SoLuongDat))rows.push({MaSP:bom.MaSPThanhPham,MaViTri:r.MaViTriDat,physical:Number(r.SoLuongDat),faulty:0});
  if(Number(r.SoLuongLoi))rows.push({MaSP:bom.MaSPThanhPham,MaViTri:r.MaViTriLoi,physical:Number(r.SoLuongLoi),faulty:Number(r.SoLuongLoi)});
 }
 const delta=n=>(n>0?'+':'')+num(n);
 return `<strong>${e(def.prefix)}-${e(String(id).padStart(3,'0'))}</strong><p>${e(source)}</p><ul class="stock-summary">${rows.map(line=>{const p=getProduct(line.MaSP);return `<li><strong>${e(p?.SKU)} · ${e(p?.TenSP)}</strong><span>Vị trí: ${e(getLocation(line.MaViTri))} · Đơn vị: ${e(p?.DonViTinh)}</span><span>Tồn thực tế: <b>${delta(line.physical)}</b> · Hàng lỗi: <b>${delta(line.faulty)}</b> · Khả dụng: <b>${delta(line.physical-line.faulty)}</b></span></li>`;}).join('')}</ul>`;
}
let transitionPending=false;
async function transition(kind,id,action){
 if(transitionPending)throw Error('Đang kiểm tra hoặc xử lý chứng từ. Vui lòng chờ.');
 const version=authVersion;
 transitionPending=true;
 try{
  const names={commit:'Chốt nhập kho',send:'Gửi chứng từ',approve:'Duyệt và bàn giao',reject:'Từ chối chứng từ',publish:'Ban hành BOM',assign:'Giao yêu cầu',receive:'Nhận việc',accept:'Tiếp nhận thành phẩm',cancel:'Hủy yêu cầu'};
  const messages={commit:'Tồn tăng theo số thực nhận và số lỗi. Phiếu sẽ khóa sau khi chốt.',approve:'Tồn giảm khi duyệt đồng thời bàn giao. Toàn phiếu phải đủ hàng khả dụng.',accept:'Tự sinh nhập thành phẩm; không trừ nguyên liệu ở kệ lần hai.',publish:'Phiên bản đang áp dụng trước đó sẽ ngừng. Việc đã giao giữ định mức cũ.',assign:'Nhu cầu vật liệu sẽ được chốt theo BOM và số PC.',cancel:'Chỉ hủy trước khi đã cấp vật liệu.'};
  let summary='';
  if(['commit','approve','accept'].includes(action)){
   await reload();
   const r=S.data[kind].find(x=>x[docDefs[kind].key]==id),expected={commit:'NHAP',approve:'CHO_DUYET',accept:'CHO_TIEP_NHAN'};
   if(!r||r.TrangThai!==expected[action])throw Error('Chứng từ đã đổi trạng thái. Kiểm tra danh sách mới trước khi thao tác.');
   summary=stockConfirmation(kind,id);
  }
  const answer=await confirmAction(names[action],messages[action]||'Chứng từ sẽ chuyển trạng thái theo quyền của tài khoản.', ['reject','cancel'].includes(action),summary);
  if(!answer)return;
  const b=await api(`/api/actions/${kind}/${id}/${action}`,'POST',answer);toast(b.message);await reload();
 }finally{if(version===authVersion)transitionPending=false;}
}
function reportQuery(){const period=$('#period').value,y=Number($('#report-year').value),m=Number($('#report-month').value),q=Number($('#report-quarter').value);let from,to;if(period==='custom'){from=$('#report-from').value;to=$('#report-to').value;}else{const first=period==='year'?1:period==='quarter'?(q-1)*3+1:m;const length=period==='year'?12:period==='quarter'?3:1;from=`${y}-${String(first).padStart(2,'0')}-01`;const next=new Date(Date.UTC(y,first-1+length,1));to=next.toISOString().slice(0,10);}return new URLSearchParams({from,to,type:$('#report-type').value,location:$('#report-location').value});}
function invalidateReport(){S.report=null;reportRequest++;$('#report-results').innerHTML='<div class="panel empty">Bộ lọc đã thay đổi. Nhấn “Xem báo cáo” để cập nhật trước khi in hoặc xuất CSV.</div>';}
async function runReport(){const query=reportQuery(),version=++reportRequest;const b=await api('/api/report?'+query);if(version!==reportRequest||S.page!=='report'||query.toString()!==reportQuery().toString())return;S.report=query;$('#report-results').innerHTML=panel('Báo cáo '+b.start.slice(0,10)+' → '+b.end.slice(0,10),`<div class="hint">Khoảng [${e(b.start.slice(0,10))}, ${e(b.end.slice(0,10))}), không gồm đầu kỳ tiếp theo. Từng dòng là một SKU và vị trí.<br>Loại hàng: ${e(query.get('type')?kindText(query.get('type')):'Tất cả')} · Vị trí: ${e(query.get('location')?getLocation(query.get('location')):'Tất cả')}.</div>`+table([['SKU',r=>e(r.SKU)],['VỊ TRÍ',r=>e(getLocation(r.MaViTri))],['ĐƠN VỊ',r=>e(r.DonViTinh)],['TỒN ĐẦU',r=>num(r.TonDauKy)],['NHẬP',r=>num(r.NhapTrongKy)],['XUẤT',r=>num(r.XuatTrongKy)],['TỒN CUỐI',r=>num(r.TonCuoiKy)],['KHÔNG BÁN',r=>num(r.KhongBanCuoiKy)],['KHẢ DỤNG',r=>`<span class="number">${num(r.KhaDungCuoiKy)}</span>`]],b.rows,'Không có biến động trước mốc cuối cho bộ lọc này.'));}
document.addEventListener('input',ev=>{if(ev.target.id==='search')filterTable();if(ev.target.closest('#report-form'))invalidateReport();});
document.addEventListener('change',ev=>{
 if(['type-filter','location-filter','state-filter','category-filter'].includes(ev.target.id))filterTable();
 if(ev.target.name==='LoaiXuat'){toggleOutgoing();$('#lines').innerHTML=lineHtml('outgoing');}
 if(ev.target.id==='period'){const v=ev.target.value;for(const [id,visible] of [['year',v!=='custom'],['month',v==='month'],['quarter',v==='quarter'],['from',v==='custom'],['to',v==='custom']]){const input=$('#report-'+id);input.closest('label').hidden=!visible;input.disabled=!visible;}}
 if(ev.target.closest('#report-form'))invalidateReport();
});
document.addEventListener('click',async ev=>{
 const b=ev.target.closest('button');if(!b)return;
 try{
  if(b.dataset.nav){location.hash=b.dataset.nav;setMenu(false);}
  if(b.dataset.close){if(b.dataset.close==='editor'&&editorSaving)return;$('#'+b.dataset.close).close();}
  if(b.hasAttribute('data-refresh'))await reload();
  if(b.hasAttribute('data-print')){if(S.page==='report'&&!S.report&&!$('#editor').open)throw Error('Xem báo cáo trước khi in.');window.print();}
  if(b.id==='mobile-menu')toggleSidebar();
  if(['sidebar-close','menu-backdrop'].includes(b.id))setMenu(false);
  if(b.id==='logout'){b.disabled=true;await authLock(async()=>{invalidateAuth();S.csrf=(await api('/api/session')).csrf;await api('/api/logout','POST',{});showLogin();},true);}
  if(b.dataset.new)documentEditor(b.dataset.new);
  if(b.dataset.edit)documentEditor(b.dataset.edit,b.dataset.id);
  if(b.dataset.detail)detail(b.dataset.detail,b.dataset.id);
  if(b.dataset.addLine)$('#lines').insertAdjacentHTML('beforeend',lineHtml(b.dataset.addLine));
  if(b.hasAttribute('data-remove-line'))b.closest('.line-grid').remove();
  if(b.id==='suggest-allocation')allocation();
  if(b.dataset.allocate){documentEditor('outgoing',null,{LoaiXuat:'CAP_PHAT',MaYCLapRap:b.dataset.allocate});allocation();}
  if(b.dataset.resultJob)documentEditor('results',null,{MaYC:b.dataset.resultJob});
  if(b.dataset.action){b.disabled=true;await transition(b.dataset.kind,b.dataset.id,b.dataset.action);}
  if(b.dataset.deleteDoc){if(await confirmAction('Xóa bản nháp','Bản nháp này chưa làm thay đổi tồn.')){await api(`/api/documents/${b.dataset.deleteDoc}/${b.dataset.id}`,'DELETE');$('#editor').close();await reload();toast('Đã xóa nháp.');}}
  if(b.dataset.catalogTab){S.catalog=b.dataset.catalogTab;render();}
  if(b.dataset.catalogNew)catalogEditor(b.dataset.catalogNew);
  if(b.dataset.catalogEdit)catalogEditor(b.dataset.catalogEdit,b.dataset.id);
  if(b.dataset.catalogDelete){if(await confirmAction('Xóa danh mục','Chỉ xóa được đối tượng chưa có tham chiếu. Nếu đã có chứng từ, hãy chọn ngừng sử dụng.')){await api(`/api/catalog/${b.dataset.catalogDelete}/${b.dataset.id}`,'DELETE');await reload();toast('Đã xóa danh mục.');}}
  if(b.hasAttribute('data-account-new'))accountEditor();
  if(b.dataset.accountEdit)accountEditor(b.dataset.accountEdit);
  if(b.dataset.accountDelete){if(await confirmAction('Xóa tài khoản','Tài khoản của nhân viên đã có chứng từ phải được khóa để giữ lịch sử.')){await api('/api/accounts/'+b.dataset.accountDelete,'DELETE');await reload();toast('Đã xóa tài khoản.');}}
  if(b.id==='csv-export'){if(!S.report)throw Error('Xem báo cáo trước khi xuất CSV.');location.href='/api/report?'+S.report+'&format=csv';}
  if(b.id==='backup-create'){b.disabled=true;const x=await api('/api/backup','POST',{});S.backup=x.file;render();toast(x.message);}
  if(b.id==='restore-test'){
   if(!await confirmAction('Kiểm chứng khôi phục','Khôi phục vào bản thử nghiệm riêng và kiểm tra dữ liệu, đăng nhập, giao dịch. Dữ liệu đang dùng được giữ nguyên.'))return;
   b.disabled=true;$('#backup-results .backup-result')?.remove();$('#backup-results').insertAdjacentHTML('beforeend','<p id="restore-progress" role="status">Đang khôi phục và đối chiếu…</p>');
   try{const x=await api('/api/restore-test','POST',{file:S.backup});$('#backup-results')?.insertAdjacentHTML('beforeend',`<div class="backup-result"><strong>Khôi phục đạt</strong><br>${x.result.tables} bảng · ${x.result.views} view · ${x.result.routines} routine · ${x.result.triggers} trigger<br>${x.result.data_matched?'Dữ liệu khớp với bản sao lưu tại thời điểm tạo.':'Bản sao lưu cũ: đã kiểm tra cấu trúc và khôi phục, chưa có thông tin đối chiếu dữ liệu lúc sao lưu.'}<br>Đăng nhập tài khoản kiểm thử và chốt nhập thử thành công. Dữ liệu chính không đổi.</div>`);toast(x.message);}
   finally{$('#restore-progress')?.remove();}
  }
  if(b.dataset.sort!==undefined){const table=b.closest('table'),index=Number(b.dataset.sort),body=table.tBodies[0],dir=b.dataset.direction==='asc'?-1:1;b.dataset.direction=dir===1?'asc':'desc';[...body.rows].sort((a,z)=>{let x=a.cells[index]?.textContent.trim()||'',y=z.cells[index]?.textContent.trim()||'';const nx=Number(x.replaceAll('.','').replaceAll(',','.')),ny=Number(y.replaceAll('.','').replaceAll(',','.'));return dir*(x&&y&&Number.isFinite(nx)&&Number.isFinite(ny)?nx-ny:x.localeCompare(y,'vi',{numeric:true}));}).forEach(r=>body.append(r));}
 }catch(error){if(!(error instanceof StaleRequestError))toast(error.message,true);}finally{if(b.isConnected)b.disabled=false;}
});
document.addEventListener('submit',async ev=>{
 if(ev.target.id==='confirm-form')return;
 const form=ev.target;if(!['login-form','document-form','catalog-form','account-form','report-form'].includes(form.id))return;ev.preventDefault();const inEditor=!!form.closest('#editor');if(inEditor&&editorSaving||form.id==='login-form'&&loginPending)return;const btn=form.querySelector('[type="submit"]');btn.disabled=true;
 try{
  if(form.id==='login-form'){const credentials=Object.fromEntries(new FormData(form));await authLock(async()=>{invalidateAuth();S.csrf=(await api('/api/session')).csrf;const x=await api('/api/login','POST',credentials);S.user=x.user;S.csrf=x.csrf;$('#login-error').textContent='';await reload();},true);return;}
  if(form.id==='report-form'){await runReport();return;}
  if(form.dataset.saved){editorBusy(true);btn.textContent='Đang cập nhật…';await reload();$('#editor').close();toast(form.dataset.savedMessage);return;}
  let data={},url;const id=form.dataset.id;
  if(form.id==='document-form'){
   const header=form.querySelector('.form-grid');header.querySelectorAll('input,select,textarea').forEach(el=>data[el.name]=el.value);
   if(form.querySelector('#lines'))data.lines=[...form.querySelectorAll('.line-grid')].map(row=>{const d={};row.querySelectorAll('input,select').forEach(el=>d[el.name]=el.value);return d;});
   url='/api/documents/'+form.dataset.kind+(id?'/'+id:'');
  }else {data=Object.fromEntries(new FormData(form));url=form.id==='catalog-form'?'/api/catalog/'+form.dataset.kind+(id?'/'+id:''):'/api/accounts'+(id?'/'+id:'');}
  const headers={};
  if(form.id==='document-form'&&!id){
   form.dataset.operation ||= crypto.randomUUID();headers['Idempotency-Key']=form.dataset.operation;
   if(form.dataset.uncertain)data=JSON.parse(form.dataset.retryPayload);
   else form.dataset.retryPayload=JSON.stringify(data);
  }
  editorBusy(true);btn.textContent='Đang lưu…';const x=await api(url,id?'PUT':'POST',data,headers);delete form.dataset.uncertain;form.dataset.saved='1';form.dataset.savedMessage=x.message||'Đã lưu.';S.needsSync=true;form.querySelectorAll('input,select,textarea').forEach(el=>el.disabled=true);btn.textContent='Đang cập nhật…';await reload();$('#editor').close();toast(form.dataset.savedMessage);
 }catch(error){
  if(error instanceof StaleRequestError)return;
  if(form.id==='document-form'&&!form.dataset.id&&!form.dataset.saved){
   if(error instanceof ApiError&&(error.status===400||error.saveNotCommitted)){delete form.dataset.uncertain;delete form.dataset.operation;delete form.dataset.retryPayload;}
   else if(error instanceof NetworkError||error instanceof ApiError&&(error.status===409||error.status>=500))form.dataset.uncertain='1';
  }
  const message=form.dataset.saved?'Đã lưu thành công, nhưng chưa cập nhật được danh sách. Nhấn Tải lại dữ liệu để thử lại. '+error.message:form.dataset.uncertain?'Chưa xác định được kết quả lưu. Nhấn Thử lại lưu trên biểu mẫu này để kiểm tra; không tạo phiếu mới. '+(error instanceof NetworkError?'':error.message):error.message;
  if(form.id==='login-form')$('#login-error').textContent=message;else if(form.querySelector('.form-error')){const box=form.querySelector('.form-error');box.textContent=message;box.scrollIntoView?.({block:'nearest'});}else toast(message,true);
 }finally{if(inEditor&&$('#editor').contains(form))editorBusy(false);if(btn.isConnected){btn.disabled=form.id==='login-form'?loginPending:false;if(inEditor)btn.textContent=form.dataset.saved?'Tải lại dữ liệu':form.dataset.uncertain?'Thử lại lưu':form.id==='document-form'?'Lưu nháp':form.id==='account-form'?'Lưu tài khoản':'Lưu';}}
});
window.addEventListener('hashchange',render);
document.addEventListener('keydown',ev=>{if(ev.key==='Escape'&&$('.sidebar').classList.contains('open'))setMenu(false);});
window.matchMedia?.('(max-width:760px)').addEventListener('change',()=>setMenu(false));
$('#login-form [type="submit"]').disabled=true;
(async()=>{try{await syncSession();}catch(error){if(!(error instanceof StaleRequestError))$('#login-error').textContent='Backend chưa sẵn sàng: '+error.message;}})();
