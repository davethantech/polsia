/* Polsia browser app: data comes from the authenticated company APIs only. */
'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const dashboard = Boolean($('appShell'));
  const state = { user: null, csrf: '', companyId: '', missions: [], overview: null, activeView: 'overview', authMode: 'login', provider: null };
  const VIEWS = new Set(['overview','missions','knowledge','intelligence','capacity','team']);
  function element(tag, klass, txt) {
    const n = document.createElement(tag);
    if (klass) n.className = klass;
    if (txt !== undefined && txt !== null) n.textContent = String(txt);
    return n;
  }
  function clear(n) { if (n) n.replaceChildren(); }
  function text(id, value) { const n=$(id);if(n)n.textContent=value===undefined||value===null?'—':String(value); }
  function feedback(id,message,error=false) { const n=$(id);if(n){n.textContent=message;n.classList.toggle('error',error);} }
  function formatDate(ts){if(!ts)return 'TIME UNKNOWN';return new Date(ts*1000).toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});}
  function qty(n){return Number(n||0).toLocaleString();}
  function bytes(n) {if(n===null||n===undefined)return 'Unavailable';const v=Number(n)/1073741824;return v>=1?v.toFixed(1)+' GB':(Number(n)/1048576).toFixed(0)+' MB';}
  async function api(path, options={}){
    const method=options.method || 'GET';
    const headers={'Accept':'application/json'};
    if(options.body!==undefined)headers['Content-Type']='application/json';
    if(state.companyId)headers['X-Company-ID']=state.companyId;
    if(method!=='GET'&&method!=='HEAD'&&state.csrf)headers['X-CSRF-Token']=state.csrf;
    const response=await fetch(path,{method,credentials:'same-origin',headers,body:options.body===undefined?undefined:JSON.stringify(options.body),cache:'no-store'});
    const data=await response.json().catch(()=>({}));
    if(!response.ok){const detail=data.detail;throw new Error(typeof detail==='string'?detail:`Request failed (${response.status})`);}
    return data;
  }
  function openDialog(id){const d=$(id);if(d && !d.open)d.showModal();}
  function closeDialog(id){const d=$(id);if(d?.open)d.close();}
  function tagForStatus(status){ const s=(status||'unknown').toLowerCase();return element('span','status-chip '+s,status||'UNKNOWN'); }
  function empty(container,title,description){clear(container);const n=element('div','empty-state');n.append(element('strong',null,title),element('p',null,description));container.append(n);}
  function setMode(mode){state.authMode=mode;text('authSubmitLabel',mode==='login'?'Sign in':mode==='register'?'Create account':'Join workspace');text('authTitle',mode==='login'?'Make your move.':mode==='register'?'Begin here.':'Take your place.');text('authSub',mode==='login'?'Sign in to enter your company’s mission control.':mode==='register'?'Create a secure account and your first workspace.':'Enter the invitation token your workspace owner shared with you.');$('signupFields').hidden=mode!=='register';$('inviteFields').hidden=mode!=='invite';$('authToggle').hidden=mode!=='login'||!$('authToggle').dataset.enabled;$('authInviteToggle').hidden=mode!=='login';$('authLoginToggle').hidden=mode==='login';$('signupCompany').required=mode==='register';$('inviteToken').required=mode==='invite';$('authPassword').autocomplete=mode==='login'?'current-password':'new-password';feedback('authMessage','');}
  async function initAuth(){
    if(!dashboard){text('copyright-year',new Date().getFullYear());return;}
    const config=await api('/auth/config').catch(()=>({signup_enabled:false}));
    if(config.signup_enabled){$('authToggle').dataset.enabled='1';$('authToggle').hidden=false;}
    const inviteFromQuery=new URLSearchParams(location.search).get('invite');
    if(inviteFromQuery){$('inviteToken').value=inviteFromQuery;setMode('invite');history.replaceState(null,'','/dashboard');}
    $('authToggle').addEventListener('click',()=>setMode('register'));
    $('authInviteToggle').addEventListener('click',()=>setMode('invite'));
    $('authLoginToggle').addEventListener('click',()=>setMode('login'));
    $('authForm').addEventListener('submit',handleAuth);
    try { const me=await api('/auth/me'); await signedIn(me); } catch { $('authShell').hidden=false;$('appShell').hidden=true; }
  }
  async function handleAuth(event){
    event.preventDefault();feedback('authMessage','Signing in…');const mode=state.authMode;
    const body={email:$('authEmail').value,password:$('authPassword').value};
    let path='/auth/login';
    if(mode==='register'){path='/auth/register';body.company_name=$('signupCompany').value;}
    if(mode==='invite'){path='/auth/accept-invite';body.token=$('inviteToken').value;}
    const submit=$('authForm').querySelector('button[type=submit]');submit.disabled=true;
    try{await api(path,{method:'POST',body});const me=await api('/auth/me');await signedIn(me);feedback('authMessage','');}
    catch(e){feedback('authMessage',e.message,true);}finally{submit.disabled=false;}
  }
  async function signedIn(me){
    state.user=me;state.csrf=me.csrf_token;const preferred=sessionStorage.getItem('polsia-company');
    state.companyId=(me.memberships.find(m=>m.company_id===preferred)||me.memberships[0]||{}).company_id||'';
    if(!state.companyId){feedback('authMessage','No workspace membership. Contact an owner.',true);return;}
    $('authShell').hidden=true;$('appShell').hidden=false;
    text('avatarInitial',me.email.charAt(0).toUpperCase());
    updateCompanySelect();registerWorkspaceEvents();await refreshAll();
    if(location.hash.slice(1)&&VIEWS.has(location.hash.slice(1)))showView(location.hash.slice(1));
  }
  function updateCompanySelect(){
    const select=$('workspaceSelect');clear(select);
    for(const m of state.user.memberships){const o=element('option',null,m.name);o.value=m.company_id;select.append(o);}select.value=state.companyId;
    const role=roleInCurrentCompany();$('inviteForm').querySelector('button[type=submit]').disabled=role!=='owner';
  }
  function roleInCurrentCompany(){return state.user?.memberships.find(m=>m.company_id===state.companyId)?.role||'viewer';}
  let eventsRegistered=false;
  function registerWorkspaceEvents(){
    if(eventsRegistered)return;eventsRegistered=true;
    $('workspaceSelect').addEventListener('change',async e=>{state.companyId=e.target.value;sessionStorage.setItem('polsia-company',state.companyId);updateCompanySelect();await refreshAll();});
    $('refreshButton').addEventListener('click',refreshAll);$('capacityRefresh').addEventListener('click',refreshCapacity);
    $('signOut').addEventListener('click',async()=>{try{await api('/auth/logout',{method:'POST'});}catch{}location.replace('/dashboard');});
    $('mobileMenu').addEventListener('click',()=>document.querySelector('.sidebar').classList.toggle('open'));
    document.querySelectorAll('[data-view]').forEach(n=>n.addEventListener('click',()=>showView(n.dataset.view)));
    document.querySelectorAll('[data-action="open-mission"]').forEach(n=>n.addEventListener('click',()=>openDialog('missionDialog')));
    document.querySelectorAll('[data-close-dialog]').forEach(n=>n.addEventListener('click',()=>closeDialog(n.dataset.closeDialog)));
    $('closeDetail').addEventListener('click',()=>{$('missionDetail').hidden=true;});
    $('addKnowledgeButton').addEventListener('click',()=>openDialog('knowledgeDialog'));
    $('newCompanyButton').addEventListener('click',()=>openDialog('companyDialog'));
    $('knowledgeSearch').addEventListener('click',refreshKnowledge);$('knowledgeQuery').addEventListener('keydown',e=>{if(e.key==='Enter')refreshKnowledge();});
    $('missionForm').addEventListener('submit',submitMission);
    $('knowledgeForm').addEventListener('submit',submitKnowledge);
    $('researchForm').addEventListener('submit',submitResearch);
    $('inviteForm').addEventListener('submit',submitInvitation);
    $('companyForm').addEventListener('submit',submitCompany);
    document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelector('.sidebar')?.classList.remove('open');});
    let timer;document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshAll();});
    timer=setInterval(()=>{if(!document.hidden&&state.user)refreshAll();},30000);
  }
  function showView(name){if(!VIEWS.has(name))return;state.activeView=name;location.hash=name;
    document.querySelectorAll('.view').forEach(n=>n.classList.toggle('active',n.id==='view-'+name));
    document.querySelectorAll('.nav-item').forEach(n=>n.classList.toggle('active',n.dataset.view===name));
    text('currentViewLabel',name.toUpperCase());document.querySelector('.sidebar').classList.remove('open');window.scrollTo({top:0,behavior:'smooth'});
    if(name==='capacity')refreshCapacity();if(name==='knowledge')refreshKnowledge();if(name==='team')refreshTeam();if(name==='intelligence')refreshProvider();
  }
  async function refreshAll(){
    const company=state.companyId;
    const results=await Promise.allSettled([api('/overview'),api('/missions'),api('/intelligence/provider')]);
    if(company!==state.companyId)return;
    if(results[0].status==='fulfilled'){state.overview=results[0].value;renderOverview(results[0].value);}
    else{feedback('missionFormMessage','Could not refresh overview: '+results[0].reason.message,true);}
    if(results[1].status==='fulfilled'){state.missions=results[1].value.missions||[];renderMissions();}
    if(results[2].status==='fulfilled'){state.provider=results[2].value;renderProvider(results[2].value);}
    refreshCapacity();if(state.activeView==='knowledge')refreshKnowledge();if(state.activeView==='team')refreshTeam();
    api('/health').then(d=>text('sidebarHealth',d.ai_provider==='unconfigured'?'AI provider unconfigured':'AI provider '+d.ai_provider)).catch(()=>text('sidebarHealth','Status unavailable'));
  }
  function renderOverview(data){
    text('statMissions',qty(Object.values(data.missions||{}).reduce((n,v)=>n+v,0)));
    text('statActive',qty(data.missions?.ACTIVE));text('statCompleted',qty(data.tasks?.SUCCEEDED));text('statApprovals',qty(data.tasks?.WAITING_APPROVAL));
    text('todayLabel',new Date().toLocaleDateString(undefined,{weekday:'short',month:'short',day:'numeric',year:'numeric'}).toUpperCase());
    const tasks=data.tasks||{};const total=Object.values(tasks).reduce((n,v)=>n+v,0);const succeeded=tasks.SUCCEEDED||0;const pct=total?Math.round(succeeded/total*100):0;
    $('taskDonut').style.setProperty('--pct',pct);text('donutPct',total?pct+'%':'—');text('pulseSucceeded',qty(succeeded));text('pulseRunning',qty(tasks.RUNNING));text('pulseWaiting',qty((tasks.QUEUED||0)+(tasks.WAITING_APPROVAL||0)));text('pulseFailed',qty((tasks.FAILED||0)+(tasks.BLOCKED||0)));
    const events=$('recentEvents');clear(events);
    if(!data.recent_events?.length)empty(events,'Nothing yet.','Events appear here after real company or mission actions.');
    else for(const event of data.recent_events){const row=element('div','event-item'),mark=element('span','event-mark','✳'),copy=element('div','mission-copy');copy.append(element('strong',null,event.event_type.replaceAll('.',' / ')),element('small',null,event.mission_id?'MISSION '+event.mission_id.slice(0,8):'COMPANY EVENT'));row.append(mark,copy,element('time',null,formatDate(event.created_at)));events.append(row);}
  }
  function makeMissionRow(m){const row=element('button','mission-item');row.type='button';row.append(element('span','mission-icon','◎'));const copy=element('span','mission-copy');copy.append(element('strong',null,m.objective),element('small',null,`${m.task_count} tasks · ${m.succeeded_tasks} completed · ${formatDate(m.created_at)}`));row.append(copy,tagForStatus(m.status));row.addEventListener('click',()=>openMissionDetail(m.id));return row;}
  function renderMissions(){
    const feed=$('overviewMissions'),table=$('missionsTable');clear(feed);clear(table);
    text('missionCount',qty(state.missions.length)+' MISSIONS');
    if(!state.missions.length){empty(feed,'A blank canvas.','Create your first objective to start a tracked mission.');empty(table,'No missions yet.','Launch a mission to begin building an execution history.');return;}
    for(const m of state.missions.slice(0,4))feed.append(makeMissionRow(m));
    for(const m of state.missions)table.append(makeMissionRow(m));
  }
  async function openMissionDetail(id){showView('missions');const root=$('missionTasks');empty(root,'Loading mission…','');$('missionDetail').hidden=false;
    try{const res=await api('/missions/'+encodeURIComponent(id));text('detailTitle',res.mission.objective);clear(root);
      for(const t of res.tasks){const row=element('div','task-item'),icon=element('span','mission-icon','◈'),copy=element('div','mission-copy');copy.append(element('strong',null,t.name+' · '+t.tool),element('small',null,'Attempts: '+t.attempt));
        if(t.outputs){const p=element('p',null,typeof t.outputs==='string'?t.outputs:JSON.stringify(t.outputs));copy.append(p);}row.append(icon,copy,tagForStatus(t.status));
        if(t.status==='WAITING_APPROVAL'&&roleInCurrentCompany()!=='viewer'){const btn=element('button','approval-button','Approve');btn.type='button';btn.addEventListener('click',async()=>{btn.disabled=true;try{await api('/tasks/'+encodeURIComponent(t.id)+'/approve',{method:'POST'});await openMissionDetail(id);await refreshAll();}catch(e){btn.disabled=false;btn.textContent=e.message;}});row.append(btn);}root.append(row);}
    }catch(e){empty(root,'Unable to load mission.',e.message);}
  }
  async function submitMission(e){e.preventDefault();const input=$('missionInput').value.trim(),tool=$('missionTool').value,objective=$('missionObjective').value.trim();let inputs;
    if(tool==='internal.echo')inputs={text:input||objective};
    else if(tool==='math.evaluate')inputs={expression:input};
    else inputs={url:input};
    feedback('missionFormMessage','Validating mission…');
    try{const spec={objective,tasks:[{name:'step-1',tool,inputs,approval_required:$('missionApproval').checked}]};await api('/missions/estimate',{method:'POST',body:spec});const result=await api('/missions',{method:'POST',body:spec});closeDialog('missionDialog');$('missionForm').reset();await refreshAll();openMissionDetail(result.mission_id);}catch(err){feedback('missionFormMessage',err.message,true);}
  }
  async function refreshKnowledge(){const company=state.companyId,list=$('knowledgeList');
    try{const results=await api('/knowledge?query='+encodeURIComponent($('knowledgeQuery').value||'')+'&limit=50');if(company!==state.companyId)return;clear(list);
      if(!results.length)empty(list,'Memory begins here.','Add source-labeled company knowledge; it will not be invented or shared with other tenants.');
      for(const record of results){const row=element('article','knowledge-item'),glyph=element('span',null,'⌘'),copy=element('div','mission-copy');copy.append(element('strong',null,record.layer.toUpperCase()+' · '+record.evidence_status),element('small',null,record.source||'NO SOURCE PROVIDED'),element('p',null,record.content));row.append(glyph,copy);list.append(row);}
    }catch(e){empty(list,'Knowledge unavailable.',e.message);}
  }
  async function submitKnowledge(e){e.preventDefault();feedback('memoryMessage','Saving…');try{await api('/knowledge',{method:'POST',body:{layer:$('memoryLayer').value,content:$('memoryContent').value,source:$('memorySource').value}});closeDialog('knowledgeDialog');$('knowledgeForm').reset();feedback('memoryMessage','');await refreshKnowledge();await refreshAll();}catch(err){feedback('memoryMessage',err.message,true);}}
  async function refreshProvider(){try{const provider=await api('/intelligence/provider');state.provider=provider;renderProvider(provider);}catch{}}
  function renderProvider(provider){const usable=!!provider.live_requests;text('providerTag',usable?'CONFIGURED':'NOT CONFIGURED');$('providerTag').classList.toggle('tag-outline',!usable);text('providerDetails',`Provider: ${provider.status || 'unknown'} · Model: ${provider.model || 'not configured'} · Daily call limit: ${provider.daily_call_limit ?? 'unknown'}.`);$('researchForm').querySelector('button').disabled=!usable;}
  async function submitResearch(e){e.preventDefault();feedback('researchMessage','Submitting…');try{const result=await api('/intelligence/questions',{method:'POST',body:{question:$('researchQuestion').value,min_sources:1}});feedback('researchMessage','Research queued as mission '+result.mission_id+'. Not marked complete.');$('researchForm').reset();await refreshAll();}catch(err){feedback('researchMessage',err.message,true);}}
  async function refreshCapacity(){const company=state.companyId;try{const result=await api('/capacity');if(company!==state.companyId)return;const m=result.measurements||{},d=result.decision||{};
    text('capMemory',bytes(m.memory_available_bytes));text('capDisk',bytes(m.disk_free_bytes));text('capCpu',m.load_per_core===null||m.load_per_core===undefined?'Unavailable':Number(m.load_per_core).toFixed(2));text('capTemperature',m.max_temperature_c===null||m.max_temperature_c===undefined?'Unavailable':Number(m.max_temperature_c).toFixed(1)+' °C');text('capacityStatus',d.admitted?'ADMITTED':'THROTTLED');text('capacityReason',d.admitted?'Within current admission limits. These are measured snapshots, not guarantees.':'Execution is throttled: '+(d.reasons||[]).join(', '));
  }catch(e){text('capacityStatus','UNAVAILABLE');text('capacityReason',e.message);}}
  async function refreshTeam(){const company=state.companyId,root=$('membersList');try{const data=await api('/companies/members');if(company!==state.companyId)return;clear(root);for(const m of data.members){const row=element('div','member-item');row.append(element('span','mission-icon',m.email.charAt(0).toUpperCase()));const copy=element('div','mission-copy');copy.append(element('strong',null,m.email),element('small',null,'JOINED '+formatDate(m.joined_at)));row.append(copy,tagForStatus(m.role.toUpperCase()));root.append(row);}}catch(e){empty(root,'Members unavailable.',e.message);}}
  async function submitInvitation(e){e.preventDefault();const root=$('inviteResult');text('inviteResult','Creating single-use invitation…');try{const result=await api('/companies/invitations',{method:'POST',body:{email:$('inviteEmail').value,role:$('inviteRole').value}});clear(root);root.append(element('p',null,'Share this invitation token privately. No email was sent. It expires in 7 days.'));const code=element('code',null,result.invitation_token);root.append(code);const button=element('button','secondary-button','Copy invitation token');button.type='button';button.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(result.invitation_token);button.textContent='Copied';}catch{button.textContent='Select the token to copy';}});root.append(document.createTextNode(' '),button);$('inviteForm').reset();}catch(err){text('inviteResult',err.message);}}
  async function submitCompany(e){e.preventDefault();feedback('companyMessage','Creating workspace…');try{const result=await api('/companies',{method:'POST',body:{name:$('newCompanyName').value}});const me=await api('/auth/me');state.user=me;state.csrf=me.csrf_token;state.companyId=result.company_id;sessionStorage.setItem('polsia-company',state.companyId);updateCompanySelect();closeDialog('companyDialog');$('companyForm').reset();showView('overview');await refreshAll();}catch(err){feedback('companyMessage',err.message,true);}}
  initAuth();
})();
