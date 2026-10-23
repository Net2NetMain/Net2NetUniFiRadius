let usagePeriod='month', usageUser='', usageKnownUsers=[];
const usagePeriods=[['today','Today'],['7days','Last 7 days'],['month','This month'],['30days','Last 30 days'],['all','All recorded history']];

function bytes(value){
 if(value===null||value===undefined)return '—';
 const units=['B','KB','MB','GB','TB','PB'];let n=Number(value),unit=0;
 while(n>=1000&&unit<units.length-1){n/=1000;unit++;}
 return n.toLocaleString(undefined,{maximumFractionDigits:unit?2:0})+' '+units[unit];
}
function reportTime(value){return value?new Date(Number(value)*1000).toLocaleString():'No reports yet';}
function elapsed(value){const n=Number(value)||0;return n>=3600?`${Math.floor(n/3600)}h ${Math.floor(n%3600/60)}m`:`${Math.floor(n/60)}m ${n%60}s`;}
function usageQuery(){return new URLSearchParams({period:usagePeriod,username:usageUser,offset_minutes:-new Date().getTimezoneOffset(),timezone_name:Intl.DateTimeFormat().resolvedOptions().timeZone||''});}

function usagePage(data){
 usageKnownUsers=[...new Set([...usageKnownUsers,...state.users.map(u=>u.username),...data.users.map(u=>u.username)])].sort();
 const s=data.summary, known=s.has_upload||s.has_download;
 const timezone=Intl.DateTimeFormat().resolvedOptions().timeZone||'your browser timezone';
 let html=`<div class="toolbar usage-toolbar"><div><p>Find your highest-usage users and track reported upload and download totals.</p><small>Last accounting report: ${esc(reportTime(data.last_report))} · ${esc(timezone)}</small></div><button data-refresh>Refresh</button></div><div class="usage-filters"><label>Report period<select id="usage-period">${usagePeriods.map(([v,l])=>`<option value="${v}" ${usagePeriod===v?'selected':''}>${l}</option>`).join('')}</select></label><label>User<select id="usage-user"><option value="">All users</option>${usageKnownUsers.map(u=>`<option value="${esc(u)}" ${usageUser===u?'selected':''}>${esc(u)}</option>`).join('')}</select></label></div>`;
 html+=`<div class="cards usage-cards"><div class="card"><p>Total reported data</p><strong>${known?bytes(s.total_bytes):'—'}</strong><small>${s.users} users in selected period</small></div><div class="card"><p>Downloaded by users</p><strong>${s.has_download?bytes(s.download_bytes):'—'}</strong><small>Received by client devices</small></div><div class="card"><p>Uploaded by users</p><strong>${s.has_upload?bytes(s.upload_bytes):'—'}</strong><small>Sent by client devices</small></div><div class="card"><p>Recently reporting sessions</p><strong>${s.recent_sessions}</strong><small>Unstopped reports in the last 15 minutes</small></div></div>`;
 if(data.backlog)html+='<p class="note">Historical accounting logs are still being processed. Totals may increase as the backlog is imported.</p>';
 if(data.counter_decreases)html+='<p class="note">Some session counters decreased. Totals are kept conservative to avoid inflating usage; affected sessions may be undercounted.</p>';
 html+='<div class="panel usage-ranking"><h2>Highest data users</h2><p>Ranked by combined upload and download in the selected period.</p>';
 html+=data.users.length?table(['Rank / user','Download','Upload','Total','Share of usage',''],data.users.map((u,i)=>`<tr><td><b>${i+1}. ${esc(u.display_name)}</b><small>${esc(u.username)} · ${u.sessions} sessions</small></td><td>${u.has_download?bytes(u.download_bytes):'—'}</td><td>${u.has_upload?bytes(u.upload_bytes):'—'}</td><td><b>${u.has_upload||u.has_download?bytes(u.total_bytes):'Not reported'}</b></td><td><div class="usage-share"><span style="width:${Math.min(100,Math.max(0,u.share))}%"></span></div><small>${u.share.toFixed(1)}%</small></td><td class="actions"><button data-usage-user="${esc(u.username)}">Details</button></td></tr>`)):
 empty('No usage reports for this period','Enable UniFi accounting with 300-second interim updates, or choose a different report period.');
 html+='</div>';
 const max=Math.max(1,...data.daily.map(d=>d.total_bytes));
 html+=`<div class="columns usage-history"><div class="panel"><h2>Daily usage</h2><p>Last 31 days within the selected period.</p>${data.daily.length?`<figure class="usage-chart" aria-label="Daily reported data usage">${data.daily.map(d=>`<div class="usage-bar-column" title="${esc(d.day)}: ${bytes(d.total_bytes)}"><div class="usage-bar-space"><div class="usage-bar" style="height:${Math.max(1,d.total_bytes/max*100)}%" aria-label="${esc(d.day)}: ${bytes(d.total_bytes)}"></div></div><small>${esc(d.day.slice(5))}</small></div>`).join('')}</figure>`:empty('No daily reports','Reported data will appear here.')}</div><div class="panel"><h2>Monthly history</h2><p>Last 12 recorded months${usageUser?' for this user':''}.</p>${data.monthly.length?table(['Month','Download','Upload','Total'],data.monthly.map(m=>`<tr><td>${esc(m.month)}</td><td>${bytes(m.has_download?m.download_bytes:null)}</td><td>${bytes(m.has_upload?m.upload_bytes:null)}</td><td><b>${bytes(m.has_upload||m.has_download?m.total_bytes:null)}</b></td></tr>`)):empty('No monthly history','History builds automatically from accounting reports.')}</div></div>`;
 html+=`<div class="panel usage-history"><h2>Recent sessions</h2><p>Latest 200 sessions across all dates. Reporting status reflects received accounting, not a live connection test.</p>${data.sessions.length?usageSessionTable(data.sessions):empty('No sessions yet','Connect a user after enabling accounting.')}</div>`;
 html+='<p class="note">Usage depends on the counters sent by UniFi. Daily and monthly totals assign each increase to the report time, so a session crossing midnight may be split approximately. Missing counters show —. Use 300-second interim updates for timely reporting.</p>';
 return html;
}

function usageSessionTable(rows){return table(['User','Session report','Duration','Download','Upload','Last report'],rows.map(r=>`<tr><td><b>${esc(r.username)}</b><small>${esc(r.session_id)}</small></td><td><span class="badge ${r.state==='Stop'?'disabled':r.reporting?'':'suspended'}">${r.state==='Stop'?'Stopped':r.reporting?'Reporting':'Stale report'}</span><small>${esc(r.state)}</small></td><td>${elapsed(r.seconds)}</td><td>${bytes(r.download_bytes)}</td><td>${bytes(r.upload_bytes)}</td><td>${esc(reportTime(r.timestamp))}</td></tr>`));}

document.addEventListener('change',async event=>{
 if(!['usage-period','usage-user'].includes(event.target.id))return;
 if(event.target.id==='usage-period')usagePeriod=event.target.value;
 else usageUser=event.target.value;
 try{await render();}catch(error){notice(error.message);}
});
document.addEventListener('click',async event=>{
 const button=event.target.closest('button');if(!button||!button.hasAttribute('data-usage-user'))return;
 usageUser=button.dataset.usageUser;
 try{await render();}catch(error){notice(error.message);}
});
