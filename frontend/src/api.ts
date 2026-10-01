const BASE = 'http://127.0.0.1:8000/api'

export interface DocumentSummary {
  id: string
  filename: string
  uploaded_at: string
  char_count: number
  chunk_count: number
  fact_count: number
}
export interface DocumentDetail extends DocumentSummary {
  extracted_text: string
  sections: Array<{ ordinal: number; source_ref: string; text: string }>
}
export interface Memory {
  id: string
  subject: string
  attribute: string
  value: string
  status: string
  sources: string[]
  created_at: string
}
export interface Alert {
  id: string
  existing_value: string
  existing_source: string
  new_subject: string
  new_attribute: string
  new_value: string
  new_source: string
  classification: string
  confidence: number
  reason: string
  status: string
  created_at: string
}
export interface Evidence {
  id: number
  document_id: string
  filename: string
  source_ref: string
  marker: string
  score: number
  text?: string
}
export interface Answer { answer: string; sources: Evidence[]; retrieved: Evidence[] }
export interface Health {
  status: string
  embedding_model: string
  ollama: { available: boolean; running: boolean; model: string; message: string }
}
export interface UploadResult {
  id: string
  filename: string
  chunk_count: number
  fact_count: number
  events: Array<{ classification: string; subject: string; attribute: string; value: string; reason: string; alert_id?: string }>
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try { response = await fetch(BASE + path, init) }
  catch { throw new Error('Cannot reach the backend. Start it on 127.0.0.1:8000, then refresh.') }
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`)
  return body as T
}

export const api = {
  health: () => request<Health>('/health'),
  dashboard: () => request<{ documents: number; memories: number; pending_alerts: number }>('/dashboard'),
  documents: () => request<DocumentSummary[]>('/documents'),
  document: (id: string) => request<DocumentDetail>(`/documents/${encodeURIComponent(id)}`),
  memories: () => request<Memory[]>('/memories'),
  alerts: () => request<Alert[]>('/alerts'),
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<UploadResult>('/documents/upload', { method: 'POST', body: form })
  },
  ask: (question: string) => request<Answer>('/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }) }),
  resolve: (id: string, action: string) => request<{ status: string }>(`/alerts/${encodeURIComponent(id)}/resolve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action }) }),
}
