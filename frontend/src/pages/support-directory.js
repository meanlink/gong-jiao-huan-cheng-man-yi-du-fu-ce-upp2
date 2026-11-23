import {bindForm, esc, notify} from '../components.js';
import {deskNames, supportApi} from '../support-api.js';

function deskCard(key, name, desk, editable) {
  const availability = desk ? (desk.available ? '开放' : '暂停接单') : '待设置';
  return `<li data-desk="${key}" class="desk-card"><div class="desk-head"><strong>${name}</strong>
    <span class="chip ${desk?.available ? 'decided' : 'queue'}">${availability}</span></div>
    ${desk ? `<p>${esc(desk.location)}</p><small class="mono">在办 ${desk.active_count} / ${desk.capacity}</small>` : ''}
    ${editable ? `<details><summary>编辑服务点</summary><form id="desk-${key}" class="vertical-form support-form">
      <label>接应位置<input name="location" required minlength="2" maxlength="100" value="${esc(desk?.location)}"></label>
      <div class="support-controls"><label>同时接单上限<input name="capacity" type="number" min="1" max="30" required value="${desk?.capacity ?? 2}"></label>
      <label>接单状态<select name="available"><option value="true" ${desk?.available ? 'selected' : ''}>开放</option>
        <option value="false" ${desk?.available ? '' : 'selected'}>暂停</option></select></label></div>
      <button class="quiet">保存服务点</button></form></details>` : ''}</li>`;
}

export function directory(board, role) {
  return `<section class="panel support-directory"><div class="panel-head"><h2>服务点与负荷</h2></div>
    <ul class="desk-grid">${Object.entries(deskNames).map(([key, name]) =>
      deskCard(key, name, board.desks.find(desk => desk.desk === key), role === 'director')).join('')}</ul></section>`;
}

export function bindDirectory(root, refresh) {
  for (const desk of Object.keys(deskNames)) {
    bindForm(root, `#desk-${desk}`, async data => {
      await supportApi.desk(desk, {...data, capacity: Number(data.capacity), available: data.available === 'true'});
      notify('已保存服务点。');
      await refresh(true);
    });
  }
}
