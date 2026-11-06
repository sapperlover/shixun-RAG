/** fetch 封装：统一前缀 /api；返回 {status, body}，由调用方按契约解释。 */

export interface HttpResult<T> {
  status: number
  body: T
}

const BASE = '/api'

export async function http<T>(
  method: 'GET' | 'POST' | 'PATCH',
  path: string,
  options: { body?: unknown; headers?: Record<string, string> } = {},
): Promise<HttpResult<T>> {
  const res = await fetch(BASE + path, {
    method,
    headers: { 'Content-Type': 'application/json', ...options.headers },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })
  const body = (await res.json().catch(() => null)) as T
  return { status: res.status, body }
}

/** 开发联调用的角色模拟头（后端仅在 APP_ENV=dev 时识别） */
export const demoRole = { value: '' }

export function roleHeaders(): Record<string, string> {
  return demoRole.value ? { 'X-Demo-Role': demoRole.value } : {}
}
