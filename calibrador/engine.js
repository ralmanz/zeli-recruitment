// Pure logic: no DOM. Turns a brief + the client's reactions into
// (1) the live profile, (2) the master profile, (3) the channel pieces.
// The reaction log (state.decisions) is the single source of truth; everything else is derived.

export const CARD_COUNT = 6;

export function initialState() {
  return {
    i: 0,                 // index of the current example card
    phase: 'react',       // 'react' (sí/no buttons) | 'reasons' (chips)
    verdict: null,        // 'yes' | 'no' while choosing reasons
    picked: [],           // indexes of selected reason chips
    leaving: null,        // 'yes' | 'no' while the card animates out
    decisions: [],        // [{ i, v: 'yes'|'no', r: [reasonIndex] }]  <- source of truth
    confirmed: false,     // client confirmed the detected hidden constraint
    dismissed: false,     // client rejected it
    done: false,
    sending: false,
    sent: false,
    tab: null,            // active channel id
    copied: null          // channel id just copied
  };
}

const clamp = (x) => Math.max(0, Math.min(100, x));
const bul = (arr, f) => arr.map((x) => '• ' + f(x)).join('\n');
// Lowercase only the first letter, and keep acronyms / proper nouns intact (NIIF, React, Costa del Este...).
const KEEP = ['React', 'TypeScript', 'SAP', 'Costa', 'Colón', 'GitHub', 'Meta', 'Google'];
export const lc = (t) => {
  if (!t) return t;
  const first = t.split(/[\s/]/)[0];
  if (KEEP.includes(first) || (first.length > 1 && first === first.toUpperCase() && /[A-ZÁÉÍÓÚ]/.test(first))) return t;
  return t.charAt(0).toLowerCase() + t.slice(1);
};

export function computeProfile(brief, s) {
  const W = {}, ev = {}, dbEv = {}, counters = {}, counterCards = {}, flags = {}, touched = {};
  brief.crit.forEach((c) => { W[c.id] = c.base; ev[c.id] = []; });
  let reasonsN = 0;
  const log = [], yesList = [], noList = [];

  s.decisions.forEach((d, di) => {
    const card = brief.cards[d.i];
    const isLast = di === s.decisions.length - 1;
    const vword = d.v === 'yes' ? 'Sí' : 'No';
    // Accepting a profile mildly reinforces the lead criterion and experience.
    if (d.v === 'yes') {
      const lead = brief.crit.find((c) => c.lead);
      if (lead) { W[lead.id] += 5; if (isLast) touched[lead.id] = 1; }
      if (W.exp !== undefined) { W.exp += 5; if (isLast) touched.exp = 1; }
    }
    const names = [];
    d.r.forEach((ri) => {
      const r = (d.v === 'yes' ? card.yes : card.no)[ri];
      names.push(r.t); reasonsN++;
      const line = `${vword} a ${card.letter}: “${lc(r.t)}”`;
      Object.keys(r.fx).forEach((k) => {
        if (k.startsWith('n_')) {
          counters[k] = (counters[k] || 0) + r.fx[k];
          (counterCards[k] = counterCards[k] || []).push(card.letter);
        } else if (k.startsWith('db_')) {
          flags[k] = 1; dbEv[k] = line;
        } else if (W[k] !== undefined) {
          W[k] += r.fx[k]; ev[k].push(line); if (isLast) touched[k] = 1;
        }
      });
    });
    const desc = `${card.title}, ${card.company}`;
    if (d.v === 'yes') yesList.push({ letter: card.letter, text: desc + (names.length ? '. Pesó: ' + names.map(lc).join(', ') : '') });
    else noList.push({ letter: card.letter, text: desc + '. ' + (names.length ? names[0] : 'Sin razón dada') });
    log.push({ tag: `${card.letter} · ${vword}`, yes: d.v === 'yes', text: names.length ? names.join(', ') : 'sin razón' });
  });

  const ins = brief.insight;
  if (s.confirmed && ins) {
    W[ins.confirm.crit] = Math.max(W[ins.confirm.crit], ins.confirm.min);
    flags[ins.confirm.db] = 1;
    dbEv[ins.confirm.db] = `Patrón: descartó ${(counterCards[ins.counter] || []).join(' y ')} por ${ins.why}. El cliente lo confirmó.`;
  }

  const level = (id) => { const w = clamp(W[id] ?? 0); return w >= 60 ? 2 : (w > 0 ? 1 : 0); };
  const musts = [], nices = [], criteria = [];
  brief.crit.forEach((c) => {
    const w = clamp(W[c.id]);
    const conf = s.confirmed && ins && ins.confirm.crit === c.id;
    const item = {
      id: c.id, w, tag: c.tag, q: c.q, src: c.src, fromBrief: !!c.fromBrief, lead: !!c.lead, bool: c.bool,
      label: conf && c.confirmedLabel ? c.confirmedLabel : c.label,
      post: conf && c.confirmedPost ? c.confirmedPost : c.post,
      form: conf && c.confirmedForm ? c.confirmedForm : c.form,
      isMust: w >= 60, isNice: w > 0 && w < 60, hot: !!touched[c.id], ev: ev[c.id]
    };
    criteria.push(item);
    if (item.isMust) musts.push(item); else if (item.isNice) nices.push(item);
  });
  musts.sort((a, b) => b.w - a.w);
  nices.sort((a, b) => b.w - a.w);
  const dbs = brief.db.filter((b) => flags[b.id]).map((b) => ({ ...b, ev: dbEv[b.id] || '' }));
  const n = s.decisions.length;
  const pct = Math.min(97, 18 + 11 * n + 2 * reasonsN + (s.confirmed ? 8 : 0));

  const insightVisible = !!ins && (counters[ins.counter] || 0) >= ins.threshold && !s.confirmed && !s.dismissed;

  const open = (brief.open || []).filter((o) => {
    if (o.unlessFlag && flags[o.unlessFlag]) return false;
    if (o.unlessConfirmed && s.confirmed) return false;
    if (o.ifLevel && level(o.ifLevel[0]) !== o.ifLevel[1]) return false;
    return true;
  }).slice(0, 4).map((o) => o.t);

  const mustShort = musts.filter((m) => !m.lead).map((m) => lc(m.label));
  const sentence = brief.meta.summaryLead + '.' +
    (mustShort.length ? ' Imprescindible: ' + mustShort.join(', ') + '.' : '') +
    (nices.length ? ' Suma: ' + nices.map((x) => lc(x.label)).join(', ') + '.' : '') +
    (dbs.length ? ' No aplica: ' + dbs.map((b) => lc(b.ko)).join('; ') + '.' : '');

  const zone = s.confirmed && brief.meta.zoneConfirmed ? brief.meta.zoneConfirmed : brief.meta.zone;
  const budget = !!flags.db_budget;

  // Master-profile rows: each criterion with its evidence and whether reactions contradicted the brief.
  const master = musts.concat(nices).map((m) => {
    let changeNote = '';
    if (m.fromBrief && !m.isMust) changeNote = 'El brief lo pedía; las reacciones lo dejaron como deseable.';
    return {
      id: m.id, label: m.label, w: m.w, isMust: m.isMust,
      ev: m.ev.length ? m.ev.slice(-3).join(' · ') : (m.src || 'Sin reacciones que lo toquen.'),
      changeNote
    };
  });
  // Criteria the brief asked for that the reactions removed entirely.
  criteria.filter((c) => c.fromBrief && c.w === 0).forEach((c) => {
    master.push({ id: c.id, label: c.label, w: 0, isMust: false, ev: c.ev.slice(-3).join(' · '), changeNote: 'El brief lo pedía; las reacciones lo descartaron.' });
  });

  return {
    W, flags, level, criteria, musts, nices, dbs, n, reasonsN, pct, log, yesList, noList,
    insightVisible, open, sentence, mustShort, zone, budget, master,
    meterLabel: pct < 40 ? 'Brief vago' : (pct < 75 ? 'Tomando forma' : 'Listo para buscar'),
    summary: brief.role + '.' + (mustShort.length ? ' Imprescindible: ' + mustShort.join(' · ') + '.' : '') +
      (dbs.length ? ' Descarta: ' + dbs.map((b) => lc(b.label)).join(' · ') + '.' : '')
  };
}

// Channel definitions shared by every brief. Grouped by the moment of the search.
const BASE_CHANNELS = [
  { id: 'ats', group: 'Publicar', label: 'Vacante en el ATS', title: 'Vacante para Zoho Recruit u otro ATS',
    why: 'Los campos que pide una vacante en el ATS: descripción, requisitos, etiquetas y preguntas de preselección. Las preguntas de descarte salen de los “no” del cliente.' },
  { id: 'bolsa', group: 'Publicar', label: 'Bolsas de empleo', title: 'Anuncio para Konzerta y Computrabajo',
    why: 'Requisitos y deseables en el orden que el cliente les dio, sin la frase genérica “experiencia comprobable”.' },
  { id: 'lipost', group: 'Publicar', label: 'Post en LinkedIn', title: 'Publicación en LinkedIn para alcance',
    why: 'Para que la vacante circule en su red. Corta, con lo imprescindible, y pide referidos.' },
  { id: 'boolean', group: 'Buscar', label: 'Búsqueda LinkedIn', title: 'Búsqueda booleana y filtros de LinkedIn', mono: true,
    why: 'Cada término sale de lo que el cliente aceptó o descartó, con lo que falta preguntar.' },
  { id: 'github', group: 'Buscar', label: 'GitHub', title: 'Búsqueda de perfiles en GitHub', mono: true, onlyIf: 'github',
    why: 'Para roles técnicos: encuentra a quien muestra su trabajo, no solo su CV.' },
  { id: 'pool', group: 'Buscar', label: 'Su base de candidatos', title: 'Búsqueda en su base (ATS o pool interno)',
    why: 'Antes de salir a buscar: etiquetas para filtrar su base, y los ejemplos que el cliente aceptó como referencia.' },
  { id: 'inmail', group: 'Contactar', label: 'Mensaje al candidato', title: 'Mensaje directo al candidato (InMail o correo)',
    why: 'Para candidatos pasivos. Menciona lo que el cliente más valora, para que el candidato se reconozca o se descarte solo.' },
  { id: 'wa', group: 'Contactar', label: 'WhatsApp a su red', title: 'Mensaje de WhatsApp para pedir referidos',
    why: 'Incluye qué no aplica, para que nadie refiera al perfil equivocado.' },
  { id: 'screen', group: 'Filtrar', label: 'Llamada de filtro', title: 'Guion de la primera llamada',
    why: 'Preguntas en orden de importancia y los descartes inmediatos. Cada uno nace de un “no” del cliente.' }
];
export const GROUPS = ['Publicar', 'Buscar', 'Contactar', 'Filtrar'];

export function buildChannels(brief, p, s) {
  const m = brief.meta;
  const { musts, nices, dbs, mustShort, zone, budget, level, sentence } = p;
  const ranked = musts.concat(nices);
  const cap = budget ? 'hasta ' + m.salaryCap : '[RANGO]';
  const B = {};

  let q = 0;
  B.ats = `Título: ${brief.role}` +
    `\nUbicación: ${zone}` +
    `\nTipo: Tiempo completo · [MODALIDAD POR CONFIRMAR]` +
    `\nSalario: ${cap}` +
    `\n\nDescripción\n${sentence}` +
    `\n\nRequisitos` + (musts.length ? '\n' + bul(musts, (x) => x.post) : '\n• [POR DEFINIR]') +
    (nices.length ? '\n\nDeseable\n' + bul(nices, (x) => x.post) : '') +
    `\n\nEtiquetas: ${ranked.map((x) => x.tag).join(', ')}` +
    `\n\nPreguntas de preselección (Sí/No)` +
    musts.filter((x) => x.form).map((x) => `\n${++q}. ${x.form}`).join('') +
    dbs.filter((b) => b.form).map((b) => `\n${++q}. ${b.form} (Sí descarta)`).join('');

  B.bolsa = `${brief.role} · ${zone}` +
    `\n\n${m.postIntro}` +
    `\n\nRequisitos` + (musts.length ? '\n' + bul(musts, (x) => x.post) : '\n• [POR DEFINIR]') +
    (nices.length ? '\n\nSuma puntos\n' + bul(nices, (x) => x.post) : '') +
    `\n\nSalario: ${budget ? cap + ', según experiencia' : '[RANGO]'}` +
    `\nPostulación: [ENLACE O CORREO]`;

  B.lipost = `Estoy buscando ${brief.roleArticle} para una empresa en ${zone}.` +
    (mustShort.length ? `\n\nLo que buscamos: ${mustShort.join(', ')}.` : '') +
    (nices.length ? `\nSuma: ${nices.map((x) => lc(x.label)).join(', ')}.` : '') +
    `\n\nSi es usted o conoce a alguien, escríbame por mensaje o deje un comentario.` +
    `\n\n${m.hashtags}`;

  const terms = [brief.boolean.titles, brief.boolean.base];
  musts.forEach((x) => { if (x.bool && !terms.includes(x.bool)) terms.push(x.bool); });
  const nots = dbs.filter((b) => b.not).map((b) => b.not);
  const boolStr = terms.join(' AND ') + (nots.length ? ' NOT ' + nots.join(' NOT ') : '');
  const ef = m.expFilter;
  B.boolean = boolStr +
    `\n\nFiltros` +
    `\n• Ubicación: ${s.confirmed && m.locFilter.confirmed ? m.locFilter.confirmed : m.locFilter.default}` +
    (ef ? `\n• Experiencia: ${level(ef.crit) === 2 ? ef.must : ef.else}` : '') +
    (budget ? `\n• Excluir: ${m.excludeIfBudget}` : '') +
    (nices.length ? `\n\nPalabras que suman: ${nices.map((x) => lc(x.tag)).join(' · ')}` : '') +
    (p.open.length ? `\n\nPor confirmar con el cliente: ${p.open[0]}` : '');

  if (brief.github) {
    const g = brief.github;
    const extra = Object.keys(g.extra || {}).filter((id) => level(id) >= 1).map((id) => g.extra[id]);
    B.github = [g.query].concat(extra).join(' ') +
      `\n\nRevise primero perfiles con actividad en el último año y repositorios propios, no solo forks.` +
      (musts.length ? `\nConfirme en el código: ${musts.map((x) => lc(x.label)).join(', ')}.` : '');
  }

  B.pool = `Filtrar por etiquetas\n` + bul(musts, (x) => x.tag + ' (obligatoria)') +
    (nices.length ? '\n' + bul(nices, (x) => x.tag + ' (suma)') : '') +
    (dbs.length ? '\n\nExcluir\n' + bul(dbs, (b) => b.label) : '') +
    (p.yesList.length ? '\n\nCandidatos de referencia (aceptados por el cliente)\n' + bul(p.yesList, (y) => y.letter + ': ' + y.text) : '') +
    `\n\nRevise primero a quienes postularon en los últimos 12 meses a puestos parecidos.`;

  B.inmail = `Hola, [Nombre]. Mucho gusto.` +
    `\n\nVi su experiencia en [EMPRESA ACTUAL] y creo que puede encajar en una búsqueda que llevo para una empresa en ${zone}. Buscan ${brief.roleArticle}` +
    (mustShort.length ? `; lo que más valoran es ${mustShort.slice(0, 3).join(', ')}` : '') + '.' +
    `\n\n¿Le interesaría conversar 10 minutos esta semana?`;

  B.wa = `Hola, ¿cómo está? Estoy buscando ${brief.roleArticle} para una empresa en ${zone}.` +
    (mustShort.length ? `\n\nLo clave: ${mustShort.join(', ')}.` : '') +
    (dbs.length ? `\nNo aplica si: ${dbs.map((b) => lc(b.ko)).join('; ')}.` : '') +
    `\n\n¿Conoce a alguien? Le agradezco mucho si me lo refiere.`;

  let k = 0;
  B.screen = `Preguntas, en orden` +
    (musts.length ? '\n' + musts.map((x) => `${++k}. ${x.q}`).join('\n') : '') +
    (nices.length ? '\n' + nices.slice(0, 2).map((x) => `${++k}. ${x.q} (suma)`).join('\n') : '') +
    `\n\nDescarte inmediato` +
    (dbs.length ? '\n' + bul(dbs, (b) => b.ko) : '\n• Ninguno definido por el cliente') +
    (budget ? '' : '\n\nPregunte la aspiración salarial: el cliente no fijó tope.');

  return BASE_CHANNELS
    .filter((c) => !c.onlyIf || brief[c.onlyIf])
    .map((c) => ({ ...c, body: B[c.id] }));
}
