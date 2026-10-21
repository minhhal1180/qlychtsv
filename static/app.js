'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const STATUS = {NEW:'Mới gửi',IN_PROGRESS:'Đang xử lý',WAITING_STUDENT:'Chờ bổ sung',COMPLETED:'Hoàn tất',CANCELLED:'Đã hủy',REJECTED:'Từ chối'};
const ROLE = {STUDENT:'Sinh viên',STAFF:'Cán bộ hỗ trợ',ADMIN:'Quản trị viên'};
const EVENT = {CREATE:'Đã tạo yêu cầu',ACCEPT:'Cán bộ đã tiếp nhận',ASK:'Cần bổ sung thông tin',SUPPLEMENT:'Sinh viên đã bổ sung',COMPLETE:'Đã hoàn tất yêu cầu',CANCEL:'Đã hủy yêu cầu',REJECT:'Đã từ chối yêu cầu',REOPEN:'Đã mở lại yêu cầu',MESSAGE:'Có trao đổi mới',IN_PROGRESS:'Đang được xử lý',WAITING_STUDENT:'Cần bổ sung thông tin',COMPLETED:'Đã hoàn tất yêu cầu'};
let currentUser, csrf, types = [], activePage = '', renderVersion = 0, toastTimer;
const filters = {q:'',status:'',mine:false};
const date = value => new Date(value).toLocaleDateString('vi-VN',{day:'2-digit',month:'2-digit',year:'numeric'});
const time = value => new Date(value).toLocaleString('vi-VN');
const badge = status => `<span class="status ${escapeHTML(status)}">${escapeHTML(STATUS[status] || status)}</span>`;
function toast(message) { $('#toast').textContent = message; $('#toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').hidden = true, 4500); }
async function api(path, options = {}) {
  const settings = {...options, headers:{...options.headers}};
  if (settings.method && settings.method !== 'GET') {
    settings.headers['X-CSRF-Token'] = csrf || '';
    if (!settings.headers['Idempotency-Key'] && path !== '/login' && path !== '/logout') settings.headers['Idempotency-Key'] = crypto.randomUUID();
    if (!(settings.body instanceof FormData)) {
      settings.headers['Content-Type'] = 'application/json';
      settings.body = JSON.stringify(settings.body || {});
    }
  }
  const response = await fetch('/api' + path, settings);
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== '/login') showLogin();
    throw new Error(data.error || 'Không thể thực hiện thao tác.');
  }
  return data;
}
async function write(path, element, body, method = 'POST') {
  // Keep one operation key after a lost response; editing the form starts a new operation.
  element.dataset.retryKey ||= crypto.randomUUID();
  const result = await api(path, {method, body, headers:{'Idempotency-Key':element.dataset.retryKey}});
  delete element.dataset.retryKey;
  return result;
}
document.addEventListener('input', event => {
  const form = event.target.closest('form');
  if (form) delete form.dataset.retryKey;
  if (event.target.id === 'action-body') document.querySelectorAll('[data-action]').forEach(button=>delete button.dataset.retryKey);
});
function showLogin() { currentUser = null; csrf = ''; renderVersion++; $('#workspace').hidden = true; $('#login-screen').hidden = false; $('#main').replaceChildren(); $('#create-dialog').close(); }
function heading(title, subtitle, extra = '') { return `<div class="breadcrumb">Không gian làm việc / ${escapeHTML(title)}</div><div class="page-heading"><div><span class="eyebrow">STUDENT SUPPORT</span><h1>${escapeHTML(title)}</h1><p>${escapeHTML(subtitle)}</p></div>${extra}</div>`; }
function empty(title, subtitle) { return `<div class="empty"><strong>${escapeHTML(title)}</strong>${escapeHTML(subtitle)}</div>`; }
function go(path) { if (location.hash === '#' + path) route(); else location.hash = path; }
function navButton(page, icon, label) { return `<button class="nav-item ${activePage === page ? 'active' : ''}" data-nav="${page}"><span class="nav-icon" aria-hidden="true">${icon}</span>${label}</button>`; }
function navigation() {
  $('#navigation').innerHTML = currentUser.role === 'ADMIN'
    ? navButton('types','▦','Loại yêu cầu') + navButton('users','♙','Tài khoản')
    : navButton('requests','▤',currentUser.role === 'STUDENT' ? 'Yêu cầu của tôi' : 'Hàng đợi yêu cầu') + navButton('notifications','♧','Thông báo');
  document.querySelectorAll('[data-nav]').forEach(button => button.onclick = () => go(button.dataset.nav));
}
async function boot() {
  const data = await api('/me'); currentUser = data.user; csrf = data.csrf;
  $('#login-screen').hidden = true; $('#workspace').hidden = false;
  $('#user-name').textContent = currentUser.name; $('#user-role').textContent = ROLE[currentUser.role];
  $('#user-avatar').textContent = currentUser.name.split(' ').slice(-2).map(part => part[0]).join('');
  types = (await api('/types')).items;
  await route();
}
async function route() {
  if (!currentUser) return;
  const version = ++renderVersion;
  const parts = location.hash.slice(1).split('/');
  const target = parts[0] || (currentUser.role === 'ADMIN' ? 'types' : 'requests');
  activePage = target === 'request' ? 'requests' : target;
  navigation();
  $('#main').innerHTML = '<p class="muted">Đang tải dữ liệu…</p>';
  try {
    if (target === 'request' && /^\d+$/.test(parts[1])) await renderDetail(Number(parts[1]), version);
    else if (target === 'notifications' && currentUser.role !== 'ADMIN') await renderNotifications(version);
    else if (target === 'types' && currentUser.role === 'ADMIN') await renderTypes(version);
    else if (target === 'users' && currentUser.role === 'ADMIN') await renderUsers(version);
    else if (currentUser.role !== 'ADMIN') await renderList(version);
    else go('types');
  } catch (error) {
    if (version === renderVersion) { $('#main').innerHTML = empty('Không thể tải dữ liệu', error.message); toast(error.message); }
  }
}
async function renderList(version) {
  const params = new URLSearchParams({q:filters.q,status:filters.status,mine:filters.mine?'1':'0'});
  const data = await api('/requests?' + params);
  if (version !== renderVersion) return;
  const counts = data.counts, total = Object.values(counts).reduce((a,b)=>a+b,0);
  const stats = [['Tổng yêu cầu',total,'▤'],['Đang xử lý',counts.IN_PROGRESS,'◷'],['Chờ bổ sung',counts.WAITING_STUDENT,'↗'],['Đã hoàn tất',counts.COMPLETED,'✓']];
  const student = currentUser.role === 'STUDENT';
  $('#main').innerHTML = heading(student?'Yêu cầu của tôi':'Hàng đợi yêu cầu',student?'Gửi yêu cầu, theo dõi tiến trình và nhận hỗ trợ từ nhà trường.':'Tiếp nhận và đồng hành giải quyết các yêu cầu của sinh viên.',student?'<button class="primary" id="new-request">＋ Tạo yêu cầu</button>':'')
    + `<div class="stats">${stats.map(([label,value,symbol])=>`<div class="stat"><div><div class="stat-label">${label}</div><strong>${value}</strong></div><span class="stat-symbol" aria-hidden="true">${symbol}</span></div>`).join('')}</div>`
    + `<section class="panel"><div class="panel-title"><div><h3>Danh sách yêu cầu</h3><p>${student?'Mọi yêu cầu của bạn, tại một nơi.':'Hàng đợi chung của bộ phận hỗ trợ sinh viên.'}</p></div><span class="muted">${data.items.length} yêu cầu</span></div><form id="filter-form" class="filterbar"><input class="search" name="q" aria-label="Tìm theo mã hoặc tiêu đề" placeholder="⌕  Tìm theo mã hoặc tiêu đề…" value="${escapeHTML(filters.q)}"><select name="status" aria-label="Lọc trạng thái"><option value="">Tất cả trạng thái</option>${Object.entries(STATUS).map(([key,value])=>`<option value="${key}" ${filters.status===key?'selected':''}>${value}</option>`).join('')}</select>${!student?`<label><input type="checkbox" name="mine" ${filters.mine?'checked':''}>Tôi phụ trách</label>`:''}<button type="submit">Lọc</button></form>`
    + (data.items.length ? `<div class="table-wrap"><table><thead><tr><th>MÃ YÊU CẦU</th><th>NỘI DUNG</th><th>TRẠNG THÁI</th><th>NGÀY TẠO</th><th></th></tr></thead><tbody>${data.items.map(item=>`<tr><td><span class="ticket-code">${item.code}</span></td><td><button class="ticket-title" data-ticket="${item.id}">${escapeHTML(item.title || '(Tiêu đề trống)')}</button><span class="ticket-sub">${escapeHTML(item.type_name)}${!student?' · '+escapeHTML(item.student_name):''}</span></td><td>${badge(item.status)}</td><td>${date(item.created_at)}<div class="ticket-sub">Cập nhật ${date(item.updated_at)}</div></td><td><button class="text-button" data-ticket="${item.id}" aria-label="Xem ${item.code}">Chi tiết ↗</button></td></tr>`).join('')}</tbody></table></div>` : empty('Chưa có yêu cầu phù hợp','Thử đổi bộ lọc hoặc tạo yêu cầu hỗ trợ mới.'))
    + `<div class="table-bottom">Hiển thị ${data.items.length} yêu cầu · Số đếm tính theo trạng thái hiện tại, trước bộ lọc tìm kiếm và trạng thái</div></section>`;
  if (student) $('#new-request').onclick = openCreate;
  $('[name=status]').onchange = () => $('#filter-form').requestSubmit();
  const mine = $('[name=mine]'); if (mine) mine.onchange = () => $('#filter-form').requestSubmit();
  $('#filter-form').onsubmit = event => { event.preventDefault(); const form = new FormData(event.target); filters.q = form.get('q'); filters.status = form.get('status'); filters.mine = form.get('mine') === 'on'; route(); };
  bindTickets();
}
function bindTickets() { document.querySelectorAll('[data-ticket]').forEach(button => button.onclick = () => go('request/' + button.dataset.ticket)); }
async function openCreate() {
  try {
    types = (await api('/types')).items;
    $('#create-form').reset(); delete $('#create-form').dataset.retryKey; $('#create-error').textContent = '';
    $('#create-type').innerHTML = '<option value="">Chọn loại yêu cầu</option>' + types.map(type=>`<option value="${type.id}">${escapeHTML(type.name)}</option>`).join('');
    $('#create-dialog').showModal();
  } catch(error) { toast(error.message); }
}
function filesHTML(files) { return files.map(file=>`<a class="file-link" href="/api/attachments/${file.id}">↙ ${escapeHTML(file.filename)} · ${Math.ceil(file.size/1024)} KB</a>`).join(''); }
async function renderDetail(id, version) {
  const data = await api('/requests/' + id); if (version !== renderVersion) return;
  const item = data.item, student = currentUser.role === 'STUDENT', owner = item.assignee_id === currentUser.id;
  const actions = [];
  if (student && ['NEW','IN_PROGRESS'].includes(item.status)) actions.push(['cancel','Hủy yêu cầu','danger']);
  if (student && ['COMPLETED','REJECTED'].includes(item.status)) actions.push(['reopen','Mở lại yêu cầu','primary']);
  if (!student && item.status === 'NEW') actions.push(['accept','Tiếp nhận yêu cầu','primary'],['reject','Từ chối','danger']);
  if (!student && owner && item.status === 'IN_PROGRESS') actions.push(['ask','Yêu cầu bổ sung',''],['complete','Hoàn tất','primary'],['reject','Từ chối','danger']);
  const canMessage = student ? item.status === 'WAITING_STUDENT' : owner && ['IN_PROGRESS','WAITING_STUDENT'].includes(item.status);
  const needsBody = actions.some(([key])=>['ask','complete','reject'].includes(key));
  $('#main').innerHTML = heading(item.code,item.type_name,'<button id="back-list">← Danh sách</button>')
    + `<div class="detail-grid"><div><section class="panel section-pad"><div class="page-heading"><h2>${escapeHTML(item.title)}</h2>${badge(item.status)}</div><p class="body-text">${escapeHTML(item.content)}</p>${filesHTML(data.attachments.filter(file=>!file.message_id))}</section>`
    + `<section class="panel section-pad section-gap"><h3>Trao đổi & bổ sung</h3><div class="message-list">${data.messages.map(message=>`<article class="message"><strong>${escapeHTML(message.sender_name)}</strong> <span class="ticket-sub">${ROLE[message.sender_role]}</span><small>${time(message.created_at)}</small><p>${escapeHTML(message.body)}</p>${filesHTML(data.attachments.filter(file=>file.message_id===message.id))}</article>`).join('') || '<p class="muted">Chưa có trao đổi.</p>'}</div>${canMessage?'<form id="message-form"><label>Nội dung trao đổi<textarea name="body" rows="3" maxlength="10000" placeholder="Nhập nội dung hoặc đính kèm tệp…"></textarea></label><label>Tệp đính kèm<input name="files" type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.txt"></label><p class="help">Tối đa 3 tệp, 5 MB/tệp.</p><button class="primary" type="submit">Gửi '+(student?'bổ sung':'trao đổi')+' →</button></form>':''}</section>`
    + (actions.length?`<section class="panel section-pad section-gap"><h3>Thao tác xử lý</h3>${needsBody?'<label>Nội dung xử lý<textarea id="action-body" rows="3" maxlength="10000" placeholder="Nhập kết quả, lý do từ chối hoặc nội dung cần bổ sung…"></textarea></label>':''}<div class="action-row">${actions.map(([action,label,cls])=>`<button data-action="${action}" class="${cls}">${label}</button>`).join('')}</div><p class="error" id="action-error" role="alert"></p></section>`:'')
    + `</div><aside><section class="panel section-pad"><h3>Thông tin yêu cầu</h3><dl class="detail-meta"><div><dt>SINH VIÊN</dt><dd>${escapeHTML(item.student_name)}</dd></div><div><dt>NGƯỜI PHỤ TRÁCH</dt><dd>${escapeHTML(item.assignee_name || 'Chưa tiếp nhận')}</dd></div><div><dt>LOẠI YÊU CẦU</dt><dd>${escapeHTML(item.type_name)}</dd></div><div><dt>NGÀY TẠO</dt><dd>${time(item.created_at)}</dd></div><div><dt>CẬP NHẬT GẦN NHẤT</dt><dd>${time(item.updated_at)}</dd></div></dl></section><section class="panel section-pad section-gap"><h3>Lịch sử xử lý</h3>${data.history.map(event=>`<div class="history-item"><strong>${escapeHTML(EVENT[event.action]||event.action)}</strong><br>${escapeHTML(event.actor_name)}<small>${time(event.created_at)}</small><small>${event.from_status?STATUS[event.from_status]+' → ':''}${STATUS[event.to_status]}</small></div>`).join('')}</section></aside></div>`;
  $('#back-list').onclick = () => go('requests');
  document.querySelectorAll('[data-action]').forEach(button => button.onclick = async () => {
    const action = button.dataset.action;
    if (['cancel','reject'].includes(action) && !confirm(action==='cancel'?'Bạn muốn hủy yêu cầu này?':'Bạn muốn từ chối yêu cầu này?')) return;
    const buttons = document.querySelectorAll('[data-action]'); buttons.forEach(b=>b.disabled=true);
    try { await write(`/requests/${id}/action`,button,{action,body:$('#action-body')?.value || ''}); toast('Đã cập nhật yêu cầu.'); await route(); }
    catch (error) { $('#action-error').textContent = error.message; buttons.forEach(b=>b.disabled=false); }
  });
  if (canMessage) $('#message-form').onsubmit = async event => {
    event.preventDefault(); const button = $('button',event.target); button.disabled = true;
    try { await write(`/requests/${id}/messages`,event.target,cleanForm(event.target)); toast('Đã gửi thông tin.'); await route(); }
    catch(error) { toast(error.message); button.disabled = false; }
  };
}
function cleanForm(form) { const data = new FormData(form); const files = data.getAll('files').filter(file=>file.size>0); data.delete('files'); files.forEach(file=>data.append('files',file)); return data; }
async function renderNotifications(version) {
  const {items} = await api('/notifications'); if (version !== renderVersion) return;
  $('#main').innerHTML = heading('Thông báo','Cập nhật mới nhất về các yêu cầu của bạn.') + `<section class="panel">${items.length?items.map(item=>`<article class="notification ${item.is_read?'':'unread'}"><div><strong>${escapeHTML(EVENT[item.event_type]||item.event_type)}</strong><p>${item.code} · ${escapeHTML(item.title)}</p><small>${time(item.created_at)} · ${item.is_read?'Đã đọc':'Chưa đọc'}</small></div><div>${!item.is_read?`<button class="text-button" data-read="${item.id}">Đánh dấu đã đọc</button>`:''}<button class="text-button" data-ticket="${item.request_id}">Xem yêu cầu ↗</button></div></article>`).join(''):empty('Chưa có thông báo','Các thay đổi của yêu cầu sẽ xuất hiện tại đây.')}</section>`;
  bindTickets();
  document.querySelectorAll('[data-read]').forEach(button=>button.onclick=async()=>{ button.disabled=true; try {await api(`/notifications/${button.dataset.read}/read`,{method:'POST'}); await route();}catch(error){toast(error.message);button.disabled=false;} });
}
async function renderTypes(version) {
  types = (await api('/types')).items; if (version !== renderVersion) return;
  $('#main').innerHTML = heading('Loại yêu cầu','Quản lý danh mục dùng chung cho bộ phận hỗ trợ.') + `<div class="admin-grid"><section class="panel"><div class="panel-title"><h3>Danh mục yêu cầu</h3></div><div class="table-wrap"><table><thead><tr><th>MÃ / TÊN LOẠI</th><th>TRẠNG THÁI</th><th></th></tr></thead><tbody>${types.map(type=>`<tr><td><strong>${escapeHTML(type.name)}</strong><p class="ticket-sub">${escapeHTML(type.code)} · ${escapeHTML(type.description)}</p></td><td>${type.active?'Đang hoạt động':'Ngừng hoạt động'}</td><td><button class="text-button" data-edit-type="${type.id}">Sửa</button><button class="text-button" data-toggle-type="${type.id}">${type.active?'Ngừng':'Kích hoạt'}</button></td></tr>`).join('')}</tbody></table></div></section><section class="panel section-pad"><h3 id="type-form-title">Thêm loại yêu cầu</h3><form id="type-form"><input name="id" type="hidden"><label>Mã loại<input name="code" required maxlength="30"></label><label>Tên loại<input name="name" required maxlength="120"></label><label>Mô tả<textarea name="description" rows="3" maxlength="1000"></textarea></label><label class="check-label"><input name="active" type="checkbox" checked>Đang hoạt động</label><p class="error" id="type-error" role="alert"></p><div class="action-row"><button class="primary" type="submit">Lưu danh mục</button><button type="button" id="reset-type">Tạo mới</button></div></form></section></div>`;
  const form = $('#type-form');
  $('#reset-type').onclick=()=>{form.reset();form.elements.id.value='';$('#type-form-title').textContent='Thêm loại yêu cầu';};
  document.querySelectorAll('[data-edit-type]').forEach(button=>button.onclick=()=>{ const item=types.find(type=>type.id===Number(button.dataset.editType)); for (const key of ['id','code','name','description']) form.elements[key].value=item[key];form.elements.active.checked=!!item.active;$('#type-form-title').textContent='Sửa loại yêu cầu';form.elements.code.focus(); });
  document.querySelectorAll('[data-toggle-type]').forEach(button=>button.onclick=async()=>{button.disabled=true;const item=types.find(type=>type.id===Number(button.dataset.toggleType));try{await api('/types/'+item.id,{method:'PATCH',body:{active:!item.active}});await route();}catch(error){toast(error.message);button.disabled=false;}});
  form.onsubmit=async event=>{event.preventDefault();const button=$('[type=submit]',form);button.disabled=true;const data=Object.fromEntries(new FormData(form));data.active=form.elements.active.checked;const id=data.id;delete data.id;try{await api('/types'+(id?'/'+id:''),{method:id?'PATCH':'POST',body:data});toast('Đã lưu danh mục.');await route();}catch(error){$('#type-error').textContent=error.message;button.disabled=false;}};
}
async function renderUsers(version) {
  const {items} = await api('/users'); if (version !== renderVersion) return;
  $('#main').innerHTML = heading('Quản lý tài khoản','Cấp tài khoản, quản lý vai trò và quyền truy cập.') + `<div class="admin-grid"><section class="panel"><div class="panel-title"><h3>Tài khoản hệ thống</h3></div><div class="table-wrap"><table><thead><tr><th>NGƯỜI DÙNG</th><th>VAI TRÒ</th><th>TRẠNG THÁI</th><th></th></tr></thead><tbody>${items.map(user=>`<tr><td><strong>${escapeHTML(user.name)}</strong><p class="ticket-sub">${escapeHTML(user.username)}</p></td><td>${ROLE[user.role]}</td><td>${user.active?'Hoạt động':'Đã khóa'}</td><td><button class="text-button" data-edit-user="${user.id}">Sửa</button></td></tr>`).join('')}</tbody></table></div></section><section class="panel section-pad"><h3 id="user-form-title">Cấp tài khoản</h3><form id="user-form"><input name="id" type="hidden"><label>Họ tên<input name="name" required maxlength="120"></label><label>Tài khoản<input name="username" required maxlength="80" autocomplete="off"></label><label>Mật khẩu<input name="password" type="password" minlength="8" maxlength="200" autocomplete="new-password" required></label><p class="help">Ít nhất 8 ký tự. Khi sửa, để trống để giữ mật khẩu.</p><label>Vai trò<select name="role">${Object.entries(ROLE).map(([key,value])=>`<option value="${key}">${value}</option>`).join('')}</select></label><label class="check-label"><input name="active" type="checkbox" checked>Cho phép đăng nhập</label><p class="error" id="user-error" role="alert"></p><div class="action-row"><button class="primary" type="submit">Lưu tài khoản</button><button id="reset-user" type="button">Tạo mới</button></div></form></section></div>`;
  const form=$('#user-form');
  $('#reset-user').onclick=()=>{form.reset();form.elements.id.value='';form.elements.username.disabled=false;form.elements.password.required=true;$('#user-form-title').textContent='Cấp tài khoản';};
  document.querySelectorAll('[data-edit-user]').forEach(button=>button.onclick=()=>{const item=items.find(user=>user.id===Number(button.dataset.editUser));for(const key of ['id','name','username','role'])form.elements[key].value=item[key];form.elements.active.checked=!!item.active;form.elements.username.disabled=true;form.elements.password.required=false;form.elements.password.value='';$('#user-form-title').textContent='Sửa tài khoản';form.elements.name.focus();});
  form.onsubmit=async event=>{event.preventDefault();const button=$('[type=submit]',form);button.disabled=true;const data=Object.fromEntries(new FormData(form));data.active=form.elements.active.checked;const id=data.id;delete data.id;if(id&&!data.password)delete data.password;try{await api('/users'+(id?'/'+id:''),{method:id?'PATCH':'POST',body:data});toast('Đã lưu tài khoản.');await boot();}catch(error){$('#user-error').textContent=error.message;button.disabled=false;}};
}
$('#login-form').onsubmit = async event => { event.preventDefault(); const button=$('button',event.target);button.disabled=true;$('#login-error').textContent='';try{await api('/login',{method:'POST',body:Object.fromEntries(new FormData(event.target))});$('#login-form').reset();await boot();}catch(error){$('#login-error').textContent=error.message;}finally{button.disabled=false;} };
$('#logout').onclick=async()=>{try{await api('/logout',{method:'POST'});location.hash='';showLogin();}catch(error){toast(error.message);}};
$('#close-create').onclick=$('#cancel-create').onclick=()=>$('#create-dialog').close();
$('#create-form').onsubmit=async event=>{event.preventDefault();const button=$('[type=submit]',event.target);button.disabled=true;try{const item=await write('/requests',event.target,cleanForm(event.target));$('#create-dialog').close();toast('Đã gửi yêu cầu '+item.code);go('request/'+item.id);}catch(error){$('#create-error').textContent=error.message;}finally{button.disabled=false;}};
window.addEventListener('hashchange',route);
boot().catch(error=>{showLogin();if(error.message!=='Vui lòng đăng nhập.')$('#login-error').textContent=error.message;});
