/** 应急预案演练台账接口封装：所有页面共用一套请求与消息处理。 */
import { request } from '@/api/client'

const BASE = '/api/emergency-plan'

export type Row = Record<string, unknown>

export type Page<T = Row> = { items: T[]; total: number; page: number; size: number }
export type ActionResponse = { ok: boolean; message: string; entry?: Row | null }

async function parse(response: Response): Promise<ActionResponse> {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    return { ok: false, message: data?.detail ?? `接口返回 ${response.status}` }
  }
  return data as ActionResponse
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await request(`${BASE}${path}`)
  if (!response.ok) throw new Error(`接口返回 ${response.status}`)
  return (await response.json()) as T
}

export async function getPage(path: string): Promise<Page> {
  return getJson<Page>(path)
}

export async function postAction(path: string, body: unknown): Promise<ActionResponse> {
  const response = await request(`${BASE}${path}`, {
    method: 'POST',
    body: JSON.stringify(body ?? {}),
  })
  return parse(response)
}

export async function putAction(path: string, body: unknown): Promise<ActionResponse> {
  const response = await request(`${BASE}${path}`, {
    method: 'PUT',
    body: JSON.stringify(body ?? {}),
  })
  return parse(response)
}

export async function deleteAction(path: string): Promise<ActionResponse> {
  const response = await request(`${BASE}${path}`, { method: 'DELETE' })
  return parse(response)
}

export type Meta = {
  accident_catalog: string[]
  conclusion_grades: string[]
  version_statuses: string[]
  todo_statuses: string[]
}

export function fetchMeta(): Promise<Meta> {
  return getJson<Meta>('/meta')
}

export type Stats = { year: number; cards: { label: string; value: string | number }[] }

export function fetchStats(year?: number): Promise<Stats> {
  return getJson<Stats>(`/stats${year ? `?year=${year}` : ''}`)
}
