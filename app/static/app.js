/* Polsia browser app: data comes from the authenticated company APIs only. */
'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const dashboard = Boolean($('appShell'));
  const state = { user: null, csrf: '', companyId: '', missions: [], overview: null, activeView: 'overview', authMode: 'login', provider: null };
  const VIEWS = new Set(['overview','missions','knowledge','intelligence','capacity','team','factory','business']);
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
    $('businessForm').addEventListener('submit',submitBusiness);
    $('businessLeadForm').addEventListener('submit',submitLead);
    $('businessTicketForm').addEventListener('submit',submitTicket);
    $('businessRefresh').addEventListener('click',refreshBusiness);
    $('businessCloseDetails').addEventListener('click',()=>{$('businessDetails').hidden=true;});
    $('factoryForm').addEventListener('submit',submitFactory);
    $('factoryInspectButton').addEventListener('click',inspectFactory);
    $('factoryRefresh').addEventListener('click',refreshFactory);
    $('factoryClosePreview').addEventListener('click',()=>{$('factoryPreview').hidden=true;});
    document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelector('.sidebar')?.classList.remove('open');});
    let timer;document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshAll();});
    timer=setInterval(()=>{if(!document.hidden&&state.user)refreshAll();},30000);
  }
  function showView(name){if(!VIEWS.has(name))return;state.activeView=name;location.hash=name;
    document.querySelectorAll('.view').forEach(n=>n.classList.toggle('active',n.id==='view-'+name));
    document.querySelectorAll('.nav-item').forEach(n=>n.classList.toggle('active',n.dataset.view===name));
    text('currentViewLabel',name.toUpperCase());document.querySelector('.sidebar').classList.remove('open');window.scrollTo({top:0,behavior:'smooth'});
    if(name==='capacity')refreshCapacity();if(name==='knowledge')refreshKnowledge();if(name==='team')refreshTeam();if(name==='intelligence')refreshProvider();if(name==='factory')refreshFactory();if(name==='business')refreshBusiness();
  }
  async function refreshAll(){
    const company=state.companyId;
    const results=await Promise.allSettled([api('/overview'),api('/missions'),api('/intelligence/provider')]);
    if(company!==state.companyId)return;
    if(results[0].status==='fulfilled'){state.overview=results[0].value;renderOverview(results[0].value);}
    else{feedback('missionFormMessage','Could not refresh overview: '+results[0].reason.message,true);}
    if(results[1].status==='fulfilled'){state.missions=results[1].value.missions||[];renderMissions();}
    if(results[2].status==='fulfilled'){state.provider=results[2].value;renderProvider(results[2].value);}
    refreshCapacity();if(state.activeView==='knowledge')refreshKnowledge();if(state.activeView==='team')refreshTeam();if(state.activeView==='factory')refreshFactory();if(state.activeView==='business')refreshBusiness();
    api('/health').then(d=>text('sidebarHealth',d.ai_provider==='unconfigured'?'Local model not configured':'Local model '+d.ai_provider)).catch(()=>text('sidebarHealth','Status unavailable'));
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

  function factorySnapshot(){return {[$('factoryPath').value.trim()]:$('factorySource').value};}
  async function inspectFactory(){
    feedback('factoryMessage','Inspecting supplied source…');
    try{const res=await api('/factory/inspect',{method:'POST',body:{files:factorySnapshot()}});
      const details=res.files.map(f=>f.path+' · '+f.bytes+' bytes · '+(f.syntax.valid===false?'INVALID SYNTAX':f.syntax.checked?'SYNTAX VALID':'SYNTAX NOT CHECKED')).join('\n');
      feedback('factoryMessage',details+'\nNo code was executed.');
    }catch(err){feedback('factoryMessage',err.message,true);}
  }
  async function submitFactory(e){
    e.preventDefault();feedback('factoryMessage','Creating an inspected, local-model engineering mission…');
    const submit=$('factoryForm').querySelector('button[type=submit]');submit.disabled=true;
    try{const result=await api('/factory/missions',{method:'POST',body:{goal:$('factoryGoal').value,files:factorySnapshot()}});
      feedback('factoryMessage','Mission '+result.mission_id+' created. The worker runs the inspection, then requests a local model proposal. Check missions or refresh artifacts; no code has been executed or deployed.');
      await refreshAll();
    }catch(err){feedback('factoryMessage',err.message,true);}finally{submit.disabled=roleInCurrentCompany()==='viewer';}
  }
  async function submitBusiness(e){
    e.preventDefault();feedback('businessMessage','Creating a persisted nine-department mission…');
    try{const result=await api('/business/programs',{method:'POST',body:{idea:$('businessIdea').value,industry:$('businessIndustry').value,market:$('businessMarket').value}});
      feedback('businessMessage','Mission '+result.mission_id.slice(0,8)+' queued. The local model must be running; drafts will appear as departments finish.');
      $('businessForm').reset();await refreshBusiness();await refreshAll();
    }catch(err){feedback('businessMessage',err.message,true);}
  }
  async function refreshBusiness(){
    const company=state.companyId;
    try{
      const [catalog,programs,leads,tickets]=await Promise.all([api('/business/capabilities'),api('/business/programs'),api('/business/leads'),api('/business/tickets')]);
      if(company!==state.companyId)return;
      text('businessModelTag',catalog.model_configured_unverified?'LOCAL MODEL CONFIGURED · UNVERIFIED':'LOCAL MODEL NOT CONFIGURED');
      const roles=$('businessRoles');clear(roles);
      for(const r of catalog.roles){const row=element('div','task-item');const info=element('div','mission-copy');
        info.append(element('strong',null,r.name),element('small',null,r.scope));row.append(element('span','mission-icon','✳'),info,tagForStatus(r.status));roles.append(row);}
      const root=$('businessPrograms');clear(root);
      if(!programs.programs.length)empty(root,'No business programs yet.','Describe an idea above; the model and workforce must be configured for execution.');
      for(const p of programs.programs){const row=element('button','mission-item');row.type='button';const info=element('span','mission-copy');
        info.append(element('strong',null,p.idea),element('small',null,p.drafts+' / 9 draft deliverables · '+formatDate(p.created_at)));
        row.append(element('span','mission-icon','◈'),info,tagForStatus(p.status));row.addEventListener('click',()=>openBusinessProgram(p.id));root.append(row);}
      const leadRoot=$('businessLeads');clear(leadRoot);
      if(!leads.leads.length)empty(leadRoot,'No contacts recorded.','Add a real supplied lead; none are invented by the model.');
      for(const l of leads.leads){const row=element('div','task-item'),info=element('div','mission-copy');
        info.append(element('strong',null,l.name),element('small',null,l.organization+(l.email?' · '+l.email:'')));
        const select=element('select','workspace-select');select.setAttribute('aria-label','Lead stage for '+l.name);
        for(const st of ['new','qualified','contacted','converted','lost']){const o=element('option',null,st);o.value=st;select.append(o);}select.value=l.stage;select.disabled=roleInCurrentCompany()==='viewer';
        select.addEventListener('change',async()=>{try{await api('/business/leads/'+encodeURIComponent(l.id),{method:'PATCH',body:{stage:select.value}});}catch(err){feedback('leadMessage',err.message,true);select.value=l.stage;}});
        row.append(element('span','mission-icon','♧'),info,select);leadRoot.append(row);}
      const ticketsRoot=$('businessTickets');clear(ticketsRoot);
      if(!tickets.tickets.length)empty(ticketsRoot,'No support tickets yet.','Create a real issue; no response will be sent automatically.');
      for(const t of tickets.tickets){const row=element('div','task-item'),info=element('div','mission-copy');
        info.append(element('strong',null,t.subject),element('small',null,t.message.slice(0,180)));
        const select=element('select','workspace-select');select.setAttribute('aria-label','Ticket status for '+t.subject);
        for(const st of ['open','needs_follow_up','closed']){const o=element('option',null,st.replaceAll('_',' '));o.value=st;select.append(o);}select.value=t.status;select.disabled=roleInCurrentCompany()==='viewer';
        select.addEventListener('change',async()=>{try{await api('/business/tickets/'+encodeURIComponent(t.id),{method:'PATCH',body:{status:select.value}});}catch(err){feedback('ticketMessageStatus',err.message,true);select.value=t.status;}});
        row.append(element('span','mission-icon','♧'),info,select);ticketsRoot.append(row);}
    }catch(err){feedback('businessMessage',err.message,true);}
  }
  async function openBusinessProgram(id){const company=state.companyId,root=$('businessArtifacts');$('businessDetails').hidden=false;empty(root,'Loading department drafts…','');
    try{const data=await api('/business/programs/'+encodeURIComponent(id));if(company!==state.companyId)return;clear(root);
      text('businessDetailsTitle',data.program.idea.slice(0,90));
      if(!data.artifacts.length)empty(root,'Work queued.','Worker results appear here only when a local model returns a valid draft.');
      for(const a of data.artifacts){const box=element('article','panel roomy'),h=element('h3',null,a.role.toUpperCase()+' · '+a.content.title);
        box.append(h,element('p','muted',a.content.summary));
        for(const d of a.content.deliverables){box.append(element('h4',null,d.name),element('pre','factory-code',d.content));}
        box.append(element('p','capacity-hint','Unverified local-model draft · '+a.content.limitations));root.append(box);}
    }catch(err){empty(root,'Unable to load company drafts.',err.message);}
  }
  async function submitLead(e){e.preventDefault();feedback('leadMessage','Saving lead…');try{await api('/business/leads',{method:'POST',body:{name:$('leadName').value,organization:$('leadOrg').value,email:$('leadEmail').value}});
    $('businessLeadForm').reset();feedback('leadMessage','Lead stored under this workspace.');await refreshBusiness();}catch(err){feedback('leadMessage',err.message,true);}}
  async function submitTicket(e){e.preventDefault();feedback('ticketMessageStatus','Saving ticket…');try{await api('/business/tickets',{method:'POST',body:{subject:$('ticketSubject').value,message:$('ticketMessage').value}});
    $('businessTicketForm').reset();feedback('ticketMessageStatus','Ticket stored under this workspace.');await refreshBusiness();}catch(err){feedback('ticketMessageStatus',err.message,true);}}
  async function refreshFactory(){const company=state.companyId,root=$('factoryProposals');
    const local=state.provider?.live_requests;
    text('factoryModelState',local?'LOCAL MODEL CONFIGURED':'MODEL NOT CONFIGURED');
    const operator=roleInCurrentCompany()!=='viewer';
    $('factoryForm').querySelector('button[type=submit]').disabled=!operator;
    $('factoryInspectButton').disabled=!operator;
    try{const proposals=await api('/factory/proposals');if(company!==state.companyId)return;clear(root);
      if(!proposals.length){empty(root,'No engineering proposals yet.','Create a mission with the local model, run the worker, then return here for a reviewable artifact.');return;}
      for(const item of proposals){const row=element('button','mission-item');row.type='button';const copy=element('span','mission-copy');copy.append(element('strong',null,item.summary),element('small',null,item.model+' · '+formatDate(item.created_at)));row.append(element('span','mission-icon','⌘'),copy,tagForStatus('UNTRUSTED'));row.addEventListener('click',()=>openFactoryProposal(item.id));root.append(row);}
    }catch(err){empty(root,'Proposals unavailable.',err.message);}
  }
  async function openFactoryProposal(id){const company=state.companyId,body=$('factoryPreviewBody');
    $('factoryPreview').hidden=false;empty(body,'Loading candidate…','');
    try{const item=await api('/factory/proposals/'+encodeURIComponent(id));if(company!==state.companyId)return;
      text('factoryPreviewTitle',item.summary);clear(body);
      body.append(element('p','capacity-hint','UNTRUSTED CANDIDATE · NOT EXECUTED · NOT TESTED · NOT DEPLOYED'));
      body.append(element('p','capacity-hint',item.limitations||'No limitations reported'));
      for(const change of item.changes){const block=element('div','factory-code-block');block.append(element('strong',null,change.path+' · '+(change.syntax.checked?'syntax checked':'syntax unchecked')));
        const code=element('pre','factory-code',change.content);block.append(code);body.append(block);}
      const controls=element('div','factory-operations');
      const heading=element('h3',null,'Execution pipeline');controls.append(heading);
      const mode=element('select');for(const [value,label] of [['python_syntax','Check Python in sandbox'],['python_unittest','Run Python unit tests'],['python_entrypoint','Execute Python entrypoint'],['node_test','Run Node tests']]){const option=element('option',null,label);option.value=value;mode.append(option);}
      const entry=element('input');entry.placeholder='Entrypoint path for Python run';entry.maxLength=180;
      const run=element('button','secondary-button','Queue isolated run');run.type='button';run.disabled=roleInCurrentCompany()==='viewer';
      controls.append(mode,entry,run);
      const repo=element('input');repo.placeholder='Authorized owner/repository';repo.maxLength=181;
      const publish=element('button','secondary-button','Create draft pull request');publish.type='button';publish.disabled=roleInCurrentCompany()!=='owner';controls.append(repo,publish);
      const environment=element('select');for(const target of ['staging','production']){const o=element('option',null,target);o.value=target;environment.append(o);}
      const publishJob=element('input');publishJob.placeholder='Published PR job ID';publishJob.maxLength=80;
      const deploy=element('button','secondary-button','Request deployment approval');deploy.type='button';deploy.disabled=roleInCurrentCompany()!=='owner';
      controls.append(publishJob,environment,deploy);
      const notice=element('p','form-feedback','No code executes on this web server; a separately configured runner is required.');controls.append(notice);
      const history=element('div','factory-job-history');controls.append(history);body.append(controls);
      const fresh=async()=>{const all=await api('/factory/jobs?proposal_id='+encodeURIComponent(id));if(company!==state.companyId)return;clear(history);for(const j of all.jobs){
        const line=element('div','capacity-hint',j.kind+' · '+j.status+' · '+j.id);const detail=element('button','soft-link','Details');detail.type='button';detail.addEventListener('click',async()=>{try{const v=await api('/factory/jobs/'+encodeURIComponent(j.id));notice.textContent=JSON.stringify(v.result||v.status).slice(0,5000);}catch(e){notice.textContent=e.message;}});
        line.append(detail);if(j.kind==='deploy'&&j.status==='WAITING_APPROVAL'&&roleInCurrentCompany()==='owner'){const approve=element('button','secondary-button','Approve deployment');approve.type='button';approve.addEventListener('click',async()=>{try{await api('/factory/deployments/'+encodeURIComponent(j.id)+'/approve',{method:'POST'});notice.textContent='Deployment approved; external workflow not yet confirmed.';await fresh();}catch(e){notice.textContent=e.message;}});line.append(approve);}history.append(line);
      }};
      run.addEventListener('click',async()=>{try{const result=await api('/factory/proposals/'+encodeURIComponent(id)+'/tests',{method:'POST',body:{mode:mode.value,entrypoint:mode.value==='python_entrypoint'?entry.value.trim():null}});notice.textContent='Test queued: '+result.job_id;await fresh();}catch(e){notice.textContent=e.message;}});
      publish.addEventListener('click',async()=>{try{const result=await api('/factory/proposals/'+encodeURIComponent(id)+'/pull-requests',{method:'POST',body:{repo:repo.value.trim()}});notice.textContent='PR job queued: '+result.job_id;await fresh();}catch(e){notice.textContent=e.message;}});
      deploy.addEventListener('click',async()=>{try{const result=await api('/factory/proposals/'+encodeURIComponent(id)+'/deployments',{method:'POST',body:{publish_job_id:publishJob.value.trim(),environment:environment.value}});notice.textContent='Approval required for deployment job '+result.job_id;await fresh();}catch(e){notice.textContent=e.message;}});
      await fresh();
    }catch(err){empty(body,'Unable to open proposal.',err.message);}
  }
  initAuth();
})();
