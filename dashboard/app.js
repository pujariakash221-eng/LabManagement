/**
 * Computer Lab Management - Operator Dashboard Client Application
 * Milestone 11: UI & UX Refinement
 */

(function () {
  'use strict';

  // Application State
  const state = {
    agents: [],
    selectedId: null,
    discovery: [],
    auditLogs: [],
    screenViewerId: null,
    screenWebSocket: null,
    username: null,
    role: null,
    statusFilter: 'all', // 'all' | 'online' | 'offline'
    pendingPower: null,   // { agent, action }
  };

  const serverOrigin = window.location.origin;

  // DOM Elements Cache
  const elements = {
    // Header & Session
    connectionDot: document.querySelector('#connection-dot'),
    connectionLabel: document.querySelector('#connection-label'),
    userName: document.querySelector('#user-name'),
    userAvatar: document.querySelector('#user-avatar'),
    rolePill: document.querySelector('#role-pill'),
    logoutBtn: document.querySelector('#logout-button'),
    updatedLabel: document.querySelector('#updated-label'),

    // Sidebar Navigation
    navDashboard: document.querySelector('#nav-dashboard'),
    navComputers: document.querySelector('#nav-computers'),
    navDiscovery: document.querySelector('#nav-discovery'),
    navActivity: document.querySelector('#nav-activity'),

    // Summary Metric Cards
    totalCount: document.querySelector('#total-count'),
    onlineCount: document.querySelector('#online-count'),
    offlineCount: document.querySelector('#offline-count'),
    discoveryCount: document.querySelector('#discovery-count'),

    // Computers Section
    searchInput: document.querySelector('#search-input'),
    filterTabs: document.querySelectorAll('.filter-tab'),
    refreshBtn: document.querySelector('#refresh-button'),
    refreshIcon: document.querySelector('#refresh-icon'),
    tableBody: document.querySelector('#agent-table-body'),
    tableMeta: document.querySelector('#table-meta'),
    detailsContent: document.querySelector('#details-content'),

    // Discovery Section
    discoveryMeta: document.querySelector('#discovery-meta'),
    scanBtn: document.querySelector('#scan-button'),
    scanIcon: document.querySelector('#scan-icon'),
    scanBtnLabel: document.querySelector('#scan-btn-label'),
    discoveryList: document.querySelector('#discovery-list'),

    // Activity Log Section (Admin)
    activitySection: document.querySelector('#activity-section'),
    auditTableBody: document.querySelector('#audit-table-body'),
    auditRefreshBtn: document.querySelector('#audit-refresh-button'),

    // Screen Viewer Modal
    screenModal: document.querySelector('#screen-modal'),
    screenModalTitle: document.querySelector('#screen-modal-title'),
    screenModalStatus: document.querySelector('#screen-modal-status'),
    screenModalClose: document.querySelector('#screen-modal-close'),
    screenImage: document.querySelector('#screen-image'),
    screenLoading: document.querySelector('#screen-loading'),
    screenLoadingText: document.querySelector('#screen-loading-text'),

    // Power Confirmation Modal
    powerModal: document.querySelector('#power-modal'),
    powerModalIcon: document.querySelector('#power-modal-icon'),
    powerModalTitle: document.querySelector('#power-modal-title'),
    powerModalDesc: document.querySelector('#power-modal-desc'),
    powerModalTargetHost: document.querySelector('#power-modal-target-host'),
    powerModalTargetIp: document.querySelector('#power-modal-target-ip'),
    powerModalWarning: document.querySelector('#power-modal-warning'),
    powerModalCancel: document.querySelector('#power-modal-cancel'),
    powerModalConfirm: document.querySelector('#power-modal-confirm'),
    powerConfirmSpinner: document.querySelector('#power-confirm-spinner'),
    powerConfirmLabel: document.querySelector('#power-confirm-label'),

    // Toast Container
    toastContainer: document.querySelector('#toast-container'),
  };

  // Helper Utilities
  function apiUrl(path) {
    return `${serverOrigin}${path}`;
  }

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str).replace(/[&<>'"]/g, (char) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;',
    }[char]));
  }

  function formatDate(value) {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '—';
    return date.toLocaleString([], {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  }

  function formatRelativeTime(value) {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '—';
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 10) return 'Just now';
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }

  // Toast Notification System
  function showToast(message, type = 'info', duration = 4000) {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    let icon = 'ℹ️';
    if (type === 'success') icon = '✓';
    if (type === 'danger') icon = '⚠️';
    if (type === 'warning') icon = '⚡';

    toast.innerHTML = `<span aria-hidden="true">${icon}</span><span>${escapeHtml(message)}</span>`;
    elements.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(12px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  // Connection State Management
  function setConnection(connected) {
    if (connected) {
      elements.connectionLabel.textContent = 'Server Connected';
      elements.connectionDot.className = 'status-dot connected';
    } else {
      elements.connectionLabel.textContent = 'Server Offline';
      elements.connectionDot.className = 'status-dot error';
    }
  }

  // Session & Role Handling
  async function loadSession() {
    try {
      const response = await fetch(apiUrl('/api/auth/session'), {
        cache: 'no-store',
        credentials: 'same-origin',
      });

      if (response.status === 401) {
        window.location.assign('/login?reason=expired');
        return;
      }

      if (response.ok) {
        const data = await response.json();
        state.username = data.username;
        state.role = data.role;

        // Update User Profile Badge in Header
        elements.userName.textContent = state.username;
        elements.userAvatar.textContent = state.username.slice(0, 1).toUpperCase();

        const roleLower = state.role.toLowerCase();
        elements.rolePill.textContent = state.role;
        elements.rolePill.className = `role-pill ${roleLower}`;

        // Admin-only view controls
        if (state.role === 'ADMIN') {
          elements.navActivity.classList.remove('hidden');
          elements.activitySection.classList.remove('hidden');
          loadAudit();
        } else {
          elements.navActivity.classList.add('hidden');
          elements.activitySection.classList.add('hidden');
        }

        renderTable();
        renderDetails();
      }
    } catch (err) {
      console.warn('Session verification error:', err);
    }
  }

  // Metrics Summary Cards
  function renderSummary() {
    const total = state.agents.length;
    const online = state.agents.filter((a) => a.status === 'ONLINE').length;
    const offline = state.agents.filter((a) => a.status === 'OFFLINE').length;

    elements.totalCount.textContent = total;
    elements.onlineCount.textContent = online;
    elements.offlineCount.textContent = offline;
    elements.discoveryCount.textContent = state.discovery.length;
  }

  // Filter and Search Computers Table
  function getFilteredAgents() {
    const query = elements.searchInput.value.trim().toLowerCase();
    return state.agents.filter((agent) => {
      // Status filter
      if (state.statusFilter === 'online' && agent.status !== 'ONLINE') return false;
      if (state.statusFilter === 'offline' && agent.status !== 'OFFLINE') return false;

      // Text search
      if (!query) return true;
      const haystack = [
        agent.hostname || '',
        agent.ip_address || '',
        agent.operating_system || '',
        agent.agent_id || '',
      ].join(' ').toLowerCase();

      return haystack.includes(query);
    });
  }

  function renderTable() {
    const visibleAgents = getFilteredAgents();
    elements.tableMeta.textContent = `Showing ${visibleAgents.length} of ${state.agents.length} registered workstations`;

    if (state.agents.length === 0) {
      elements.tableBody.innerHTML = `
        <tr>
          <td colspan="6" class="empty-state-box">
            <div class="empty-state-icon">💻</div>
            <div class="empty-state-text">No computers registered yet</div>
            <div class="empty-state-sub">Start the Lab Agent client on workstations to register them automatically.</div>
          </td>
        </tr>`;
      renderDetails();
      return;
    }

    if (visibleAgents.length === 0) {
      elements.tableBody.innerHTML = `
        <tr>
          <td colspan="6" class="empty-state-box">
            <div class="empty-state-icon">🔍</div>
            <div class="empty-state-text">No matching computers found</div>
            <div class="empty-state-sub">Try adjusting your search terms or filter criteria.</div>
          </td>
        </tr>`;
      renderDetails();
      return;
    }

    const canControlPower = ['OPERATOR', 'ADMIN'].includes(state.role);

    elements.tableBody.innerHTML = visibleAgents.map((agent) => {
      const isOnline = agent.status === 'ONLINE';
      const isSelected = agent.agent_id === state.selectedId;
      const statusBadge = isOnline
        ? '<span class="status-badge online">ONLINE</span>'
        : '<span class="status-badge offline">OFFLINE</span>';

      // Table quick action buttons
      let actionButtons = '';
      if (isOnline) {
        actionButtons += `<button class="action-icon-btn primary btn-table-screen" data-id="${escapeHtml(agent.agent_id)}" type="button" title="View live screen">📺 View</button>`;
        if (canControlPower) {
          actionButtons += `<button class="action-icon-btn btn-table-power" data-id="${escapeHtml(agent.agent_id)}" data-action="shutdown" type="button" title="Shut down workstation">⏻</button>`;
          actionButtons += `<button class="action-icon-btn btn-table-power" data-id="${escapeHtml(agent.agent_id)}" data-action="restart" type="button" title="Restart workstation">↻</button>`;
        }
      } else {
        actionButtons = '<span style="color: var(--text-muted); font-size: 11px;">Offline</span>';
      }

      return `
        <tr data-agent-id="${escapeHtml(agent.agent_id)}" class="${isSelected ? 'selected' : ''}">
          <td>${statusBadge}</td>
          <td>
            <div class="cell-host">
              <span class="hostname-text">${escapeHtml(agent.hostname)}</span>
              <span class="agent-id-sub">${escapeHtml(agent.agent_id)}</span>
            </div>
          </td>
          <td style="font-family: var(--font-mono); font-size: 12.5px;">${escapeHtml(agent.ip_address)}</td>
          <td>${escapeHtml(agent.operating_system)}</td>
          <td title="${escapeHtml(formatDate(agent.last_seen))}">${escapeHtml(formatRelativeTime(agent.last_seen))}</td>
          <td style="text-align: right;">
            <div class="table-actions" style="justify-content: flex-end;">${actionButtons}</div>
          </td>
        </tr>`;
    }).join('');

    // Attach Row Selection Events
    elements.tableBody.querySelectorAll('tr[data-agent-id]').forEach((row) => {
      row.addEventListener('click', (e) => {
        if (e.target.closest('button')) return;
        state.selectedId = row.dataset.agentId;
        renderTable();
      });
    });

    // Attach Screen View Buttons
    elements.tableBody.querySelectorAll('.btn-table-screen').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const agent = state.agents.find((a) => a.agent_id === btn.dataset.id);
        if (agent) openScreenViewer(agent.agent_id, agent.hostname);
      });
    });

    // Attach Table Power Action Buttons
    elements.tableBody.querySelectorAll('.btn-table-power').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const agent = state.agents.find((a) => a.agent_id === btn.dataset.id);
        if (agent) openPowerModal(agent, btn.dataset.action);
      });
    });

    renderDetails();
  }

  // Render Selected Computer Details Panel
  function renderDetails() {
    const agent = state.agents.find((item) => item.agent_id === state.selectedId);

    if (!agent) {
      elements.detailsContent.className = 'details-body empty-details';
      elements.detailsContent.innerHTML = `
        <div class="empty-details-icon">💻</div>
        <p>Select a computer from the inventory table to view details and available actions.</p>`;
      return;
    }

    const isOnline = agent.status === 'ONLINE';
    const canControlPower = ['OPERATOR', 'ADMIN'].includes(state.role);
    const statusBadge = isOnline
      ? '<span class="status-badge online">ONLINE</span>'
      : '<span class="status-badge offline">OFFLINE</span>';

    // Screen View Action Button
    let screenActionHtml = '';
    if (isOnline) {
      screenActionHtml = `
        <button id="btn-details-screen" class="btn btn-primary" style="width: 100%;" type="button">
          📺 View Live Screen
        </button>`;
    }

    // Power Actions HTML
    let powerActionsHtml = '';
    if (canControlPower && isOnline) {
      powerActionsHtml = `
        <div class="details-actions-wrapper">
          <div class="details-actions-title">Workstation Power Operations</div>
          <div class="power-controls-grid">
            <button id="btn-details-shutdown" class="btn btn-danger btn-sm" type="button">
              ⏻ Shutdown
            </button>
            <button id="btn-details-restart" class="btn btn-warning btn-sm" type="button">
              ↻ Restart
            </button>
          </div>
        </div>`;
    }

    elements.detailsContent.className = 'details-body';
    elements.detailsContent.innerHTML = `
      <div class="details-hero">
        <div class="details-avatar">${escapeHtml(agent.hostname.slice(0, 1).toUpperCase())}</div>
        <div class="details-titles">
          <div class="details-name" title="${escapeHtml(agent.hostname)}">${escapeHtml(agent.hostname)}</div>
          <div style="margin-top: 4px;">${statusBadge}</div>
        </div>
      </div>

      <div class="details-meta-list">
        <div class="meta-row">
          <span class="meta-key">Agent ID</span>
          <span class="meta-val mono" style="font-size: 11px;">
            ${escapeHtml(agent.agent_id)}
            <button id="btn-copy-id" type="button" title="Copy Agent ID" style="margin-left: 4px; color: var(--primary); cursor: pointer;">📋</button>
          </span>
        </div>
        <div class="meta-row">
          <span class="meta-key">Hostname</span>
          <span class="meta-val">${escapeHtml(agent.hostname)}</span>
        </div>
        <div class="meta-row">
          <span class="meta-key">IP Address</span>
          <span class="meta-val mono">${escapeHtml(agent.ip_address)}</span>
        </div>
        <div class="meta-row">
          <span class="meta-key">Operating System</span>
          <span class="meta-val">${escapeHtml(agent.operating_system)}</span>
        </div>
        <div class="meta-row">
          <span class="meta-key">First Seen</span>
          <span class="meta-val">${formatDate(agent.first_seen)}</span>
        </div>
        <div class="meta-row">
          <span class="meta-key">Last Heartbeat</span>
          <span class="meta-val">${formatDate(agent.last_seen)}</span>
        </div>
      </div>

      <div style="display: flex; flex-direction: column; gap: 12px;">
        ${screenActionHtml}
        ${powerActionsHtml}
      </div>`;

    // Copy Agent ID button listener
    const copyBtn = elements.detailsContent.querySelector('#btn-copy-id');
    if (copyBtn) {
      copyBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(agent.agent_id);
        showToast('Agent ID copied to clipboard.', 'success');
      });
    }

    // View Screen button listener
    const screenBtn = elements.detailsContent.querySelector('#btn-details-screen');
    if (screenBtn) {
      screenBtn.addEventListener('click', () => {
        openScreenViewer(agent.agent_id, agent.hostname);
      });
    }

    // Shutdown / Restart button listeners
    const shutdownBtn = elements.detailsContent.querySelector('#btn-details-shutdown');
    if (shutdownBtn) {
      shutdownBtn.addEventListener('click', () => openPowerModal(agent, 'shutdown'));
    }

    const restartBtn = elements.detailsContent.querySelector('#btn-details-restart');
    if (restartBtn) {
      restartBtn.addEventListener('click', () => openPowerModal(agent, 'restart'));
    }
  }

  // Power Action Confirmation Modal
  function openPowerModal(agent, action) {
    state.pendingPower = { agent, action };
    const isShutdown = action === 'shutdown';

    elements.powerModalTitle.textContent = isShutdown ? 'Confirm Computer Shutdown' : 'Confirm Computer Restart';
    elements.powerModalIcon.className = `confirm-header-icon ${isShutdown ? 'danger' : 'warning'}`;
    elements.powerModalIcon.textContent = isShutdown ? '⏻' : '↻';
    elements.powerModalDesc.innerHTML = `Are you sure you want to <strong>${isShutdown ? 'shut down' : 'restart'}</strong> workstation <strong>${escapeHtml(agent.hostname)}</strong>?`;
    elements.powerModalTargetHost.textContent = agent.hostname;
    elements.powerModalTargetIp.textContent = agent.ip_address;
    elements.powerModalWarning.textContent = isShutdown
      ? 'This will immediately power off the selected workstation. Any unsaved student or user work will be lost.'
      : 'Users currently working on this workstation will be interrupted while the system reboots.';

    elements.powerConfirmLabel.textContent = isShutdown ? 'Shut Down Workstation' : 'Restart Workstation';
    elements.powerModalConfirm.className = `btn ${isShutdown ? 'btn-danger' : 'btn-warning'}`;
    elements.powerConfirmSpinner.classList.add('hidden');
    elements.powerModalConfirm.disabled = false;
    elements.powerModalCancel.disabled = false;

    elements.powerModal.classList.add('active');
  }

  function closePowerModal() {
    state.pendingPower = null;
    elements.powerModal.classList.remove('active');
  }

  async function executePowerAction() {
    if (!state.pendingPower) return;
    const { agent, action } = state.pendingPower;

    elements.powerModalConfirm.disabled = true;
    elements.powerModalCancel.disabled = true;
    elements.powerConfirmSpinner.classList.remove('hidden');
    elements.powerConfirmLabel.textContent = 'Queueing...';

    try {
      const response = await fetch(apiUrl(`/api/agents/${encodeURIComponent(agent.agent_id)}/${action}`), {
        method: 'POST',
        credentials: 'same-origin',
      });

      if (response.status === 401) {
        window.location.assign('/login?reason=expired');
        return;
      }

      if (response.status === 403) {
        throw new Error('You do not have sufficient permissions for power management operations.');
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Power request could not be queued.');
      }

      closePowerModal();
      showToast(`${action === 'shutdown' ? 'Shutdown' : 'Restart'} command successfully queued for ${agent.hostname}.`, 'success');
      loadAgents();
      if (state.role === 'ADMIN') loadAudit();
    } catch (err) {
      showToast(err.message, 'danger');
      closePowerModal();
    }
  }

  // Screen Viewer Modal Logic
  function openScreenViewer(agentId, hostname) {
    closeScreenViewer();

    state.screenViewerId = agentId;
    elements.screenModalTitle.textContent = `Screen Feed: ${hostname}`;
    elements.screenModalStatus.textContent = 'Connecting...';
    elements.screenModalStatus.className = 'screen-live-badge';
    elements.screenImage.style.display = 'none';
    elements.screenLoading.style.display = 'flex';
    elements.screenLoadingText.textContent = 'Connecting to workstation screen stream...';
    elements.screenModal.classList.add('active');

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/agents/${encodeURIComponent(agentId)}/screen`;

    try {
      state.screenWebSocket = new WebSocket(wsUrl);

      state.screenWebSocket.onopen = () => {
        elements.screenModalStatus.textContent = 'Connected (Waiting for frames)';
        elements.screenLoadingText.textContent = 'Waiting for live screen frames...';
        state.screenWebSocket.send(JSON.stringify({ role: 'viewer' }));
      };

      state.screenWebSocket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'frame' && msg.data) {
            // Validate base64 format (only alphanumeric, +, /, =)
            if (!/^[A-Za-z0-9+/]*={0,2}$/.test(msg.data)) {
              console.error('Invalid base64 data in frame');
              return;
            }
            // Validate JPEG magic bytes when decoded
            if (!msg.data.startsWith('/9j/')) {
              console.warn('Frame data does not appear to be JPEG format');
            }
            elements.screenImage.src = `data:image/jpeg;base64,${msg.data}`;
            elements.screenImage.onerror = () => {
              console.error('Failed to render JPEG frame');
            };
            elements.screenImage.style.display = 'block';
            elements.screenLoading.style.display = 'none';
            elements.screenModalStatus.textContent = '● LIVE STREAM';
            elements.screenModalStatus.className = 'screen-live-badge live';
          }
        } catch (e) {
          console.error('Screen stream frame parsing error:', e);
        }
      };

      state.screenWebSocket.onerror = () => {
        elements.screenModalStatus.textContent = 'Connection Error';
        elements.screenLoadingText.textContent = 'Unable to establish screen feed. Workstation may be offline.';
      };

      state.screenWebSocket.onclose = () => {
        if (state.screenViewerId === agentId) {
          elements.screenModalStatus.textContent = 'Disconnected';
          elements.screenModalStatus.className = 'screen-live-badge';
          elements.screenLoadingText.textContent = 'Screen stream ended.';
        }
      };
    } catch (err) {
      elements.screenModalStatus.textContent = 'Failed to connect';
      elements.screenLoadingText.textContent = 'WebSocket connection initialization error.';
    }
  }

  function closeScreenViewer() {
    state.screenViewerId = null;
    if (state.screenWebSocket) {
      try {
        state.screenWebSocket.close();
      } catch (_) {}
      state.screenWebSocket = null;
    }
    elements.screenModal.classList.remove('active');
    elements.screenImage.src = '';
  }

  // Network Discovery
  function renderDiscovery() {
    elements.discoveryCount.textContent = state.discovery.length;
    elements.discoveryMeta.textContent = `${state.discovery.length} active device${state.discovery.length === 1 ? '' : 's'} identified on local subnet`;

    if (state.discovery.length === 0) {
      elements.discoveryList.innerHTML = `
        <tr>
          <td colspan="4" class="empty-state-box">
            <div class="empty-state-icon">📡</div>
            <div class="empty-state-text">No active scan results.</div>
            <div class="empty-state-sub">Click "Scan Network" above to probe the local subnet for active IP addresses.</div>
          </td>
        </tr>`;
      return;
    }

    elements.discoveryList.innerHTML = state.discovery.map((dev) => `
      <tr>
        <td><span class="status-dot connected" title="Active LAN device"></span></td>
        <td style="font-family: var(--font-mono); font-weight: 600;">${escapeHtml(dev.ip_address)}</td>
        <td>${escapeHtml(dev.hostname || 'Hostname unavailable')}</td>
        <td style="text-align: right;">
          <span class="badge-tag info">Discovered Endpoint</span>
        </td>
      </tr>`).join('');
  }

  async function loadDiscovery() {
    try {
      const response = await fetch(apiUrl('/api/discovery'), { cache: 'no-store' });
      if (response.status === 401) {
        window.location.assign('/login?reason=expired');
        return;
      }
      if (response.ok) {
        state.discovery = await response.json();
        renderDiscovery();
        renderSummary();
      }
    } catch (_) {}
  }

  async function scanNetwork() {
    elements.scanBtn.disabled = true;
    elements.scanIcon.className = 'spinner spinner-dark';
    elements.scanBtnLabel.textContent = 'Scanning subnet...';

    try {
      const response = await fetch(apiUrl('/api/discovery/scan'), { method: 'POST' });
      if (response.status === 401) {
        window.location.assign('/login?reason=expired');
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.discovery = await response.json();
      renderDiscovery();
      renderSummary();
      showToast(`Network scan complete: ${state.discovery.length} device(s) found.`, 'success');
      if (state.role === 'ADMIN') loadAudit();
    } catch (err) {
      showToast('Network discovery scan failed.', 'danger');
    } finally {
      elements.scanBtn.disabled = false;
      elements.scanIcon.className = '';
      elements.scanIcon.textContent = '⌁';
      elements.scanBtnLabel.textContent = 'Scan Network';
    }
  }

  // Activity & Audit Log (ADMIN Only)
  async function loadAudit() {
    if (state.role !== 'ADMIN') return;
    try {
      const response = await fetch(apiUrl('/api/audit'), { cache: 'no-store' });
      if (response.status === 401) {
        window.location.assign('/login?reason=expired');
        return;
      }
      if (response.status === 403) {
        elements.activitySection.classList.add('hidden');
        return;
      }
      if (response.ok) {
        const events = await response.json();
        state.auditLogs = events;
        renderAudit();
      }
    } catch (_) {}
  }

  function renderAudit() {
    if (!state.auditLogs || state.auditLogs.length === 0) {
      elements.auditTableBody.innerHTML = `
        <tr>
          <td colspan="5" class="empty-state-box">
            <div class="empty-state-icon">📜</div>
            <div class="empty-state-text">No security or management activity recorded yet</div>
          </td>
        </tr>`;
      return;
    }

    elements.auditTableBody.innerHTML = state.auditLogs.map((ev) => {
      let resultBadge = `<span class="badge-tag info">${escapeHtml(ev.result || 'info')}</span>`;
      const resLower = (ev.result || '').toLowerCase();
      if (resLower.includes('success') || resLower.includes('executed') || resLower === 'ok') {
        resultBadge = `<span class="badge-tag success">${escapeHtml(ev.result)}</span>`;
      } else if (resLower.includes('denied') || resLower.includes('failed') || resLower.includes('failure')) {
        resultBadge = `<span class="badge-tag danger">${escapeHtml(ev.result)}</span>`;
      } else if (resLower.includes('queued') || resLower.includes('dry_run')) {
        resultBadge = `<span class="badge-tag warning">${escapeHtml(ev.result)}</span>`;
      }

      return `
        <tr>
          <td style="font-size: 12px; color: var(--text-muted);">${escapeHtml(formatDate(ev.timestamp))}</td>
          <td><strong>${escapeHtml(ev.username || 'System')}</strong></td>
          <td><span style="font-family: var(--font-mono); font-size: 12px;">${escapeHtml(ev.action)}</span></td>
          <td><span style="font-family: var(--font-mono); font-size: 11.5px; color: var(--text-muted);">${escapeHtml(ev.target_agent || '—')}</span></td>
          <td style="text-align: right;">${resultBadge}</td>
        </tr>`;
    }).join('');
  }

  // Load Managed Agents
  async function loadAgents() {
    elements.refreshIcon.classList.add('spinner', 'spinner-dark');
    try {
      const response = await fetch(apiUrl('/api/agents'), { cache: 'no-store' });
      if (response.status === 401) {
        window.location.assign('/login?reason=expired');
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      state.agents = await response.json();
      if (state.selectedId && !state.agents.some((a) => a.agent_id === state.selectedId)) {
        state.selectedId = null;
      }

      renderSummary();
      renderTable();
      setConnection(true);
      elements.updatedLabel.textContent = `Last updated: ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
    } catch (err) {
      setConnection(false);
      elements.tableMeta.textContent = 'Server unavailable — retrying...';
    } finally {
      elements.refreshIcon.classList.remove('spinner', 'spinner-dark');
      elements.refreshIcon.textContent = '↻';
    }
  }

  // Event Listeners Setup
  function setupEvents() {
    // Search input
    elements.searchInput.addEventListener('input', renderTable);

    // Status filter tabs
    elements.filterTabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        elements.filterTabs.forEach((t) => {
          t.classList.remove('active');
          t.setAttribute('aria-selected', 'false');
        });
        tab.classList.add('active');
        tab.setAttribute('aria-selected', 'true');
        state.statusFilter = tab.dataset.filter;
        renderTable();
      });
    });

    // Refresh buttons
    elements.refreshBtn.addEventListener('click', loadAgents);
    if (elements.auditRefreshBtn) {
      elements.auditRefreshBtn.addEventListener('click', loadAudit);
    }

    // Discovery Scan
    elements.scanBtn.addEventListener('click', scanNetwork);

    // Screen Modal Close
    elements.screenModalClose.addEventListener('click', closeScreenViewer);
    elements.screenModal.addEventListener('click', (e) => {
      if (e.target === elements.screenModal) closeScreenViewer();
    });

    // Power Confirmation Modal
    elements.powerModalCancel.addEventListener('click', closePowerModal);
    elements.powerModalConfirm.addEventListener('click', executePowerAction);
    elements.powerModal.addEventListener('click', (e) => {
      if (e.target === elements.powerModal && !elements.powerModalConfirm.disabled) {
        closePowerModal();
      }
    });

    // Global Keyboard Shortcuts (Escape to close modals)
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        if (elements.screenModal.classList.contains('active')) closeScreenViewer();
        if (elements.powerModal.classList.contains('active') && !elements.powerModalConfirm.disabled) closePowerModal();
      }
    });

    // Sidebar navigation active switching & scroll
    const navLinks = [elements.navDashboard, elements.navComputers, elements.navDiscovery, elements.navActivity];
    navLinks.forEach((link) => {
      if (!link) return;
      link.addEventListener('click', (e) => {
        e.preventDefault();
        navLinks.forEach((l) => l && l.classList.remove('active'));
        link.classList.add('active');

        const targetId = link.getAttribute('href').replace('#', '');
        let targetEl = null;
        if (targetId === 'dashboard') targetEl = document.querySelector('#metrics-summary');
        if (targetId === 'computers') targetEl = document.querySelector('#computers-section');
        if (targetId === 'discovery') targetEl = document.querySelector('#discovery-section');
        if (targetId === 'activity') targetEl = document.querySelector('#activity-section');

        if (targetEl) {
          targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      });
    });

    // Logout
    elements.logoutBtn.addEventListener('click', async () => {
      try {
        await fetch(apiUrl('/api/auth/logout'), {
          method: 'POST',
          credentials: 'same-origin',
        });
      } catch (_) {}
      window.location.assign('/login');
    });
  }

  // Initialization
  async function init() {
    setupEvents();
    await loadSession();
    await loadAgents();
    await loadDiscovery();

    // Auto-refresh loops
    setInterval(loadAgents, 5000);
    setInterval(() => {
      if (state.role === 'ADMIN') loadAudit();
    }, 30000);
  }

  init();
})();
