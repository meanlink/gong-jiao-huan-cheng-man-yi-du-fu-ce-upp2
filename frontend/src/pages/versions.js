import {api, planPath} from '../api.js';
import {bindForm, dateLabel, esc, heading, notify, routeBadge, stageChip} from '../components.js';
import {state} from '../state.js';

function pathPanel(plan) {
  return ['baseline', 'trial'].map((wave, index) => `<div class="path-step ${wave}">
    <div class="map-point"></div><div class="path-copy"><span class="eyebrow">${index ? '改线后 · 复测' : '改线前 · 基线'}</span>
    <strong>${esc(plan[`${wave}_path`])}</strong></div>
    <span class="date-ticket">${dateLabel(plan[`${wave}_from`])} — ${dateLabel(plan[`${wave}_to`])}</span>
  </div>`).join('');
}

function draftForm(plan) {
  const field = (key, label, type = 'text') => `<label>${label}<input type="${type}" name="${key}" value="${esc(plan?.[key])}" required></label>`;
  return `<section class="panel"><div class="panel-head"><h2>${plan ? '修改版本草稿' : '新建版本草稿'}</h2>
    <button id="cancel-edit" type="button" class="quiet">返回</button></div>
    <form id="draft-form" class="edit-grid">
    ${plan ? '' : field('code', '版本编号（大写字母、数字、连字符）')}
    ${field('hub', '枢纽')}${field('feeder', '接驳线路')}${field('connection', '换乘线路')}
    <div class="fields-wide">${field('baseline_path', '改线前路径')}${field('trial_path', '改线后路径')}</div>
    ${field('baseline_from', '基线开始日', 'date')}${field('baseline_to', '基线结束日', 'date')}
    ${field('trial_from', '复测开始日', 'date')}${field('trial_to', '复测结束日', 'date')}
    <div class="fields-wide"><button class="primary" type="submit">保存草稿</button></div>
    </form></section>`;
}

export function versions(root, refresh) {
  const {plan, plans, user, editing} = state;
  const director = user.role === 'director';
  root.innerHTML = heading('线路版本', '换乘路径与调查窗口', '比对改线路径，确认两轮调查的采样日期。',
    director ? '<button id="new-plan" class="quiet">＋ 新建版本</button>' : '') + `
    <div class="split versions-grid"><div>
    ${editing ? draftForm(editing === 'edit' ? plan : null) : plan ? `<section class="panel route-sheet">
      <div class="panel-head"><div>${routeBadge(plan)}<h2>${esc(plan.hub)}</h2></div>${stageChip(plan.stage)}</div>
      <div class="route-paths">${pathPanel(plan)}</div>
      <div class="panel-foot"><span class="mono">${esc(plan.code)}</span>
      ${director && plan.stage === 'draft' ? '<div class="actions"><button id="edit-plan" class="quiet">修改草稿</button><button id="open-plan" class="primary">开启调查</button></div>' :
        '<p>问卷按乘车日归入对应波次，再按高峰和平峰分别比较。</p>'}</div>
      </section>` : '<div class="empty">创建线路版本后可录入基线和复测问卷。</div>'}</div>
    <aside class="panel"><div class="panel-head"><h2>版本台账</h2><span class="mono muted">${plans.length} 个版本</span></div>
    <div class="ledger">${plans.map(item => `<button type="button" data-version="${item.id}" aria-pressed="${item.id === plan?.id}">
     <span class="mono">${esc(item.code)}</span><strong>${esc(item.hub)}</strong>${stageChip(item.stage)}</button>`).join('')}</div>
    </aside></div>`;
  const changeEdit = value => { state.editing = value; versions(root, refresh); };
  root.querySelector('#new-plan')?.addEventListener('click', () => changeEdit('new'));
  root.querySelector('#edit-plan')?.addEventListener('click', () => changeEdit('edit'));
  root.querySelector('#cancel-edit')?.addEventListener('click', () => changeEdit(false));
  root.querySelectorAll('[data-version]').forEach(button => button.addEventListener('click', () => {
    location.hash = `#/versions/${button.dataset.version}`;
  }));
  root.querySelector('#open-plan')?.addEventListener('click', async event => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await api(planPath('/open'), 'POST');
      notify('调查已开启，版本路径与时间窗口已锁定。');
      await refresh();
    } catch (error) { notify(error.message, true); }
    finally { button.disabled = false; }
  });
  bindForm(root, '#draft-form', async data => {
    const saved = editing === 'edit' ? await api(planPath(), 'PUT', data) : await api('/plans', 'POST', data);
    state.editing = false;
    notify('版本草稿已保存。');
    const target = `#/versions/${saved.id}`;
    if (location.hash === target) await refresh();
    else location.hash = target;
  });
}
