import type { SettingsResponse, TaskEvent } from './types'

export const API_BASE = 'http://127.0.0.1:8000'
const WS_BASE = 'ws://127.0.0.1:8000'

async function parseError(response: Response): Promise<string> {
  try {
    const body = await response.json()
    return body.detail ?? JSON.stringify(body)
  } catch {
    return `HTTP ${response.status}`
  }
}

export async function getSettings(): Promise<SettingsResponse> {
  const response = await fetch(`${API_BASE}/api/settings`)
  if (!response.ok) throw new Error(await parseError(response))
  return response.json()
}

export async function saveBlenderPath(executablePath: string): Promise<SettingsResponse> {
  const response = await fetch(`${API_BASE}/api/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ executable_path: executablePath }),
  })
  if (!response.ok) throw new Error(await parseError(response))
  return response.json()
}

export async function startBlenderTest(executablePath: string): Promise<string> {
  const response = await fetch(`${API_BASE}/api/blender/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ executable_path: executablePath }),
  })
  if (!response.ok) throw new Error(await parseError(response))
  const body = await response.json()
  return body.task_id
}

export async function startAssetImport(model: File, resources: File[]): Promise<{ assetId: string; taskId: string }> {
  const form = new FormData()
  form.append('model', model, model.name)
  resources.forEach((resource) => form.append('resources', resource, resource.name))

  const response = await fetch(`${API_BASE}/api/assets/import`, {
    method: 'POST',
    body: form,
  })
  if (!response.ok) throw new Error(await parseError(response))
  const body = await response.json()
  return { assetId: body.asset_id, taskId: body.task_id }
}

export function absoluteAssetUrl(relativeUrl: string): string {
  return `${API_BASE}${relativeUrl}`
}

export function watchTask(taskId: string, onEvent: (event: TaskEvent) => void): WebSocket {
  const socket = new WebSocket(`${WS_BASE}/ws/tasks/${taskId}`)
  socket.onmessage = (message) => {
    onEvent(JSON.parse(message.data) as TaskEvent)
  }
  return socket
}

export async function startExistingPreparation(assetId: string): Promise<{ preparationId: string; taskId: string }> {
  const response = await fetch(`${API_BASE}/api/assets/${assetId}/prepare/existing`, { method: 'POST' })
  if (!response.ok) throw new Error(await parseError(response))
  const body = await response.json()
  return { preparationId: body.preparation_id, taskId: body.task_id }
}

export async function startAdaptPreparation(
  assetId: string,
  base: File,
  resources: File[],
  options: import('./types').AdaptBaseOptions,
): Promise<{ preparationId: string; taskId: string }> {
  const form = new FormData()
  form.append('base', base, base.name)
  resources.forEach((resource) => form.append('resources', resource, resource.name))
  Object.entries(options).forEach(([key, value]) => form.append(key, String(value)))
  const response = await fetch(`${API_BASE}/api/assets/${assetId}/prepare/adapt`, {
    method: 'POST',
    body: form,
  })
  if (!response.ok) throw new Error(await parseError(response))
  const body = await response.json()
  return { preparationId: body.preparation_id, taskId: body.task_id }
}
