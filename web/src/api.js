// API 客户端：统一 {code,data,message} 解包 + 单 Token 自动携带。

let _token = ''
let _tokenPromise = null

function ensureToken() {
  if (_token) return Promise.resolve(_token)
  if (!_tokenPromise) {
    _tokenPromise = fetch('/api/auth/bootstrap')
      .then((r) => r.json())
      .then((body) => {
        _token = (body && body.data && body.data.token) || ''
        return _token
      })
      .catch(() => {
        _token = ''
        return ''
      })
  }
  return _tokenPromise
}

// 模块加载即开始拉取令牌，保证后续 WS / 下载等场景可用
ensureToken()

export function getToken() {
  return _token
}

async function request(path, options = {}) {
  const token = await ensureToken()
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(path, { ...options, headers })
  let body
  try {
    body = await res.json()
  } catch {
    body = { code: -1, message: res.statusText || `请求失败 (${res.status})` }
  }
  if (body.code !== 0) {
    throw new Error(body.message || `请求失败 (${res.status})`)
  }
  return body.data
}

export const apiGet = (p) => request(p)
export const apiPost = (p, body) =>
  request(p, { method: 'POST', body: JSON.stringify(body ?? {}) })
export const apiPut = (p, body) =>
  request(p, { method: 'PUT', body: JSON.stringify(body ?? {}) })
export const apiDelete = (p) => request(p, { method: 'DELETE' })

// WebSocket 进度客户端（token 经查询参数传入，因 WS 握手无法带自定义 header）
export function connectWS(projectId, onMessage, onClose) {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(
    `${proto}://${window.location.host}/ws/projects/${projectId}?token=${encodeURIComponent(_token)}`,
  )
  ws.onmessage = (e) => {
    try {
      onMessage(JSON.parse(e.data))
    } catch {
      /* ignore malformed frame */
    }
  }
  ws.onclose = () => onClose && onClose()
  ws.onerror = () => ws.close()
  return ws
}
