/* ═══════════════════════════════════════════════════
   AutoSRE Dashboard v3 — Application Logic
   Features: multi-view, search/filter, export, logs
   ═══════════════════════════════════════════════════ */
const API = '';
let pollTimer = null;
let currentIncidentId = null;
let allIncidents = [];
let activityLog = [];

// ─── Auth ───
function getToken() { return localStorage.getItem('autosre_token'); }
function authHeaders() { return { 'Authorization': `Bearer ${getToken()}` }; }
function logout() {
    localStorage.removeItem('autosre_token');
    localStorage.removeItem('autosre_user');
    window.location.href = '/login';
}

// ─── Init ───
document.addEventListener('DOMContentLoaded', () => {
    if (!getToken()) { window.location.href = '/login'; return; }
    checkHealth();
    refreshIncidents();
    buildAgentsView();
    pollTimer = setInterval(() => {
        checkHealth();
        refreshIncidents();
        if (currentIncidentId) loadDetail(currentIncidentId);
    }, 3000);
});

// ─── View Switching ───
function switchView(name) {
    if (name === 'integrations') { window.location.href = '/settings'; return; }
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    const view = document.getElementById(`view-${name}`);
    const nav = document.querySelector(`[data-view="${name}"]`);
    if (view) view.classList.add('active');
    if (nav) nav.classList.add('active');
    const titles = { dashboard:'Dashboard', incidents:'Incidents', agents:'Agents', logs:'Activity Logs' };
    document.getElementById('pageTitle').textContent = titles[name] || name;
}

// ─── Health & Status ───
async function checkHealth() {
    try {
        const [hRes, sRes] = await Promise.all([
            fetch(`${API}/health`), fetch(`${API}/system/status`)
        ]);
        const h = await hRes.json();
        const s = await sRes.json();

        // System chip
        const dot = document.querySelector('.chip-dot');
        const txt = document.getElementById('chipText');
        if (h.status === 'healthy') { dot.className='chip-dot online'; txt.textContent='System Online'; }
        else { dot.className='chip-dot offline'; txt.textContent='Degraded'; }

        // Model
        document.getElementById('modelName').textContent = s.ollama_model || '—';

        // Core infra integrations (global — these are system-level)
        updateInt('intOllama', h.checks?.ollama);
        updateInt('intRedis', h.checks?.redis);
        updateInt('intPostgres', h.checks?.postgres);

        // User-specific integrations — check from user's own settings
        checkUserIntegrations();

        // URLs
        if (s.langfuse_url) window._langfuseUrl = s.langfuse_url;
        if (s.omium_url) window._omiumUrl = s.omium_url;

        // Metrics — ONLY from allIncidents (per-user filtered)
        const total = allIncidents.length;
        const resolved = allIncidents.filter(i => i.status === 'diagnosed_and_escalated' || i.status === 'resolved').length;
        const active = allIncidents.filter(i => i.status === 'processing' || i.status === 'investigating' || i.status === 'open').length;
        document.getElementById('metricTotal').textContent = total;
        document.getElementById('metricActive').textContent = active;
        document.getElementById('metricResolved').textContent = resolved;
        document.getElementById('navIncidentCount').textContent = total || '';

        // Avg resolution time
        const resolvedIncs = allIncidents.filter(i => i.pipeline_duration_ms > 0);
        const avgEl = document.getElementById('metricAvgTime');
        if (resolvedIncs.length) {
            const avgMs = resolvedIncs.reduce((s, i) => s + i.pipeline_duration_ms, 0) / resolvedIncs.length;
            avgEl.textContent = (avgMs / 1000).toFixed(1) + 's';
        } else if (resolved > 0) {
            avgEl.textContent = '~30s';
        } else {
            avgEl.textContent = 'N/A';
        }

        // Bars
        const pct = total > 0 ? Math.min((resolved/total)*100, 100) : 0;
        document.getElementById('metricBar3').style.width = pct + '%';
        document.getElementById('metricBar2').style.width = (active > 0 ? 100 : 0) + '%';
        document.getElementById('metricBar1').style.width = (total > 0 ? 60 : 0) + '%';
        document.getElementById('metricBar4').style.width = (resolvedIncs.length > 0 ? 70 : resolved > 0 ? 50 : 0) + '%';

    } catch {
        document.querySelector('.chip-dot').className = 'chip-dot offline';
        document.getElementById('chipText').textContent = 'Offline';
    }
}

// Check user's own integration settings
let _userIntChecked = false;
async function checkUserIntegrations() {
    if (_userIntChecked) return; // Only check once per session
    try {
        const res = await fetch(`${API}/settings/integrations`, {headers: authHeaders()});
        if (!res.ok) return;
        const data = await res.json();
        const ints = data.integrations || {};
        updateInt('intSlack', ints.slack?.configured || false);
        updateInt('intGithub', ints.github?.configured || false);
        updateInt('intJira', ints.jira?.configured || false);
        updateInt('intEmail', ints.email?.configured || false);
        updateInt('intLangfuse', ints.langfuse?.configured || false);
        updateInt('intOmium', ints.omium?.configured || false);
        _userIntChecked = true;

        // Show welcome popup if NO integrations are configured (first-time user)
        const hasAny = Object.values(ints).some(v => v.configured);
        if (!hasAny && !sessionStorage.getItem('welcomeShown')) {
            showWelcomePopup();
            sessionStorage.setItem('welcomeShown', '1');
        }
    } catch {
        // If settings endpoint fails, show as offline
        ['intSlack','intGithub','intJira','intEmail','intLangfuse','intOmium'].forEach(id => updateInt(id, false));
    }
}

function updateInt(id, val) {
    const el = document.getElementById(id);
    if (!el) return;
    const dot = el.querySelector('.int-dot');
    const v = el.querySelector('.int-val');
    if (val === true) { dot.className='int-dot on'; v.textContent='Connected'; v.className='int-val on'; }
    else { dot.className='int-dot off'; v.textContent='Offline'; v.className='int-val off'; }
}

function openLangfuse() { window.open(window._langfuseUrl || 'https://jp.cloud.langfuse.com', '_blank'); }
function openOmium() { window.open(window._omiumUrl || 'https://app.omium.ai', '_blank'); }

// ─── Incidents ───
async function refreshIncidents() {
    try {
        const res = await fetch(`${API}/incidents`, {headers: authHeaders()});
        const data = await res.json();
        allIncidents = data.incidents || [];
        renderRecentIncidents();
        renderIncidentsList();
    } catch(e) { console.error('Refresh failed:', e); }
}

function renderRecentIncidents() {
    const el = document.getElementById('recentIncidents');
    if (!allIncidents.length) {
        el.innerHTML = `<div class="empty-state"><svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg><h3>No incidents yet</h3><p>Click "Simulate Incident" to trigger the autonomous pipeline</p></div>`;
        return;
    }
    el.innerHTML = allIncidents.slice(0, 10).map(inc => incidentRow(inc)).join('');
}

function renderIncidentsList() {
    const el = document.getElementById('incidentsList');
    if (!el) return;
    const search = (document.getElementById('incidentSearch')?.value || '').toLowerCase();
    const sev = document.getElementById('filterSeverity')?.value || '';
    const stat = document.getElementById('filterStatus')?.value || '';

    let filtered = allIncidents.filter(inc => {
        if (search && !(inc.title||'').toLowerCase().includes(search) && !(inc.incident_id||'').toLowerCase().includes(search)) return false;
        if (sev && inc.severity !== sev) return false;
        if (stat && inc.status !== stat) return false;
        return true;
    });

    if (!filtered.length) {
        el.innerHTML = '<div class="empty-state"><h3>No matching incidents</h3></div>';
        return;
    }
    el.innerHTML = filtered.map(inc => incidentRow(inc)).join('');
}

function incidentRow(inc) {
    const id = inc.incident_id || '??';
    const isActive = id === currentIncidentId ? ' active' : '';
    const isProcesing = inc.status === 'processing' ? ' processing' : '';
    return `<div class="inc-row${isActive}${isProcesing}" onclick="selectIncident('${id}')">
        <div class="inc-sev ${inc.severity||'medium'}"></div>
        <div class="inc-body">
            <div class="inc-id">${id}</div>
            <div class="inc-title">${esc(inc.title||'Untitled')}</div>
            <div class="inc-meta"><span class="badge ${inc.severity||'medium'}">${inc.severity||'medium'}</span><span class="badge ${inc.status||'open'}">${fmtStatus(inc.status)}</span><span>${fmtTime(inc.timestamp||inc.created_at)}</span></div>
        </div></div>`;
}

function filterIncidents() { renderIncidentsList(); }

function selectIncident(id) {
    currentIncidentId = id;
    document.querySelectorAll('.inc-row').forEach(r => r.classList.remove('active'));
    loadDetail(id);
    // If on dashboard, switch to incidents view
    if (document.getElementById('view-dashboard').classList.contains('active')) switchView('incidents');
}

async function loadDetail(id) {
    try {
        const res = await fetch(`${API}/incidents/${id}`);
        if (!res.ok) return;
        const data = await res.json();
        const inc = data.incident || {};
        const runs = data.agent_runs || [];

        updateAgents(inc, runs);
        document.getElementById('liveBadge').style.display = inc.status === 'processing' ? '' : 'none';

        // Log activity
        addLog('info', `Loaded incident ${id} — ${inc.status}`);

        let html = `<div class="detail-header"><h2>${esc(inc.title||'Untitled')}</h2><div class="detail-badges"><span class="badge ${inc.severity}">${inc.severity}</span><span class="badge ${inc.status}">${fmtStatus(inc.status)}</span>${inc.pipeline_duration_ms?`<span style="font-size:0.7rem;color:var(--text-3)">⏱ ${(inc.pipeline_duration_ms/1000).toFixed(1)}s</span>`:''}</div></div>`;

        // Description
        html += `<div class="detail-section"><h4>📋 Description</h4><div class="detail-text">${esc(inc.description||'No description')}</div></div>`;

        // Root cause
        if (inc.root_cause) html += `<div class="detail-section"><h4>🔍 Root Cause</h4><div class="detail-code">${esc(inc.root_cause)}</div></div>`;

        // Execution plan
        if (inc.execution_plan?.tasks) html += `<div class="detail-section"><h4>🗺️ Execution Plan</h4><div class="detail-code">${esc(JSON.stringify(inc.execution_plan.tasks,null,2))}</div></div>`;

        // Agent results
        if (inc.agent_results) {
            html += `<div class="detail-section"><h4>🤖 Agent Results</h4>`;
            for (const [agent, result] of Object.entries(inc.agent_results)) {
                const preview = typeof result==='object' ? JSON.stringify(result,null,2) : String(result);
                const truncated = preview.length > 500 ? preview.substring(0,500)+'…' : preview;
                html += `<div class="agent-result-card"><h5>${agent}</h5><div class="detail-code">${esc(truncated)}</div></div>`;
            }
            html += `</div>`;
        }

        // Post-resolution monitoring
        if (inc.post_resolution_monitoring) {
            const mon = inc.post_resolution_monitoring;
            html += `<div class="detail-section"><h4>🔄 Post-Resolution Monitoring</h4><dl class="detail-kv">`;
            html += `<dt>Duration</dt><dd>${mon.duration_seconds}s</dd>`;
            html += `<dt>All Healthy</dt><dd>${mon.all_healthy ? '✅ Yes' : '⚠️ No'}</dd>`;
            html += `<dt>Checks</dt><dd>${(mon.checks||[]).length}</dd>`;
            html += `</dl></div>`;
        }

        // Key-value summary
        html += `<div class="detail-section"><h4>📊 Metadata</h4><dl class="detail-kv">`;
        html += `<dt>ID</dt><dd style="font-family:var(--mono)">${id}</dd>`;
        html += `<dt>Source</dt><dd>${inc.source||'manual'}</dd>`;
        html += `<dt>Created</dt><dd>${fmtTime(inc.timestamp||inc.created_at)}</dd>`;
        if (inc.completed_at) html += `<dt>Completed</dt><dd>${fmtTime(inc.completed_at)}</dd>`;
        html += `</dl></div>`;

        document.getElementById('incidentDetail').innerHTML = html;

        // Also highlight in list
        document.querySelectorAll('.inc-row').forEach(r => {
            r.classList.toggle('active', r.innerHTML.includes(id));
        });

    } catch(e) {
        document.getElementById('incidentDetail').innerHTML = `<div class="empty-state"><h3>Failed to load</h3><p>${e.message}</p></div>`;
    }
}

function updateAgents(inc, runs) {
    const states = {};
    if (inc.agent_status) for (const [a,s] of Object.entries(inc.agent_status)) states[a]=s;
    if (inc.agent_results) for (const a of Object.keys(inc.agent_results)) {
        if (!states[a]||states[a]==='idle') states[a] = inc.agent_results[a]?.error ? 'failed' : 'completed';
    }
    runs.forEach(r => { if(!states[r.agent_type]) states[r.agent_type]=r.status==='completed'?'completed':r.status==='running'?'running':'idle'; });

    document.querySelectorAll('.agent-chip').forEach(chip => {
        const a = chip.dataset.agent; if(!a) return;
        const s = states[a]||'idle';
        chip.className = `agent-chip ${s}`;
        const st = chip.querySelector('.agent-status');
        if(st){ st.textContent=s.charAt(0).toUpperCase()+s.slice(1); st.className=`agent-status ${s}`; }
    });
}

// ─── Agents View ───
function buildAgentsView() {
    const agents = [
        {name:'Planner',icon:'🧠',desc:'Creates execution plans and task delegation for each incident. Orchestrates the multi-agent workflow.'},
        {name:'Analyst',icon:'🔍',desc:'Analyzes incident data using LLM reasoning. Identifies root cause and severity assessment.'},
        {name:'Researcher',icon:'📚',desc:'Searches the web (DuckDuckGo), CVE databases, StackOverflow, and internal runbooks for context.'},
        {name:'Coder',icon:'💻',desc:'Generates code patches, fix suggestions, and validation scripts for the identified issue.'},
        {name:'Executor',icon:'⚡',desc:'Takes action: creates GitHub issues, Jira tickets, triggers rollbacks, and executes remediation.'},
        {name:'Communicator',icon:'📢',desc:'Posts Slack notifications, sends email reports, and updates stakeholders on incident status.'},
    ];
    document.getElementById('agentsDetailGrid').innerHTML = agents.map(a => `
        <div class="agent-detail-card"><div class="agent-icon">${a.icon}</div><h3>${a.name}</h3><p>${a.desc}</p><div class="agent-status idle" data-agent="${a.name.toLowerCase()}" id="agentStatus_${a.name.toLowerCase()}">Idle</div></div>
    `).join('');
}

// ─── Integrations View ───
function buildIntegrationsView() {
    const ints = [
        {name:'Gemini LLM',id:'intOllama',desc:'Google Gemini 2.5 Flash — cloud-native AI model powering all agent reasoning.'},
        {name:'Slack',id:'intSlack',desc:'Incident notifications and follow-up reports posted to #incidents channel.'},
        {name:'GitHub',id:'intGithub',desc:'Auto-creates issues and triggers deployment rollbacks on incident detection.'},
        {name:'Jira',id:'intJira',desc:'Service desk ticket creation for incident tracking and SLA management.'},
        {name:'Email (SMTP)',id:'intEmail',desc:'Sends detailed incident reports to on-call engineers via SMTP.'},
        {name:'Langfuse',id:'intLangfuse',desc:'LLM observability and tracing. Click to open dashboard.',click:'openLangfuse()'},
        {name:'Omium',id:'intOmium',desc:'AI reliability monitoring and execution tracing. Click to open dashboard.',click:'openOmium()'},
        {name:'Redis',id:'intRedis',desc:'In-memory caching for active incident state and real-time agent coordination.'},
        {name:'PostgreSQL',id:'intPostgres',desc:'Persistent storage for incident history, agent runs, and vector embeddings.'},
    ];
    document.getElementById('intDetailGrid').innerHTML = ints.map(i => {
        const el = document.getElementById(i.id);
        const isOn = el?.querySelector('.int-dot')?.classList?.contains('on');
        return `<div class="int-detail-card" ${i.click?`onclick="${i.click}" style="cursor:pointer"`:''}>
            <h3>${i.name}</h3><div class="int-status-big ${isOn?'on':'off'}">${isOn?'● Connected':'○ Offline'}</div><p>${i.desc}</p></div>`;
    }).join('');
}

// ─── Logs ───
function addLog(level, msg) {
    const now = new Date();
    const ts = now.toTimeString().split(' ')[0];
    activityLog.push({ time: ts, level, msg, raw: `${ts} [${level.toUpperCase()}] ${msg}` });
    if (activityLog.length > 500) activityLog.shift();
    renderLogs();
}

function renderLogs() {
    const el = document.getElementById('logViewer');
    if (!el || !document.getElementById('view-logs').classList.contains('active')) return;
    const search = (document.getElementById('logSearch')?.value || '').toLowerCase();
    const level = document.getElementById('logLevel')?.value || '';
    const filtered = activityLog.filter(l => {
        if (search && !l.msg.toLowerCase().includes(search)) return false;
        if (level && l.level !== level) return false;
        return true;
    });
    if (!filtered.length) { el.innerHTML = '<div class="empty-state"><h3>No logs</h3></div>'; return; }
    el.innerHTML = filtered.map(l => `<div class="log-line"><span class="log-time">${l.time}</span><span class="log-level ${l.level}">${l.level.toUpperCase()}</span><span class="log-msg">${esc(l.msg)}</span></div>`).join('');
    el.scrollTop = el.scrollHeight;
}

function filterLogs() { renderLogs(); }
function clearLogs() { activityLog = []; renderLogs(); }

// ─── Export ───
function exportData() {
    exportIncidents('json');
}

function exportIncidents(format) {
    if (!allIncidents.length) { showToast('No incidents to export', 'info'); return; }
    let content, filename, type;
    if (format === 'csv') {
        const headers = ['incident_id','title','severity','status','source','timestamp','root_cause','pipeline_duration_ms'];
        const rows = allIncidents.map(inc => headers.map(h => `"${(inc[h]||'').toString().replace(/"/g,'""')}"`).join(','));
        content = [headers.join(','), ...rows].join('\n');
        filename = `autosre_incidents_${Date.now()}.csv`;
        type = 'text/csv';
    } else {
        content = JSON.stringify(allIncidents, null, 2);
        filename = `autosre_incidents_${Date.now()}.json`;
        type = 'application/json';
    }
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
    showToast(`Exported ${allIncidents.length} incidents as ${format.toUpperCase()}`, 'success');
    addLog('info', `Exported ${allIncidents.length} incidents as ${format}`);
}

function exportLogs() {
    if (!activityLog.length) { showToast('No logs to export', 'info'); return; }
    const content = activityLog.map(l => l.raw).join('\n');
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `autosre_logs_${Date.now()}.txt`; a.click();
    URL.revokeObjectURL(url);
    showToast('Logs exported', 'success');
}

// ─── Simulation ───
function simulateIncident() { document.getElementById('simulateModal').style.display = 'flex'; }
function closeModal() { document.getElementById('simulateModal').style.display = 'none'; }

async function fireSimulation() {
    const btn = document.getElementById('btnFire');
    btn.disabled = true; btn.textContent = '⏳ Firing…';
    try {
        const body = {
            title: document.getElementById('simTitle').value,
            description: document.getElementById('simDescription').value,
            severity: document.getElementById('simSeverity').value,
            source: document.getElementById('simSource').value,
        };
        const res = await fetch(`${API}/incidents/simulate`, { method:'POST', headers:{'Content-Type':'application/json', ...authHeaders()}, body:JSON.stringify(body) });
        const data = await res.json();
        closeModal();
        showToast(`Incident ${data.incident_id} fired!`, 'success');
        addLog('info', `Incident ${data.incident_id} simulated: ${body.title}`);
        currentIncidentId = data.incident_id;
        setTimeout(refreshIncidents, 500);
        setTimeout(() => loadDetail(data.incident_id), 1000);
        switchView('incidents');
    } catch(e) {
        showToast(`Failed: ${e.message}`, 'error');
        addLog('error', `Simulation failed: ${e.message}`);
    } finally {
        btn.disabled = false; btn.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> Fire Incident';
    }
}

// ─── Toast ───
function showToast(msg, type='info') {
    const c = document.getElementById('toastContainer');
    const t = document.createElement('div');
    t.className = `toast ${type}`; t.innerHTML = msg;
    c.appendChild(t);
    setTimeout(() => { t.style.opacity='0'; t.style.transform='translateX(16px)'; setTimeout(()=>t.remove(),300); }, 4000);
}

// ─── Utils ───
function fmtStatus(s) {
    return { open:'Open', processing:'Processing', investigating:'Investigating', diagnosed_and_escalated:'Resolved', resolved:'Resolved', failed:'Failed' }[s] || s;
}

function fmtTime(ts) {
    if (!ts) return '—';
    try {
        const d = new Date(ts); const now = new Date(); const diff = Math.floor((now-d)/1000);
        if (diff < 60) return `${diff}s ago`;
        if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
        return d.toLocaleDateString();
    } catch { return ts; }
}

function esc(t) { if(!t) return ''; const d=document.createElement('div'); d.textContent=String(t); return d.innerHTML; }

// Keyboard shortcuts
document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
    if (e.key === '1' && e.altKey) switchView('dashboard');
    if (e.key === '2' && e.altKey) switchView('incidents');
    if (e.key === '3' && e.altKey) switchView('agents');
    if (e.key === '4' && e.altKey) switchView('logs');
    if (e.key === '5' && e.altKey) switchView('integrations');
});

// ─── Sidebar Toggle ───
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const main = document.querySelector('.main');
    const toggle = document.getElementById('sidebarToggle');
    sidebar.classList.toggle('collapsed');
    main.classList.toggle('sidebar-collapsed');
    toggle.classList.toggle('collapsed');
}

// ─── Profile Dropdown ───
function initProfile() {
    const user = JSON.parse(localStorage.getItem('autosre_user') || '{}');
    const name = user.name || 'User';
    const email = user.email || '';
    document.getElementById('profileAvatar').textContent = name[0].toUpperCase();
    document.getElementById('profileName').textContent = name;
    document.getElementById('profileEmail').textContent = email;
}

function toggleProfileMenu() {
    const dd = document.getElementById('profileDropdown');
    dd.classList.toggle('open');
}

// Close dropdown when clicking outside
document.addEventListener('click', (e) => {
    const wrapper = document.getElementById('profileWrapper');
    const dd = document.getElementById('profileDropdown');
    if (wrapper && dd && !wrapper.contains(e.target)) {
        dd.classList.remove('open');
    }
});

// ─── Password Change ───
function openPasswordModal() {
    document.getElementById('profileDropdown').classList.remove('open');
    document.getElementById('passwordModal').style.display = 'flex';
    document.getElementById('pwError').style.display = 'none';
    document.getElementById('pwSuccess').style.display = 'none';
    document.getElementById('pwCurrent').value = '';
    document.getElementById('pwNew').value = '';
    document.getElementById('pwConfirm').value = '';
}

function closePasswordModal() {
    document.getElementById('passwordModal').style.display = 'none';
}

async function changePassword() {
    const err = document.getElementById('pwError');
    const ok = document.getElementById('pwSuccess');
    err.style.display = 'none'; ok.style.display = 'none';

    const current = document.getElementById('pwCurrent').value;
    const newPw = document.getElementById('pwNew').value;
    const confirm = document.getElementById('pwConfirm').value;

    if (!current || !newPw) { err.textContent = 'All fields required'; err.style.display = 'block'; return; }
    if (newPw.length < 6) { err.textContent = 'New password must be at least 6 characters'; err.style.display = 'block'; return; }
    if (newPw !== confirm) { err.textContent = 'Passwords do not match'; err.style.display = 'block'; return; }

    const btn = document.getElementById('btnChangePw');
    btn.disabled = true; btn.textContent = 'Updating…';

    try {
        const res = await fetch('/auth/change-password', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'Authorization': `Bearer ${getToken()}`},
            body: JSON.stringify({current_password: current, new_password: newPw}),
        });
        const data = await res.json();
        if (!res.ok) {
            err.textContent = data.detail || 'Failed to change password';
            err.style.display = 'block';
        } else {
            ok.textContent = 'Password updated successfully!';
            ok.style.display = 'block';
            setTimeout(closePasswordModal, 1500);
        }
    } catch (e) {
        err.textContent = 'Connection error'; err.style.display = 'block';
    } finally {
        btn.disabled = false; btn.textContent = 'Update Password';
    }
}

// Init profile on load
if (getToken()) initProfile();

// ─── Welcome Popup (for new users) ───
function showWelcomePopup() {
    const user = JSON.parse(localStorage.getItem('autosre_user') || '{}');
    const name = user.name || 'there';
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.id = 'welcomePopup';
    overlay.style.display = 'flex';
    overlay.innerHTML = `
        <div class="modal" style="max-width:460px">
            <div class="modal-header">
                <h3>👋 Welcome, ${name}!</h3>
                <button class="modal-close" onclick="document.getElementById('welcomePopup').remove()">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
            </div>
            <div class="modal-body" style="text-align:center;padding:24px">
                <div style="font-size:3rem;margin-bottom:12px">🚀</div>
                <h3 style="margin-bottom:8px;color:var(--text-1)">Get Started with AutoSRE</h3>
                <p style="color:var(--text-2);font-size:0.85rem;margin-bottom:20px;line-height:1.6">
                    Configure your integrations (Slack, GitHub, Jira, Email) to enable autonomous incident resolution, 
                    then simulate your first incident to see the AI agents in action.
                </p>
                <div style="display:flex;gap:10px;justify-content:center">
                    <button class="btn-primary" onclick="window.location.href='/settings'" style="padding:10px 20px">
                        🔗 Configure Integrations
                    </button>
                    <button class="btn-secondary" onclick="document.getElementById('welcomePopup').remove(); simulateIncident();" style="padding:10px 20px">
                        ⚡ Simulate Incident
                    </button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
}
