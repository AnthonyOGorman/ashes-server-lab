'use strict';

const $ = (selector) => document.querySelector(selector);
const state = { packets: [], runs: [], selected: null, kind: null, tab: 'hex', live: true, fetching: false, online: false, lastState: null, screenshotUrl: null, region: null, presets: [], templates: [] };
const milestoneDefinitions = [
  ['authentication', 'Authentication'], ['lobby', 'Lobby'], ['udp_handshake', 'UDP handshake'],
  ['welcome', 'Welcome'], ['world_loaded', 'World loaded'], ['player_spawned', 'Player spawned'], ['movement', 'Movement'],
];

function escapeHTML(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
}
function showError(message) { $('#error-message').textContent = message; $('#error-banner').hidden = false; }
let noticeTimer;
function notify(message, tone = '') {
  $('#notice').className = tone === 'experiment' ? 'notice experimental-notice' : 'notice';
  $('#notice').textContent = message; $('#notice').hidden = false;
  clearTimeout(noticeTimer); noticeTimer = setTimeout(() => { $('#notice').hidden = true; }, 6500);
}
async function request(path, options = {}) {
  const response = await fetch(path, { cache: 'no-store', ...options, headers: { 'Content-Type': 'application/json', ...options.headers }, signal: options.signal ?? AbortSignal.timeout(15000) });
  const contentType = response.headers.get('content-type') || '';
  let result;
  if (contentType.includes('json')) result = await response.json();
  else { const message = await response.text(); result = { message: contentType.includes('html') ? `HTTP ${response.status}: ${response.statusText || 'The API endpoint is unavailable'}` : message.slice(0, 500) }; }
  if (!response.ok || result?.ok === false) throw new Error(result?.error || result?.message || `Request failed (${response.status})`);
  return result;
}
function list(value) { return Array.isArray(value) ? value : (value && typeof value === 'object' ? Object.entries(value).map(([id, item]) => typeof item === 'object' && item !== null ? { id, ...item } : { id, status: item }) : []); }
function formatTime(value, full = false) {
  if (value == null || value === '') return '—';
  const date = new Date(typeof value === 'number' ? (value < 1e12 ? value * 1000 : value) : value);
  if (Number.isNaN(date.getTime())) return String(value);
  return full ? date.toLocaleString([], { timeZone: 'Asia/Tokyo' }) : date.toLocaleTimeString([], { timeZone: 'Asia/Tokyo', hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
function textStatus(value) { const text = String(value || 'unknown').replace(/_/g, ' '); return text.charAt(0).toUpperCase() + text.slice(1); }
function renderTestStep(step) {
  const input = ['click', 'key'].includes(step.action);
  const sent = input && ['passed', 'sent'].includes(step.status);
  const status = sent ? 'sent' : step.status || 'pending';
  const label = sent ? 'Sent' : textStatus(status);
  const detail = sent ? 'Input delivery recorded; verify the result with an image or protocol gate.' : step.action === 'wait_image' && status === 'passed' ? 'Visual checkpoint matched.' : step.action === 'wait_milestone' && status === 'passed' ? 'Protocol milestone observed.' : step.reason || step.error || '';
  const position = step.position_observation;
  const positionDetail = position ? position.status === 'compared' && Array.isArray(position.delta_cm) ? `Position change: ${position.delta_cm.map((value) => Number(value).toFixed(2)).join(', ')} cm · walking unverified` : `Position check: ${position.error || 'incomplete evidence'}` : '';
  return `<div class="test-step" title="${escapeHTML(detail)}"><span>${escapeHTML(step.name || step.action || 'Step')}</span><span class="${escapeHTML(status)}">${escapeHTML(label)}</span></div>${positionDetail ? `<div class="muted">${escapeHTML(positionDetail)}</div>` : ''}`;
}
function connected(online) {
  state.online = online;
  $('#connection-dot').className = `status-dot ${online ? 'connected' : 'disconnected'}`;
  $('#connection-label').textContent = online ? 'Local server connected' : 'Local server unreachable';
}
function renderState(data) {
  state.lastState = data;
  const initializationErrors = Array.isArray(data.initialization_failures) ? data.initialization_failures : [];
  const failureNotice = $('#initialization-failure');
  failureNotice.hidden = initializationErrors.length === 0;
  failureNotice.textContent = initializationErrors.length ? `Client initialization errors: ${initializationErrors.map(item => item.message).join(' · ')}` : '';
  const services = list(data.services);
  const online = services.filter((item) => item.running === true || item.alive === true || ['running', 'online', 'listening', 'started'].includes(String(item.status).toLowerCase()));
  $('#service-count').innerHTML = data.services ? `${online.length}<span>/ ${services.length} online</span>` : '—<span>online</span>';
  $('#service-chips').innerHTML = services.length ? services.map((item) => `<span class="service-chip ${online.includes(item) ? 'online' : ''}" title="${escapeHTML(item.detail || item.message || item.status || '')}">${escapeHTML(item.name || item.id || 'service')}${item.port ? ` :${escapeHTML(item.port)}` : ''}</span>`).join('') : '<span class="muted">No service state available</span>';
  const client = typeof data.client === 'object' && data.client ? data.client : { status: data.client };
  $('#client-status').textContent = textStatus(client.status || (client.running === true ? 'Running' : client.running === false ? 'Stopped' : 'Unknown'));
  $('#client-detail').textContent = client.detail || client.message || (client.pid ? `Process ${client.pid}${client.path ? ' · ' + client.path : ''}` : 'No game process confirmed');
  $('#process-state').textContent = String(client.status || (client.running ? 'RUNNING' : 'UNKNOWN')).toUpperCase();
  $('#packet-count').textContent = Number.isFinite(Number(data.packet_count)) ? Number(data.packet_count).toLocaleString() : '—';
  const catalog = list(data.catalog);
  const kinds = new Set(catalog.map((item) => item.kind || item.id));
  $('#packet-foot').textContent = data.importing ? 'Importing capture · packet evidence is accumulating' : catalog.length ? `${kinds.size} packet kinds in the evidence catalog` : 'Local session evidence';
  $('#import-capture').disabled = Boolean(data.importing);
  $('#import-capture').textContent = data.importing ? 'Importing…' : 'Import';
  renderCatalog(catalog);
  const active = data.active_run;
  $('#test-status').textContent = active ? textStatus(active.status || 'running') : 'No active test';
  $('#test-detail').textContent = active ? `${textStatus(active.scenario || active.name || 'test')} · ${active.id || active.run_id || ''}` : 'Ready when the client is configured';
  const activeDetail = $('#active-test-detail');
  activeDetail.hidden = !active || (!active.reason && !active.message && !active.error && !active.steps?.length);
  activeDetail.innerHTML = active ? `<span>${escapeHTML(active.reason || active.message || active.error || '')}</span>${Array.isArray(active.steps) ? active.steps.map(renderTestStep).join('') : ''}` : '';
  const testActive = Boolean(active && ['running', 'queued', 'starting'].includes(active.status || 'running'));
  $('#run-test').disabled = testActive;
  $('#reload-tester').disabled = testActive;
  $('#reload-tester').title = testActive ? 'Wait for the active test to finish before reloading the tester.' : 'Reload edited local tester code for subsequent runs.';
  const milestones = list(data.milestones);
  $('#milestones').innerHTML = milestoneDefinitions.map(([id, name], index) => {
    const item = milestones.find((entry) => entry.id === id || entry.name === id) || {};
    const status = item.status === 'passed' || item.status === 'verified' ? 'passed' : item.status === 'blocked' || item.status === 'failed' ? 'blocked' : 'idle';
    return `<div class="milestone status-${status}" title="${escapeHTML(item.detail || '')}"><div class="milestone-mark">${status === 'passed' ? '✓' : status === 'blocked' ? '!' : String(index + 1).padStart(2, '0')}</div><div class="milestone-name">${escapeHTML(item.label || name)}</div><div class="milestone-status">${status === 'passed' ? 'Verified' : status === 'blocked' ? 'Blocked' : 'Not observed'}</div><div class="milestone-detail">${escapeHTML(item.detail || '')}</div></div>`;
  }).join('');
  if (Array.isArray(data.runs)) renderRuns(data.runs);
}
function renderCatalog(catalog) {
  const groups = new Map();
  for (const item of catalog) {
    const kind = item.kind || item.id || 'unknown'; const key = `${item.channel || ''}:${kind}`;
    const group = groups.get(key) || { kind, channel: item.channel || '', count: 0, observed: 0, hypothesis: 0, verified: 0 };
    group.count += Number(item.count ?? item.total ?? 0);
    if (typeof item.confidence === 'string' && ['observed', 'hypothesis', 'verified'].includes(item.confidence)) group[item.confidence] += Number(item.count ?? item.total ?? 0);
    else for (const confidence of ['observed', 'hypothesis', 'verified']) group[confidence] += Number(item[confidence] ?? item.confidence?.[confidence] ?? 0);
    groups.set(key, group);
  }
  $('#catalog-list').innerHTML = groups.size ? [...groups.values()].map((item) => `<button class="catalog-item" data-kind="${escapeHTML(item.kind)}" data-channel="${escapeHTML(item.channel)}" title="${escapeHTML(item.kind)}"><span class="catalog-kind">${escapeHTML(item.kind)}</span><span class="catalog-count mono">${escapeHTML(item.count)} <small>packets · ${escapeHTML(item.channel)}</small></span><span class="catalog-confidence"><span>OBS ${item.observed}</span><span>HYP ${item.hypothesis}</span><span>VER ${item.verified}</span></span></button>`).join('') : '<div class="empty-state"><strong>No packet kinds recorded</strong><p>Evidence accumulates as captures and tests run.</p></div>';
}
function renderRuns(runs) {
  state.runs = runs;
  $('#run-count').textContent = runs.length;
  const current = $('#run-filter').value;
  $('#run-filter').innerHTML = '<option value="">All runs</option>' + runs.map((run) => `<option value="${escapeHTML(run.id || run.run_id)}">${escapeHTML(run.scenario || run.name || 'Test')} · ${escapeHTML(run.id || run.run_id)}</option>`).join('');
  $('#run-filter').value = current;
  $('#run-list').innerHTML = runs.length ? [...runs].sort((a, b) => (b.started ?? b.started_at ?? b.ts ?? 0) > (a.started ?? a.started_at ?? a.ts ?? 0) ? 1 : -1).map((run) => {
    const id = run.id || run.run_id;
    const status = String(run.status || 'unknown');
    let detail = run.reason || run.message || run.error || run.detail || '';
    try { const parsed = JSON.parse(detail); detail = parsed.reason || parsed.message || parsed.error || ''; } catch {}
    return `<button class="run-item" data-run="${escapeHTML(id)}" title="${escapeHTML(detail)}"><span class="run-icon">${status === 'passed' || status === 'completed' ? '✓' : status === 'running' ? '▶' : '⌁'}</span><span class="run-info"><span class="run-name">${escapeHTML(textStatus(run.scenario || run.name || 'Test run'))}</span><span class="run-date">${escapeHTML(formatTime(run.started_at || run.started || run.ts || run.created_at, true))} · ${escapeHTML(id)}</span>${detail ? `<span class="run-reason">${escapeHTML(detail)}</span>` : ''}</span><span class="run-status ${escapeHTML(status.replace(/[^a-z_]/gi, ''))}">${escapeHTML(textStatus(status))}</span></button>`;
  }).join('') : '<div class="empty-state"><strong>No test runs yet</strong><p>Every run gets its own evidence trail.</p></div>';
}
function direction(packet) {
  const value = String(packet.direction || '').toLowerCase();
  if (['in', 'inbound', 'recv', 'received', 'rx', 'c2s', 'client_to_server', 'client→server', 'client->server'].includes(value)) return 'inbound';
  if (['out', 'outbound', 'send', 'sent', 'tx', 's2c', 'server_to_client', 'server→client', 'server->client'].includes(value)) return 'outbound';
  return value;
}
function annotation(packet) { return typeof packet.annotation === 'object' && packet.annotation ? packet.annotation : { note: packet.annotation || '', label: packet.label || '', confidence: packet.confidence || 'observed' }; }
function renderPackets() {
  const query = $('#packet-search').value.trim().toLowerCase();
  const dir = $('#direction-filter').value;
  const channel = $('#channel-filter').value;
  const packets = state.packets.filter((packet) => (!dir || direction(packet) === dir) && (!channel || String(packet.channel) === channel) && (!query || [packet.id, packet.kind, packet.hex, packet.channel, JSON.stringify(packet.decoded), JSON.stringify(packet.annotation)].join(' ').toLowerCase().includes(query)));
  $('#visible-count').textContent = packets.length;
  $('#packet-empty').hidden = packets.length > 0;
  $('#packet-rows').innerHTML = packets.map((packet) => {
    const flow = direction(packet);
    const note = annotation(packet);
    return `<tr data-packet="${escapeHTML(packet.id)}" tabindex="0" aria-label="Inspect packet ${escapeHTML(packet.id)}" class="${String(state.selected?.id) === String(packet.id) ? 'selected' : ''}"><td><span class="packet-id">#${escapeHTML(packet.id)}</span><span class="packet-time">${escapeHTML(formatTime(packet.ts))}</span></td><td><span class="flow ${flow === 'outbound' ? 'out' : ''}" title="${flow === 'inbound' ? 'Client → Server' : flow === 'outbound' ? 'Server → Client' : escapeHTML(packet.direction)}">${flow === 'inbound' ? 'C → S' : flow === 'outbound' ? 'S → C' : escapeHTML(packet.direction || '—')}</span></td><td><span class="channel-label">${escapeHTML(packet.channel || 'unknown')}</span></td><td class="packet-kind" title="${escapeHTML(note.label || packet.kind || '')}">${escapeHTML(note.label || packet.kind || 'unclassified')}</td><td class="align-right mono muted">${escapeHTML(packet.size ?? '—')}</td></tr>`;
  }).join('');
  if (!packets.length && state.packets.length) {
    $('#packet-empty').innerHTML = '<div class="empty-symbol">⌕</div><strong>No packets match these filters</strong><p>Change the search, direction, or channel.</p>';
  } else if (!packets.length) $('#packet-empty').innerHTML = '<div class="empty-symbol">⇄</div><strong>No packet evidence yet</strong><p>Start the services and launch a test, or import a capture.</p>';
}
let packetFetchVersion = 0;
async function loadPackets() {
  const requestVersion = ++packetFetchVersion;
  const exactKind = state.kind;
  const query = new URLSearchParams({ limit: '100', after: '0' });
  if ($('#run-filter').value) query.set('run_id', $('#run-filter').value);
  if (exactKind) query.set('kind', exactKind);
  const result = await request(`/api/packets?${query}`);
  if (requestVersion !== packetFetchVersion) return;
  state.packets = Array.isArray(result) ? result : result.packets || [];
  if (exactKind) state.packets = state.packets.filter((packet) => packet.kind === exactKind);
  const selectedChannel = $('#channel-filter').value;
  const channels = [...new Set(state.packets.map((packet) => String(packet.channel || 'unknown')))];
  $('#channel-filter').innerHTML = '<option value="">All channels</option>' + channels.map((channel) => `<option value="${escapeHTML(channel)}">${escapeHTML(channel)}</option>`).join('');
  $('#channel-filter').value = selectedChannel;
  $('#kind-filter').hidden = !state.kind;
  $('#kind-filter').textContent = state.kind ? `${state.kind} ×` : '';
  $('#kind-filter').title = state.kind ? `Exact kind: ${state.kind}. Click to clear.` : '';
  $('#capture-note').textContent = state.kind ? 'Latest 100 of this kind' : 'Most recent 100 packets';
  renderPackets();
  $('#packet-updated').textContent = `Updated ${new Date().toLocaleTimeString([], { hour12: false })}`;
}
function hexDump(value) {
  if (!value) return '(No payload captured)';
  const clean = String(value).replace(/\s+/g, '');
  if (!/^[0-9a-f]*$/i.test(clean) || clean.length % 2) return String(value);
  const bytes = clean.match(/../g) || [];
  const lines = [];
  for (let offset = 0; offset < bytes.length; offset += 16) {
    const row = bytes.slice(offset, offset + 16);
    const hex = row.slice(0, 8).join(' ').padEnd(23, ' ') + '  ' + row.slice(8).join(' ').padEnd(23, ' ');
    const ascii = row.map((byte) => { const code = parseInt(byte, 16); return code >= 32 && code <= 126 ? String.fromCharCode(code) : '·'; }).join('');
    lines.push(`${offset.toString(16).padStart(6, '0')}   ${hex}  ${ascii}`);
  }
  return lines.join('\n');
}
function renderDetail() {
  const packet = state.selected;
  $('#detail-empty').hidden = Boolean(packet); $('#detail-content').hidden = !packet;
  if (!packet) return;
  $('#selected-id').textContent = `#${packet.id}`;
  $('#detail-meta').innerHTML = [packet.kind || 'unclassified', packet.channel || 'unknown', `${packet.size ?? '?'} bytes`, formatTime(packet.ts), `Run ${packet.run_id ?? '—'}`].map((value) => `<span class="meta-tag">${escapeHTML(value)}</span>`).join('');
  $('#payload').textContent = state.tab === 'hex' ? hexDump(packet.hex) : JSON.stringify(packet.decoded ?? { message: 'No decoded fields available for this packet.' }, null, 2);
  const note = annotation(packet);
  $('#annotation-label').value = note.label || '';
  $('#annotation-note').value = note.note || note.text || '';
  $('#annotation-confidence').value = note.confidence || 'observed';
}
let packetSelection = 0;
async function selectPacket(id) {
  const selection = ++packetSelection;
  try {
    const packet = await request(`/api/packet?id=${encodeURIComponent(id)}`);
    if (selection !== packetSelection) return;
    state.selected = packet.packet || packet;
    renderDetail(); renderPackets();
  } catch (error) { showError(`Unable to inspect packet: ${error.message}`); }
}
async function refresh(force = false) {
  if (state.fetching || (!state.live && !force)) return;
  state.fetching = true;
  try {
    const results = await Promise.allSettled([request('/api/state'), request('/api/runs'), loadPackets()]);
    if (results[0].status === 'fulfilled') { connected(true); renderState(results[0].value); }
    else { connected(false); throw results[0].reason; }
    if (results[1].status === 'fulfilled') renderRuns(Array.isArray(results[1].value) ? results[1].value : results[1].value.runs || []);
    for (const result of results.slice(1)) if (result.status === 'rejected') showError(`Evidence refresh failed: ${result.reason.message}`);
  } catch (error) { connected(false); showError(`Local server connection failed: ${error.message}. Start the Python lab server on port 8765.`); }
  finally { state.fetching = false; }
}
async function control(action, button) {
  const payload = { action };
  const experimental = ['controller_bootstrap', 'scene_bootstrap', 'reload_world_protocol', 'reload_tester'].includes(action);
  if (action === 'run_test') { payload.scenario = $('input[name="scenario"]:checked').value; payload.driver = $('#test-driver').value; }
  if (action === 'import_capture') {
    payload.capture = $('#capture-path').value.trim();
    if (!payload.capture) { showError('Enter the absolute path of a capture file.'); return; }
  }
  button.disabled = true;
  try {
    const result = await request('/api/control', { method: 'POST', body: JSON.stringify(payload) });
    let message = result.message || `${textStatus(action)} accepted`;
    if (action === 'run_test' && payload.driver === 'foreground' && !/foreground/i.test(message)) message += ' · Put the game in the foreground within 5 seconds.';
    if (action === 'run_test' && payload.driver === 'background') message += ' · Experimental background driver targets only the launched game window.';
    if (action === 'run_test' && payload.driver === 'attached') message += ' · Experimental game process adapter selected. Keep the game restored and verify screen and packet gates.';
    if (experimental) {
      $('#bootstrap-status').textContent = result.message || 'Research action accepted. Inspect packet evidence for the result.';
      if (action === 'reload_world_protocol') message += ' · Reconnect after channel layout changes.';
      else if (action !== 'reload_tester') message += ' · Player spawn and movement remain separate evidence checks.';
    }
    notify(message, experimental || (action === 'run_test' && payload.driver !== 'foreground') ? 'experiment' : ''); await refresh(true);
  }
  catch (error) { showError(`${textStatus(action)} failed: ${error.message}`); if (experimental) $('#bootstrap-status').textContent = `Experimental request blocked or failed: ${error.message}`; }
  finally { button.disabled = ['run_test', 'reload_tester'].includes(action) ? Boolean(state.lastState?.active_run && ['running', 'queued', 'starting'].includes(state.lastState.active_run.status || 'running')) : action === 'import_capture' ? Boolean(state.lastState?.importing) : false; }
}
async function loadScenario() {
  try { const result = await request('/api/scenario'); $('#scenario-json').value = JSON.stringify(result, null, 2); renderCalibrationOptions(); $('#scenario-status').textContent = 'Loaded from the local runner'; return true; }
  catch (error) { $('#scenario-status').textContent = `Configuration unavailable: ${error.message}`; return false; }
}
async function loadPresets() {
  try {
    const result = await request('/api/presets'); state.presets = Array.isArray(result) ? result : result.presets || [];
    $('#scenario-preset').innerHTML = '<option value="">Choose a starting screen…</option>' + state.presets.map((preset) => `<option value="${escapeHTML(preset.id)}">${escapeHTML(preset.name)}</option>`).join('');
    $('#preset-description').textContent = state.presets.length ? 'Select a preset to see its required starting screen.' : 'No presets are available from the local runner.';
  } catch (error) { $('#scenario-preset').innerHTML = '<option value="">Presets unavailable</option>'; $('#preset-description').textContent = error.message; }
}
async function loadTemplates() {
  try {
    const previous = $('#template-select').value === '' ? null : state.templates[Number($('#template-select').value)];
    const result = await request('/api/templates'); state.templates = Array.isArray(result) ? result : result.templates || [];
    $('#template-select').innerHTML = '<option value="">Choose a saved checkpoint…</option>' + state.templates.map((template, index) => `<option value="${index}">${escapeHTML(template.template || template.name)} · ${escapeHTML(template.width ?? '?')} × ${escapeHTML(template.height ?? '?')}</option>`).join('');
    const selected = previous ? state.templates.findIndex((item) => (item.template || item.name) === (previous.template || previous.name)) : -1;
    $('#template-select').value = selected >= 0 ? String(selected) : ''; $('#append-template').disabled = $('#template-select').value === '';
    $('#template-list-status').textContent = `${state.templates.length} saved checkpoints · visual matches are evaluated separately from packet milestones`;
  } catch (error) { $('#template-list-status').textContent = `Checkpoint list unavailable: ${error.message}`; }
}
function appendCheckpoint(template) {
  const filename = template.template || template.name;
  if (!filename || !Array.isArray(template.bbox) || template.bbox.length !== 4) throw new Error('Checkpoint metadata must include its template filename and bounding box.');
  const scenario = JSON.parse($('#scenario-json').value);
  if (!Array.isArray(scenario.steps)) throw new Error('The scenario must contain a steps array.');
  scenario.steps.push({ name: `Checkpoint: ${filename.replace(/\.png$/i, '')}`, action: 'wait_image', template: filename, bbox: [...template.bbox], timeout: 30, threshold: 8 });
  $('#scenario-json').value = JSON.stringify(scenario, null, 2); renderCalibrationOptions();
  $('#scenario-status').textContent = `Added ${filename} wait_image step · unsaved, select Save scenario to apply`;
}
function selectedRegion() {
  if (!state.region?.second) return null;
  const image = $('#client-screenshot'); const first = state.region.first; const second = state.region.second;
  return [Math.min(first[0], second[0]), Math.min(first[1], second[1]), Math.min(image.naturalWidth, Math.max(first[0], second[0]) + 1), Math.min(image.naturalHeight, Math.max(first[1], second[1]) + 1)];
}
function renderRegion() {
  const bbox = selectedRegion(); const overlay = $('#checkpoint-region'); const image = $('#client-screenshot');
  overlay.hidden = !bbox || image.hidden || $('input[name="image-mode"]:checked').value !== 'checkpoint';
  $('#learn-template').disabled = !bbox || !$('#template-name').value.trim();
  if (!bbox) { $('#checkpoint-bbox').textContent = state.region?.first ? `First corner: ${state.region.first.join(', ')} · choose the opposite corner.` : 'Choose region mode, then click two opposite corners.'; return; }
  const rect = image.getBoundingClientRect(); const box = $('#screenshot-box').getBoundingClientRect();
  overlay.style.left = `${rect.left - box.left + bbox[0] * rect.width / image.naturalWidth}px`;
  overlay.style.top = `${rect.top - box.top + bbox[1] * rect.height / image.naturalHeight}px`;
  overlay.style.width = `${(bbox[2] - bbox[0]) * rect.width / image.naturalWidth}px`;
  overlay.style.height = `${(bbox[3] - bbox[1]) * rect.height / image.naturalHeight}px`;
  $('#checkpoint-bbox').textContent = `[${bbox.join(', ')}] · ${bbox[2] - bbox[0]} × ${bbox[3] - bbox[1]} native pixels`;
}
function renderCalibrationOptions() {
  try {
    const scenario = JSON.parse($('#scenario-json').value);
    const selected = $('#click-step').value;
    $('#click-step').innerHTML = '<option value="">Coordinates only</option>' + (scenario.steps || []).map((step, index) => step.action === 'click' ? `<option value="${index}">${escapeHTML(step.name || `Step ${index + 1}`)} · ${escapeHTML(step.x ?? '?')}, ${escapeHTML(step.y ?? '?')}</option>` : '').join('');
    $('#click-step').value = selected;
    $('#scenario-calibrated').checked = scenario.calibrated === true;
  } catch { $('#scenario-status').textContent = 'Invalid JSON · finish editing before calibrating'; }
}
async function loadScreenshot() {
  const button = $('#refresh-screenshot'); button.disabled = true;
  try {
    const response = await fetch(`/api/screenshot?t=${Date.now()}`, { cache: 'no-store', signal: AbortSignal.timeout(15000) });
    if (!response.ok) { const value = await response.text(); let message = value; try { message = JSON.parse(value).error || JSON.parse(value).message || value; } catch {} throw new Error(message.slice(0, 300) || `HTTP ${response.status}`); }
    if (!(response.headers.get('content-type') || '').startsWith('image/')) throw new Error('The runner did not return a screenshot image.');
    const url = URL.createObjectURL(await response.blob());
    if (state.screenshotUrl) URL.revokeObjectURL(state.screenshotUrl);
    state.screenshotUrl = url; $('#client-screenshot').src = url; $('#client-screenshot').hidden = false; $('#screenshot-placeholder').hidden = true; $('#coordinate-marker').hidden = true;
    state.region = null; renderRegion();
    $('#screenshot-status').textContent = 'Latest screenshot loaded · click a step position to calibrate';
  } catch (error) { showError(`Screenshot unavailable: ${error.message}`); $('#screenshot-status').textContent = 'Screenshot unavailable · see the error above'; }
  finally { button.disabled = false; }
}

document.querySelectorAll('[data-action]').forEach((button) => button.addEventListener('click', () => control(button.dataset.action, button)));
$('#import-capture').addEventListener('click', (event) => control('import_capture', event.currentTarget));
$('#refresh').addEventListener('click', () => refresh(true));
$('#dismiss-error').addEventListener('click', () => { $('#error-banner').hidden = true; });
$('#follow').addEventListener('click', () => { state.live = !state.live; $('#follow').classList.toggle('active', state.live); $('#follow').textContent = state.live ? '● Live' : 'Ⅱ Paused'; $('#follow').setAttribute('aria-pressed', String(state.live)); if (state.live) refresh(true); });
['#packet-search', '#direction-filter', '#channel-filter'].forEach((selector) => $(selector).addEventListener(selector === '#packet-search' ? 'input' : 'change', renderPackets));
$('#run-filter').addEventListener('change', () => loadPackets().catch((error) => showError(error.message)));
$('#packet-rows').addEventListener('click', (event) => { const row = event.target.closest('[data-packet]'); if (row) selectPacket(row.dataset.packet); });
$('#packet-rows').addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { const row = event.target.closest('[data-packet]'); if (row) { event.preventDefault(); selectPacket(row.dataset.packet); } } });
$('#run-list').addEventListener('click', (event) => { const row = event.target.closest('[data-run]'); if (row) { $('#run-filter').value = row.dataset.run; loadPackets().catch((error) => showError(error.message)); $('#packet-workspace').scrollIntoView({ behavior: 'smooth' }); } });
$('#catalog-list').addEventListener('click', (event) => { const item = event.target.closest('[data-kind]'); if (item) { state.kind = item.dataset.kind; $('#packet-search').value = ''; $('#run-filter').value = ''; $('#direction-filter').value = ''; $('#channel-filter').value = ''; loadPackets().catch((error) => showError(error.message)); $('#packet-workspace').scrollIntoView({ behavior: 'smooth' }); } });
$('#kind-filter').addEventListener('click', () => { state.kind = null; loadPackets().catch((error) => showError(error.message)); });
document.querySelectorAll('[data-tab]').forEach((button) => button.addEventListener('click', () => {
  state.tab = button.dataset.tab;
  document.querySelectorAll('[data-tab]').forEach((tab) => { tab.classList.toggle('active', tab === button); tab.setAttribute('aria-selected', String(tab === button)); });
  if (state.selected) $('#payload').textContent = state.tab === 'hex' ? hexDump(state.selected.hex) : JSON.stringify(state.selected.decoded ?? { message: 'No decoded fields available for this packet.' }, null, 2);
}));
$('#copy-payload').addEventListener('click', async () => { try { await navigator.clipboard.writeText($('#payload').textContent); notify('Displayed payload copied'); } catch (error) { showError(`Clipboard unavailable: ${error.message}`); } });
$('#annotation-form').addEventListener('submit', async (event) => {
  event.preventDefault(); if (!state.selected) return;
  const button = event.submitter; button.disabled = true;
  const note = { packet_id: state.selected.id, note: $('#annotation-note').value, confidence: $('#annotation-confidence').value, label: $('#annotation-label').value };
  try { await request('/api/annotate', { method: 'POST', body: JSON.stringify(note) }); state.selected.annotation = note; const packet = state.packets.find((item) => item.id === state.selected.id); if (packet) packet.annotation = note; renderPackets(); notify('Evidence annotation saved'); }
  catch (error) { showError(`Annotation failed: ${error.message}`); }
  finally { button.disabled = false; }
});
$('#load-scenario').addEventListener('click', loadScenario);
$('#scenario-preset').addEventListener('change', () => { const preset = state.presets.find((item) => item.id === $('#scenario-preset').value); $('#load-preset').disabled = !preset; $('#preset-description').textContent = preset ? `Required starting screen: ${preset.start_screen} · loading sets the runner scenario` : 'Select a preset to see its required starting screen.'; });
$('#load-preset').addEventListener('click', async () => {
  const preset = $('#scenario-preset').value; if (!preset) return;
  const button = $('#load-preset'); button.disabled = true;
  try { const result = await request('/api/control', { method: 'POST', body: JSON.stringify({ action: 'load_preset', preset }) }); if (!await loadScenario()) throw new Error('The preset was accepted, but the scenario could not be reloaded. Select Reload to read the runner configuration.'); $('input[name="scenario"][value="walk"]').checked = true; notify((result.message || 'Preset loaded into the local runner') + ' · Full configured scenario selected.'); }
  catch (error) { showError(`Preset load failed: ${error.message}`); }
  finally { button.disabled = false; }
});
$('#reload-templates').addEventListener('click', loadTemplates);
$('#template-select').addEventListener('change', () => { $('#append-template').disabled = $('#template-select').value === ''; });
$('#append-template').addEventListener('click', () => {
  try { const template = state.templates[Number($('#template-select').value)]; if (!template || $('#template-select').value === '') return; appendCheckpoint(template); notify('Visual checkpoint step added to the editor · save the scenario to apply'); }
  catch (error) { showError(`Cannot add checkpoint step: ${error.message}`); }
});
$('#template-name').addEventListener('input', renderRegion);
$('#clear-region').addEventListener('click', () => { state.region = null; $('#coordinate-marker').hidden = true; renderRegion(); });
document.querySelectorAll('input[name="image-mode"]').forEach((radio) => radio.addEventListener('change', () => { $('#coordinate-marker').hidden = true; $('#image-instructions').textContent = radio.value === 'checkpoint' ? 'Click two opposite corners to select a checkpoint.' : 'Click the image to calibrate the selected step.'; renderRegion(); }));
$('#learn-template').addEventListener('click', async () => {
  const bbox = selectedRegion(); const name = $('#template-name').value.trim(); if (!bbox || !name) return;
  const filename = /\.png$/i.test(name) ? name : `${name}.png`;
  const button = $('#learn-template'); button.disabled = true;
  try {
    if ($('#append-checkpoint').checked) { const scenario = JSON.parse($('#scenario-json').value); if (!Array.isArray(scenario.steps)) throw new Error('The scenario must contain a steps array before adding a checkpoint.'); }
    const result = await request('/api/template', { method: 'POST', body: JSON.stringify({ name: filename, bbox }) });
    const template = result.template && typeof result.template === 'object' ? result.template : result;
    $('#template-name').value = filename;
    let message = result.message || `Learned ${template.template || name}`;
    if ($('#append-checkpoint').checked) { appendCheckpoint(template); message += ' · wait_image step added to editor; save scenario to apply'; }
    $('#template-learn-status').textContent = message; notify(message); await loadTemplates();
  } catch (error) { showError(`Checkpoint learning failed: ${error.message}`); $('#template-learn-status').textContent = `Learning failed: ${error.message}`; }
  finally { renderRegion(); }
});
$('#save-scenario').addEventListener('click', async () => {
  let scenario; try { scenario = JSON.parse($('#scenario-json').value); } catch (error) { showError(`Scenario JSON is invalid: ${error.message}`); return; }
  const button = $('#save-scenario'); button.disabled = true;
  try { const result = await request('/api/scenario', { method: 'PUT', body: JSON.stringify(scenario) }); $('#scenario-status').textContent = 'Saved to the local runner'; notify(result.message || 'Scenario saved'); }
  catch (error) { showError(`Scenario save failed: ${error.message}`); }
  finally { button.disabled = false; }
});
$('#scenario-json').addEventListener('input', () => { $('#scenario-status').textContent = 'Unsaved edits'; renderCalibrationOptions(); });
$('#scenario-calibrated').addEventListener('change', () => {
  try { const scenario = JSON.parse($('#scenario-json').value); scenario.calibrated = $('#scenario-calibrated').checked; $('#scenario-json').value = JSON.stringify(scenario, null, 2); $('#scenario-status').textContent = 'Unsaved edits'; }
  catch (error) { showError(`Fix scenario JSON before setting calibration: ${error.message}`); $('#scenario-calibrated').checked = false; }
});
$('#refresh-screenshot').addEventListener('click', loadScreenshot);
const DRIVER_PREFERENCE = 'ashesLab.testerDriver';
const driverDescriptions = {
  foreground: 'Foreground input requires the exact game window to remain focused. Input stops when focus changes.',
  background: 'Experimental messages target the exact game PID/window without taking focus or moving the global mouse. Sent input needs separate visual or protocol confirmation; GPU-rendered screenshots may be unavailable.',
  attached: 'Uses a local game-process adapter with a virtual cursor and targeted input. Keep game restored; verify screen and packet gates. Background button activation is still being tested.',
};
function updateDriverDescription() {
  const driver = $('#test-driver').value;
  $('#driver-description').textContent = driverDescriptions[driver] || driverDescriptions.foreground;
  $('#driver-description').classList.toggle('experimental-driver', driver !== 'foreground');
}
function restoreDriverPreference() {
  try { const saved = localStorage.getItem(DRIVER_PREFERENCE); if (Object.hasOwn(driverDescriptions, saved)) $('#test-driver').value = saved; } catch {}
  updateDriverDescription();
}
$('#test-driver').addEventListener('change', () => { updateDriverDescription(); try { localStorage.setItem(DRIVER_PREFERENCE, $('#test-driver').value); } catch {} });
$('#capture-screenshot').addEventListener('click', async () => {
  const button = $('#capture-screenshot'); button.disabled = true;
  const driver = $('#test-driver').value;
  try {
    const result = await request('/api/control', { method: 'POST', body: JSON.stringify({ action: 'capture_screenshot', driver }) });
    const captureInstruction = driver === 'attached' ? 'Experimental game process adapter capture queued. Keep the game restored; verify screen and packet gates.' : driver === 'background' ? 'Experimental background capture queued for the exact game PID/window. GPU-rendered screenshots may be unavailable.' : 'Capture queued. Put the game in the foreground within 5 seconds.';
    notify(result.message || captureInstruction, driver !== 'foreground' ? 'experiment' : '');
    $('#client-screenshot').hidden = true; $('#coordinate-marker').hidden = true; $('#screenshot-placeholder').hidden = false;
    state.region = null; renderRegion();
    $('#screenshot-status').textContent = captureInstruction;
    let remaining = 5; button.textContent = `Capturing in ${remaining}s`;
    const countdown = setInterval(() => { remaining -= 1; button.textContent = remaining > 0 ? `Capturing in ${remaining}s` : 'Loading capture…'; }, 1000);
    await new Promise((resolve) => setTimeout(resolve, 6500)); clearInterval(countdown);
    await loadScreenshot();
  } catch (error) { showError(`Capture failed: ${error.message}`); $('#screenshot-status').textContent = 'Capture failed · see the error above'; }
  finally { button.disabled = false; button.textContent = 'Capture in 5s'; }
});
$('#client-screenshot').addEventListener('click', (event) => {
  const image = event.currentTarget; const rect = image.getBoundingClientRect(); const box = $('#screenshot-box').getBoundingClientRect();
  const x = Math.min(image.naturalWidth - 1, Math.max(0, Math.round((event.clientX - rect.left) * image.naturalWidth / rect.width)));
  const y = Math.min(image.naturalHeight - 1, Math.max(0, Math.round((event.clientY - rect.top) * image.naturalHeight / rect.height)));
  $('#coordinates').textContent = `x ${x}   y ${y}`;
  const marker = $('#coordinate-marker'); marker.hidden = false; marker.style.left = `${event.clientX - box.left}px`; marker.style.top = `${event.clientY - box.top}px`;
  if ($('input[name="image-mode"]:checked').value === 'checkpoint') {
    if (!state.region || state.region.second) state.region = { first: [x, y] };
    else state.region.second = [x, y];
    renderRegion(); return;
  }
  if ($('#click-step').value !== '') {
    try {
      const scenario = JSON.parse($('#scenario-json').value); const step = scenario.steps?.[Number($('#click-step').value)];
      if (!step || step.action !== 'click') throw new Error('Select a valid click step.');
      step.x = x; step.y = y;
      $('#scenario-json').value = JSON.stringify(scenario, null, 2); renderCalibrationOptions(); $('#scenario-status').textContent = `${step.name || 'Click step'} updated to ${x}, ${y} · save to apply`;
    } catch (error) { showError(`Coordinate update failed: ${error.message}`); }
  }
});
$('#capture-path').value = 'E:\\Ashes Of Creation Wire Shark\\general start up log in relm select walk around mount etc.pcapng';
$('#client-screenshot').addEventListener('load', renderRegion);
window.addEventListener('resize', renderRegion);
restoreDriverPreference();
renderState({}); refresh(true); loadScenario(); loadPresets(); loadTemplates();
setInterval(() => { if (!document.hidden) refresh(); }, 2000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
