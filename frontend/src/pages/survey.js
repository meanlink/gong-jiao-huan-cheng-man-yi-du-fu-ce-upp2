import {api, planPath} from '../api.js';
import {bindForm, coverageTable, empty, esc, heading, notify} from '../components.js';
import {bands, cohorts, dispositions, state} from '../state.js';

const options = (labels, first) => `<option value="">${first}</option>` +
  Object.entries(labels).map(([key, name]) => `<option value="${key}">${name}</option>`).join('');

function captureForm() {
  return `<section class="panel"><div class="panel-head"><h2>登记换乘问卷</h2></div>
    <form id="sample-form" class="vertical-form">
       <label>匿名乘客码<input name="passenger_code" placeholder="例如 CX-051" required minlength="4" maxlength="40" pattern="[A-Za-z0-9\\-]+"></label>
       <div class="form-pair"><label>调查波次<select name="cohort" required>${options(cohorts, '选择波次')}</select></label>
       <label>乘车日期<input name="trip_day" type="date" required></label></div>
       <label>乘车时段<select name="time_band">${options(bands, '原始问卷未填写')}</select></label>
       <fieldset><legend>换乘满意度</legend><div class="scores">${[1,2,3,4,5].map(score =>
          `<label><input name="rating" type="radio" value="${score}" required><span>${score}</span></label>`).join('')}</div>
       <div class="scale-labels"><span>很不满意</span><span>很满意</span></div></fieldset>
       <button class="primary" type="submit">登记问卷</button>
    </form></section>`;
}

function reason(sample) {
  const flags = [];
  if (sample.duplicate_of) flags.push('重复乘客');
  if (!sample.time_band) flags.push('缺少分层');
  return flags.join(' / ');
}

function sampleTable(items) {
  return `<div class="table-scroll"><table><thead><tr><th>样本号 / 乘车日</th><th>波次</th><th>时段</th><th>评分</th><th>处置</th></tr></thead>
    <tbody>${items.map(sample => `<tr><td><strong class="mono">${esc(sample.sample_ref)}</strong><small class="subline">${esc(sample.trip_day)}</small></td>
    <td>${cohorts[sample.cohort]}</td><td>${bands[sample.time_band] || '未填写'}</td>
    <td><span class="mono">${sample.rating}</span></td><td>${sample.disposition === 'queue' ? `<span class="warning-text">${reason(sample)}</span>` :
    `<span>${dispositions[sample.disposition]}</span>`}${sample.cleanup_note ? `<small class="subline">${esc(sample.cleanup_note)}</small>` : ''}</td></tr>`).join('')}
    </tbody></table></div>`;
}

function queueCards(items, canClean) {
  return `<div class="queue-items">${items.map(sample => `<article class="queue-item">
    <div class="queue-label"><div><strong class="mono">${esc(sample.sample_ref)}</strong><small class="subline">${cohorts[sample.cohort]} · ${esc(sample.trip_day)} · ${sample.rating} 分</small></div>
    <span class="chip queue">${reason(sample)}</span></div>
    ${sample.duplicate_of ? '<p>已记录该乘客首份问卷。后续问卷保留处置记录并剔除。</p>' : '<p>核对现场记录后补录时段，无法核实时留痕剔除。</p>'}
    ${canClean ? `<form data-clean="${sample.id}" class="clean-form">
      ${sample.duplicate_of ? '' : `<label>核实的时段<select name="time_band">${options(bands, '无法核实 · 剔除')}</select></label>`}
      <label>处理依据<input name="note" required minlength="4" maxlength="250" placeholder="记录核查来源或剔除原因"></label>
      <button type="submit" class="quiet">${sample.duplicate_of ? '留痕剔除' : '保存处置'}</button>
    </form>` : ''}</article>`).join('')}</div>`;
}

export async function survey(root, refresh, current) {
  const query = state.query === 'all' ? '' : `&state=${state.query}`;
  const [data, coverage] = await Promise.all([
    api(planPath(`/samples?offset=${state.offset}${query}`)), api(planPath('/coverage')),
  ]);
  if (!current()) return;
  const open = state.plan.stage === 'surveying';
  const pending = coverage.totals.queue || 0;
  const tabs = [['queue', `清洗队列（${pending}）`], ['all', '全部问卷']];
  root.innerHTML = heading('乘客调查', '换乘问卷与清洗队列', '一条乘客码在同一版本中只计一次。', '') + `
    <div class="split survey-grid"><section class="panel"><div class="panel-head"><h2>问卷记录</h2>
      <div class="tabs" aria-label="问卷筛选">${tabs.map(([key, title]) => `<button data-query="${key}" aria-pressed="${state.query === key}">${title}</button>`).join('')}</div></div>
      ${data.items.length ? (state.query === 'queue' ? queueCards(data.items, open && state.user.role === 'analyst') : sampleTable(data.items)) :
        empty(state.query === 'queue' ? '清洗队列为空。可到分层比较页查看样本覆盖。' : '还没有问卷记录。请在调查开启后用调查员账号录入。')}
      ${data.has_more || state.offset ? `<div class="pagination"><button id="prev" class="quiet" ${state.offset ? '' : 'disabled'}>上一页</button>
        <span class="mono">第 ${state.offset / 20 + 1} 页</span><button id="next" class="quiet" ${data.has_more ? '' : 'disabled'}>下一页</button></div>` : ''}
    </section><aside class="side-stack">
       ${state.user.role === 'collector' && open ? captureForm() : ''}
       <section class="panel"><div class="panel-head"><h2>有效样本</h2><strong class="mono">${coverage.totals.eligible || 0} 份</strong></div>
       ${coverageTable(coverage)}<div class="panel-foot"><p>同一波次、同一时段至少 ${coverage.minimum} 份有效问卷。</p></div></section>
    </aside></div>`;
  root.querySelectorAll('[data-query]').forEach(button => button.addEventListener('click', () => {
    state.query = button.dataset.query;
    state.offset = 0;
    refresh();
  }));
  root.querySelector('#prev')?.addEventListener('click', () => { state.offset -= 20; refresh(); });
  root.querySelector('#next')?.addEventListener('click', () => { state.offset += 20; refresh(); });
  bindForm(root, '#sample-form', async data => {
    data.rating = Number(data.rating);
    data.time_band ||= null;
    const result = await api(planPath('/samples'), 'POST', data);
    notify(result.disposition === 'queue' ? `${reason(result)}，问卷已进入清洗队列。` : '已登记有效问卷。');
    state.offset = 0;
    await refresh();
  });
  root.querySelectorAll('[data-clean]').forEach(form => bindForm(root, `[data-clean="${form.dataset.clean}"]`, async data => {
    data.time_band ||= null;
    const result = await api(planPath(`/samples/${form.dataset.clean}/cleanup`), 'POST', data);
    notify(result.disposition === 'eligible' ? '已补齐时段，问卷纳入分析。' : '问卷已留痕剔除。');
    state.offset = 0;
    await refresh();
  }));
}
