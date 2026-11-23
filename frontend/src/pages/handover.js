import {api, planPath} from '../api.js';
import {bindForm, empty, esc, heading, notify} from '../components.js';
import {roleNames, state} from '../state.js';

const taskLabels = {stop_signage: '更换站牌与导向标识', dispatch_briefing: '同步调度与班前交接', accessibility_notice: '更新无障碍换乘告知'};

function taskCard(task, canEdit) {
  return `<li class="module-item" data-task="${task.kind}"><div class="panel-head"><div><h3>${taskLabels[task.kind]}</h3>
    <small class="muted">${roleNames[task.owner_role]}</small></div>
    <span class="chip ${task.evidence ? 'decided' : 'queue'}">${task.evidence ? '凭证已交' : '待交凭证'}</span></div>
    ${task.evidence ? `<p class="issue-detail proof">${esc(task.evidence)}<small class="subline">${esc(task.completed_by)}</small></p>` : ''}
    ${canEdit ? `<form id="task-${task.kind}" class="vertical-form"><label>验收凭证<input name="evidence" required minlength="4" maxlength="250"
    value="${esc(task.evidence)}" placeholder="例如：现场照片或班前交接表编号"></label><button class="quiet">保存凭证</button></form>` : ''}</li>`;
}

function launch(plan, conclusion, user) {
  if (conclusion?.status !== 'signed' || conclusion.decision !== 'adopt') {
    return `${empty('运营决策签署采用改线后，可建立交接单。')}<div class="panel-foot"><a href="#/decision/${plan.id}">查看运营决策</a></div>`;
  }
  if (user.role !== 'director') return empty('待运营主管创建交接单。');
  return `<form id="create-packet" class="vertical-form"><label>计划启用日<input name="effective_on" type="date" required></label>
    <button class="primary">建立交接单</button></form>`;
}

function information(packet, user, complete) {
  const released = packet.status === 'released';
  return `<dl class="packet-facts"><div><dt>采用路径</dt><dd>${esc(packet.trial_path)}</dd></div>
    <div><dt>计划启用日</dt><dd class="mono">${esc(packet.effective_on)}</dd></div>
    <div><dt>签署快照</dt><dd class="mono hash-line">${esc(packet.snapshot_hash)}</dd></div></dl>
    ${released ? `<div class="signed-sheet"><h2>交接单已发布</h2><p>${esc(packet.release_note)}</p><small>${esc(packet.released_by)}</small>
      <div class="actions"><button class="quiet" id="download-handover">下载交接单</button>
      <a href="#/support/${packet.plan_id}">打开乘客协助工作台</a></div></div>` :
      (user.role === 'director' ? `<form id="release-packet" class="vertical-form"><label>交接说明<textarea name="note" rows="2" minlength="8" maxlength="350" required></textarea></label>
      <button class="primary" ${complete ? '' : 'disabled'}>发布交接单</button></form>` : empty('交接凭证齐备后，由运营主管统一发布。'))}`;
}

function download(packet) {
  const blob = new Blob([JSON.stringify(packet, null, 2)], {type: 'application/json'});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${packet.code}-handover.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function handover(root, refresh, current) {
  const [packet, conclusion] = await Promise.all([api(planPath('/handover')), api(planPath('/conclusion'))]);
  if (!current()) return;
  const {plan, user} = state;
  const received = packet?.tasks.filter(task => task.evidence).length ?? 0;
  root.innerHTML = heading('运营交接', '改线交接与站务任务验收', '把采用路径、调度安排和站务凭证整理为同一份线路交接单。') + `
    <div class="split module-grid"><section class="panel"><div class="panel-head"><h2>${esc(plan.code)} 交接单</h2>
    ${packet ? `<span class="chip ${packet.status === 'released' ? 'decided' : 'queue'}">${packet.status === 'released' ? '已发布' : '准备中'}</span>` : ''}</div>
    ${packet ? information(packet, user, received === packet.tasks.length) : launch(plan, conclusion, user)}
    </section><section class="panel"><div class="panel-head"><h2>站务与调度验收</h2>${packet ? `<span class="mono">${received} / ${packet.tasks.length} 已交</span>` : ''}</div>
    ${packet ? `<ul class="module-log">${packet.tasks.map(task => taskCard(task, packet.status === 'preparing' && user.role === task.owner_role)).join('')}</ul>` : empty('建立交接单后逐项收集凭证。')}
    </section></div>`;
  bindForm(root, '#create-packet', async data => {
    await api(planPath('/handover'), 'POST', data);
    notify('已建立改线交接单。');
    await refresh();
  });
  for (const task of packet?.tasks || []) {
    bindForm(root, `#task-${task.kind}`, async data => {
      await api(planPath(`/handover/tasks/${task.kind}`), 'PUT', data);
      notify('已保存任务凭证。');
      await refresh();
    });
  }
  bindForm(root, '#release-packet', async data => {
    await api(planPath('/handover/release'), 'POST', data);
    notify('已发布改线交接单。');
    await refresh();
  });
  root.querySelector('#download-handover')?.addEventListener('click', () => download(packet));
}
