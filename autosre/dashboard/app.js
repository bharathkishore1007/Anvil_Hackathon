/* ═══════════════════════════════════════════════════
   AutoSRE Dashboard — Application Logic
   ═══════════════════════════════════════════════════ */

const API_BASE = '';
let pollInterval = null;
let currentIncidentId = null;
let incidents = {};

// ─── Init ───
document.addEventListener('DOMContentLoaded', () => {
    checkSystemHealth();
    refreshIncidents();
    pollInterval = setInterval(() => {
        checkSystemHealth();
        refreshIncidents();
        if (currentIncidentId) loadIncidentDetails(currentIncidentId);
    }, 3000);
});

// ─── System Health ───
async function checkSystemHealth() {
    try {
        const res = await fetch(`${API_BASE}/health`);
        const data = await res.json();
        const dot = document.querySelector('.status-dot');
        const text = document.getElementById('statusText');

        if (data.status === 'healthy') {
            dot.className = 'status-dot pulse';
            text.textContent = 'System Operational';
        } else {
            dot.className = 'status-dot pulse';
            dot.style.background = '#FF9100';
            text.textContent = 'Degraded';
        }

        // Update infrastructure integrations
        updateIntegration('intOllama', data.checks?.ollama);
        updateIntegration('intRedis', data.checks?.redis);
        updateIntegration('intPostgres', data.checks?.postgres);

        // Fetch system status for app integrations
        const sRes = await fetch(`${API_BASE}/system/status`);
        const sData = await sRes.json();

        updateIntegration('intSlack', sData.integrations?.slack, true);
        updateIntegration('intGithub', sData.integrations?.github, true);
        updateIntegration('intJira', sData.integrations?.jira, true);
        updateIntegration('intLangfuse', sData.integrations?.langfuse, true);
        updateIntegration('intEmail', sData.integrations?.email, true);

        // Store langfuse URL for click-through
        if (sData.langfuse_url) {
            window._langfuseUrl = sData.langfuse_url;
        }

        document.getElementById('modelName').textContent = sData.ollama_model || 'Unknown';

        // Update metrics
        document.getElementById('metricTotal').textContent = sData.total_incidents || 0;
        document.getElementById('metricActive').textContent = sData.active_incidents?.length || 0;
        document.getElementById('metricResolved').textContent = sData.resolved_incidents || 0;

    } catch (e) {
        document.querySelector('.status-dot').className = 'status-dot error';
        document.getElementById('statusText').textContent = 'API Offline';
    }
}

function updateIntegration(id, connected, isConfigured) {
    const el = document.getElementById(id);
    if (!el) return;
    const status = el.querySelector('.int-status');
    if (connected === true) {
        status.textContent = 'CONNECTED';
        status.className = 'int-status connected';
    } else if (connected === false && isConfigured) {
        status.textContent = 'NOT SET';
        status.className = 'int-status disconnected';
    } else {
        status.textContent = 'OFFLINE';
        status.className = 'int-status disconnected';
    }
}

function openLangfuse() {
    const url = window._langfuseUrl || 'https://jp.cloud.langfuse.com';
    window.open(url, '_blank');
}

// ─── Incidents ───
async function refreshIncidents() {
    try {
        const res = await fetch(`${API_BASE}/incidents`);
        const data = await res.json();
        const feed = document.getElementById('incidentFeed');
        const list = data.incidents || [];

        if (list.length === 0) {
            feed.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">🛡️</div>
                    <h3>No incidents yet</h3>
                    <p>Click "Simulate Incident" to trigger the autonomous pipeline</p>
                </div>`;
            return;
        }

        feed.innerHTML = list.map(inc => {
            const id = inc.incident_id || 'Unknown';
            const status = inc.status || 'open';
            const severity = inc.severity || 'medium';
            const isActive = id === currentIncidentId ? ' active' : '';
            const isProcessing = status === 'processing' ? ' shimmer' : '';
            incidents[id] = inc;
            return `
                <div class="incident-card severity-${severity}${isActive}${isProcessing}"
                     onclick="selectIncident('${id}')">
                    <div class="incident-header">
                        <span class="incident-id">${id}</span>
                        <span class="status-badge ${status}">${formatStatus(status)}</span>
                    </div>
                    <div class="incident-title">${escapeHtml(inc.title || 'Untitled')}</div>
                    <div class="incident-meta">
                        <span class="severity-badge ${severity}">${severity}</span>
                        <span>📡 ${inc.source || 'manual'}</span>
                        <span>⏱️ ${formatTime(inc.timestamp || inc.created_at)}</span>
                    </div>
                </div>`;
        }).join('');
    } catch (e) {
        console.error('Failed to refresh incidents:', e);
    }
}

function selectIncident(id) {
    currentIncidentId = id;
    document.querySelectorAll('.incident-card').forEach(c => c.classList.remove('active'));
    event?.target?.closest?.('.incident-card')?.classList?.add?.('active');
    loadIncidentDetails(id);
}

async function loadIncidentDetails(id) {
    try {
        const res = await fetch(`${API_BASE}/incidents/${id}`);
        const data = await res.json();
        const inc = data.incident || {};
        const runs = data.agent_runs || [];
        const panel = document.getElementById('incidentDetails');

        // Update agent grid
        updateAgentNodes(inc, runs);
        document.getElementById('liveBadge').style.display =
            inc.status === 'processing' ? '' : 'none';

        let html = `
            <div class="detail-section">
                <h4>📋 Overview</h4>
                <div class="detail-text">
                    <strong>${escapeHtml(inc.title || 'Untitled')}</strong><br>
                    ${escapeHtml(inc.description || 'No description')}
                </div>
            </div>`;

        if (inc.root_cause) {
            html += `
                <div class="detail-section">
                    <h4>🔍 Root Cause</h4>
                    <div class="detail-code">${escapeHtml(inc.root_cause)}</div>
                </div>`;
        }

        if (inc.resolution) {
            html += `
                <div class="detail-section">
                    <h4>✅ Resolution</h4>
                    <div class="detail-text">${escapeHtml(inc.resolution)}</div>
                </div>`;
        }

        if (inc.execution_plan?.tasks) {
            html += `
                <div class="detail-section">
                    <h4>🗺️ Execution Plan</h4>
                    <div class="detail-code">${JSON.stringify(inc.execution_plan.tasks, null, 2)}</div>
                </div>`;
        }

        if (inc.agent_results) {
            html += `<div class="detail-section"><h4>🤖 Agent Results</h4>`;
            for (const [agent, result] of Object.entries(inc.agent_results)) {
                const preview = typeof result === 'object'
                    ? JSON.stringify(result, null, 2).substring(0, 300)
                    : String(result).substring(0, 300);
                html += `
                    <div style="margin-bottom: 10px">
                        <span class="timeline-agent">${agent}</span>
                        <div class="detail-code">${escapeHtml(preview)}${preview.length >= 300 ? '...' : ''}</div>
                    </div>`;
            }
            html += `</div>`;
        }

        if (runs.length > 0) {
            html += `<div class="detail-section"><h4>📊 Agent Trace</h4>`;
            runs.forEach(run => {
                const statusClass = run.status || 'completed';
                html += `
                    <div class="timeline-entry ${statusClass}">
                        <div class="timeline-time">${run.duration_ms ? run.duration_ms + 'ms' : '...'}</div>
                        <div class="timeline-content">
                            <span class="timeline-agent">${run.agent_type}</span>
                            — ${run.status} ${run.token_count ? `(${run.token_count} tokens)` : ''}
                        </div>
                    </div>`;
            });
            html += `</div>`;
        }

        panel.innerHTML = html;

    } catch (e) {
        document.getElementById('incidentDetails').innerHTML = `
            <div class="empty-state small"><p>Failed to load details</p></div>`;
    }
}

function updateAgentNodes(incident, runs) {
    const agentStates = {};

    // Priority 1: live agent_status from pipeline (real-time)
    if (incident.agent_status) {
        for (const [agent, status] of Object.entries(incident.agent_status)) {
            agentStates[agent] = status;
        }
    }

    // Priority 2: from agent_results (completed)
    if (incident.agent_results) {
        for (const agent of Object.keys(incident.agent_results)) {
            const r = incident.agent_results[agent];
            if (!agentStates[agent] || agentStates[agent] === 'idle') {
                agentStates[agent] = r?.error ? 'failed' : 'completed';
            }
        }
    }

    // Priority 3: from DB runs
    runs.forEach(run => {
        if (!agentStates[run.agent_type]) {
            agentStates[run.agent_type] = run.status === 'completed' ? 'completed' :
                run.status === 'running' ? 'running' : run.status === 'failed' ? 'failed' : 'idle';
        }
    });

    document.querySelectorAll('.agent-node').forEach(node => {
        const agent = node.dataset.agent;
        if (!agent) return;
        const state = agentStates[agent] || 'idle';
        node.className = `agent-node ${state}`;
        const statusEl = node.querySelector('.agent-status');
        if (statusEl) {
            statusEl.textContent = state.charAt(0).toUpperCase() + state.slice(1);
            statusEl.className = `agent-status ${state}`;
        }
    });
}

// ─── Simulation ───
function simulateIncident() {
    document.getElementById('simulateModal').style.display = 'flex';
}

function closeModal() {
    document.getElementById('simulateModal').style.display = 'none';
}

async function fireSimulation() {
    const btn = document.getElementById('btnFire');
    btn.disabled = true;
    btn.textContent = '⏳ Firing...';

    try {
        const body = {
            title: document.getElementById('simTitle').value,
            description: document.getElementById('simDescription').value,
            severity: document.getElementById('simSeverity').value,
            source: document.getElementById('simSource').value,
        };

        const res = await fetch(`${API_BASE}/incidents/simulate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        const data = await res.json();
        closeModal();
        showToast(`🔥 Incident ${data.incident_id} fired!`, 'success');
        currentIncidentId = data.incident_id;

        // Immediately refresh
        setTimeout(refreshIncidents, 500);
        setTimeout(() => loadIncidentDetails(data.incident_id), 1000);

    } catch (e) {
        showToast(`❌ Failed to fire incident: ${e.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '🔥 Fire Incident';
    }
}

// ─── Toast Notifications ───
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(20px)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ─── Utilities ───
function formatStatus(status) {
    const map = {
        'open': '● Open',
        'processing': '◉ Processing',
        'investigating': '◉ Investigating',
        'diagnosed_and_escalated': '✓ Resolved',
        'resolved': '✓ Resolved',
        'failed': '✗ Failed',
    };
    return map[status] || status;
}

function formatTime(ts) {
    if (!ts) return '';
    try {
        const d = new Date(ts);
        const now = new Date();
        const diff = Math.floor((now - d) / 1000);
        if (diff < 60) return `${diff}s ago`;
        if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
        return d.toLocaleDateString();
    } catch { return ts; }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

// Close modal on Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
});
