import {api, planPath} from './api.js';

const path = (suffix = '') => planPath(`/support${suffix}`);
export const supportApi = {
  board: () => api(path()),
  desk: (desk, data) => api(path(`/desks/${desk}`), 'PUT', data),
  publish: data => api(path('/notices'), 'POST', data),
  register: data => api(path('/cases'), 'POST', data),
  timeline: id => api(path(`/cases/${id}/timeline`)),
  redispatch: id => api(path(`/cases/${id}/redispatch`), 'POST'),
  resolve: (id, data) => api(path(`/cases/${id}/resolve`), 'POST', data),
};

export const deskNames = {access: '无障碍协助点', station: '站务服务台', dispatch: '换乘调度岗'};
export const categoryNames = {step_free: '无台阶通行', wayfinding: '路线问询', missed_connection: '错过换乘'};
export const routeReasons = {primary: '首选服务点', fallback: '备用服务点', waiting: '待派单'};
