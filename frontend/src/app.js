import {api} from './api.js';
import {bindForm, empty, esc, notify, routeBadge, stageChip} from './components.js';
import {analysis, noPlan} from './pages/analysis.js';
import {decision} from './pages/decision.js';
import {handover} from './pages/handover.js';
import {support} from './pages/support.js';
import {survey} from './pages/survey.js';
import {versions} from './pages/versions.js';
import {walks} from './pages/walks.js';
import {clearSession, roleNames, saveSession, state} from './state.js';

const app = document.querySelector('#app');
const routes = {versions: ['线路版本', versions], survey: ['乘客调查', survey],
  walks: ['站点巡检', walks], analysis: ['分层比较', analysis], decision: ['运营决策', decision],
  handover: ['改线交接', handover], support: ['乘客协助', support]};
let renderId = 0;

function login() {
  app.innerHTML = `<main class="signin"><section class="signin-map"><div class="kicker">城西公交运营中心</div>
    <h1>公交换乘<br>满意度复测</h1>
    <div class="signin-stops"><div><i></i>北广场 3 号站台<span>K12</span></div><div><i></i>东连廊 1 号港湾</div><div><i></i>地铁 C 口<span>M3</span></div></div>
    <p>对照改线前后的乘客体验，留下运营决策依据。</p></section>
    <section class="signin-form"><h2>工作台登录</h2><form id="login" class="vertical-form">
      <label>工作邮箱<input name="email" type="email" autocomplete="username" required></label>
      <label>密码<input name="password" type="password" autocomplete="current-password" required></label>
      <button type="submit" class="primary">登录</button></form>
      <div class="demo-accounts"><h3>演示账号</h3><div class="actions">${Object.entries(roleNames).map(([role, name]) =>
        `<button class="quiet" data-demo="${role}">${name}</button>`).join('')}</div></div></section></main>`;
  app.querySelectorAll('[data-demo]').forEach(button => button.addEventListener('click', () => {
    const form = app.querySelector('#login');
    form.elements.email.value = `${button.dataset.demo}@chengxi.local`;
    form.elements.password.value = 'transfer1051';
  }));
  bindForm(app, '#login', async data => { saveSession(await api('/auth/login', 'POST', data)); await render(); });
}

async function render(quiet = false) {
  const id = ++renderId;
  const current = () => id === renderId;
  if (!state.token) { login(); return; }
  try {
    if (!state.user) state.user = await api('/auth/me');
    const plans = await api('/plans');
    if (!current()) return;
    const [, requestedView, requestedId] = location.hash.split('/');
    const view = Object.hasOwn(routes, requestedView) ? requestedView : 'versions';
    const previous = state.plan;
    const plan = plans.find(item => item.id === Number(requestedId)) ?? plans[0] ?? null;
    if (previous?.id !== plan?.id || state.view !== view) Object.assign(state, {editing: false, offset: 0, query: 'queue'});
    Object.assign(state, {plans, plan, view});
    if (!quiet || !app.querySelector('#screen')) {
      app.innerHTML = `<header class="mast"><div class="mast-inner"><a class="brand" href="#/versions/${plan?.id || ''}">
        <span class="brand-icon" aria-hidden="true"><i></i><i></i><i></i></span><span><strong>公交换乘复测</strong><small>城西公交运营中心</small></span></a>
        <div class="identity"><span class="role">${esc(roleNames[state.user.role])}</span><strong>${esc(state.user.name)}</strong><button class="quiet" id="logout">退出</button></div></div></header>
        <div class="workspace"><div class="rail"><nav aria-label="业务阶段">${Object.entries(routes).map(([key, [label]]) =>
          `<a href="#/${key}/${plan?.id || ''}" ${key === view ? 'aria-current="page"' : ''}>${label}</a>`).join('')}</nav>
          ${plan ? `<div class="context">${routeBadge(plan)}${stageChip(plan.stage)}</div>` : ''}</div><main id="screen" aria-busy="true"></main></div>`;
      app.querySelector('#logout').addEventListener('click', () => { clearSession(); render(); });
    }
    const screen = app.querySelector('#screen');
    if (plan || view === 'versions') await routes[view][1](screen, render, current);
    else noPlan(screen);
    if (current()) screen.removeAttribute('aria-busy');
  } catch (error) {
    if (!current()) return;
    if (!state.user) { clearSession(); login(); }
    else if (app.querySelector('#screen')) app.querySelector('#screen').innerHTML = `${empty('页面暂时无法加载。')}<button id="retry" class="quiet">重试</button>`;
    else app.innerHTML = `<main class="workspace">${empty('工作台暂时无法加载。')}<button id="retry" class="quiet">重试</button></main>`;
    app.querySelector('#retry')?.addEventListener('click', () => render());
    notify(error.message, true);
  }
}

window.addEventListener('hashchange', () => render());
window.addEventListener('transfer-session-ended', () => render());
render();
