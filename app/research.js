/* Research and connections share the desktop's authenticated local API. */
const rsStore = {engines: null, engineError: '', loading: null, registry: null, lastReport: ''};
const rsNames = {kronos: 'Kronos', ruflo: 'Ruflo', tradingagents: 'TradingAgents',
    swarm: 'Swarm review', autonomous: 'Autonomous local analysis', research: 'Specialist review', backtest: 'Backtest', filings: 'SEC filings'};

function rsSignal(value) {
    if (['VETO', 'error', 'Unavailable'].includes(value)) return 'bad';
    if (['UNKNOWN', 'WATCH', 'running', 'Setup required'].includes(value)) return 'hold';
    if (['PASS', 'complete', 'Ready'].includes(value)) return 'good';
    return '';
}

function rsWhen(seconds) {
    if (!Number.isFinite(Number(seconds)) || seconds == null) return 'Time unavailable';
    return new Date(Number(seconds) * 1000).toLocaleString(undefined, {dateStyle:'short', timeStyle:'short'});
}

function rsButton(action, caption, more='') {
    return '<button type="button" data-act="' + esc(action) + '" ' + more + '>' + esc(caption) + '</button>';
}

function rsSource() {
    const i = (state.watch || []).find(row => row.symbol === symbol);
    if (!state.market) return badge('WAITING', 'hold');
    const mode = i?.kind || 'UNAVAILABLE';
    const tone = mode === 'LIVE' ? 'good' : ['STALE', 'WAIT', 'SIM'].includes(mode) ? 'hold' : '';
    return badge(mode, tone) + ' <span class="muted">' + esc(state.market.source || '') +
        (state.market.interval ? ' · ' + esc(state.market.interval) : '') + '</span>';
}

function rsJobTable() {
    const jobs = (state.jobs || []).filter(x => x.symbol === symbol).slice(-8).reverse();
    if (!jobs.length) return '<div class="empty">No research runs for ' + esc(symbol) + ' in this session.</div>';
    return '<div class="scroll"><table class="results-table"><thead><tr><th>Run</th><th>Started</th><th>Status</th><th>Report</th></tr></thead><tbody>' +
        jobs.map(j => '<tr><td>' + esc(rsNames[j.task] || j.task) + '</td><td class="mono">' + esc(rsWhen(j.ts)) +
            '</td><td>' + badge(j.state, rsSignal(j.state)) + '</td><td>' +
            (j.state === 'running' ? '<span class="muted">In progress</span>' :
                rsButton('result', j.state === 'error' ? 'View error' : 'View report', 'data-id="' + esc(j.id) + '"')) +
            '</td></tr>').join('') + '</tbody></table></div>';
}

function rsIsRunning(task) {
    return (state.jobs || []).some(j => j.symbol === symbol && j.task === task && j.state === 'running');
}

function rsFilings() {
    if (!['MSFT','AAPL'].includes(symbol)) {
        return panel('SEC filings', '<div class="empty">Select AAPL or MSFT to inspect SEC filing sources.</div>');
    }
    const docs = state.filings || [];
    const body = docs.length ? '<div class="panel-body">' + docs.map((doc, idx) =>
        '<div class="stat-line"><span><b>' + esc(doc.form) + '</b> · ' + esc(doc.filed) + '</span>' +
        rsButton('rs-filing', 'Source', 'data-index="' + idx + '"') + '</div>').join('') + '</div>' :
        '<div class="empty">No filings loaded for ' + esc(symbol) + '. Refresh from SEC EDGAR to retrieve recent filings.</div>';
    return panel('SEC filings', body, rsButton('rs-filings', rsIsRunning('filings') ? 'Refreshing…' : 'Refresh',
        !state.market || rsIsRunning('filings') ? 'disabled' : ''));
}

function rsAutonomousPanel() {
    const latest = [...(state.jobs || [])].reverse().find(job => job.symbol === symbol && job.task === 'autonomous');
    const summary = '<p class="foot-note">Runs automatically after a selected global stock receives a public observation, or on demand. ' +
        'Six local deterministic research agents plan, challenge and verify a frozen source snapshot. ' +
        'No cloud models, broker tools, trade signals or paid inference.</p>';
    const action = rsButton('rs-autonomous',
        rsIsRunning('autonomous') ? 'Research in progress…' : 'Run local agents',
        (!state.market || rsIsRunning('autonomous') ? 'disabled' : '') + ' class="primary"');
    if (!latest) return panel('Autonomous research mission', summary +
        '<div class="empty">No autonomous report for this instrument yet. Select a global stock or run local agents.</div>', action);
    const report = latest.result && typeof latest.result === 'object' ? latest.result : null;
    if (!report) return panel('Autonomous research mission', summary +
        '<div class="panel-body">' + badge(latest.state, rsSignal(latest.state)) +
        '<p class="tagline">' + esc(String(latest.result || 'Analyzing a frozen market snapshot.')) + '</p></div>', action);
    const status = report.decision === 'ABSTAIN' ? 'hold' : '';
    const explain = (report.reasons || []).map(reason => '<p>' + esc(reason) + '</p>').join('');
    const agents = (report.agents || []).map(agent => '<div class="stat-line"><span>' +
        esc(agent.name) + ' ' + badge(agent.signal, rsSignal(agent.signal)) + '</span>' +
        '<span class="muted">' + esc(agent.summary) + '</span></div>').join('');
    const evidence = '<div class="tagline">Source: ' + esc(report.source) + ' · ' +
        esc(report.source_asof) + ' · ' + esc(report.currency) + '</div>' +
        '<p class="foot-note">Snapshot SHA256: <code>' + esc(report.snapshot_sha256) + '</code></p>';
    return panel('Autonomous research mission', summary + '<div class="panel-body">' +
        '<div class="row">' + badge(report.decision, status) +
        '<span class="muted">Evidence: ' + (report.verifier?.passed ? 'verified' : 'unverified') +
        ' · Execution disabled</span></div>' +
        '<div class="tagline">' + explain + '</div>' + evidence + agents +
        '<p class="foot-note">Observed price data only. No independently verified issuer valuation or return prediction.</p>' +
        rsButton('result', 'Open complete evidence report', 'data-id="' + esc(latest.id) + '"') +
        '</div>', action);
}

function renderResearch() {
    const a = state.analysis || {};
    const specialists = a.agents || [];
    const gate = a.verdict || 'Awaiting data';
    const reasons = (a.reasons || []).map(r => '<p>' + esc(r) + '</p>').join('');
    const detail = Object.entries(a.metrics || {}).map(([name, value]) => '<div class="stat-line"><span class="muted">' +
        esc(name) + '</span><strong>' + esc(String(value)) + '</strong></div>').join('');
    const status = '<div class="panel-body"><div class="row">' + badge(gate, a.veto ? 'hold' : a.verdict ? 'good' : '') +
        '</div><div class="tagline">' + reasons + '</div></div>';
    const verdicts = specialists.length ? '<div class="scroll"><table><thead><tr><th>Specialist</th><th>Signal</th><th>Evidence</th></tr></thead><tbody>' +
        specialists.map(agent => '<tr><td><b>' + esc(agent.name) + '</b><div class="tagline">' + esc(agent.pod) +
            '</div></td><td>' + badge(agent.signal, rsSignal(agent.signal)) +
            '</td><td>' + esc(agent.detail) + '</td></tr>').join('') + '</tbody></table></div>' :
        '<div class="empty">' + esc(state.error || 'Waiting for a completed bar before assessing this instrument.') + '</div>';
    const snap = '<div class="row">' + instrumentSelect() + rsSource() + '</div>';
    const actions = '<div class="chart-tool">' +
        rsButton('rs-review', rsIsRunning('research') ? 'Review running…' : 'Run review',
            !state.market || rsIsRunning('research') ? 'disabled' : '') +
        rsButton('rs-backtest', rsIsRunning('backtest') ? 'Backtesting…' : 'Backtest',
            !state.market || rsIsRunning('backtest') ? 'disabled' : '') +
        rsButton('rs-swarm', 'Run swarm', (!state.market ? 'disabled ' : '') + 'class="primary"') + '</div>';
    return '<div class="stack">' + panel('Research instrument', snap, actions) +
        '<div class="grid-main"><div class="stack" style="align-content:start">' +
            panel('Specialist verdicts', verdicts, rsButton('rs-registry', 'Agent registry')) +
            rsAutonomousPanel() +
            panel('Research runs', rsJobTable()) +
        '</div><div class="stack" style="align-content:start">' + panel('Risk decision', status) +
            panel('Risk and valuation', detail ? '<div class="panel-body">' + detail + '</div>' :
                '<div class="empty">Waiting for a market observation.</div>') + rsFilings() + '</div></div></div>';
}

function rsLoadEngines(force=false) {
    if (rsStore.loading) return rsStore.loading;
    if (!force && (rsStore.engines || rsStore.engineError)) return Promise.resolve();
    rsStore.loading = Promise.resolve().then(() => api('/api/engines')).then(rows => {
        if (!Array.isArray(rows)) throw new Error('Invalid engine status response.');
        rsStore.engines = rows;
        rsStore.engineError = '';
    }).catch(error => {
        rsStore.engineError = error.message || String(error);
        rsStore.engines = null;
    }).finally(() => { rsStore.loading = null; render(); });
    return rsStore.loading;
}

function renderConnections() {
    void rsLoadEngines();
    const engines = rsStore.engines || [];
    const engineRows = engines.map(e => {
        const running = rsIsRunning(e.id);
        const disabled = running || e.status !== 'Ready' || !state.market;
        const note = e.id === 'tradingagents' ? '<p>Run sends a price summary to your configured model provider.</p>' : '';
        return '<div class="engine-row"><div style="flex:1"><h3>' + esc(e.name) + '</h3><p>' + esc(e.detail) + '</p>' + note +
            '</div>' + badge(e.status, rsSignal(e.status)) +
            rsButton('rs-engine', running ? 'Running…' : 'Run', 'data-engine="' + esc(e.id) + '" ' + (disabled ? 'disabled' : '')) + '</div>';
    }).join('');
    const engineBody = engineRows ? '<div class="panel-body">' + engineRows + '</div>' :
        '<div class="empty">' + esc(rsStore.engineError || 'Reading installed engine status…') + '</div>';
    const auditReport = (state.audit || []).find(x => x.category === 'MT5 IMPORT' && x.detail);
    const hasReport = Boolean(rsStore.lastReport || auditReport);
    const mt5 = '<div class="panel-body"><h3>APEX-FX signal report</h3><p class="tagline">Import an exported report or an MT5 Experts log. Meridian reads the latest complete report.</p>' +
        '<div class="actions section-gap">' +
        rsButton('rs-import', 'Choose file…') + (hasReport ? rsButton('rs-report', 'View last report') : '') + '</div></div>';
    const feeds = (state.watch || []).map(i => '<div class="stat-line"><span>' + esc(i.symbol) + '</span>' +
        badge(i.kind, i.kind === 'LIVE' ? 'good' : ['WAIT','STALE','SIM'].includes(i.kind) ? 'hold' : '') + '</div>').join('');
    return '<div class="stack">' + panel('Run on instrument', '<div class="panel-body row">' + instrumentSelect() + rsSource() + '</div>') +
        '<div class="grid-main"><div class="stack" style="align-content:start">' +
            panel('Research engines', engineBody, rsButton('rs-engines', 'Refresh status')) +
            panel('Research runs', rsJobTable()) +
        '</div><div class="stack" style="align-content:start">' + panel('MetaTrader 5', mt5) +
            panel('Market feeds', '<div class="panel-body">' + feeds + '</div>') + '</div></div></div>';
}

async function rsRegistry() {
    if (!rsStore.registry) rsStore.registry = await api('/api/registry');
    const cards = rsStore.registry;
    const pods = [...new Set(cards.map(c => c.pod))];
    const profiles = [...new Set(cards.map(c => c.profile))];
    const options = values => values.map(v => '<option value="' + esc(v) + '">' + esc(v.replaceAll('_',' ')) + '</option>').join('');
    modal('Agent registry', cards.length + ' specialist cards',
        '<label class="field">Search by name, mandate or ID<input id="rs-search" type="search" placeholder="Search specialists"></label>' +
        '<div class="form-pair"><label class="field">Pod<select id="rs-pod"><option value="">All pods</option>' + options(pods) + '</select></label>' +
        '<label class="field">Profile<select id="rs-profile"><option value="">All profiles</option>' + options(profiles) + '</select></label></div>' +
        '<div class="tagline" id="rs-count" role="status"></div><div id="rs-list"></div>');
    const search = document.querySelector('#rs-search'), pod = document.querySelector('#rs-pod'), profile = document.querySelector('#rs-profile');
    function apply() {
        const q = search.value.toLowerCase().trim();
        const list = cards.filter(c => (!pod.value || pod.value === c.pod) && (!profile.value || profile.value === c.profile) &&
            [c.name, c.mandate, c.id].some(v => String(v).toLowerCase().includes(q)));
        document.querySelector('#rs-count').textContent = list.length + ' of ' + cards.length + ' cards';
        document.querySelector('#rs-list').innerHTML = list.map(c => '<div class="registry-item"><div class="row"><strong>' + esc(c.name) +
            '</strong>' + (c.has_hard_veto ? badge('VETO AUTHORITY','hold') : '') + '</div><p>' + esc(c.mandate) +
            '</p><small class="muted">' + esc(c.id) + ' · ' + esc(c.pod) + ' · ' + esc(c.profile.replaceAll('_',' ')) + '</small></div>').join('');
    }
    search.addEventListener('input', apply);
    pod.addEventListener('change', apply);
    profile.addEventListener('change', apply);
    apply();
    search.focus();
}

async function researchClick(action, element) {
    if (!action.startsWith('rs-')) return false;
    try {
        switch (action) {
        case 'rs-review': await job('research'); break;
        case 'rs-autonomous': await job('autonomous'); break;
        case 'rs-backtest': await job('backtest'); break;
        case 'rs-swarm':
            modal('Run swarm', symbol, '<p>The local run combines specialist verdicts, a Ruflo risk review and a Kronos forecast on the selected snapshot.</p>' +
                '<p class="foot-note">Including TradingAgents sends a price summary to your configured model provider and may use its paid quota.</p>' +
                '<div class="actions section-gap">' + rsButton('rs-swarm-local', 'Run locally', 'class="primary"') +
                rsButton('rs-swarm-provider', 'Include TradingAgents') + '</div>');
            break;
        case 'rs-swarm-local':
        case 'rs-swarm-provider':
            document.getElementById('modal').close();
            await job('swarm', action === 'rs-swarm-provider' ? 'with-provider' : undefined);
            break;
        case 'rs-engine': await job('integration', element.dataset.engine); break;
        case 'rs-engines': await rsLoadEngines(true); break;
        case 'rs-registry': await rsRegistry(); break;
        case 'rs-filings': await job('filings'); break;
        case 'rs-filing': {
            const doc = state.filings?.[Number(element.dataset.index)];
            if (!doc || !/^https:\/\/www\.sec\.gov\/Archives\/edgar\/data\//i.test(doc.url)) throw new Error('SEC source unavailable.');
            modal(doc.form + ' filing', symbol + ' · ' + doc.filed, '<label class="field">SEC EDGAR source URL<input readonly id="rs-source-url" value="' +
                esc(doc.url) + '"></label><p class="foot-note">Press Ctrl+C to copy the selected source URL.</p>');
            document.querySelector('#rs-source-url').select();
            break;
        }
        case 'rs-import': {
            let picker = document.getElementById('rs-mt5-file');
            if (!picker) {
                picker = document.createElement('input');
                picker.id = 'rs-mt5-file';
                picker.type = 'file';
                picker.accept = '.txt,.log';
                picker.hidden = true;
                picker.setAttribute('aria-label', 'APEX-FX signal report or Experts log');
                // Market refreshes replace the view while the Windows file picker is open.
                document.body.appendChild(picker);
            }
            picker.click();
            break;
        }
        case 'rs-report': {
            const recent = (state.audit || []).find(x => x.category === 'MT5 IMPORT' && x.detail);
            modal('APEX-FX signal report', 'MetaTrader 5', '<pre>' + esc(rsStore.lastReport || recent?.detail || 'No report imported.') + '</pre>');
            break;
        }
        default: return false;
        }
    } catch (error) { toast(error.message || String(error)); }
    return true;
}

async function researchChange(element) {
    if (element.id !== 'rs-mt5-file') return false;
    const file = element.files?.[0];
    if (!file) return true;
    element.value = '';
    try {
        let offset = Math.max(0, file.size - 4000000);
        // MT5 commonly emits UTF-16. Align the tail on a code-unit boundary.
        offset += offset % 2;
        const data = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result).split(',')[1]);
            reader.onerror = () => reject(new Error('Could not read the selected file.'));
            reader.readAsDataURL(file.slice(offset));
        });
        const out = await api('/api/mt5', {content:data});
        rsStore.lastReport = out.report;
        await refresh();
        modal('APEX-FX signal report', file.name, '<pre>' + esc(out.report) + '</pre>');
    } catch (error) { toast(error.message || String(error)); }
    return true;
}
