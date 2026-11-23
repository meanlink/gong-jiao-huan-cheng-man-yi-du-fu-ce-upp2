import {api, planPath} from '../api.js';
import {bindForm, empty, esc, heading, notify} from '../components.js';
import {bands, cohorts, state} from '../state.js';

const outcomes = {clear: '正常通行', detour: '临时绕行', blocked: '无法通行'};
const optionTags = dictionary => Object.entries(dictionary).map(([value, label]) => `<option value="${value}">${label}</option>`).join('');

function intake() {
  return `<section class="panel"><div class="panel-head"><h2>登记实走</h2></div>
    <form id="walk-intake" class="vertical-form"><div class="module-fields">
      <label>调查波次<select name="cohort">${optionTags(cohorts)}</select></label>
      <label>巡检日期<input name="walk_day" type="date" required></label>
      <label>乘车时段<select name="time_band">${optionTags(bands)}</select></label>
      <label>通行情况<select name="outcome">${optionTags(outcomes)}</select></label>
      <label>步行分钟<input name="walk_minutes" type="number" min="1" max="90" required></label>
      <label>巡检凭证<input name="source_ref" required minlength="3" maxlength="120" placeholder="东连廊巡检_1113.csv"></label>
    </div><label>现场记录<textarea name="note" required minlength="4" maxlength="250" rows="2"></textarea></label>
    <button class="primary">保存实走记录</button></form></section>`;
}

function clearanceForm(issue, candidates) {
  const matches = candidates.filter(row => row.id > issue.id && row.outcome === 'clear'
    && row.cohort === issue.cohort && row.time_band === issue.time_band && row.walk_day >= issue.walk_day);
  if (!matches.length) return '<p class="issue-detail">需先登记同波次同时段的正常通行复查。</p>';
  return `<form class="vertical-form clearance-form" id="clearance-${issue.id}"><label>正常通行复查<select name="recheck_id">
    ${matches.map(row => `<option value="${row.id}">${esc(row.walk_day)} · ${esc(row.source_ref)}</option>`).join('')}
    </select></label><label>清除依据<input name="note" required minlength="6" maxlength="250"></label>
    <button class="primary">签署清除</button></form>`;
}

function logRow(row, all, canClear) {
  const cleared = all.find(item => item.id === row.cleared_by_walk_id);
  return `<li class="module-item" data-walk="${row.id}"><div class="panel-head"><div><h3>${esc(row.source_ref)}</h3>
    <small class="mono muted">${esc(row.walk_day)} · ${cohorts[row.cohort]} · ${bands[row.time_band]}</small></div>
    <span class="chip ${row.outcome === 'clear' || cleared ? 'decided' : 'queue'}">${outcomes[row.outcome]}${cleared ? ' · 已清除' : ''}</span></div>
    <p class="issue-detail">${esc(row.note)}${row.walk_minutes === null ? '' : ` · ${row.walk_minutes} 分钟`}</p>
    ${cleared ? `<p class="issue-detail proof">复查 ${esc(cleared.source_ref)} · ${esc(row.clearance_note)}<small class="subline">${esc(row.cleared_by)}</small></p>` : ''}
    ${canClear && row.outcome !== 'clear' && !cleared ? clearanceForm(row, all) : ''}</li>`;
}

export async function walks(root, refresh, current) {
  const result = await api(planPath('/walk-checks'));
  if (!current()) return;
  const {plan, user} = state;
  const editable = ['surveying', 'sealed'].includes(plan.stage);
  const targets = result.items.filter(row => row.outcome !== 'clear' && !row.cleared_by_walk_id);
  root.innerHTML = heading('线路现场', '站点换乘巡检', '在各调查波次实走换乘路径，记录耗时、需要绕行的位置和恢复通行的复查。') + `
    <div class="split module-grid"><div class="module-stack"><section class="panel"><div class="panel-head"><h2>分波次实走摘要</h2>
    <span class="chip ${result.unresolved_trial ? 'queue' : 'decided'}">${result.unresolved_trial} 处复测待清除</span></div>
    <div class="table-scroll"><table><thead><tr><th>波次</th><th>时段</th><th>巡检数</th><th>正常通行中位数</th></tr></thead><tbody>
    ${result.cells.map(row => `<tr><td>${cohorts[row.cohort]}</td><td>${bands[row.time_band]}</td><td>${row.checks}</td><td>${row.clear_median_minutes === null ? '—' : `${row.clear_median_minutes} 分钟`}</td></tr>`).join('')}
    </tbody></table></div><div class="panel-foot"><a href="#/decision/${plan.id}">查看运营签署单</a>${result.unresolved_trial ? '<span>清除复测障碍后，可签署采用改线。</span>' : ''}</div></section>
    ${editable && user.role === 'collector' ? intake() : ''}</div>
    <section class="panel"><div class="panel-head"><h2>实走与复查凭证</h2></div>
    ${result.items.length ? `<ul class="module-log">${result.items.map(row => logRow(row, result.items, editable && user.role === 'director')).join('')}</ul>`
      : empty(plan.stage === 'draft' ? '方案开启调查后，现场调查员可登记巡检。' : '暂无实走记录。')}
    </section></div>`;

  const form = root.querySelector('#walk-intake');
  if (form) {
    const sync = () => {
      const wave = form.elements.cohort.value;
      const day = form.elements.walk_day;
      day.min = plan[`${wave}_from`];
      day.max = plan[`${wave}_to`];
      const blocked = form.elements.outcome.value === 'blocked';
      form.elements.walk_minutes.disabled = blocked;
      form.elements.walk_minutes.required = !blocked;
    };
    form.addEventListener('change', sync);
    sync();
  }
  bindForm(root, '#walk-intake', async data => {
    if (data.walk_minutes !== undefined) data.walk_minutes = Number(data.walk_minutes);
    await api(planPath('/walk-checks'), 'POST', data);
    notify('已登记实走记录。');
    await refresh();
  });
  for (const issue of targets) {
    bindForm(root, `#clearance-${issue.id}`, async data => {
      data.recheck_id = Number(data.recheck_id);
      await api(planPath(`/walk-checks/${issue.id}/clearance`), 'POST', data);
      notify('妨碍通行的巡检记录已签署清除。');
      await refresh();
    });
  }
}
