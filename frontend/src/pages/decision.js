import {api, planPath} from '../api.js';
import {bindForm, empty, esc, fmt, heading, notify, pValue} from '../components.js';
import {decisions, state} from '../state.js';

const auditLabels = {'plan.created':'建立路线版本', 'plan.revised':'修改版本草稿', 'plan.opened':'开启调查',
  'plan.seeded':'载入示例版本', 'survey.seeded':'载入示例问卷', 'sample.captured':'登记问卷',
  'sample.resolved':'处置清洗问卷', 'survey.sealed':'封存问卷快照', 'comparison.completed':'完成分层比较', 'decision.signed':'签署运营决策',
  'walk.recorded':'登记实走巡检', 'walk.cleared':'清除通行障碍', 'handover.opened':'建立改线交接单',
  'handover.proof_added':'提交交接凭证', 'handover.released':'发布改线交接单'};

function decisionForm(result) {
  return `<form id="sign-form" class="vertical-form"><fieldset><legend>签署结论</legend><div class="decision-options">
    ${Object.entries(decisions).map(([key, name]) => `<label><input name="decision" value="${key}" type="radio"
     ${key === 'adopt' && (!result.adopt_allowed || result.unresolved_trial_walks) ? 'disabled' : ''} required> ${name}</label>`).join('')}
    </div></fieldset><label>依据与下游安排<textarea name="note" required minlength="8" maxlength="350" rows="3"
      placeholder="例如：调度负责同步站位，站务在周末更新现场引导。"></textarea></label>
    <button type="submit" class="primary">签署运营决策</button></form>`;
}

function dossier(result) {
  return `<div class="dossier"><div><span>双侧 p 值</span><strong class="mono">${pValue(result.combined_p)}</strong></div>
    <div><span>分层效应量</span><strong class="mono">${fmt(result.stratified_effect, 3)}</strong></div>
    <div><span>采用条件</span><strong>${result.adopt_allowed ? '达标' : '未达标'}</strong></div></div>`;
}

export async function decision(root, refresh, current) {
  const canAudit = state.user.role !== 'collector';
  const [result, audit] = await Promise.all([api(planPath('/conclusion')), canAudit ? api(planPath('/audit')) : []]);
  if (!current()) return;
  const {plan, user} = state;
  root.innerHTML = heading('运营决策', '线路复测签署单', '留存采用、维持或另开复测的依据，供调度和站务交接。') + `
    <div class="split decision-grid"><section class="panel"><div class="panel-head"><div><span class="mono muted">${esc(plan.code)}</span>
    <h2>${esc(plan.hub)} · ${esc(plan.feeder)} ↔ ${esc(plan.connection)}</h2></div>
    ${result?.status === 'signed' ? '<span class="chip decided">已签署</span>' : ''}</div>
    ${result?.unresolved_trial_walks && result.status !== 'signed' ? `<p class="issue-detail proof">复测线路有 ${result.unresolved_trial_walks} 处待清除的通行障碍。<a href="#/walks/${plan.id}">核对站点巡检</a></p>` : ''}
    ${!result?.band_results ? empty('分层结果就绪后可签署。') : `${dossier(result)}
      ${result.status === 'signed' ? `<div class="signed-sheet"><span class="kicker">运营决定</span>
        <h2>${decisions[result.decision]}</h2><p>${esc(result.decision_note)}</p>
        <small class="mono">${esc(result.signed_by)} · ${esc(result.signed_at.slice(0, 10))}</small>
        <div class="actions"><button id="download" class="quiet">下载签署记录</button>
        ${result.decision === 'adopt' ? `<a href="#/handover/${plan.id}">进入改线交接</a>` : ''}</div></div>` :
        (user.role === 'director' ? decisionForm(result) : empty('分层报告已就绪，待运营主管签署。'))}`}
    </section>${canAudit ? `<aside class="panel"><div class="panel-head"><h2>操作留痕</h2></div>
       <ol class="audit-list">${audit.slice(0, 10).map(entry => `<li><strong>${esc(auditLabels[entry.event] || entry.event)}</strong>
        <small class="subline">${esc(entry.actor)}${entry.details.sample_ref ? ` · ${esc(entry.details.sample_ref)}` : ''}</small></li>`).join('')}</ol>
    </aside>` : ''}</div>`;
  bindForm(root, '#sign-form', async data => {
    await api(planPath('/conclusion/sign'), 'POST', data);
    notify('运营决策已签署。');
    await refresh();
  });
  root.querySelector('#download')?.addEventListener('click', () => {
    const blob = new Blob([JSON.stringify({plan, conclusion: result}, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${plan.code}-decision.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
}
