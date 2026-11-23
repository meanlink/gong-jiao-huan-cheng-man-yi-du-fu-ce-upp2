import {api, planPath} from '../api.js';
import {bindForm, empty, esc, notify} from '../components.js';
import {bands, cohorts} from '../state.js';

const outcomes = {first: '首份计入', superseded: '被替下留档', duplicate: '重复留档剔除'};
const statuses = {staging: '补传中', merged: '已合并', cancelled: '已取消'};
const time = new Intl.DateTimeFormat('zh-CN', {timeZone: 'Asia/Shanghai', dateStyle: 'short', timeStyle: 'short'});
export const clock = value => value ? time.format(new Date(value)) : '—';

function startForm() {
  return `<form id="batch-start" class="vertical-form">
    <div class="form-pair"><label>批次号<input name="batch_ref" required minlength="3" maxlength="60"
      placeholder="例如 OFFLINE-1113-A"></label>
    <label>应到份数（可选）<input name="expected_items" type="number" min="1" max="500"></label></div>
    <button class="primary">开始 / 续传批次</button></form>`;
}

function uploadForm(batch) {
  return `<form id="upload-${batch.id}" class="vertical-form">
    <label>离线问卷（JSON 数组）<textarea name="payload" rows="7" required
      placeholder='[{"offline_ref":"P-001","passenger_code":"CX-NEW-011","cohort":"trial","trip_day":"2026-11-13","filled_at":"2026-11-13T08:45:00+08:00","time_band":"peak","rating":4}]'></textarea></label>
    <button class="primary">上传本批问卷</button></form>`;
}

function progress(batch) {
  const expected = batch.expected_items;
  return `<span class="mono">${batch.received_items}${expected ? ` / ${expected}` : ''} 份已收</span>`;
}

function itemRows(items) {
  return `<div class="table-scroll"><table><thead><tr><th>离线编号</th><th>填写时间</th><th>波次 / 时段</th>
    <th>去向</th><th>依据</th></tr></thead><tbody>${items.map(item => `<tr>
    <td><strong class="mono">${esc(item.offline_ref)}</strong><small class="subline">${esc(item.trip_day)} · ${item.rating} 分</small></td>
    <td class="mono">${esc(clock(item.filled_at))}</td>
    <td>${cohorts[item.cohort]}<small class="subline">${bands[item.time_band] || '未填写'}</small></td>
    <td>${item.sample_id ? `${esc(outcomes[item.outcome] || '已合并')}<small class="subline mono">${esc(item.sample_ref || '')}</small>`
      : '<span class="warning-text">尚未合并</span>'}</td>
    <td>${item.basis ? esc(item.basis) : '<span class="muted">合并后生成去向依据</span>'}</td></tr>`).join('')}
    </tbody></table></div>`;
}

function batchCard(batch, canEdit) {
  const open = batch.status === 'staging';
  return `<article class="module-item" data-batch="${batch.id}">
    <div class="panel-head"><div><h3 class="mono">${esc(batch.batch_ref)}</h3>
      <small class="subline">${esc(clock(batch.created_at))} · ${esc(batch.created_by)}</small></div>
      <span class="chip ${open ? 'queue' : 'decided'}">${statuses[batch.status]}</span></div>
    <p class="issue-detail">${progress(batch)} · 首份 ${batch.counts.first} · 被替下 ${batch.counts.superseded} · 重复 ${batch.counts.duplicate}
      ${batch.closing_note ? `<small class="subline">${esc(batch.closing_note)}</small>` : ''}</p>
    ${open && canEdit ? uploadForm(batch) : ''}
    ${open && canEdit ? `<div class="actions batch-actions">
      <button class="primary" data-merge="${batch.id}">合并本批</button>
      ${batch.received_items ? '' : `<button class="quiet" data-cancel="${batch.id}">取消批次</button>`}</div>` : ''}
    ${batch.items.length ? itemRows(batch.items) : empty(open ? '批次已建立，等待上传离线问卷。' : '本批没有问卷。')}
  </article>`;
}

export function backfillSection(data, role, open) {
  const canEdit = open && (role === 'collector' || role === 'analyst');
  const staging = data.staging[0];
  return `<section class="panel" id="backfill-panel"><div class="panel-head"><h2>离线补传批次</h2>
    <span class="mono">${open && data.staging.length ? `补传中 ${data.staging.length} 批 · 暂缓封存`
      : data.staging.length ? `另有 ${data.staging.length} 批尚未合并` : '无待处理批次'}</span></div>
    ${canEdit && !staging ? startForm() : ''}
    ${data.batches.length ? `<div class="module-log">${data.batches.map(batch => batchCard(batch, canEdit)).join('')}</div>`
      : empty('断网收集的离线问卷按批次补传，可中断后继续。')}</section>`;
}

function parsePayload(text) {
  let parsed;
  try { parsed = JSON.parse(text); }
  catch { throw Error('离线问卷须为 JSON 数组'); }
  if (!Array.isArray(parsed) || !parsed.length) throw Error('离线问卷须为非空 JSON 数组');
  return parsed.map((item, index) => {
    for (const key of ['offline_ref', 'passenger_code', 'cohort', 'trip_day', 'filled_at', 'rating']) {
      if (item[key] === undefined || item[key] === null || item[key] === '') throw Error(`第 ${index + 1} 条缺少 ${key}`);
    }
    const filled = String(item.filled_at);
    return {
      ...item,
      rating: Number(item.rating),
      time_band: item.time_band || null,
      filled_at: /(?:Z|[+-]\d{2}:?\d{2})$/.test(filled) ? filled : `${filled}+08:00`,
    };
  });
}

export function bindBackfill(root, data, refresh) {
  bindForm(root, '#batch-start', async formData => {
    const body = {
      batch_ref: formData.batch_ref,
      expected_items: formData.expected_items ? Number(formData.expected_items) : null,
    };
    const batch = await api(planPath('/backfill'), 'POST', body);
    notify(batch.status === 'merged' ? '该批次已结案。' : `批次 ${batch.batch_ref} 已建立，可继续上传。`);
    await refresh();
  });
  for (const batch of data.batches.filter(item => item.status === 'staging')) {
    if (root.querySelector(`[data-batch="${batch.id}"] #upload-${batch.id}`)) {
      bindForm(root, `[data-batch="${batch.id}"] #upload-${batch.id}`, async formData => {
        const items = parsePayload(formData.payload);
        const result = await api(planPath(`/backfill/${batch.id}/items`), 'POST', {items});
        const skipped = result.skipped.length ? `，跳过 ${result.skipped.length} 条已收记录` : '';
        notify(`本批已收 ${result.received_items} 份${skipped}。`);
        await refresh();
      });
    }
    root.querySelector(`[data-merge="${batch.id}"]`)?.addEventListener('click', async event => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        const result = await api(planPath(`/backfill/${batch.id}/merge`), 'POST', {});
        notify(`批次已合并：首份 ${result.counts.first}，被替下 ${result.counts.superseded}，重复 ${result.counts.duplicate}。`);
        await refresh();
      } catch (error) { notify(error.message, true); }
      finally { button.disabled = false; }
    });
    root.querySelector(`[data-cancel="${batch.id}"]`)?.addEventListener('click', async event => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        await api(planPath(`/backfill/${batch.id}/cancel`), 'POST');
        notify('批次已取消。');
        await refresh();
      } catch (error) { notify(error.message, true); }
      finally { button.disabled = false; }
    });
  }
}
