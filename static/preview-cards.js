import { h, render } from './vendor/preact.module.js';
import { useState } from './vendor/hooks.module.js';
import htm from './vendor/htm.module.js';

const html = htm.bind(h);
const params = new URLSearchParams(location.search);
const SHOT = params.get('shot'); // A | A-yes | A-no | B | ...

const CARDS = [
  {
    letter: 'A',
    title: 'Ejecutiva de ventas',
    company: 'tienda de electrónica',
    headline: 'Piso de venta · 2 años',
    note: 'Atiende el mostrador: celulares, accesorios, quien entra. Cierra y se acaba — no tiene clientes que le sigan ni CRM. Le ha pedido a su jefa pasar a cuentas; le dicen que aprende rápido.',
    facts: [
      ['Dónde vive', 'Bethania. A Costa del Este son unos 20 min.'],
      ['A quién le vende', 'Consumidor, en tienda. Sin cartera propia.'],
      ['Inglés', 'Básico: saluda y entiende precios, no una reunión.'],
      ['Aspiración', '$1,200']
    ],
    yes: ['Vive cerca', 'Puede aprender'],
    no: ['Muy junior', 'Solo ha vendido a consumidor', 'Inglés muy básico']
  },
  {
    letter: 'B',
    title: 'Representante de ventas',
    company: 'distribuidora de consumo masivo',
    headline: 'Cuentas de supermercado · 6 años',
    note: 'Vende a supermercados y minimarkets del interior. Trae relaciones con compradores de cadena, no con plantas. Buena trayectoria B2B, pero el producto es consumo, no industrial.',
    facts: [
      ['Dónde vive', 'David, Chiriquí. A Costa del Este son unas 6 horas.'],
      ['A quién le vende', 'Consumo masivo B2B. Cartera parcial.'],
      ['Inglés', 'Intermedio: se defiende por correo, se traba en una llamada.'],
      ['Aspiración', '$1,800']
    ],
    yes: ['Experiencia B2B', 'Buena trayectoria'],
    no: ['Vive fuera del área', 'Consumo masivo, no industrial', 'Inglés insuficiente']
  },
  {
    letter: 'C',
    title: 'Ejecutiva de cuentas clave',
    company: 'suministros industriales',
    headline: 'Cuentas industriales · 5 años',
    note: 'Maneja unas 40 cuentas de plantas y talleres que le siguen. Visita, habla de stock y plazos, y cierra en inglés con compradores de casa matriz. Vive a diez minutos de la oficina.',
    facts: [
      ['Dónde vive', 'Costa del Este. Unos 10 min a la oficina.'],
      ['A quién le vende', 'Industrial B2B. Cartera propia, unos 40 clientes.'],
      ['Inglés', 'Avanzado: llamadas con compradores.'],
      ['Aspiración', '$2,000']
    ],
    yes: ['Trae cartera propia', 'Conoce el sector industrial', 'Inglés avanzado', 'Vive cerca'],
    no: ['El inglés no hace falta', 'Demasiado senior']
  },
  {
    letter: 'D',
    title: 'Gerente regional de ventas',
    company: 'agroquímicos',
    headline: 'Gerencia regional · 9 años',
    note: 'Dirige un equipo y una zona. Ya no cierra cuenta por cuenta: arma plan, revisa números, viaja. De Arraiján a Costa del Este son 45–60 min. Pide $3,500.',
    facts: [
      ['Dónde vive', 'Arraiján, Panamá Oeste. 45–60 min a Costa del Este.'],
      ['A quién le vende', 'Agro B2B, a escala regional. Equipo a cargo.'],
      ['Inglés', 'Avanzado.'],
      ['Aspiración', '$3,500']
    ],
    yes: ['Liderazgo', 'Inglés avanzado'],
    no: ['Fuera de presupuesto', 'Vive fuera del área', 'Sobrecalificado']
  },
  {
    letter: 'E',
    title: 'Vendedor técnico',
    company: 'distribución ferretera',
    headline: 'Ruta ferretera · 4 años',
    note: 'Recorre ferreterías y constructoras chicas. Habla de calibre, marca y plazo, no de marca de consumo. Lleva el seguimiento en Salesforce, y tiene clientes que le recompran.',
    facts: [
      ['Dónde vive', 'San Francisco. A Costa del Este son unos 15 min.'],
      ['A quién le vende', 'Ferretería B2B, venta técnica. Clientes que le recompran.'],
      ['Inglés', 'Intermedio: se defiende, no cierra una negociación.'],
      ['Herramientas', 'Salesforce · aspiración $1,900']
    ],
    yes: ['Trae cartera propia', 'Domina un CRM', 'Venta técnica'],
    no: ['Poca experiencia', 'Inglés insuficiente']
  },
  {
    letter: 'F',
    title: 'Ejecutivo comercial',
    company: 'materiales de construcción',
    headline: 'Obra y ferretería · 7 años',
    note: 'Vende cemento, varilla y acabados a ferreterías y a obra. Conoce el sector. Los clientes son de la empresa: no trae una cartera que se mude con él.',
    facts: [
      ['Dónde vive', 'La Chorrera. 40–50 min a Costa del Este, más en hora pico.'],
      ['A quién le vende', 'Construcción B2B. Sin cartera propia.'],
      ['Inglés', 'Básico: lee una cotización, no una llamada.'],
      ['Aspiración', '$1,900']
    ],
    yes: ['Sector correcto', 'Experiencia sólida'],
    no: ['Vive fuera del área', 'Sin cartera propia', 'Inglés insuficiente']
  }
];

function Dots({ i }) {
  return html`<div class="dots">${CARDS.map((_, ix) => html`<span class=${'dot' + (ix === i ? ' cur' : ix < i ? ' past' : '')}></span>`)}</div>`;
}

function CardView({ card, i, phase, picked, onYes, onNo, onToggle, onBack }) {
  const list = phase === 'yes' ? card.yes : card.no;
  return html`
    <article class="card">
      <div class="card-head">
        <div class="avatar">${card.letter}</div>
        <div class="card-titles">
          <div class="card-title">${card.title}</div>
          <div class="card-sub">${card.company} · ${card.headline}</div>
        </div>
      </div>
      <p class="card-note">${card.note}</p>
      <dl class="fields rich">
        ${card.facts.map(([k, v]) => html`<div class="field"><dt>${k}</dt><dd>${v}</dd></div>`)}
      </dl>
      ${phase === 'react' && html`
        <div class="verdict">
          <div class="muted-p">¿Así es la persona que busca?</div>
          <div class="btn-row">
            <button type="button" class="btn ghost grow" onClick=${onNo}>No es este</button>
            <button type="button" class="btn primary grow" onClick=${onYes}>Sí, algo así</button>
          </div>
        </div>`}
      ${phase !== 'react' && html`
        <div class="reasons">
          <div class="reasons-title">${phase === 'yes' ? '¿Qué pesó más?' : '¿Por qué no?'} <span>Toque una o varias</span></div>
          <div class="chips">
            ${list.map((t, ri) => html`
              <button type="button" class=${'chip' + (picked.includes(ri) ? ' on' : '')} onClick=${() => onToggle(ri)}>${t}</button>`)}
          </div>
          <div class="btn-row">
            <button type="button" class="btn ghost" onClick=${onBack}>Volver</button>
            <button type="button" class="btn dark grow">${picked.length ? `Listo (${picked.length})` : 'Seguir sin razón'}</button>
          </div>
        </div>`}
    </article>`;
}

function Shot({ id }) {
  const [letter, kind] = id.includes('-') ? id.split('-') : [id, 'react'];
  const card = CARDS.find((c) => c.letter === letter) || CARDS[0];
  const i = CARDS.indexOf(card);
  const phase = kind === 'yes' || kind === 'no' ? kind : 'react';
  const [picked, setPicked] = useState([]);
  const toggle = (ri) => setPicked((x) => x.includes(ri) ? x.filter((r) => r !== ri) : [...x, ri]);
  return html`
    <div class="preview-page preview-phone shot">
      <div class="preview-block">
        <div class="deck-top">
          <div class="step">Ejemplo ${i + 1} de ${CARDS.length}</div>
          <${Dots} i=${i} />
        </div>
        <div style=${{ height: 12 }}></div>
        <${CardView} card=${card} i=${i} phase=${phase} picked=${picked}
          onYes=${() => {}} onNo=${() => {}} onToggle=${toggle} onBack=${() => {}} />
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
      <${CardView} card=${card} i=${i} phase=${phase} picked=${picked}
        onYes=${() => { setPhase('yes'); setPicked([]); }}
        onNo=${() => { setPhase('no'); setPicked([]); }}
        onToggle=${toggle}
        onBack=${() => { setPhase('react'); setPicked([]); }} />
      <div class="btn-row" style=${{ marginTop: 14 }}>
        <button type="button" class="btn ghost grow" disabled=${i === 0} onClick=${() => go(i - 1)}>Anterior</button>
        <button type="button" class="btn ghost grow" disabled=${i === CARDS.length - 1} onClick=${() => go(i + 1)}>Siguiente</button>
      </div>
    </div></div>`;
}

render(html`${SHOT ? html`<${Shot} id=${SHOT} />` : html`<${Gallery} />`}`, document.getElementById('app'));
