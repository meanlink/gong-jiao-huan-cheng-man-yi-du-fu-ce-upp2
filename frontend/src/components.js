import {bands, stages} from './state.js';

export const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
})[char]);
export const fmt = (value, digits = 2) => value === null || value === undefined ? '—' : Number(value).toFixed(digits);
export const pValue = value => value < 0.0001 ? '&lt;0.0001' : fmt(value, 4);

export function dateLabel(value) {
  return esc(value?.slice(5).replace('-', '.'));
}

export function stageChip(stage) {
  return `<span class="chip ${esc(stage)}">${esc(stages[stage])}</span>`;
}

export function routeBadge(plan) {
  return `<span class="route-badge"><span>${esc(plan.feeder)}</span><i>↔</i><span>${esc(plan.connection)}</span></span>`;
}

export function heading(kicker, title, description, action = '') {
  return `<div class="heading"><div><div class="kicker">${esc(kicker)}</div><h1>${esc(title)}</h1>
    <p>${esc(description)}</p></div>${action}</div>`;
}

export function empty(text) {
  return `<div class="empty">${esc(text)}</div>`;
}

export function coverageTable(data) {
  const count = value => `<span class="cell-count ${value >= data.minimum ? 'met' : ''}">${value}<small> / ${data.minimum}</small></span>`;
  return `<table><thead><tr><th>乘车时段</th><th>改线前</th><th>改线后</th></tr></thead><tbody>
     ${data.cells.map(row => `<tr><th>${bands[row.band]}</th><td>${count(row.baseline)}</td><td>${count(row.trial)}</td></tr>`).join('')}
     </tbody></table>`;
}

export function bindForm(root, selector, handler) {
  const form = root.querySelector(selector);
  if (!form) return;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = event.submitter;
    button.disabled = true;
    try {
      await handler(Object.fromEntries(new FormData(form)), button);
    } catch (error) {
      notify(error.message, true);
    } finally {
      button.disabled = false;
    }
  });
}

let timer;
export function notify(message, error = false) {
  const box = document.querySelector('#notice');
  box.textContent = message;
  box.classList.toggle('error', error);
  box.hidden = false;
  clearTimeout(timer);
  timer = setTimeout(() => { box.hidden = true; }, error ? 7200 : 3800);
}
