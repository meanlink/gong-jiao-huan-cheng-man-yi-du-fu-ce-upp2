export const stages = {draft: '方案草稿', surveying: '调查执行中', sealed: '问卷已封存', decided: '决策已签署'};
export const cohorts = {baseline: '改线前', trial: '改线后'};
export const bands = {peak: '高峰', offpeak: '平峰'};
export const dispositions = {eligible: '有效问卷', queue: '待清洗', excluded: '已剔除'};
export const decisions = {adopt: '采用改线', retain: '维持原线路', extend: '另开下一轮复测'};
export const roleNames = {collector: '现场调查员', analyst: '数据分析员', director: '运营主管'};

export const state = {
  token: sessionStorage.getItem('transfer-token'), user: null, plans: [], plan: null,
  view: 'versions', query: 'queue', offset: 0, editing: false,
};

export function saveSession(data) {
  state.token = data.token;
  state.user = data.user;
  sessionStorage.setItem('transfer-token', data.token);
}

export function clearSession() {
  sessionStorage.removeItem('transfer-token');
  Object.assign(state, {token: null, user: null, plan: null, plans: [], editing: false, offset: 0});
}
