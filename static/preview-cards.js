import { h, render } from './vendor/preact.module.js';
import { useState } from './vendor/hooks.module.js';
import htm from './vendor/htm.module.js';

const html = htm.bind(h);
const params = new URLSearchParams(location.search);
const SHOT = params.get('shot');

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

function Shot({ id }) {
  const parts = id.split('-');
  const letter = parts[0];
  const kind = parts[1] || 'react';
  const card = CARDS.find((c) => c.letter === letter) || CARDS[0];
  const i = CARDS.indexOf(card);
  const phase = kind === 'yes' || kind === 'no' ? kind : 'react';
  const [picked, setPicked] = useState(parts[2] === 'on' ? [0] : []);
  const toggle = (ri) => setPicked((x) => x.includes(ri) ? x.filter((r) => r !== ri) : [...x, ri]);
  return html`
    <div class="preview-page preview-phone shot">
      <div class="preview-block">
        <div class="deck-top">
          <div class="step">Ejemplo ${i + 1} de ${CARDS.length}</div>
          <${Dots} i=${i} />
        </div>
        <div style=${{ height: 12 }}></div>
        <${CardView} card=${card} phase=${phase} picked=${picked}
          onYes=${() => {}} onNo=${() => {}} onToggle=${toggle} onCommit=${() => {}} />
      </div>
    </div>`;
}

function Gallery() {
  const [i, setI] = useState(0);
  const [phase, setPhase] = useState('react');
  const [picked, setPicked] = useState([]);
  const card = CARDS[i];
  const go = (n) => { setI(n); setPhase('react'); setPicked([]); };
  const toggle = (ri) => setPicked((x) => x.includes(ri) ? x.filter((r) => r !== ri) : [...x, ri]);
  return html`
    <div class="page"><div class="preview-page preview-phone">
      <p class="preview-banner">Vista previa · el calibrador no cambió</p>
      <div class="deck-top">
        <div class="step">Ejemplo ${i + 1} de ${CARDS.length}</div>
        <${Dots} i=${i} />
      </div>
      <div style=${{ height: 12 }}></div>
      <${CardView} card=${card} phase=${phase} picked=${picked}
        onYes=${() => { setPhase('yes'); setPicked([]); }}
        onNo=${() => { setPhase('no'); setPicked([]); }}
        onToggle=${toggle}
        onCommit=${() => go(Math.min(CARDS.length - 1, i + 1))} />
      <div class="choose-foot" style=${{ marginTop: 16 }}>
        <button type="button" class="choose-skip" disabled=${i === 0} onClick=${() => go(i - 1)}>Anterior</button>
        <button type="button" class="choose-skip" disabled=${i === CARDS.length - 1} onClick=${() => go(i + 1)}>Otra carta</button>
      </div>
    </div></div>`;
}

render(html`${SHOT ? html`<${Shot} id=${SHOT} />` : html`<${Gallery} />`}`, document.getElementById('app'));
