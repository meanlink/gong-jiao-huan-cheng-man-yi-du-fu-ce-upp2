import {bindForm, empty, esc, heading, notify} from '../components.js';
import {categoryNames, deskNames, supportApi} from '../support-api.js';
import {state} from '../state.js';
import {bindDirectory, directory} from './support-directory.js';
import {bindNotices, notices} from './support-notices.js';
import {bindQueue, queue} from './support-queue.js';

function intake(board) {
  if (board.status === 'scheduled') return empty('计划启用日当天开始登记协助单。');
  if (!board.notices.length) return empty('现场指引发布后开始登记协助单。');
  return `<form class="vertical-form support-form" id="register-support">
    <label>协助类型<select name="category">${Object.entries(categoryNames).map(([key, text]) =>
      `<option value="${key}">${text}</option>`).join('')}</select></label>
    <label>乘客所在位置<input name="landmark" required minlength="2" maxlength="100" placeholder="例如：南厅电梯口"></label>
    <label>现场需求<textarea name="description" rows="2" required minlength="4" maxlength="240"
      placeholder="记录换乘需求，请勿填写姓名或联系方式"></textarea></label>
    <button class="primary">登记并派单</button></form>`;
}

export async function support(root, refresh, current) {
  const board = await supportApi.board();
  if (!current()) return;
  const {plan, user} = state;
  const pageHeading = heading('改线启用', '乘客协助工作台', `${plan.hub} · ${plan.code}`);
  if (board.status === 'awaiting_handover') {
    root.innerHTML = pageHeading + `<section class="panel">${empty('发布改线交接单后，才可配置服务点和现场指引。')}
      <div class="panel-foot"><a href="#/handover/${plan.id}">查看改线交接</a></div></section>`;
    return;
  }
  root.innerHTML = pageHeading + `<div class="support-board">
    <section class="support-banner"><div><small>启用路径</small><strong>${esc(board.trial_path)}</strong></div>
      <span class="chip ${board.status === 'live' ? 'decided' : 'queue'}">${board.status === 'live' ? '已启用' : '待启用'} · ${esc(board.effective_on)}</span></section>
    <div class="support-overview">${notices(board, user.role)}${directory(board, user.role)}</div>
    <div class="support-work ${user.role === 'collector' ? 'with-intake' : ''}">
      ${user.role === 'collector' ? `<section class="panel support-intake"><div class="panel-head"><h2>登记乘客需求</h2></div>${intake(board)}</section>` : ''}
      ${queue(board, user.role)}</div></div>`;
  bindDirectory(root, refresh);
  bindNotices(root, board.notices[0], refresh);
  bindQueue(root, board, refresh);
  bindForm(root, '#register-support', async data => {
    const item = await supportApi.register({...data, notice_edition: board.notices[0].edition});
    notify(item.desk ? `已派往${deskNames[item.desk]}。` : '已保留协助单，等待可用服务点。');
    await refresh(true);
  });
}
