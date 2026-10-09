import { h, render } from './vendor/preact.module.js';
import { useState, useEffect, useRef } from './vendor/hooks.module.js';
import htm from './vendor/htm.module.js';
import { BRIEFS } from './data/briefs.js';
import { computeProfile, buildChannels, initialState, GROUPS, CARD_COUNT } from './engine.js';

const html = htm.bind(h);
const params = new URLSearchParams(location.search);
const RESEARCH = params.get('research') === '1';   // ?research=1 shows the before/after research strip
const START = BRIEFS.some((b) => b.id === params.get('b')) ? params.get('b') : BRIEFS[0].id; // ?b=contador

const Check = () => html`<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>`;
const Alert = () => html`<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="insight-icon"><circle cx="12" cy="12" r="9"/><path d="M12 8v5"/><path d="M12 16.5v.01"/></svg>`;

function App() {
  const [briefId, setBriefId] = useState(START);
  const [s, setS] = useState(initialState);
  const timers = useRef({});
  const kitRef = useRef(null);
  const brief = BRIEFS.find((b) => b.id === briefId);
  const p = computeProfile(brief, s);
  const channels = buildChannels(brief, p, s);
  const tab = s.tab && channels.some((c) => c.id === s.tab) ? s.tab : channels[0].id;

  useEffect(() => () => Object.values(timers.current).forEach(clearTimeout), []);
  useEffect(() => {
    if (!s.done) return;
    later('scrollDone', 520, scrollKit);
  }, [s.done]);
  useEffect(() => { if (s.sent) scrollKit(); }, [s.sent]);

  const later = (key, ms, fn) => { clearTimeout(timers.current[key]); timers.current[key] = setTimeout(fn, ms); };
  const scrollKit = () => { try { kitRef.current && kitRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (e) {} };

  const pickBrief = (id) => {
    Object.values(timers.current).forEach(clearTimeout);
    setBriefId(id);
    setS(initialState());
    const u = new URL(location.href); u.searchParams.set('b', id); history.replaceState(null, '', u);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  const decide = (v) => setS((x) => (x.leaving ? x : { ...x, phase: 'reasons', verdict: v, picked: [] }));
  const back = () => setS((x) => (x.leaving ? x : { ...x, phase: 'react', verdict: null, picked: [] }));
  const toggle = (ri) => setS((x) => ({ ...x, picked: x.picked.includes(ri) ? x.picked.filter((r) => r !== ri) : [...x.picked, ri] }));
  const commit = () => {
    setS((x) => (x.leaving ? x : { ...x, decisions: [...x.decisions, { i: x.i, v: x.verdict, r: x.picked }], leaving: x.verdict }));
    later('card', 440, () => setS((x) => {
      const nx = x.i + 1;
      return { ...x, i: nx, phase: 'react', verdict: null, picked: [], leaving: null, done: nx >= CARD_COUNT };
    }));
  };
  const send = () => {
    if (s.sent || s.sending) return;
    setS((x) => ({ ...x, sending: true }));
    later('send', 650, () => setS((x) => ({ ...x, sending: false, sent: true })));
  };
  const reset = () => { Object.values(timers.current).forEach(clearTimeout); setS(initialState()); };
  const copy = (c) => {
    try { navigator.clipboard && navigator.clipboard.writeText(c.body).catch(() => {}); } catch (e) {}
    setS((x) => ({ ...x, copied: c.id }));
    later('copy', 1800, () => setS((x) => ({ ...x, copied: null })));
  };

  return html`
  <div class="page"><div class="wrap">
    <${Picker} briefId=${briefId} onPick=${pickBrief} />

    <header class="hero">
      <div class="hero-text">
        <div class="eyebrow">${RESEARCH ? 'Prototipo · PR-01 calibración de perfil' : `Búsqueda: ${brief.role.toLowerCase()} · ${brief.sector}`}</div>
        <h1>${RESEARCH ? 'Calibra el perfil con ejemplos, no con una semana de correos.' : 'Ayúdenos a afinar el perfil en 5 minutos'}</h1>
        <p class="lede">${RESEARCH
          ? 'El cliente reacciona a perfiles de ejemplo. Cada “no” trae su porqué, y el perfil se arma solo, a la vista de ambos.'
          : 'Le mostramos 6 perfiles de ejemplo. Díganos sí o no, y por qué. Con eso armamos el perfil y salimos a buscar.'}</p>
      </div>
      <div class="brief-quote">
        <div class="label">Su brief original</div>
        <div class="quote">“${brief.brief}”</div>
      </div>
    </header>

    <div class="row">
      <section class="deck-col" aria-label="Ejemplos para reaccionar">
        <div class="deck-top">
          <div class="step">${s.done ? `Listo · ${CARD_COUNT} de ${CARD_COUNT}` : `Ejemplo ${s.i + 1} de ${CARD_COUNT}`}</div>
          <div class="dots">${brief.cards.map((c, ix) => {
            const cur = !s.done && ix === s.i;
            return html`<span class=${'dot' + (cur ? ' cur' : ix < s.decisions.length ? ' past' : '')}></span>`;
          })}</div>
        </div>
        <div class="deck">
          ${!s.done && html`<${Card} key=${brief.id + s.i} card=${brief.cards[s.i]} s=${s}
              onYes=${() => decide('yes')} onNo=${() => decide('no')} onToggle=${toggle} onBack=${back} onCommit=${commit} />`}
          ${s.done && html`
            <div class=${'card done' + (s.sending ? ' sending' : '')}>
              <div class="done-badge"><${Check} /></div>
              <div class="done-title">${s.sent ? 'Enviado a su reclutador' : 'Perfil calibrado'}</div>
              <p class="muted-p">${s.sent
                ? 'Su reclutador ya tiene el perfil y el porqué de cada decisión. Si algo cambia, reaccione de nuevo y todo lo derivado se actualiza.'
                : `${p.n} reacciones y ${p.reasonsN} razones capturadas. Abajo está su perfil maestro.`}</p>
              <div class="summary">${p.summary}</div>
              <div class="btn-row">
                ${!s.sent
                  ? html`<button type="button" class="btn primary grow" onClick=${send}>Enviar perfil a mi reclutador</button>`
                  : html`<button type="button" class="btn ok grow" onClick=${scrollKit}>Enviado · ver perfil maestro</button>`}
                <button type="button" class="btn ghost" onClick=${reset}>Reiniciar</button>
              </div>
            </div>`}
        </div>
      </section>

      <${LivePanel} p=${p} brief=${brief} s=${s}
        onConfirm=${() => setS((x) => ({ ...x, confirmed: true }))}
        onDismiss=${() => setS((x) => ({ ...x, dismissed: true }))} />
    </div>

    ${s.done && html`<${Kit} kitRef=${kitRef} brief=${brief} p=${p} channels=${channels} tab=${tab} copied=${s.copied} sent=${s.sent}
        onTab=${(id) => setS((x) => ({ ...x, tab: id, copied: null }))} onCopy=${copy} />`}

    ${RESEARCH && html`
      <section class="research" aria-label="Antes y después">
        <div class="r-before">
          <div class="label">Hoy (entrevistas)</div>
          <div class="r-big">≈1 semana de idas y vueltas</div>
          <div class="r-small">Para definir al candidato, según una reclutadora. Otro reclutador a veces llama a la empresa para aclarar qué quieren.</div>
        </div>
        <div class="r-after">
          <div class="label">Con el calibrador (hipótesis)</div>
          <div class="r-big">${p.n === 0 ? 'Reacciones a ejemplos, con su porqué' : `${p.n} reacciones, ${p.reasonsN} razones en esta demo`}</div>
          <div class="r-small">Por medir: reacciones hasta un perfil estable, y si el perfil maestro acorta la búsqueda.</div>
        </div>
      </section>`}
  </div></div>`;
}

function Picker({ briefId, onPick }) {
  return html`
  <nav class="picker" aria-label="Búsquedas de prueba">
    <div class="picker-label">Búsquedas de prueba</div>
    <div class="picker-row">
      ${BRIEFS.map((b) => html`
        <button type="button" class=${'pick' + (b.id === briefId ? ' on' : '')} aria-pressed=${b.id === briefId ? 'true' : 'false'} onClick=${() => onPick(b.id)}>
          <span class="pick-role">${b.role}</span>
          <span class="pick-quote">“${b.brief}”</span>
        </button>`)}
    </div>
  </nav>`;
}

function Card({ card, s, onYes, onNo, onToggle, onBack, onCommit }) {
  const cls = 'card ' + (s.leaving ? (s.leaving === 'yes' ? 'out-yes' : 'out-no') : 'enter');
  const list = s.verdict === 'yes' ? card.yes : card.no;
  return html`
  <article class=${cls}>
    ${s.leaving === 'yes' && html`<div class="stamp yes">SÍ</div>`}
    ${s.leaving === 'no' && html`<div class="stamp no">NO</div>`}
    <div class="card-head">
      <div class="avatar">${card.letter}</div>
      <div class="card-titles">
        <div class="card-title">${card.title}</div>
        <div class="card-sub">Perfil de ejemplo · ${card.company}</div>
      </div>
    </div>
    <dl class="fields">
      ${card.fields.map(([k, v]) => html`<div class="field"><dt>${k}</dt><dd>${v}</dd></div>`)}
    </dl>
    ${s.phase === 'react' && !s.leaving && html`
      <div class="verdict">
        <div class="muted-p">¿Así es la persona que busca?</div>
        <div class="btn-row">
          <button type="button" class="btn ghost grow" onClick=${onNo}>No es este</button>
          <button type="button" class="btn primary grow" onClick=${onYes}>Sí, algo así</button>
        </div>
      </div>`}
    ${s.phase === 'reasons' && !s.leaving && html`
      <div class="reasons">
        <div class="reasons-title">${s.verdict === 'yes' ? '¿Qué pesó más?' : '¿Por qué no?'} <span>Toque una o varias</span></div>
        <div class="chips">
          ${list.map((r, ri) => {
            const on = s.picked.includes(ri);
            return html`<button type="button" class=${'chip' + (on ? ' on' : '')} aria-pressed=${on ? 'true' : 'false'} onClick=${() => onToggle(ri)}>${r.t}</button>`;
          })}
        </div>
        <div class="btn-row">
          <button type="button" class="btn ghost" onClick=${onBack}>Volver</button>
          <button type="button" class="btn dark grow" onClick=${onCommit}>${s.picked.length ? `Listo (${s.picked.length})` : 'Seguir sin razón'}</button>
        </div>
      </div>`}
  </article>`;
}

function CritRow({ c, must }) {
  return html`
  <div class=${'crit' + (c.hot ? ' hot' : '')}>
    <div class="crit-top"><span>${c.label}</span><span class="num">${c.w}</span></div>
    <div class="bar"><div class=${'fill' + (must ? ' must' : ' nice')} style=${{ width: c.w + '%' }}></div></div>
  </div>`;
}

function LivePanel({ p, brief, onConfirm, onDismiss }) {
  return html`
  <aside class="live" aria-label="Perfil en vivo">
    <div class="live-head">
      <div><div class="label">Perfil en vivo</div><div class="meter-label">${p.meterLabel}</div></div>
      <div class="pct">${p.pct}<span>%</span></div>
    </div>
    <div class="meter"><div class="meterfill" style=${{ width: p.pct + '%' }}></div></div>

    ${p.insightVisible && html`
      <div class="insight pulse">
        <div class="insight-body"><${Alert} /><div><strong>Notamos un patrón.</strong> ${brief.insight.text}</div></div>
        <div class="btn-row">
          <button type="button" class="btn primary grow small" onClick=${onConfirm}>Sí, es requisito</button>
          <button type="button" class="btn ghost grow small" onClick=${onDismiss}>No</button>
        </div>
      </div>`}

    <div class="group">
      <div class="group-title"><span class="sw must"></span>Imprescindible</div>
      ${p.musts.length === 0 && html`<div class="empty">Aún nada firme. El brief es vago.</div>`}
      ${p.criteria.filter((c) => c.isMust).map((c) => html`<${CritRow} key=${'m-' + c.id} c=${c} must=${true} />`)}
    </div>
    <div class="group">
      <div class="group-title"><span class="sw nice"></span>Deseable</div>
      ${p.criteria.filter((c) => c.isNice).map((c) => html`<${CritRow} key=${'n-' + c.id} c=${c} must=${false} />`)}
    </div>
    <div class="group">
      <div class="group-title"><span class="sw no"></span>Descarta</div>
      ${p.dbs.length === 0 && html`<div class="empty">Ningún descarte explícito todavía.</div>`}
      <div class="db-row">${p.dbs.map((b) => html`<span key=${b.id} class="db-pill">${b.label}</span>`)}</div>
    </div>
    <div class="trail">
      <div class="label">Rastro de decisiones</div>
      ${p.log.length === 0 && html`<div class="empty">Cada reacción queda registrada con su razón.</div>`}
      ${p.log.map((l, ix) => html`
        <div key=${ix} class="logrow"><span class=${'tag' + (l.yes ? ' yes' : ' no')}>${l.tag}</span><span>${l.text}</span></div>`)}
    </div>
  </aside>`;
}

function Kit({ kitRef, brief, p, channels, tab, copied, sent, onTab, onCopy }) {
  const active = channels.find((c) => c.id === tab);
  return html`
  <section class="kit" ref=${kitRef} aria-label="Perfil maestro y canales">
    <div class="kit-head">
      <div class="label light">${sent ? 'Lo que recibe el reclutador' : 'Su perfil calibrado'}</div>
      <h2>Un perfil maestro. Cada canal sale de él.</h2>
    </div>

    <article class="master" aria-label="Perfil maestro">
      <div class="master-top">
        <div class="master-id">
          <div class="master-badges"><span class="label">Perfil maestro · v1</span>${sent && html`<span class="approved">Aprobado por el cliente</span>`}</div>
          <h3>${brief.role}</h3>
          <div class="muted-p">${p.zone} · ${p.budget ? 'hasta ' + brief.meta.salaryCap : 'salario por confirmar'} · ${p.n} reacciones, ${p.reasonsN} razones</div>
        </div>
        <div class="master-pct"><div class="big">${p.pct}%</div><div class="small">claridad del perfil</div></div>
      </div>
      <div class="sentence">${p.sentence}</div>
      <div class="master-cols">
        <div class="master-crit">
          <div class="label">Criterios aprendidos y su evidencia</div>
          ${p.master.map((m) => html`
            <div key=${m.id} class="mrow">
              <div class="mrow-top"><span class="mrow-label">${m.label}</span>
                <span class=${'lvl ' + (m.isMust ? 'must' : m.w > 0 ? 'nice' : 'gone')}>${m.isMust ? 'Imprescindible' : m.w > 0 ? 'Deseable' : 'Descartado'}</span></div>
              <div class="bar"><div class=${'fill ' + (m.isMust ? 'must' : 'nice')} style=${{ width: m.w + '%' }}></div></div>
              <div class="mrow-ev">${m.ev}</div>
              ${m.changeNote && html`<div class="mrow-change">${m.changeNote}</div>`}
            </div>`)}
        </div>
        <div class="master-side">
          <div class="side-block">
            <div class="label">Descarta</div>
            ${p.dbs.length === 0 && html`<div class="empty">Ningún descarte explícito.</div>`}
            ${p.dbs.map((b) => html`<div key=${b.id} class="db-card"><span class="db-l">${b.label}</span><span class="db-e">${b.ev}</span></div>`)}
          </div>
          <div class="side-block">
            <div class="label">Se parece a</div>
            ${p.yesList.length === 0 && html`<div class="empty">El cliente no aceptó ningún ejemplo.</div>`}
            ${p.yesList.map((y) => html`<div key=${y.letter} class="ex"><span class="ex-l yes">${y.letter}</span><span>${y.text}</span></div>`)}
          </div>
          <div class="side-block">
            <div class="label">No se parece a</div>
            ${p.noList.map((y) => html`<div key=${y.letter} class="ex"><span class="ex-l">${y.letter}</span><span>${y.text}</span></div>`)}
          </div>
          <div class="side-block open">
            <div class="label">Por confirmar con el cliente</div>
            ${p.open.map((t) => html`<div class="open-q"><span class="qmark">?</span><span>${t}</span></div>`)}
          </div>
        </div>
      </div>
    </article>

    <div class="feed-wrap" aria-hidden="true"><div class="feed"></div>
      <div class="feed-label">alimenta ${channels.length} piezas, en 4 momentos de la búsqueda</div></div>

    <div class="channels">
      <nav class="chan-nav" aria-label="Canales">
        ${GROUPS.map((g) => html`
          <div class="chan-group">
            <div class="chan-group-title">${g}</div>
            ${channels.filter((c) => c.group === g).map((c) => html`
              <button type="button" class=${'chan' + (c.id === tab ? ' on' : '')} aria-pressed=${c.id === tab ? 'true' : 'false'} onClick=${() => onTab(c.id)}>${c.label}</button>`)}
          </div>`)}
      </nav>
      <div class="chan-panel-wrap">
        <div key=${active.id} class="panel">
          <div class="panel-top">
            <div><span class="derived">Derivado del perfil maestro</span><div class="panel-title">${active.title}</div></div>
            <button type="button" class=${'btn small ' + (copied === active.id ? 'ok' : 'primary')} onClick=${() => onCopy(active)}>${copied === active.id ? 'Copiado' : 'Copiar texto'}</button>
          </div>
          <div class=${'panel-body' + (active.mono ? ' mono' : '')}>${active.body}</div>
          <div class="muted-p small-p">${active.why}</div>
        </div>
      </div>
    </div>
  </section>`;
}

render(html`<${App} />`, document.getElementById('app'));
