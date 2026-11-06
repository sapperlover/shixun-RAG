import type { Page } from '@/types/qa'

import { http, roleHeaders } from './client'

export async function listPage<T>(path: string, limit = 20, offset = 0) {
  return http<Page<T>>('GET', `${path}?limit=${limit}&offset=${offset}`, {
    headers: roleHeaders(),
  })
}

export async function getHealth() {
  return http<Record<string, unknown>>('GET', '/health/ready')
}
