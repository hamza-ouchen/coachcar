'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const array = value => Array.isArray(value) ? value : [];
const icon = name => `<svg class="icon" aria-hidden="true"><use href="#i-${esc(name)}"></use></svg>`;
const safeUrl = value => { try { const url = new URL(String(value)); return ['https:', 'http:'].includes(url.protocol) ? url.href : null; } catch { return null; } };
const money = value => value == null ? '—' : `$${Number(value).toFixed(4)}`;
const duration = ms => ms == null ? '—' : `${(Number(ms) / 1000).toFixed(1)} s`;
const number = value => value == null ? '—' : Number(value).toLocaleString('fr-FR');
const names = {evolution:'Évolution', reconversion:'Reconversion', supervisor:'Superviseur', workflow:'Workflow'};
const icons = {evolution:'trend', reconversion:'route', supervisor:'layers'};
const statuses = {running:'En cours', completed:'Terminée', partial:'Partielle', failed:'En erreur', interrupted:'Interrompue', cancelled:'Annulée'};
const state = {run:null, events:[], steps:{}, stream:null, view:'orientation', mode:'live', runs:[], metrics:null,
  elapsed:0, anchor:0, anchorTime:0, replaying:false, replaySource:[], replayIndex:0, lastRefresh:0, finishing:false, ops:null, opsRefresh:0};

$$('[data-icon]').forEach(el => el.innerHTML = icon(el.dataset.icon));

async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = `La requête a échoué (${response.status}).`;
    try {
      const data = await response.json();
      if (typeof data.detail === 'string') message = data.detail;
      else if (Array.isArray(data.detail)) message = 'Vérifiez les champs du profil : une valeur est manquante ou invalide.';
    } catch {}
    throw new Error(message);
  }
  return response.json();
}

let toastTimer;
function toast(message) {
  $('#toast').textContent = message;
  $('#toast').classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('#toast').classList.add('hidden'), 5000);
}

function showFormError(message) {
  $('#form-message').textContent = message;
  $('#form-message').classList.toggle('hidden', !message);
}

function badge(status) {
  return `<span class="badge ${esc(status)}"><span class="status-dot"></span>${esc(statuses[status] || status)}</span>`;
}

function dateLabel(value) {
  return new Date(value).toLocaleString('fr-FR', {timeZone:'Africa/Casablanca', day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit'});
}

function changeView(view) {
  state.view = view;
  $('#orientation-view').classList.toggle('hidden', view !== 'orientation');
  $('#supervision-view').classList.toggle('hidden', view !== 'supervision');
  $('#operations-view').classList.toggle('hidden', view !== 'operations');
  $$('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.view === view));
  $('#breadcrumb-current').textContent = view === 'orientation' ? 'Mon orientation' : view === 'operations' ? 'Exploitation' : 'Supervision';
  history.replaceState(null, '', `#${view}`);
  if (view === 'supervision') refreshSupervision().catch(error => toast(error.message));
  if (view === 'operations') refreshOperations().catch(error => toast(error.message));
}

$$('[data-view]').forEach(button => button.addEventListener('click', () => changeView(button.dataset.view)));
$('.brand').addEventListener('click', event => { event.preventDefault(); changeView('orientation'); });

const example = {situation:'Développeur web junior', skills:'JavaScript, Python, HTML/CSS, bases de SQL', objective:'compare', market:'Maroc', remote:true, hours:8, horizon:6, interests:'Automatisation, intelligence artificielle et analyse de données. Je veux un projet concret pour mon portfolio.'};

function setProfile(profile) {
  Object.entries(profile || {}).forEach(([name, value]) => {
    const field = $(`#${name}`);
    if (!field) return;
    if (field.type === 'checkbox') field.checked = Boolean(value);
    else field.value = value;
  });
}

$('#example-btn').addEventListener('click', () => { setProfile(example); toast('Exemple chargé. Vous pouvez le modifier avant de lancer.'); });
$('#run-mode').addEventListener('change', () => $('#scenario-row').classList.toggle('hidden', $('#run-mode').value !== 'demo'));

function getProfile() {
  return {situation:$('#situation').value.trim(), skills:$('#skills').value.trim(), objective:$('#objective').value,
    market:$('#market').value.trim(), remote:$('#remote').checked, hours:Number($('#hours').value),
    horizon:Number($('#horizon').value), interests:$('#interests').value.trim()};
}

$('#profile-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (state.run?.status === 'running' || state.replaying) return;
  showFormError('');
  const profile = getProfile();
  let valid = true;
  for (const name of ['situation','skills']) {
    const invalid = profile[name].length < (name === 'situation' ? 3 : 2);
    $(`#error-${name}`).textContent = invalid ? 'Ajoutez quelques mots pour décrire votre profil.' : '';
    if (invalid) valid = false;
  }
  if (!valid) return;
  $('#launch-btn').disabled = true;
  try {
    const mode = $('#run-mode').value;
    const result = await api('/api/runs', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({profile, mode, scenario:$('#alert-scenario').checked ? 'alerts' : 'normal'})});
    localStorage.setItem('capavenir-last-run', result.id);
    await openRun(result.id, false);
    if (window.innerWidth < 780) $('.mission-panel').scrollIntoView({behavior:'smooth', block:'start'});
  } catch (error) { showFormError(error.message); $('#launch-btn').disabled = false; }
});

function clearVisuals() {
  state.events = [];
  state.steps = {};
  state.elapsed = 0;
  $$('.edge').forEach(edge => edge.classList.remove('active','done'));
  $$('.packet').forEach(packet => packet.classList.add('hidden'));
}

function setAnchor(elapsed = 0) {
  state.anchor = elapsed;
  state.anchorTime = performance.now();
  state.elapsed = elapsed;
}

function consumeEvent(event, animation = true) {
  if (state.events.some(existing => existing.id === event.id)) return;
  state.events.push(event);
  const agent = event.agent;
  if (event.type === 'agent_started') {
    state.steps[agent] = {agent, status:'running', start:event.elapsed_ms, end:null, usage:null};
  } else if (['agent_completed','agent_failed','agent_cancelled'].includes(event.type)) {
    const step = state.steps[agent] || {agent, start:Math.max(0,event.elapsed_ms - (event.payload.duration_ms || 0))};
    Object.assign(step, {status:event.type === 'agent_completed' ? 'completed':event.type === 'agent_cancelled' ? 'cancelled':'failed', end:event.elapsed_ms,
      duration_ms:event.payload.duration_ms, usage:event.payload.usage, source_count:event.payload.source_count || 0});
    state.steps[agent] = step;
  } else if (event.type === 'agent_skipped') {
    state.steps[agent] = {agent, status:'skipped', start:event.elapsed_ms, end:event.elapsed_ms};
  }
  if (event.type === 'handoff' && animation) {
    const packet = $(`#packet-${agent}`);
    if (packet) { packet.classList.remove('hidden'); setTimeout(() => packet.classList.add('hidden'), 1800); }
  }
  if (!state.replaying) setAnchor(event.elapsed_ms);
}

function renderMission() {
  const run = state.run;
  const running = run?.status === 'running';
  const missionBadge = $('#mission-status');
  missionBadge.className = `badge ${state.replaying ? 'partial' : run?.status || 'neutral'}`;
  missionBadge.innerHTML = `<span class="status-dot"></span>${state.replaying ? 'Replay en cours' : run ? esc(statuses[run.status] || run.status) : 'Prête à explorer'}`;
  $('#scene').classList.toggle('replaying', state.replaying);
  $('#scene-mode-label').textContent = run?.mode === 'demo' ? 'DÉMO · données simulées' : state.replaying ? 'Replay des événements enregistrés' : 'Animation liée aux événements';
  document.body.classList.toggle('busy', running && !state.replaying);
  $('#launch-btn').disabled = running || state.replaying;
  $('#launch-label').textContent = state.replaying ? 'Replay en cours…' : running ? 'Votre équipe explore…' : 'Explorer mes possibilités';
  $('#replay-btn').disabled = !run || running;
  $('#replay-btn').innerHTML = icon(state.replaying ? 'close':'play') + (state.replaying ? 'Arrêter':'Rejouer');
  let tokens = 0, costs = [], sourceCount = 0;
  for (const agent of Object.keys(names).filter(a => a !== 'workflow')) {
    const node = $(`.agent-node[data-agent="${agent}"]`);
    const step = state.steps[agent];
    node.classList.remove('running','completed','failed','cancelled');
    if (step?.status) node.classList.add(step.status);
    let elapsed = step ? (step.end != null ? step.duration_ms : Math.max(0,state.elapsed - step.start)) : null;
    $('.node-duration', node).textContent = duration(elapsed);
    $('.node-cost', node).textContent = money(step?.usage?.cost);
    $('.agent-state', node).textContent = !step ? (agent === 'supervisor' ? 'Attend les deux dossiers':'En attente') :
      step.status === 'running' ? (agent === 'supervisor' ? 'Compare les trajectoires…':'Recherche et analyse…') :
      step.status === 'completed' ? (agent === 'supervisor' ? 'Recommandation prête':'Dossier transmis') :
      step.status === 'skipped' ? 'Synthèse annulée':step.status === 'cancelled' ? 'Interrompu localement':'Erreur · voir le détail';
    if (step?.usage) {
      tokens += (step.usage.prompt_tokens || 0) + (step.usage.completion_tokens || 0);
      if (step.usage.cost != null) costs.push(step.usage.cost);
    }
    sourceCount += step?.source_count || 0;
    if (agent !== 'supervisor') {
      $(`#edge-profile-${agent}`).classList.toggle('active', step?.status === 'running');
      $(`#edge-profile-${agent}`).classList.toggle('done', step?.status === 'completed');
      $(`#edge-${agent}-supervisor`).classList.toggle('done', step?.status === 'completed');
      $(`#edge-${agent}-supervisor`).classList.toggle('active', state.steps.supervisor?.status === 'running' && step?.status === 'completed');
    }
  }
  $('#edge-supervisor-result').classList.toggle('done', state.steps.supervisor?.status === 'completed');
  $('#mission-duration').innerHTML = run ? `${(state.elapsed / 1000).toFixed(1)}<small> s</small>` : '—';
  $('#mission-tokens').textContent = Object.values(state.steps).some(s => s.usage) ? number(tokens) : '—';
  $('#mission-cost').textContent = costs.length ? money(costs.reduce((a,b) => a+b,0)) : '—';
  $('#mission-cost').title = run?.mode === 'demo' ? 'Coût simulé : aucun appel API.' : 'Somme des coûts connus ; les appels en cours ou sans coût retourné ne sont pas inclus.';
  $('#mission-sources').textContent = Object.values(state.steps).some(s => s.status === 'completed') ? sourceCount : '—';
  renderTimeline();
}

function renderTimeline() {
  const steps = Object.values(state.steps);
  if (!steps.length) { $('#timeline').innerHTML = '<p class="subtle">La chronologie apparaîtra au lancement.</p>'; return; }
  const total = Math.max(1000, state.elapsed);
  $('#timeline').innerHTML = ['evolution','reconversion','supervisor'].map(agent => {
    const step = state.steps[agent];
    if (!step || step.status === 'skipped') return '';
    const end = step.end ?? state.elapsed;
    return `<div class="timeline-row"><span class="timeline-name">${names[agent]}</span><div class="timeline-track"><span class="timeline-bar ${agent} ${step.status}" style="left:${Math.min(100, step.start / total * 100)}%;width:${Math.max(.3, (end - step.start) / total * 100)}%"></span></div><span class="timeline-duration">${duration(end-step.start)}</span></div>`;
  }).join('');
}

function eventRows(events) {
  return events.map(event => `<div class="log-row ${event.type === 'alert' ? 'alert' : event.type.includes('failed') ? 'failed':''}"><span class="log-time">+${(event.elapsed_ms / 1000).toFixed(1)}s</span><span class="log-agent">${esc(names[event.agent] || 'Mission')}</span><span>${esc(event.payload.message || event.type)}</span></div>`).join('');
}

function renderLog() {
  if (!state.events.length) {
    $('#event-log').innerHTML = `<div class="empty-log">${icon('spark')}<span>Votre équipe est prête. Parlez-nous de vous pour démarrer.</span></div>`;
  } else {
    $('#event-log').innerHTML = eventRows(state.events.slice(-40));
    $('#event-log').scrollTop = $('#event-log').scrollHeight;
  }
}

async function openRun(id, restoreProfile = true) {
  state.stream?.close();
  state.replaying = false;
  const run = await api(`/api/runs/${encodeURIComponent(id)}`);
  state.run = run;
  clearVisuals();
  if (restoreProfile) {
    setProfile(run.profile);
    $('#run-mode').value = run.mode;
    $('#scenario-row').classList.toggle('hidden', run.mode !== 'demo');
  }
  run.events.forEach(event => consumeEvent(event, false));
  if (run.status === 'running') {
    const elapsed = Math.max(0, Date.now() - new Date(run.created_at).getTime());
    setAnchor(Math.max(elapsed, ...run.events.map(event => event.elapsed_ms), 0));
    listen(id);
  } else setAnchor(run.duration_ms || run.events.at(-1)?.elapsed_ms || 0);
  localStorage.setItem('capavenir-last-run', run.id);
  renderMission(); renderLog(); renderResults();
}

function listen(id) {
  const after = state.events.at(-1)?.id || 0;
  const stream = new EventSource(`/api/runs/${encodeURIComponent(id)}/events?after=${after}`);
  state.stream = stream;
  stream.onmessage = message => {
    if (state.run?.id !== id) return;
    try {
      const event = JSON.parse(message.data);
      consumeEvent(event);
      renderMission(); renderLog();
      if (['run_completed','run_failed','run_cancelled'].includes(event.type)) finishMission(id);
    } catch { toast('Un événement est illisible ; la reconnexion conserve les résultats.'); }
  };
  stream.addEventListener('closed', () => { stream.close(); if (state.run?.id === id && state.run.status === 'running') finishMission(id); });
  stream.onerror = () => {
    if (state.run?.id === id && state.run.status === 'running') {
      $('#mission-status').innerHTML = '<span class="status-dot"></span>Reconnexion…';
    }
  };
}

async function finishMission(id) {
  if (state.finishing) return;
  state.finishing = true;
  try {
    state.stream?.close();
    await openRun(id, false);
    toast(state.run.status === 'cancelled' ? 'La mission a été interrompue localement.' : state.run.status === 'failed' ? 'La mission a rencontré une erreur. Consultez les détails.' : 'Votre recommandation est prête.');
    if (state.view === 'supervision') await refreshSupervision();
  } catch (error) { toast(error.message); }
  finally { state.finishing = false; }
}

function stopReplay() {
  state.replaying = false;
  clearVisuals();
  array(state.run?.events).forEach(event => consumeEvent(event, false));
  setAnchor(state.run?.duration_ms || 0);
  renderMission(); renderLog(); renderResults();
}

$('#replay-btn').addEventListener('click', () => {
  if (state.replaying) { stopReplay(); return; }
  if (!state.run || state.run.status === 'running') return;
  state.replaySource = [...state.run.events];
  clearVisuals();
  state.replayIndex = 0;
  state.replaying = true;
  state.anchorTime = performance.now();
  state.anchor = 0;
  renderMission(); renderLog();
  toast('Replay local : aucun nouvel appel API.');
});

function list(items, className = '') {
  const values = array(items);
  return values.length ? `<ul class="${className}">${values.map(item => `<li>${esc(item)}</li>`).join('')}</ul>` : '';
}

function sourcesHtml(dossier) {
  const sources = array(dossier?.sources).filter(source => source && safeUrl(source.url));
  return `<div class="source-list">${sources.map(source => `<a href="${esc(safeUrl(source.url))}" target="_blank" rel="noopener noreferrer">${icon('link')}${esc(source.title || source.url)}</a>`).join('')}</div>${dossier?.source_note ? `<p class="source-note">${esc(dossier.source_note)}</p>`:''}`;
}

function dossierCard(step) {
  const dossier = step?.dossier;
  const agent = step?.agent;
  if (!step) return '';
  if (!dossier) return `<article class="panel dossier-card ${agent}"><div class="eyebrow">${esc(names[agent])}</div><h3>Dossier indisponible</h3><p>${esc(step.error || 'Cette recherche n’a pas abouti.')}</p></article>`;
  return `<article class="panel dossier-card ${agent}"><div class="eyebrow">${icon(icons[agent])} ${esc(names[agent])}</div><h3>${esc(dossier.title || names[agent])}</h3><p>${esc(dossier.summary)}</p><div class="skill-chips">${array(dossier.skills).map(skill => `<span class="skill-chip">${esc(skill.name || skill)}</span>`).join('')}</div>${sourcesHtml(dossier)}<button class="text-button" data-open-agent="${agent}">Consulter le dossier ${icon('arrow')}</button></article>`;
}

function renderResults() {
  const run = state.run;
  if (!run || run.status === 'running') {
    $('#results-section').innerHTML = `<div class="result-placeholder"><span class="placeholder-icon">${icon('compass')}</span><div><h3>${run ? 'Votre équipe explore les possibilités…':'Une direction, pas une décision à votre place.'}</h3><p>${run ? 'Les deux dossiers seront comparés pour construire votre recommandation.':'Votre recommandation, vos pistes et votre plan d’action apparaîtront ici.'}</p></div><span class="placeholder-arrow">${icon('arrow')}</span></div>`;
    return;
  }
  const report = run.result;
  const demoBanner = run.mode === 'demo' ? `<div class="demo-banner">${icon('alert')}Démonstration locale : contenus et coûts simulés, sans recherche web ni appel API.</div>` : '';
  const heading = `<div class="results-heading"><div><div class="eyebrow">VOTRE PROCHAIN CHAPITRE</div><h2>Un cap, et les étapes pour avancer.</h2></div><div class="results-actions"><button class="text-button" data-edit-profile>Modifier mon profil</button><a href="/api/runs/${esc(run.id)}/export" class="secondary-button">${icon('download')}Rapport JSON</a></div></div>`;
  const dossiers = `<div class="result-grid">${['evolution','reconversion'].map(agent => dossierCard(run.steps.find(s => s.agent === agent))).join('')}</div>`;
  if (!report) {
    $('#results-section').innerHTML = heading + demoBanner + `<div class="failure-panel"><h3>Cette mission n'a pas pu être finalisée.</h3><p>${esc(run.error || 'Exécution interrompue. Les dossiers disponibles sont conservés.')}</p><button class="secondary-button" data-edit-profile>${icon('refresh')}Réessayer avec ce profil</button></div>` + dossiers;
    bindResultButtons(); return;
  }
  const partial = run.status === 'partial' ? '<div class="demo-banner">Un dossier n’a pas abouti : cette recommandation est partielle.</div>' : '';
  $('#results-section').innerHTML = heading + demoBanner + partial +
    `<article class="recommendation"><div class="eyebrow">${icon('compass')} LA DIRECTION RECOMMANDÉE</div><h3>${esc(report.recommended_path || 'Votre prochaine trajectoire')}</h3><p>${esc(report.recommendation)}</p><div class="reason-list">${array(report.reasoning).map(reason => `<span class="reason-chip">${icon('check')}${esc(reason)}</span>`).join('')}</div></article>` + dossiers +
    `<section class="panel comparison-panel"><h3>Deux trajectoires, côte à côte</h3><table class="comparison-table"><thead><tr><th>Critère</th><th>Évolution</th><th>Reconversion</th></tr></thead><tbody>${array(report.comparison).map(row => `<tr><td>${esc(row.criterion)}</td><td>${esc(row.evolution)}</td><td>${esc(row.reconversion)}</td></tr>`).join('')}</tbody></table></section>` +
    `<section class="panel roadmap-panel"><h3>Vos 90 premiers jours</h3><div class="roadmap-grid">${array(report.roadmap).map(item => `<article class="roadmap-step"><span>${esc(item.period)}</span><h4>${esc(item.goal)}</h4>${list(item.actions)}</article>`).join('')}</div></section>` +
    `<div class="first-step"><strong>VOTRE PREMIER PAS, CETTE SEMAINE</strong>${esc(report.first_step || 'Choisissez un petit projet pour tester votre intérêt.')}</div>` +
    (array(report.uncertainties).length ? `<div class="uncertainties"><strong>Ce qu'il reste à vérifier</strong>${list(report.uncertainties)}</div>` : '');
  bindResultButtons();
}

function editProfile() {
  changeView('orientation');
  $('#situation').focus();
  $('.profile-panel').scrollIntoView({behavior:'smooth',block:'start'});
}

function bindResultButtons() {
  $$('[data-open-agent]').forEach(button => button.addEventListener('click', () => openAgent(button.dataset.openAgent)));
  $$('[data-edit-profile]').forEach(button => button.addEventListener('click', editProfile));
}

function showDialog(title, html) {
  $('#dialog-title').textContent = title;
  $('#dialog-body').innerHTML = `<div class="dialog-content">${html}</div>`;
  $('#detail-dialog').showModal();
}

$('#dialog-close').addEventListener('click', () => $('#detail-dialog').close());
$('#detail-dialog').addEventListener('click', event => { if (event.target === $('#detail-dialog')) { const r = event.target.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) event.target.close(); } });

async function openAgent(agent) {
  if (!state.run) { toast('Lancez une exploration pour consulter le dossier de cet agent.'); return; }
  try {
    const run = await api(`/api/runs/${state.run.id}`);
    const step = run.steps.find(s => s.agent === agent);
    if (!step) { toast('Cet agent n’a pas encore commencé.'); return; }
    const dossier = step.dossier;
    const metrics = `<div class="dialog-metrics"><span>${esc(statuses[step.status] || step.status)}</span><span>${duration(step.duration_ms)}</span><span>${number((step.prompt_tokens || 0) + (step.completion_tokens || 0))} tokens</span><span>${money(step.cost)} ${run.mode === 'demo' ? '(simulé)':''}</span></div>`;
    let content = '';
    if (dossier && agent !== 'supervisor') {
      content = `<h3>${esc(dossier.title)}</h3><p>${esc(dossier.summary)}</p><h4>Compétences à développer</h4><div class="skill-chips">${array(dossier.skills).map(skill => `<span class="skill-chip">${esc(skill.name || skill)} ${skill.priority ? '· '+esc(skill.priority):''}</span>`).join('')}</div><h4>Signaux observés</h4>${list(dossier.signals)}<h4>Opportunités et pistes repérées</h4>${array(dossier.opportunities).length ? array(dossier.opportunities).map(item => `<p><strong>${esc(item.title)}</strong> · ${esc(item.organization)} · ${esc(item.location)}${safeUrl(item.url) ? ` · <a href="${esc(safeUrl(item.url))}" target="_blank" rel="noopener noreferrer">Consulter la page</a>`:''}</p>`).join(''):'<p>Aucune offre vérifiée à présenter dans ce dossier.</p>'}<h4>Limites de cette analyse</h4>${list(dossier.limitations)}<h4>Sources</h4>${sourcesHtml(dossier)}`;
    } else if (dossier) content = `<h3>${esc(dossier.recommended_path)}</h3><p>${esc(dossier.recommendation)}</p>${list(dossier.reasoning)}<h4>Incertitudes</h4>${list(dossier.uncertainties)}`;
    else content = `<p>${esc(step.error || 'Le dossier est en cours de préparation. Les détails seront disponibles à la fin de l’appel.')}</p>`;
    content += `<h4>Événements de l'agent</h4><div class="event-log">${eventRows(run.events.filter(event => event.agent === agent))}</div>`;
    showDialog(names[agent], metrics + content);
  } catch (error) { toast(error.message); }
}

$$('.agent-node').forEach(node => node.addEventListener('click', () => openAgent(node.dataset.agent)));

async function refreshSupervision() {
  const [metrics, runs] = await Promise.all([api(`/api/metrics?mode=${state.mode}`), api(`/api/runs?mode=${state.mode}`)]);
  state.metrics = metrics; state.runs = runs;
  $('#kpi-total').textContent = metrics.total;
  $('#kpi-duration').textContent = metrics.total && metrics.avg_ms ? duration(metrics.avg_ms) : '—';
  $('#kpi-success').textContent = metrics.success_rate == null ? '—' : `${Math.round(metrics.success_rate)} %`;
  $('#kpi-cost').textContent = money(metrics.cost);
  $('#kpi-mode').textContent = state.mode === 'demo' ? 'Démonstrations uniquement' : 'Analyses réelles';
  $('#kpi-cost-note').textContent = state.mode === 'demo' ? 'USD simulés · aucun appel API' : `USD · ${metrics.unknown_cost_runs} mission(s) au coût incomplet`;
  $('#metrics-note').textContent = state.mode === 'demo' ? 'Contenus et métriques simulés, séparés des analyses réelles.' : 'Les démonstrations sont exclues des métriques réelles.';
  const maxMs = Math.max(1000, ...metrics.agents.map(a => a.avg_ms));
  $('#agent-performance').innerHTML = metrics.agents.map(agent => `<div class="performance-row"><span class="performance-agent">${icon(icons[agent.agent])}${names[agent.agent]}</span><div class="performance-bar"><div class="performance-fill ${agent.agent}" style="width:${agent.count ? Math.max(1, agent.avg_ms/maxMs*100):0}%"></div></div><span class="performance-value">${agent.count ? duration(agent.avg_ms):'—'}</span><span class="performance-meta">${agent.count} appel(s) · ${number(agent.tokens)} tokens · ${money(agent.cost)}${state.mode === 'demo' ? ' simulés':''}</span></div>`).join('');
  renderHistory(); renderProjection(); renderAlerts();
  state.lastRefresh = Date.now();
}

function renderProjection() {
  const metrics = state.metrics;
  if (!metrics) return;
  const count = Number($('#projection-count').value);
  $('#projection-value').textContent = metrics.projection_average == null ? '—' : (metrics.projection_average * count).toFixed(2);
  $('#projection-note').textContent = metrics.projection_sample ? `Base : ${metrics.projection_sample} mission(s) réussie(s), ${money(metrics.projection_average)} en moyenne.${state.mode === 'demo' ? ' Données simulées.':''}` : 'Une analyse réussie avec un coût complet est nécessaire.';
}

function renderHistory() {
  const status = $('#status-filter').value;
  const runs = state.runs.filter(run => status === 'all' || run.status === status);
  $('#history-body').innerHTML = runs.length ? runs.map(run => `<tr><td><strong title="${esc(run.profile.situation)}">${esc(run.profile.situation)}</strong><code title="${esc(run.id)}">${esc(run.id)}</code></td><td>${esc(dateLabel(run.created_at))}</td><td>${badge(run.status)}</td><td>${duration(run.duration_ms)}</td><td>${number(run.tokens)}</td><td title="${run.cost_complete ? 'Coût complet connu':'Coût incomplet ou inconnu'}">${money(run.cost)}${run.cost != null && !run.cost_complete ? ' *':''}</td><td><button class="text-button" data-detail-run="${esc(run.id)}">Détails ${icon('arrow')}</button></td></tr>`).join('') : '<tr><td colspan="7" class="table-empty">Aucune exécution dans cette sélection. Lancez votre première exploration.</td></tr>';
  $$('[data-detail-run]').forEach(button => button.addEventListener('click', () => showRunDetail(button.dataset.detailRun)));
}

function renderAlerts() {
  const alerts = state.metrics?.alerts || [];
  $('#alert-count').textContent = `${alerts.length} alerte${alerts.length > 1 ? 's':''}`;
  const labels = {slow:'Lenteur', budget:'Budget', error:'Erreur'};
  $('#alerts-list').innerHTML = alerts.length ? alerts.map(alert => `<div class="alert-row ${esc(alert.code)}"><span class="alert-icon">${icon('alert')}</span><div><p><strong>${esc(labels[alert.code])}</strong> · ${esc(alert.message)}</p><small>${esc(dateLabel(alert.created_at))} · ${esc(names[alert.agent] || alert.agent)} · ${esc(alert.run_id.slice(0,8))}</small></div><button class="text-button" data-alert-run="${esc(alert.run_id)}">Voir ${icon('arrow')}</button></div>`).join('') : '<div class="empty-state">Aucune alerte à signaler.</div>';
  $$('[data-alert-run]').forEach(button => button.addEventListener('click', () => showRunDetail(button.dataset.alertRun)));
}

async function showRunDetail(id) {
  try {
    const run = await api(`/api/runs/${id}`);
    const html = `<div class="dialog-metrics">${badge(run.status)}<span>${duration(run.duration_ms)}</span><span>${number(run.tokens)} tokens</span><span>${money(run.cost)} ${run.mode === 'demo' ? 'simulés':''}</span></div><p><strong>${esc(run.profile.situation)}</strong> · ${esc(run.profile.market)} · ${esc(run.model)}</p><p>Correlation ID : <code>${esc(run.id)}</code></p>${run.error ? `<p>${esc(run.error)}</p>`:''}<div class="dialog-actions"><button class="secondary-button" id="load-detail-run">${icon('compass')}Ouvrir la mission</button><a class="secondary-button" href="/api/runs/${esc(id)}/export">${icon('download')}Rapport et événements JSON</a></div><h4>Étapes</h4>${run.steps.map(step => `<p>${esc(names[step.agent])} · ${esc(statuses[step.status] || step.status)} · ${duration(step.duration_ms)} · ${money(step.cost)}</p>`).join('')}<h4>Journal corrélé</h4><div class="event-log">${eventRows(run.events)}</div><h4>Profil transmis</h4><pre>${esc(JSON.stringify(run.profile,null,2))}</pre>`;
    showDialog(`Mission ${id.slice(0,8)}`, html);
    $('#load-detail-run').addEventListener('click', async () => {
      if (state.run?.status === 'running' && state.run.id !== id) { toast('Attendez la fin de la mission active avant d’en ouvrir une autre.'); return; }
      $('#detail-dialog').close();
      try { await openRun(id); changeView('orientation'); } catch (error) { toast(error.message); }
    });
  } catch (error) { toast(error.message); }
}

$$('[data-metric-mode]').forEach(button => button.addEventListener('click', () => {
  state.mode = button.dataset.metricMode;
  $$('[data-metric-mode]').forEach(el => el.classList.toggle('selected',el === button));
  refreshSupervision().catch(error => toast(error.message));
}));
$('#status-filter').addEventListener('change', renderHistory);
$('#status-filter').add(new Option('Annulées', 'cancelled'));
$('#projection-count').addEventListener('change', renderProjection);
$('#refresh-btn').addEventListener('click', () => refreshSupervision().catch(error => toast(error.message)));
$('#csv-export').addEventListener('click', () => { window.location.href = `/api/exports/runs.csv?mode=${state.mode}`; });

setInterval(() => {
  if (state.replaying) {
    const delta = performance.now() - state.anchorTime;
    state.elapsed += delta * Number($('#replay-speed').value);
    state.anchorTime = performance.now();
    while (state.replayIndex < state.replaySource.length && state.replaySource[state.replayIndex].elapsed_ms <= state.elapsed) {
      consumeEvent(state.replaySource[state.replayIndex++]);
      renderLog();
    }
    renderMission();
    if (state.replayIndex >= state.replaySource.length) { stopReplay(); toast('Replay terminé.'); }
  } else if (state.run?.status === 'running') {
    state.elapsed = state.anchor + performance.now() - state.anchorTime;
    renderMission();
  }
  if (state.view === 'supervision' && Date.now()-state.lastRefresh > 5000) {
    state.lastRefresh = Date.now();
    refreshSupervision().catch(() => {});
  }
  if (state.view === 'operations' && Date.now()-state.opsRefresh > 3000) {
    state.opsRefresh = Date.now();
    refreshOperations().catch(() => {});
  }
}, 180);

function operatorBody() {
  const actor = $('#ops-actor').value.trim();
  if (actor.length < 2) throw new Error('Indiquez votre nom pour tracer cette intervention.');
  localStorage.setItem('capavenir-operator', actor);
  return {actor, reason:$('#ops-reason').value.trim() || 'Intervention pédagogique'};
}

async function opsPost(path, body) {
  return api(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
}

async function refreshOperations() {
  const ops = await api('/api/ops');
  state.ops = ops; state.opsRefresh = Date.now();
  $('#ops-version').textContent = `v${ops.version}`;
  $('#app-version').textContent = `v${ops.version}`;
  $('#ops-commit').textContent = ops.commit === 'local' ? 'Version locale' : `Commit ${ops.commit.slice(0,12)}`;
  $('#ops-service').className = `badge ${ops.paused ? 'failed':'completed'}`;
  $('#ops-service').textContent = ops.paused ? 'Analyses suspendues':'Analyses autorisées';
  $('#ops-active').textContent = `${ops.active_runs} mission(s) active(s)`;
  $('#ops-stop').disabled = ops.paused;
  $('#ops-resume').disabled = !ops.paused;
  $('#ops-test-incident').disabled = ops.paused;
  $('#ops-pause-note').textContent = ops.paused ? `Pause persistante · ${ops.actor} · ${ops.reason}` : 'Les frais déjà engagés chez le fournisseur peuvent subsister après l’arrêt.';
  if (document.activeElement !== $('#ops-incident')) $('#ops-incident').value = ops.incident;
  $('#ops-image-fault').textContent = ops.image_fault ? 'IMAGE D’INCIDENT : cette version force une erreur démo. Revenez à l’image stable pour supprimer cette panne.' : 'L’incident ne modifie pas les analyses réelles.';
  const candidates = [...ops.releases.candidates].reverse();
  const reviewLabels = {pending:'À valider', approved:'Approuvée', rejected:'Refusée'};
  $('#ops-releases').innerHTML = candidates.length ? candidates.map(candidate => `<tr><td><strong>v${esc(candidate.version)}</strong><code title="${esc(candidate.image_id)}">${esc(candidate.image_id.slice(0,23))}…</code></td><td>${candidate.demo_fault ? 'Image d’incident démo':'Version normale'}<br><small>${esc(candidate.image)}</small></td><td><span class="badge ${candidate.status === 'approved' ? 'completed':candidate.status === 'rejected' ? 'failed':'partial'}">${reviewLabels[candidate.status]}</span>${candidate.reviewer ? `<small class="reviewer">${esc(candidate.reviewer)} · ${esc(dateLabel(candidate.reviewed_at))}</small>`:''}</td><td>${candidate.status === 'pending' ? `<div class="ops-review-buttons"><button class="secondary-button" data-review="approved" data-version="${esc(candidate.version)}">Approuver</button><button class="text-button" data-review="rejected" data-version="${esc(candidate.version)}">Refuser</button></div>`:'Décision enregistrée'}</td></tr>`).join('') : '<tr><td colspan="4" class="table-empty">Utilisez DOCKER.cmd pour préparer les images de démonstration.</td></tr>';
  $$('[data-review]').forEach(button => button.addEventListener('click', async () => {
    try {
      await opsPost(`/api/ops/releases/${encodeURIComponent(button.dataset.version)}/review`, {...operatorBody(), decision:button.dataset.review, agent_card_reviewed:$('#ops-card-reviewed').checked});
      await refreshOperations(); toast('Décision enregistrée pour cette image exacte.');
    } catch (error) { toast(error.message); }
  }));
  const actionLabels = {kill_switch_on:'Arrêt d’urgence activé', kill_switch_off:'Analyses réautorisées', tasks_cancelled:'Tâches interrompues', incident_changed:'Scénario de démo modifié', release_approved:'Version approuvée', release_rejected:'Version refusée', database_backup:'Sauvegarde SQLite'};
  const interventions = ops.audit.map(event => ({at:event.created_at, actor:event.actor, title:actionLabels[event.action] || event.action, detail:JSON.stringify(event.details)}));
  const deployments = ops.releases.deployments.map(event => ({at:event.at, actor:event.operator, title:event.kind === 'rollback' ? 'Rollback réalisé':event.kind === 'bootstrap' ? 'Installation initiale':'Version déployée', detail:`v${event.version} · ${event.image_id.slice(0,23)}…`}));
  const logs = [...interventions,...deployments].sort((a,b) => b.at.localeCompare(a.at));
  $('#ops-audit').innerHTML = logs.length ? logs.slice(0,60).map(event => `<div class="ops-audit-row"><span>${esc(dateLabel(event.at))}</span><div><strong>${esc(event.title)}</strong><p>${esc(event.detail)}</p></div><small>${esc(event.actor)}</small></div>`).join('') : '<div class="empty-state">Aucune intervention enregistrée.</div>';
}

async function setPause(paused) {
  try {
    const result = await opsPost('/api/ops/pause', {...operatorBody(), paused});
    await refreshOperations();
    toast(paused ? `Arrêt actif · ${result.cancelled.length} mission(s) interrompue(s).`:'Les analyses sont à nouveau autorisées.');
  } catch (error) { toast(error.message); }
}
$('#ops-stop').addEventListener('click', () => setPause(true));
$('#ops-resume').addEventListener('click', () => setPause(false));
$('#ops-refresh').addEventListener('click', () => refreshOperations().catch(error => toast(error.message)));
$('#ops-apply-incident').addEventListener('click', async () => {
  try { await opsPost('/api/ops/incident', {...operatorBody(),incident:$('#ops-incident').value}); await refreshOperations(); toast('Scénario appliqué aux prochaines missions de démonstration.'); }
  catch (error) { toast(error.message); }
});
$('#ops-test-incident').addEventListener('click', async () => {
  try {
    if (state.run?.status === 'running') throw new Error('Terminez la mission active ou interrompez-la avant de commencer.');
    await opsPost('/api/ops/incident', {...operatorBody(),incident:$('#ops-incident').value});
    const result = await opsPost('/api/runs', {profile:example, mode:'demo', scenario:'normal'});
    await openRun(result.id); changeView('orientation');
  } catch (error) { toast(error.message); }
});

async function boot() {
  try {
    const health = await api('/api/health');
    $('#connection-dot').classList.add('online');
    $('#connection-label').textContent = health.configured ? 'Équipe connectée' : 'Mode démo disponible';
    $('#app-version').textContent = `v${health.version}`;
    $('#ops-actor').value = localStorage.getItem('capavenir-operator') || '';
    $('#slow-rule').textContent = `> ${health.slow_seconds} s`;
    $('#budget-rule').textContent = `> $${health.budget_usd.toFixed(2)}`;
    if (!health.configured) { $('#run-mode').value = 'demo'; $('#scenario-row').classList.remove('hidden'); }
    const lastRun = localStorage.getItem('capavenir-last-run');
    if (lastRun) {
      try { await openRun(lastRun); } catch { localStorage.removeItem('capavenir-last-run'); }
    }
    if (['#supervision','#operations'].includes(window.location.hash)) changeView(window.location.hash.slice(1));
  } catch (error) {
    $('#connection-label').textContent = 'Serveur indisponible';
    toast(error.message);
  }
}

boot();
