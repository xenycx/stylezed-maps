// Thin client for the site's server (webapp/server.py). Every call rejects with an ApiError that says what went wrong.

export class ApiError extends Error {
  constructor(code, message, data = {}) {
    super(message || code);
    this.code = code;
    this.data = data;
    this.network = code === 'network';
  }
}

export async function call(method, url, body, opts = {}) {
  let res;
  try {
    res = await fetch(url, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: 'no-store',
      credentials: 'same-origin',
      keepalive: !!opts.keepalive,
      signal: opts.signal,
    });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new ApiError('network', e.message);
  }
  let data = null;
  try { data = await res.json(); } catch { /* not JSON */ }
  if (!res.ok || !data) {
    throw new ApiError(data?.error || `http_${res.status}`, data?.message || res.statusText, data || {});
  }
  return data;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const q = (o) => Object.entries(o).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');

/** Wait for a background job; onTick({status, position, seconds}) while it runs. */
export async function waitJob(job, onTick) {
  let j = job;
  let delay = 1200;
  while (j && (j.status === 'queued' || j.status === 'running')) {
    onTick?.(j);
    await sleep(delay);
    delay = Math.min(4000, delay + 300);
    try { j = await call('GET', `/api/job/${j.id}`); } catch (e) { if (!e.network) throw e; }
  }
  if (j && j.status === 'failed') throw new ApiError('render_failed', j.error || 'failed', { log: j.error });
  return j;
}

export const api = {
  me: () => call('GET', '/api/me'),
  state: (slug) => call('GET', `/api/map/${encodeURIComponent(slug)}`),
  custom: (slug) => call('GET', `/api/custom/${encodeURIComponent(slug)}`),
  saveCustom: (slug, doc, opts) => call('PUT', `/api/custom/${encodeURIComponent(slug)}`, doc, opts),
  sidecar: (slug, theme, lang) => call('GET', `/api/render?${q({ slug, theme, lang })}`),
  /** Draw (or bake the visitor's additions into) a theme; resolves with the fresh sidecar. */
  render: async (slug, theme, lang, onTick) => {
    const res = await call('POST', '/api/render', { slug, theme, lang });
    if (res.job) await waitJob(res.job, onTick);
    return call('GET', `/api/render?${q({ slug, theme, lang })}`);
  },
  profile: (slug, coords, signal) => call('POST', '/api/profile', { slug, coords }, { signal }),
  elevation: (slug, points) => call('POST', '/api/elevation', { slug, points }),
  submit: (slug, type, id) => call('POST', '/api/submit', { slug, type, id }),
  withdraw: (id) => call('POST', `/api/submit/${id}/withdraw`, {}),
  logout: () => call('POST', '/auth/logout', {}),
  fonts: (slug, theme, lang) => call('GET', `/api/fonts/${encodeURIComponent(slug)}?${q({ theme, lang })}`),
  setFont: (slug, theme, lang, role, family) => call('PUT', `/api/fonts/${encodeURIComponent(slug)}`, { theme, lang, role, family }),
  exportUrl: (slug, o) => `/api/export/${encodeURIComponent(slug)}?${q(o)}`,
};

export function loginUrl(next = location.pathname + location.search) {
  return `/auth/google?next=${encodeURIComponent(next)}`;
}
