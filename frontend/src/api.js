import {clearSession, state} from './state.js';

export async function api(path, method = 'GET', body) {
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(`/api${path}`, {method, headers, body: JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401 && state.user) {
      clearSession();
      window.dispatchEvent(new Event('transfer-session-ended'));
    }
    throw Error(result.detail || `请求失败（${response.status}）`);
  }
  return result;
}

export function planPath(suffix = '') {
  return `/plans/${state.plan.id}${suffix}`;
}
