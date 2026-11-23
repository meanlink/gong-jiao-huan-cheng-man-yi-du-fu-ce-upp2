import {bindForm, empty, esc, notify} from '../components.js';
import {supportApi} from '../support-api.js';

function noticeLine(notice) {
  return `<span class="mono">第 ${notice.edition} 版</span> <strong>${esc(notice.meeting_point)}</strong>
    <p>${esc(notice.directions)}</p>`;
}

export function notices(board, role) {
  const [latest, ...older] = board.notices;
  return `<section class="panel support-notices"><div class="panel-head"><h2>现场指引</h2>${latest ?
    `<span class="chip decided">现行第 ${latest.edition} 版</span>` : ''}</div>
    ${latest ? `<div class="live-guide"><h3>${esc(latest.meeting_point)}</h3><p>${esc(latest.directions)}</p></div>` : empty('等待运营主管发布现场指引。')}
    ${role === 'director' ? `<details ${latest ? '' : 'open'}><summary>编辑并发布新版本</summary>
      <form class="vertical-form support-form" id="publish-notice">
      <label>乘客集合点<input name="meeting_point" required minlength="2" maxlength="100" value="${esc(latest?.meeting_point)}"></label>
      <label>引导话术<textarea name="directions" rows="2" required minlength="8" maxlength="280">${esc(latest?.directions)}</textarea></label>
      <button class="primary">发布现场指引</button></form></details>` : ''}
    ${older.length ? `<details><summary>历史版本（${older.length}）</summary><ol class="notice-editions">${older.map(notice =>
      `<li>${noticeLine(notice)}</li>`).join('')}</ol></details>` : ''}</section>`;
}

export function bindNotices(root, latest, refresh) {
  bindForm(root, '#publish-notice', async data => {
    const notice = await supportApi.publish({...data, previous_edition: latest?.edition ?? 0});
    notify(`已发布第 ${notice.edition} 版现场指引。`);
    await refresh(true);
  });
}
