import {bindForm, empty, esc, notify} from '../components.js';
import {categoryNames, deskNames, routeReasons, supportApi} from '../support-api.js';

const eventNames = {opened: '登记', redispatched: '重新分派', resolved: '办结'};
const time = new Intl.DateTimeFormat('zh-CN', {timeZone: 'Asia/Shanghai', dateStyle: 'short', timeStyle: 'short'});

function caseCard(item, board, role) {
  const {id, category, desk, resolved_at, notice_edition, landmark, description, resolution} = item;
  const entry = board.desks.find(option => option.desk === desk);
  const route = desk ? `${deskNames[desk]} · ${routeReasons[item.route_reason]}` : '暂无可接单服务点';
  const status = resolved_at ? '已办结' : (desk ? '已派单' : '待派单');
  return `<li class="case-card" data-case="${id}"><div class="desk-head">
    <span class="mono case-ref">#${id}</span><h3>${categoryNames[category]}</h3>
    <span class="chip ${resolved_at ? 'decided' : 'queue'}">${status}</span></div>
    <p><strong>${esc(landmark)}</strong> · ${esc(description)}</p>
    <div class="case-route"><strong>${route}</strong><small>指引第 ${notice_edition} 版</small></div>
    ${desk && !resolved_at && !entry?.available ? '<p class="desk-alert">当前服务点已暂停，待调度确认。</p>' : ''}
    ${resolution ? `<div class="resolution"><strong>处理结果</strong><p>${esc(resolution)}</p></div>` : ''}
    ${role === 'analyst' && !resolved_at ? `<div class="case-actions"><button class="quiet" data-redispatch="${id}">重新分派</button>
      ${desk ? `<details><summary>登记办结结果</summary><form id="resolve-${id}" class="vertical-form support-form">
        <label>处理结果<textarea name="note" minlength="8" maxlength="240" rows="2" required></textarea></label>
        <button class="primary">确认办结</button></form></details>` : ''}</div>` : ''}
    <details class="case-timeline" data-timeline="${id}"><summary>处理记录</summary><div class="case-history" aria-live="polite"></div></details></li>`;
}

export function queue(board, role) {
  const active = board.cases.filter(item => !item.resolved_at);
  const waiting = active.filter(item => !item.desk).length;
  return `<section class="panel support-queue"><div class="panel-head"><h2>协助队列</h2>
    <span class="mono queue-count">待派 ${waiting} · 在办 ${active.length - waiting} · 办结 ${board.cases.length - active.length}</span></div>
    ${board.cases.length ? `<ol class="support-cases">${board.cases.map(item => caseCard(item, board, role)).join('')}</ol>` : empty('尚无乘客协助单。')}</section>`;
}

export function bindQueue(root, board, refresh) {
  for (const item of board.cases) {
    root.querySelector(`[data-redispatch="${item.id}"]`)?.addEventListener('click', async event => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        const updated = await supportApi.redispatch(item.id);
        notify(updated.desk ? `服务点：${deskNames[updated.desk]}` : '仍待派单，暂无可接单服务点。');
        await refresh(true);
      } catch (error) { notify(error.message, true); }
      finally { button.disabled = false; }
    });
    bindForm(root, `#resolve-${item.id}`, async data => {
      await supportApi.resolve(item.id, data);
      notify('协助单已办结。');
      await refresh(true);
    });
    const details = root.querySelector(`[data-timeline="${item.id}"]`);
    details.addEventListener('toggle', async () => {
      if (!details.open) return;
      const target = details.querySelector('.case-history');
      target.textContent = '正在读取处理记录…';
      try {
        const history = await supportApi.timeline(item.id);
        target.innerHTML = `<ol>${history.map(event => `<li><strong>${eventNames[event.action]}</strong>
          · ${event.desk ? deskNames[event.desk] : '待派单'}<br><small>${esc(time.format(new Date(event.happened_at)))} · ${esc(event.actor)}</small></li>`).join('')}</ol>`;
      } catch (error) { target.textContent = error.message; }
    });
  }
}
