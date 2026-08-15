// API 客户端：请求同源相对路径（开发期由 Vite 代理转发到 FastAPI 后端）。

async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let msg = res.statusText
    try {
      const d = await res.json()
      msg = d.detail || msg
    } catch {
      /* ignore */
    }
    throw new Error(msg || `请求失败 (${res.status})`)
  }
  return res.json()
}

export const apiGet = (p) => request(p)
export const apiPost = (p, body) =>
  request(p, { method: 'POST', body: JSON.stringify(body ?? {}) })
export const apiPut = (p, body) =>
  request(p, { method: 'PUT', body: JSON.stringify(body ?? {}) })
export const apiDelete = (p) => request(p, { method: 'DELETE' })

// WebSocket 进度客户端；返回 ws 实例，由调用方决定何时关闭。
export function connectWS(projectId, onMessage, onClose) {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${window.location.host}/ws/projects/${projectId}`)
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
