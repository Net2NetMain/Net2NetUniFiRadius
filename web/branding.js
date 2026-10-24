let portalBranding={custom_logo:false,revision:'default',organization_name:'NET2NET NETWORK SERVICES'};
function applyBranding(value){
 portalBranding=value;
 const name=document.querySelector('#organization-name');name.textContent=value.organization_name??'NET2NET NETWORK SERVICES';name.hidden=!name.textContent;
 document.querySelectorAll('.logo').forEach(el=>{el.innerHTML=value.custom_logo?`<img class="custom-logo" src="/api/branding/logo?v=${encodeURIComponent(value.revision)}" alt="Organization logo">`:'N<span>2</span>N';});
 document.querySelector('#portal-favicon').href='/favicon.ico?v='+encodeURIComponent(value.revision);
}
function brandingPanel(){return `<div class="panel branding-panel"><h2>Portal branding</h2><p>Add your organization's logo to the sign-in page and sidebar. It also becomes the browser tab icon. Your logo is included in appliance backups.</p><form id="branding-text-form"><label>Sign-in organization name<input name="organization_name" maxlength="100" value="${esc(portalBranding.organization_name)}" placeholder="Your organization name"></label><p>This text appears above the sign-in heading. Leave it blank to hide it.</p><button>Save organization name</button><p id="branding-text-error" class="error" role="alert"></p></form><hr><form id="branding-form"><label>Organization logo<input name="logo" type="file" accept="image/png,image/jpeg,image/webp" required></label><p>PNG, JPG or WebP, up to 2 MB. A square logo works best as a favicon. Transparent PNG works well on the dark sidebar.</p><div class="toolbar-buttons"><button>Upload logo</button><button type="button" class="secondary" id="branding-reset" ${portalBranding.custom_logo?'':'disabled'}>Restore Net2Net logo</button></div><p id="branding-error" class="error" role="alert"></p></form></div>`;}
document.addEventListener('submit',async e=>{
 if(e.target.id==='branding-text-form'){e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;try{applyBranding(await api('branding',{method:'PUT',body:JSON.stringify({organization_name:e.target.elements.organization_name.value})}));await render();notice('Organization name updated.');}catch(err){document.querySelector('#branding-text-error').textContent=err.message;}finally{button.disabled=false;}return;}
 if(e.target.id!=='branding-form')return;
 e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;
 try{const file=e.target.elements.logo.files[0];if(!file||file.size>2*1024*1024)throw new Error('Choose an image up to 2 MB.');
 const image=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('Unable to read image.'));reader.readAsDataURL(file);});
 applyBranding(await api('branding/logo',{method:'PUT',body:JSON.stringify({image})}));await render();notice('Logo and favicon updated.');
 }catch(err){document.querySelector('#branding-error').textContent=err.message;}finally{button.disabled=false;}
});
document.addEventListener('click',async e=>{if(e.target.id!=='branding-reset')return;try{applyBranding(await api('branding',{method:'DELETE'}));await render();notice('Net2Net logo restored.');}catch(err){notice(err.message);}});
fetch('/api/branding').then(r=>r.json()).then(applyBranding).catch(()=>{});
