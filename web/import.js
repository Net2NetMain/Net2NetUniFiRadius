let importKind = 'users', importDuplicate = 'skip', importFile = null, importPreview = null;

function importPage() {
 return `<div class="panel import-intro"><p class="eyebrow">BRING YOUR EXISTING DATA</p><h2>Import your network in one go</h2><p>Upload a CSV for one record type, or an Excel workbook containing profiles, users and devices. Review every change before saving.</p><div class="template-links"><a href="/api/import/template/system?format=xlsx">Download full-system Excel template ↓</a><a href="/api/import/template/users">Users CSV ↓</a><a href="/api/import/template/profiles">Profiles CSV ↓</a><a href="/api/import/template/devices">Devices CSV ↓</a></div></div>
 <div class="panel import-panel"><form id="import-form"><fieldset id="import-controls"><div class="import-options"><label>What are you importing?<select id="import-kind">${[['users','Wi-Fi users'],['profiles','VLAN profiles'],['devices','Network devices'],['system','Full system · Excel workbook']].map(([v,l])=>`<option value="${v}" ${v===importKind?'selected':''}>${l}</option>`).join('')}</select></label><label>Existing records<select id="import-duplicates"><option value="skip" ${importDuplicate==='skip'?'selected':''}>Skip existing records</option><option value="update" ${importDuplicate==='update'?'selected':''}>Update matching records</option></select></label></div><label>CSV or Excel file<input id="import-file" type="file" accept=".csv,.xlsx" ${importFile?'':'required'}></label><p class="muted" id="import-filename">${importFile?esc(importFile.name):'Up to 8 MB and 5,000 data rows. UTF-8 CSV or .xlsx; save older .xls files as .xlsx.'}</p><button id="import-preview-button">Preview import →</button></fieldset></form><p class="error" id="import-error" role="alert"></p><div id="import-results">${importPreview?importResults(importPreview):''}</div></div>
 <div class="panel import-help"><h3>How to prepare your file</h3><p><b>Users:</b> username, display_name, password, profile, vlan, status. New users require a password of at least 12 printable ASCII characters. Status defaults to active; use active, suspended or disabled. A missing profile is created when a valid VLAN is supplied.</p><p><b>Profiles:</b> name and vlan (1–4094). <b>Devices:</b> name, address and secret. New devices need a shared secret of at least 16 characters using letters, numbers, underscore, dot, ! @ # or hyphen.</p><p><b>Full-system workbook:</b> use sheets named profiles, users and devices. Profiles are processed first. This imports network access records; it keeps this installation's administrator login and certificates.</p><p>When updating, records match by profile/device name or username. Blank passwords and shared secrets keep the existing values. Other supplied fields replace the existing values; a blank user status becomes active. No existing records are deleted. Correct all errors before import; the whole batch is saved together, with an automatic local database backup.</p><p class="note">CSV/Excel files can contain Wi-Fi passwords and device secrets. Keep them protected. Preview screens hide credentials.</p></div>`;
}

function importResults(result) {
 const counts=result.counts;
 let html=`<div class="import-summary"><b>${result.applied?'Import complete':result.valid?'Ready to import':'Fix errors before importing'}</b><span>${counts.created} create · ${counts.updated} update · ${counts.skipped} skip</span></div>`;
 if(!result.rows)html+='<p class="error">The file contains headers but no data rows.</p>';
 if(result.errors.length)html+=table(['Type','File row','Error'],result.errors.map(x=>`<tr><td>${esc(x.type)}</td><td>${x.row}</td><td>${esc(x.message)}</td></tr>`));
 if(result.changes.length)html+=table(['Type','File row','Record','Action'],result.changes.slice(0,100).map(x=>`<tr><td>${esc(x.type)}</td><td>${x.row}</td><td>${esc(x.name)}<small>${esc(x.details||'Created from user VLAN')}</small></td><td><span class="badge">${esc(x.action)}</span></td></tr>`));
 if(result.changes.length>100)html+=`<p class="muted">Showing the first 100 of ${result.changes.length} changes.</p>`;
 if(result.valid&&!result.applied)html+='<button id="apply-import" class="apply-import">Import these records</button>';
 if(result.applied)html+=`<p class="muted">Saved successfully. Recovery snapshot: ${esc(result.backup)} in the appliance data/imports folder.</p>`;
 return html;
}

function clearImportPreview(){importPreview=null;const target=$('#import-results');if(target)target.innerHTML='';}

async function sendImport(apply=false) {
 if(!importFile)throw new Error('Choose a CSV or Excel file first.');
 if(importKind==='system'&&!importFile.name.toLowerCase().endsWith('.xlsx'))throw new Error('Full-system imports require an Excel .xlsx workbook.');
 if(importFile.size>8*1024*1024)throw new Error('The file must be at most 8 MB.');
 const params=new URLSearchParams({filename:importFile.name,kind:importKind,duplicates:importDuplicate});
 const token=importPreview?.token;
 const controls=$('#import-controls');controls.disabled=true;
 const applyButton=$('#apply-import');if(applyButton)applyButton.disabled=true;
 $('#import-error').textContent='';
 try {
  const result=await api('import/'+(apply?'apply':'preview')+'?'+params,{method:'POST',body:importFile,headers:{'Content-Type':'application/octet-stream',...(apply?{'X-Import-Preview':token}:{})}});
  importPreview=result;$('#import-results').innerHTML=importResults(result);
  if(result.applied){state=await api('state');importFile=null;$('#import-file').value='';$('#import-file').required=true;notice('Import complete. Users, profiles and devices have been updated.');}
 } catch(error) {
  clearImportPreview();throw error;
 } finally {controls.disabled=false;if(applyButton)applyButton.disabled=false;}
}

document.addEventListener('change',event=>{
 if(event.target.id==='import-kind'){importKind=event.target.value;clearImportPreview();}
 if(event.target.id==='import-duplicates'){importDuplicate=event.target.value;clearImportPreview();}
 if(event.target.id==='import-file'){importFile=event.target.files[0]||null;clearImportPreview();$('#import-filename').textContent=importFile?importFile.name:'Choose a file to preview.';}
});
document.addEventListener('submit',async event=>{
 if(event.target.id!=='import-form')return;
 event.preventDefault();try{await sendImport();}catch(error){$('#import-error').textContent=error.message;}
});
document.addEventListener('click',async event=>{
 const button=event.target.closest('button');if(!button)return;
 if(button.dataset.importKind){importKind=button.dataset.importKind;clearImportPreview();view='import';await render();}
 if(button.id==='apply-import'){try{await sendImport(true);}catch(error){$('#import-error').textContent=error.message;}}
});

load().catch(()=>showLogin());
