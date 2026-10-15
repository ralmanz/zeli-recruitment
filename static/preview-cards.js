import { h, render } from './vendor/preact.module.js';
import { useState, useEffect, useRef } from './vendor/hooks.module.js';
import htm from './vendor/htm.module.js';

const html = htm.bind(h);
const params = new URLSearchParams(location.search);
const SHOT = params.get('shot');
const DEMO = params.get('demo') === '1';

const CARDS = [
  {
    letter: 'A',
    title: 'Ejecutiva de ventas',
    company: 'Tienda de electrónica',
    tenure: '2 años',
    bullets: [
      'Venta en piso a consumidor (celulares y accesorios)',
      'Sin cartera propia',
      'Sin CRM',
      'Busca pasar a cuentas'
    ],
    facts: [
      ['Ubicación', 'Bethania, Ciudad de Panamá', '20 min a Costa del Este'],
      ['Idiomas', 'Inglés · Básico'],
      ['Aspiración', '$1,200']
    ],
    yes: ['Vive cerca', 'Puede aprender'],
    no: ['Muy junior', 'Solo ha vendido a consumidor', 'Inglés muy básico']
  },
  {
    letter: 'B',
    title: 'Representante de ventas',
    company: 'Distribuidora de consumo masivo',
    tenure: '6 años',
    bullets: [
      'Venta B2B a supermercados y minimarkets',
      'Cartera parcial de compradores de cadena',
      'Consumo masivo, no industrial'
    ],
    facts: [
      ['Ubicación', 'David, Chiriquí', '6 horas a Costa del Este'],
      ['Idiomas', 'Inglés · Intermedio'],
      ['Aspiración', '$1,800']
    ],
    yes: ['Experiencia B2B', 'Buena trayectoria'],
    no: ['Vive fuera del área', 'Consumo masivo, no industrial', 'Inglés insuficiente']
  },
  {
    letter: 'C',
    title: 'Ejecutiva de cuentas clave',
    company: 'Suministros industriales',
    tenure: '5 años',
    bullets: [
      'Cartera propia, unos 40 clientes',
      'Venta industrial B2B (plantas y talleres)',
      'Visitas de stock y plazos'
    ],
    facts: [
      ['Ubicación', 'Costa del Este', '10 min a la oficina'],
      ['Idiomas', 'Inglés · Avanzado'],
      ['Aspiración', '$2,000']
    ],
    yes: ['Trae cartera propia', 'Conoce el sector industrial', 'Inglés avanzado', 'Vive cerca'],
    no: ['El inglés no hace falta', 'Demasiado senior']
  },
  {
    letter: 'D',
    title: 'Gerente regional de ventas',
    company: 'Agroquímicos',
    tenure: '9 años',
    bullets: [
      'Equipo y zona a cargo',
      'Plan comercial y viajes (no cierre de cuenta)',
      'Agro B2B'
    ],
    facts: [
      ['Ubicación', 'Arraiján, Panamá Oeste', '45–60 min a Costa del Este'],
      ['Idiomas', 'Inglés · Avanzado'],
      ['Aspiración', '$3,500']
    ],
    yes: ['Liderazgo', 'Inglés avanzado'],
    no: ['Fuera de presupuesto', 'Vive fuera del área', 'Sobrecalificado']
  },
  {
    letter: 'E',
    title: 'Vendedor técnico',
    company: 'Distribución ferretera',
    tenure: '4 años',
    bullets: [
      'Venta técnica a ferreterías y constructoras',
      'Clientes que recompran',
      'Salesforce'
    ],
    facts: [
      ['Ubicación', 'San Francisco', '15 min a Costa del Este'],
      ['Idiomas', 'Inglés · Intermedio'],
      ['Aspiración', '$1,900']
    ],
    yes: ['Trae cartera propia', 'Domina un CRM', 'Venta técnica'],
    no: ['Poca experiencia', 'Inglés insuficiente']
  },
  {
    letter: 'F',
    title: 'Ejecutivo comercial',
    company: 'Materiales de construcción',
    tenure: '7 años',
    bullets: [
      'Venta B2B a ferreterías y obra',
      'Cemento, varilla y acabados',
      'Sin cartera propia (clientes de la empresa)'
    ],
    facts: [
      ['Ubicación', 'La Chorrera', '40–50 min a Costa del Este'],
      ['Idiomas', 'Inglés · Básico'],
      ['Aspiración', '$1,900']
    ],
    yes: ['Sector correcto', 'Experiencia sólida'],
    no: ['Vive fuera del área', 'Sin cartera propia', 'Inglés insuficiente']
  }
];

function Dots({ i }) {
  return html`<div class="dots">${CARDS.map((_, ix) => html`<span class=${'dot' + (ix === i ? ' cur' : ix < i ? ' past' : '')}></span>`)}</div>`;
}

function CardView({ card, phase, picked, onYes, onNo, onToggle, onCommit }) {
  const chosen = phase === 'yes' || phase === 'no';
  const list = phase === 'yes' ? card.yes : card.no;
  return html`
    <article class="card">
      <div class="card-head">
        <div class="avatar">${card.letter}</div>
        <div class="card-titles">
          <div class="card-title">${card.title}</div>
          <div class="card-sub">${card.company} · ${card.tenure}</div>
        </div>
      </div>
      <div class="job">
        <div class="job-label">Experiencia</div>
        <ul class="job-bullets">
          ${card.bullets.map((b) => html`<li>${b}</li>`)}
        </ul>
      </div>
      <dl class="fields rich">
        ${card.facts.map(([k, v, extra]) => html`
          <div class="field">
            <dt>${k}</dt>
            <dd>${v}</dd>
            ${extra && html`<dd class="field-extra">${extra}</dd>`}
          </div>`)}
      </dl>
      <div class="choose">
        <p class="choose-q">¿Se ajusta a lo que busca?</p>
        <div class="choose-row">
          <button type="button" class=${'choose-btn no' + (phase === 'no' ? ' on' : '')} onClick=${onNo}>No</button>
          <button type="button" class=${'choose-btn yes' + (phase === 'yes' ? ' on' : '')} onClick=${onYes}>Sí</button>
        </div>
        ${chosen && html`
          <p class="choose-q">${phase === 'yes' ? '¿Qué se ajusta?' : '¿Qué no se ajusta?'}</p>
          <div class="choose-chips">
            ${list.map((t, ri) => html`
              <button type="button" class=${'choose-chip' + (picked.includes(ri) ? ' on' : '')} onClick=${() => onToggle(ri)}>${t}</button>`)}
          </div>
          <div class="choose-foot">
            <button type="button" class="choose-skip" onClick=${onCommit}>Omitir</button>
            <button type="button" class="choose-go" onClick=${onCommit}>Siguiente</button>
          </div>`}
      </div>
    </article>`;
}

function Carousel({ leaving, snap, peekH, children, next }) {
  const currentRef = useRef(null);
  const [h, setH] = useState(0);
  useEffect(() => {
    const el = currentRef.current;
    if (!el) return;
    const nextH = el.offsetHeight;
    if (nextH && nextH !== h) setH(nextH);
  });
  const peek = next ? peekH : 0;
  const shift = leaving && next && h ? -(h + 10) : 0;
  return html`
    <div class="carousel">
      <div class="carousel-viewport" style=${{ height: h ? (h + (peek ? peek + 10 : 0)) + 'px' : 'auto' }}>
        <div class=${'carousel-track' + (snap ? ' snap' : '')} style=${{ transform: 'translateY(' + shift + 'px)' }}>
          <div ref=${currentRef}>${children}</div>
          ${next && html`
            <div class="peek">
              <${CardView} card=${next} phase="react" picked=${[]}
                onYes=${() => {}} onNo=${() => {}} onToggle=${() => {}} onCommit=${() => {}} />
            </div>`}
        </div>
      </div>
      ${next && !leaving && html`<div class="peek-fade"></div>`}
    </div>`;
}

function Shot({ id }) {
  const parts = id.split('-');
  const letter = parts[0];
  const kind = parts[1] || 'react';
  const card = CARDS.find((c) => c.letter === letter) || CARDS[0];
  const i = CARDS.indexOf(card);
  const phase = kind === 'yes' || kind === 'no' ? kind : 'react';
  const [picked, setPicked] = useState(parts[2] === 'on' ? [0] : []);
  const toggle = (ri) => setPicked((x) => x.includes(ri) ? x.filter((r) => r !== ri) : [...x, ri]);
  const leaving = kind === 'up';
  const next = CARDS[i + 1];
  return html`
    <div class="preview-page preview-phone shot">
      <div class="preview-block">
        <div class="deck-top">
          <div class="step">Ejemplo ${i + 1} de ${CARDS.length}</div>
          <${Dots} i=${i} />
        </div>
        <div style=${{ height: 12 }}></div>
        <${Carousel} leaving=${leaving} snap=${false} peekH=${64} next=${next}>
          <${CardView} card=${card} phase=${leaving ? 'yes' : phase} picked=${leaving ? [0] : picked}
            onYes=${() => {}} onNo=${() => {}} onToggle=${toggle} onCommit=${() => {}} />
        </${Carousel}>
      </div>
    </div>`;
}

function Gallery() {
  const [i, setI] = useState(0);
  const [phase, setPhase] = useState('react');
  const [picked, setPicked] = useState([]);
  const [leaving, setLeaving] = useState(false);
  const [snap, setSnap] = useState(false);
  const card = CARDS[i];
  const next = CARDS[i + 1];
  const toggle = (ri) => setPicked((x) => x.includes(ri) ? x.filter((r) => r !== ri) : [...x, ri]);
  const commit = () => {
    if (leaving || !next) return;
    setLeaving(true);
  };
  useEffect(() => {
    if (!DEMO || i !== 0) return;
    const t1 = setTimeout(() => setPhase('yes'), 700);
    const t2 = setTimeout(() => setPicked([0]), 1300);
    const t3 = setTimeout(() => setLeaving(true), 1900);
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); };
  }, [i]);
  useEffect(() => {
    if (!leaving) return;
    const t = setTimeout(() => {
      setSnap(true);
      setI((n) => n + 1);
      setPhase('react');
      setPicked([]);
      setLeaving(false);
      requestAnimationFrame(() => requestAnimationFrame(() => setSnap(false)));
    }, 460);
    return () => clearTimeout(t);
  }, [leaving]);
  return html`
    <div class="page"><div class="preview-page preview-phone">
      <p class="preview-banner">Vista previa · el calibrador no cambió</p>
      <div class="deck-top">
        <div class="step">Ejemplo ${i + 1} de ${CARDS.length}</div>
        <${Dots} i=${i} />
      </div>
      <div style=${{ height: 12 }}></div>
      <${Carousel} leaving=${leaving} snap=${snap} peekH=${64} next=${next}>
        <${CardView} card=${card} phase=${phase} picked=${picked}
          onYes=${() => { setPhase('yes'); setPicked([]); }}
          onNo=${() => { setPhase('no'); setPicked([]); }}
          onToggle=${toggle}
          onCommit=${commit} />
      </${Carousel}>
    </div></div>`;
}

render(html`${SHOT ? html`<${Shot} id=${SHOT} />` : html`<${Gallery} />`}`, document.getElementById('app'));
