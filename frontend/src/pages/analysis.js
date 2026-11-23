import {api, planPath} from '../api.js';
import {coverageTable, empty, esc, fmt, heading, notify, pValue} from '../components.js';
import {bands, cohorts, state} from '../state.js';

function distribution(counts, total, wave) {
  return `<div class="distribution"><span>${cohorts[wave]}</span><div class="stacked-bar" aria-label="${cohorts[wave]} 1 到 5 分分布">
      ${counts.map((count, i) => count ? `<div class="score-${i + 1}" style="flex-grow:${count}" title="${i + 1} 分：${count} 份">
          ${count / total >= 0.12 ? i + 1 : '<span class="sr-only">' + (i + 1) + ' 分</span>'}</div>` : '').join('')}
      </div><span class="mono">n=${total}</span></div>`;
}

function results(result) {
  return `<section class="panel"><div class="panel-head"><h2>分层检验结果</h2><span class="mono muted">Mann–Whitney U</span></div>
   <div class="metric-strip"><div><span>总体双侧 p 值</span><strong>${pValue(result.combined_p)}</strong></div>
    <div><span>分层效应量</span><strong>${result.stratified_effect > 0 ? '+' : ''}${fmt(result.stratified_effect, 3)}</strong></div>
    <div><span>采用门槛</span><strong class="text-metric">${result.adopt_allowed ? '已满足' : '未满足'}</strong></div></div>
   ${result.band_results.map(band => `<article class="result-band"><div class="band-title"><h3>${bands[band.band]}</h3>
     <span>中位数 <b class="mono">${band.baseline_median} → ${band.trial_median}</b></span></div>
     ${distribution(band.baseline_scores, band.baseline, 'baseline')}
     ${distribution(band.trial_scores, band.trial, 'trial')}
     <div class="stat-line"><span>U <b>${fmt(band.u, 1)}</b></span><span>双侧 p <b>${pValue(band.p)}</b></span><span>效应量 <b>${fmt(band.effect, 3)}</b></span></div>
   </article>`).join('')}</section>`;
}

export async function analysis(root, refresh, current) {
  const [result, cells] = await Promise.all([api(planPath('/conclusion')), api(planPath('/coverage'))]);
  if (!current()) return;
  const queue = cells.totals.queue || 0;
  const cellsReady = cells.cells.every(row => row.baseline >= cells.minimum && row.trial >= cells.minimum);
  const problem = queue ? `还有 ${queue} 份问卷待清洗。` : cellsReady ? '四格样本均已达到最低要求。' : '至少有一格样本不足，需继续调查。';
  root.innerHTML = heading('分层比较', '改线前后满意度复测', '按高峰和平峰匹配调查口径，对比两波独立乘客的 1–5 分分布。') + `
    <div class="split analysis-grid"><div>
      ${result?.band_results ? results(result) : `<section class="panel"><div class="panel-head"><h2>封存前检查</h2></div>
      ${coverageTable(cells)}<div class="panel-foot"><p>${esc(problem)}</p>
      ${!result && state.plan.stage === 'surveying' && state.user.role === 'analyst' ?
        `<button id="seal" class="primary" ${queue || !cellsReady ? 'disabled' : ''}>封存并发起比较</button>` : ''}</div>
      ${result?.status === 'queued' ? '<div class="pending" role="status">问卷已封存，正在等待分析 worker 计算。</div>' : ''}
      </section>`}</div>
      <aside class="side-stack"><section class="panel guide"><div class="panel-head"><h2>读数口径</h2></div>
      <div class="guide-body"><dl><dt>为什么分层</dt><dd>分别比较高峰与平峰，降低两轮时段构成不同带来的偏差。</dd>
      <dt>如何解释效应量</dt><dd>正值表示改线后更常取得高分，负值表示改线前更常取得高分。</dd>
      <dt>采用规则</dt><dd>总体双侧 p ≤ 0.05，分层效应量 ≥ 0.15，且各层效应量均 &gt; −0.20。</dd></dl></div></section>
      ${result?.band_results ? `<section class="panel snapshot"><div class="panel-head"><h2>问卷快照</h2></div><p class="mono">${esc(result.snapshot_hash)}</p></section>` : ''}
      </aside></div>`;
  root.querySelector('#seal')?.addEventListener('click', async event => {
    const button = event.currentTarget;
    button.disabled = true;
    try { await api(planPath('/conclusion/seal'), 'POST'); notify('问卷已封存。'); await refresh(); }
    catch (error) { notify(error.message, true); }
    finally { button.disabled = false; }
  });
  if (result?.status === 'queued') setTimeout(() => { if (current()) refresh(true); }, 1200);
}

export function noPlan(root) {
  root.innerHTML = empty('请先在线路版本页选择要复测的方案。');
}
