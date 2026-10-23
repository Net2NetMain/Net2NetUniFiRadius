let adminState=null, editingAdmin=null;

function adminPage(data) {
 return `<div class="toolbar"><p>Signed in as <b>${esc(data.current.username)}</b>. Each administrator has full access to this appliance.</p><button id="add-admin">+ Add administrator</button></div>`+
 table(['Administrator','Status',''],data.admins.map(a=>`<tr><td><b>${esc(a.display_name)}</b><small>${esc(a.username)}${a.id===data.current.id?' · You':''}</small></td><td><span class="badge ${a.enabled?'':'disabled'}">${a.enabled?'Enabled':'Disabled'}</span></td><td class="actions"><button data-admin-edit="${a.id}">Manage</button></td></tr>`))+
 `<div class="panel admin-password-panel"><h2>Change my password</h2><p>Administrator passwords require at least 12 characters. Changing your password signs out all of your sessions. Other administrators stay signed in.</p><form id="admin-password-form" class="admin-password-form">${field('Current password','current_password','','password','required autocomplete="current-password" maxlength="256"')}${field('New password','new_password','','password','required minlength="12" maxlength="256" autocomplete="new-password"')}${field('Confirm new password','confirm_password','','password','required minlength="12" maxlength="256" autocomplete="new-password"')}<p class="error" id="admin-password-error" role="alert"></p><button>Change password</button></form></div>`;
}

function adminDialog(id=null) {
 if(!$('#admin-editor'))document.body.insertAdjacentHTML('beforeend','<dialog id="admin-editor"><form id="admin-editor-form"><div class="dialog-head"><h2 id="admin-editor-title"></h2><button type="button" id="admin-editor-close" class="subtle">✕</button></div><div id="admin-editor-fields"></div><p id="admin-editor-error" class="error" role="alert"></p><div class="dialog-actions"><button type="button" id="admin-editor-cancel" class="secondary">Cancel</button><button>Save administrator</button></div></form></dialog>');
 editingAdmin=id?adminState.admins.find(a=>a.id===id):null;
 $('#admin-editor-title').textContent=id?'Manage administrator':'Add administrator';
 const self=editingAdmin?.id===adminState.current.id;
 let html=id?`<p>Username: <b>${esc(editingAdmin.username)}</b></p>`:field('Username','username','','text','required pattern="[A-Za-z0-9_.@-]{3,64}" maxlength="64" autocomplete="off"');
 html+=field('Display name','display_name',editingAdmin?.display_name||'','text','required minlength="2" maxlength="100"');
 if(!self)html+=field(id?'New password (leave blank to keep)':'Initial password','password','','password',`${id?'':'required'} minlength="12" maxlength="256" autocomplete="new-password"`)+field('Confirm password','confirm_password','','password',`${id?'':'required'} minlength="12" maxlength="256" autocomplete="new-password"`);
 if(id)html+=`<label>Status<select name="enabled" ${self?'disabled':''}><option value="true" ${editingAdmin.enabled?'selected':''}>Enabled</option><option value="false" ${!editingAdmin.enabled?'selected':''}>Disabled</option></select></label><p class="muted">${self?'Use Change my password to change your own password.':'Disabling this account or resetting its password signs out its sessions.'}</p>`;
 html+=field('Your current administrator password','current_password','','password','required maxlength="256" autocomplete="current-password"');
 $('#admin-editor-fields').innerHTML=html;$('#admin-editor-error').textContent='';$('#admin-editor').showModal();
}

document.addEventListener('click',event=>{
 const button=event.target.closest('button');if(!button)return;
 if(button.id==='add-admin')adminDialog();
 if(button.dataset.adminEdit)adminDialog(Number(button.dataset.adminEdit));
 if(['admin-editor-close','admin-editor-cancel'].includes(button.id))$('#admin-editor').close();
});

document.addEventListener('submit',async event=>{
 const form=event.target;
 if(!['admin-password-form','admin-editor-form'].includes(form.id))return;
 event.preventDefault();
 const own=form.id==='admin-password-form', values=Object.fromEntries(new FormData(form));
 const error=form.querySelector('.error'), submit=form.querySelector('button:not([type="button"])');
 error.textContent='';
 const newPassword=own?values.new_password:values.password;
 if(newPassword!==undefined&&newPassword!==values.confirm_password){error.textContent='The new passwords do not match.';return;}
 submit.disabled=true;
 try {
  if(own){
   await api('admins/password',{method:'POST',body:JSON.stringify({current_password:values.current_password,new_password:values.new_password})});
   form.reset();$('#login-form').elements.username.value=adminState.current.username;showLogin();$('#login-error').textContent='Password changed. Sign in with your new password.';
  }else{
   if(editingAdmin){values.enabled=editingAdmin.id===adminState.current.id?true:values.enabled==='true';values.password=values.password||'';}
   delete values.confirm_password;
   await api('admins'+(editingAdmin?'/'+editingAdmin.id:''),{method:editingAdmin?'PUT':'POST',body:JSON.stringify(values)});
   $('#admin-editor').close();form.reset();await render();notice('Administrator saved.');
  }
 }catch(err){error.textContent=err.message;}finally{submit.disabled=false;}
});
