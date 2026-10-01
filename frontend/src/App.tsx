import { useEffect, useState, type FormEvent } from 'react'
import { api, type Alert, type Answer, type DocumentDetail, type DocumentSummary, type Health, type Memory, type UploadResult } from './api'

type Page = 'Dashboard' | 'Documents' | 'Ask NeuroVault' | 'Memory' | 'Synapse Alerts'
const pages: Page[] = ['Dashboard', 'Documents', 'Ask NeuroVault', 'Memory', 'Synapse Alerts']
const icons: Record<Page, string> = { Dashboard: '◈', Documents: '▤', 'Ask NeuroVault': '✦', Memory: '◎', 'Synapse Alerts': '⚑' }
const displayDate = (value: string) => new Date(value).toLocaleString()
const pill = (status: string) => status === 'pending' || status === 'POTENTIAL_UPDATE' || status === 'CONTRADICTION'
  ? 'border-amber-400/30 bg-amber-400/10 text-amber-200' : 'border-cyan-400/25 bg-cyan-400/10 text-cyan-200'

function Badge({ children, status = '' }: { children: string; status?: string }) {
  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${pill(status)}`}>{children}</span>
}

export default function App() {
  const [page, setPage] = useState<Page>('Dashboard')
  const [health, setHealth] = useState<Health | null>(null)
  const [counts, setCounts] = useState({ documents: 0, memories: 0, pending_alerts: 0 })
  const [documents, setDocuments] = useState<DocumentSummary[]>([])
  const [memories, setMemories] = useState<Memory[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState('')
  const [selected, setSelected] = useState<File | null>(null)
  const [lastUpload, setLastUpload] = useState<UploadResult | null>(null)
  const [inspected, setInspected] = useState<DocumentDetail | null>(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<Answer | null>(null)

  async function refresh() {
    try {
      const [h, c, d, m, a] = await Promise.all([api.health(), api.dashboard(), api.documents(), api.memories(), api.alerts()])
      setHealth(h); setCounts(c); setDocuments(d); setMemories(m); setAlerts(a); setError('')
    } catch (e) { setError((e as Error).message); setHealth(null) }
  }
  useEffect(() => { void refresh() }, [])

  async function upload(event: FormEvent) {
    event.preventDefault()
    if (!selected) return
    setBusy('upload'); setError(''); setNotice('')
    try {
      const result: UploadResult = await api.upload(selected)
      setLastUpload(result)
      setNotice(`${result.filename} indexed: ${result.chunk_count} chunks, ${result.fact_count} structured facts. ${result.events.filter(e => e.alert_id).length} new Synapse alert(s).`)
      setSelected(null)
      const input = document.getElementById('upload-input') as HTMLInputElement | null
      if (input) input.value = ''
      await refresh()
    } catch (e) { setError((e as Error).message) }
    finally { setBusy('') }
  }

  async function inspect(id: string) {
    setBusy(id); setError('')
    try { setInspected(await api.document(id)) }
    catch (e) { setError((e as Error).message) }
    finally { setBusy('') }
  }

  async function ask(event: FormEvent) {
    event.preventDefault()
    if (question.trim().length < 3) return
    setBusy('ask'); setError(''); setAnswer(null)
    try { setAnswer(await api.ask(question.trim())) }
    catch (e) { setError((e as Error).message) }
    finally { setBusy('') }
  }

  async function resolve(id: string, action: string) {
    setBusy(id); setError(''); setNotice('')
    try { await api.resolve(id, action); setNotice('Synapse decision saved.'); await refresh() }
    catch (e) { setError((e as Error).message) }
    finally { setBusy('') }
  }

  return <div className="min-h-screen bg-[radial-gradient(ellipse_at_top_right,_#123249_0%,_#0a101b_42%)] text-slate-100 lg:flex">
    <aside className="border-b border-slate-800 bg-[#0c1422]/90 px-5 py-5 lg:min-h-screen lg:w-64 lg:shrink-0 lg:border-b-0 lg:border-r lg:px-6 lg:py-8">
      <div className="flex items-center gap-3 lg:mb-11">
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-cyan-400 text-xl font-black text-slate-950">N</div>
        <div><div className="text-lg font-bold tracking-tight">NeuroVault</div><div className="text-xs tracking-widest text-cyan-300">SYNAPSE V0</div></div>
      </div>
      <nav className="mt-6 flex gap-2 overflow-x-auto lg:mt-0 lg:flex-col" aria-label="Main navigation">
        {pages.map(item => <button key={item} type="button" onClick={() => { setPage(item); setNotice('') }}
          className={`flex shrink-0 items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition ${page === item ? 'bg-cyan-400/15 font-semibold text-cyan-200 ring-1 ring-cyan-400/25' : 'text-slate-400 hover:bg-slate-800 hover:text-white'}`}>
          <span className="w-5 text-center text-lg" aria-hidden="true">{icons[item]}</span>{item}
          {item === 'Synapse Alerts' && counts.pending_alerts > 0 && <span className="ml-auto rounded-full bg-amber-400 px-1.5 text-xs font-bold text-slate-950">{counts.pending_alerts}</span>}
        </button>)}
      </nav>
      <div className="mt-12 hidden rounded-xl border border-slate-700/60 p-4 text-xs text-slate-400 lg:block">
        <span className="mb-2 block h-2 w-2 rounded-full bg-cyan-400" />Local workspace<br />Data stays on this machine. Indexing never sends documents to an external API.
      </div>
    </aside>

    <main className="mx-auto w-full max-w-6xl flex-1 px-5 pb-16 pt-7 sm:px-8 lg:px-12 lg:pt-10">
      <header className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div><div className="eyebrow">Your private knowledge workspace</div><h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">{page}</h1></div>
        <div className={`rounded-full border px-3 py-1.5 text-xs font-medium ${health?.ollama.available ? 'border-emerald-500/30 bg-emerald-400/10 text-emerald-300' : 'border-amber-500/30 bg-amber-400/10 text-amber-200'}`}>
          {health ? (health.ollama.available ? '● Local model ready' : '● Local model needs setup') : '● Backend disconnected'}
        </div>
      </header>
      {error && <div role="alert" className="mb-5 rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error} <button className="ml-2 underline" onClick={() => void refresh()}>Retry</button></div>}
      {notice && <div role="status" className="mb-5 rounded-xl border border-cyan-500/30 bg-cyan-500/10 px-4 py-3 text-sm text-cyan-100">{notice}</div>}

      {page === 'Dashboard' && <div className="space-y-6">
        <section className="panel overflow-hidden p-7 sm:p-9"><div className="eyebrow">NeuroVault × Synapse Active Brain</div>
          <h2 className="mt-4 max-w-xl text-3xl font-bold leading-tight">Grounded answers. Memory changes under your control.</h2>
          <p className="muted mt-4 max-w-2xl leading-7">Index local documents, ask questions with source citations, and review important fact changes before your structured memory changes.</p>
          <div className="mt-6 flex flex-wrap gap-3"><button className="button" onClick={() => setPage('Documents')}>Index a document →</button><button className="button-secondary" onClick={() => setPage('Ask NeuroVault')}>Ask a question</button></div>
        </section>
        <div className="grid gap-4 sm:grid-cols-3">{([['Documents indexed', counts.documents], ['Active memories', counts.memories], ['Synapse alerts', counts.pending_alerts]] as const).map(([label, value]) => <div key={label} className="panel p-6"><div className="muted text-sm">{label}</div><div className="mt-3 text-4xl font-bold">{value}</div></div>)}</div>
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="panel p-6"><h3 className="text-lg font-semibold">Try the two-file demo</h3><ol className="muted mt-4 list-decimal space-y-2 pl-5 text-sm leading-6"><li>Upload <code>assignment-original.txt</code>.</li><li>Upload <code>assignment-update.txt</code>.</li><li>Open Synapse Alerts and decide whether to accept the changed deadline.</li><li>Ask: “What is the Machine Learning assignment deadline?”</li></ol></div>
          <div className="panel p-6"><h3 className="text-lg font-semibold">Local services</h3><p className="muted mt-3 text-sm">Embeddings: {health?.embedding_model ?? 'Backend not connected'}</p><p className="muted mt-2 text-sm">Ollama: {health?.ollama.message ?? 'Start the backend first.'}</p><p className="muted mt-4 text-xs">The first indexing request may download the embedding model. Ollama must be installed separately for answers.</p></div>
        </div>
      </div>}

      {page === 'Documents' && <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <div className="space-y-6"><form onSubmit={upload} className="panel p-6"><h2 className="text-lg font-semibold">Add knowledge</h2><p className="muted mt-2 text-sm">PDF, DOCX, or UTF-8 TXT · up to 10 MiB · text-based PDF only</p>
          <input id="upload-input" className="input mt-5 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-700 file:px-3 file:py-2 file:text-slate-100" type="file" accept=".pdf,.docx,.txt" onChange={e => setSelected(e.target.files?.[0] ?? null)} />
          <button disabled={!selected || busy === 'upload'} className="button mt-4" type="submit">{busy === 'upload' ? 'Extracting and embedding…' : 'Index document'}</button></form>
          {lastUpload && <div className="panel p-6"><h2 className="text-lg font-semibold">Last upload · {lastUpload.filename}</h2>{lastUpload.events.length ? <div className="mt-3 space-y-3">{lastUpload.events.map((event, i) => <div key={`${event.subject}-${event.attribute}-${i}`} className="rounded-xl border border-slate-700 p-3 text-sm"><Badge status={event.classification}>{event.classification.replaceAll('_', ' ')}</Badge><p className="mt-2 capitalize">{event.subject} · {event.attribute}: {event.value}</p><p className="muted mt-1 text-xs">{event.reason}</p></div>)}</div> : <p className="muted mt-3 text-sm">No facts matched V0's explicit extraction patterns. The text was still indexed for Q&A.</p>}</div>}
          <div className="panel p-6"><h2 className="mb-4 text-lg font-semibold">Indexed documents</h2>{documents.length === 0 ? <p className="muted text-sm">No documents yet. Start with the safe sample files.</p> : <div className="space-y-3">{documents.map(doc => <div key={doc.id} className="rounded-xl border border-slate-700 p-4"><div className="break-all font-semibold">{doc.filename}</div><p className="muted mt-1 text-xs">{displayDate(doc.uploaded_at)} · {doc.chunk_count} chunks · {doc.fact_count} facts</p><button onClick={() => void inspect(doc.id)} disabled={busy === doc.id} className="mt-3 text-sm font-semibold text-cyan-300 hover:underline">Inspect extracted source →</button></div>)}</div>}</div>
        </div>
        <div className="panel max-h-[750px] overflow-auto p-6"><h2 className="text-lg font-semibold">Source inspector</h2>{inspected ? <><p className="muted mt-2 break-all text-sm">{inspected.filename} · {inspected.char_count.toLocaleString()} characters</p><div className="mt-5 whitespace-pre-wrap break-words rounded-xl bg-slate-950/70 p-4 text-sm leading-6 text-slate-200">{inspected.extracted_text}</div><h3 className="mt-6 font-semibold">Indexed chunks</h3>{inspected.sections.map(section => <div key={section.ordinal} className="mt-3 rounded-lg border border-slate-700 p-3 text-xs"><span className="text-cyan-300">{section.source_ref} · chunk {section.ordinal + 1}</span><p className="muted mt-2 break-words">{section.text}</p></div>)}</> : <p className="muted mt-4 text-sm">Select a document to inspect the text that was extracted and indexed.</p>}</div>
      </div>}

      {page === 'Ask NeuroVault' && <div className="space-y-6"><form className="panel p-6" onSubmit={ask}><label htmlFor="question" className="text-lg font-semibold">Ask your documents</label><p className="muted mt-2 text-sm">Answers use retrieved excerpts and cite their sources. Review pending Synapse alerts for disputed facts.</p><div className="mt-5 flex flex-col gap-3 sm:flex-row"><input id="question" className="input" value={question} onChange={e => setQuestion(e.target.value)} minLength={3} maxLength={1000} placeholder="What is the Machine Learning assignment deadline?" /><button className="button shrink-0" disabled={busy === 'ask'}>{busy === 'ask' ? 'Thinking…' : 'Ask →'}</button></div></form>
        {counts.pending_alerts > 0 && <div className="rounded-xl border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-100">There are {counts.pending_alerts} unresolved fact changes. Treat answers involving those facts as disputed until you review them.</div>}
        {answer && <section className="panel p-6"><div className="eyebrow">Grounded answer</div><p className="mt-4 whitespace-pre-wrap text-lg leading-8">{answer.answer}</p><h3 className="mt-7 font-semibold">Cited sources</h3>{answer.sources.length ? <div className="mt-3 space-y-2">{answer.sources.map(source => <button key={source.marker} onClick={() => { setPage('Documents'); void inspect(source.document_id) }} className="block w-full rounded-xl border border-slate-700 p-3 text-left text-sm hover:border-cyan-400"><span className="font-semibold text-cyan-300">[{source.marker}] {source.filename}</span><span className="muted"> · {source.source_ref}</span></button>)}</div> : <p className="muted mt-2 text-sm">No cited source.</p>}
          {answer.retrieved.length > 0 && <details className="mt-6"><summary className="cursor-pointer text-sm text-cyan-300">Inspect retrieved excerpts</summary><div className="mt-3 space-y-3">{answer.retrieved.map(item => <div className="rounded-xl bg-slate-950/60 p-4 text-sm" key={item.marker}><span className="text-cyan-300">[{item.marker}] {item.filename} · {item.source_ref}</span><p className="muted mt-2 break-words">{item.text}</p></div>)}</div></details>}</section>}
      </div>}

      {page === 'Memory' && <div className="space-y-4"><p className="muted text-sm">Structured facts extracted from explicit patterns. Other document text is still searchable, but it does not automatically become structured memory.</p>{memories.length === 0 ? <div className="panel p-6 muted">No structured memories yet.</div> : memories.map(memory => <div key={memory.id} className="panel p-5"><div className="flex flex-wrap items-center gap-2"><h2 className="font-semibold capitalize">{memory.subject} · {memory.attribute}</h2><Badge status={memory.status}>{memory.status}</Badge></div><p className="mt-2 text-lg">{memory.value}</p><p className="muted mt-3 break-all text-xs">Source: {memory.sources.join('; ') || 'No source recorded'}</p></div>)}</div>}

      {page === 'Synapse Alerts' && <div className="space-y-5"><p className="muted text-sm">ChangeGuard compares supported structured facts. Potential updates and contradictions require a decision before memory changes.</p>{alerts.length === 0 ? <div className="panel p-6 muted">No alerts. Upload both sample files to try an update.</div> : alerts.map(alert => <article key={alert.id} className="panel p-6"><div className="flex flex-wrap items-center gap-3"><Badge status={alert.classification}>{alert.classification.replaceAll('_', ' ')}</Badge><Badge status={alert.status}>{alert.status.replaceAll('_', ' ')}</Badge></div><h2 className="mt-4 text-lg font-semibold capitalize">{alert.new_subject} · {alert.new_attribute}</h2><div className="mt-5 grid gap-3 md:grid-cols-2"><div className="rounded-xl border border-slate-700 bg-slate-950/40 p-4"><div className="eyebrow">Existing fact</div><p className="mt-3 text-lg">{alert.existing_value}</p><p className="muted mt-3 break-all text-xs">{alert.existing_source}</p></div><div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4"><div className="eyebrow">New evidence</div><p className="mt-3 text-lg">{alert.new_value}</p><p className="muted mt-3 break-all text-xs">{alert.new_source}</p></div></div><p className="muted mt-4 text-sm">Reason: {alert.reason} · Rule confidence: {Math.round(alert.confidence * 100)}%</p>{alert.status === 'pending' && <div className="mt-5 flex flex-wrap gap-2"><button disabled={busy === alert.id} onClick={() => void resolve(alert.id, 'accept_update')} className="button">Accept Update</button><button disabled={busy === alert.id} onClick={() => void resolve(alert.id, 'keep_existing')} className="button-secondary">Keep Existing</button><button disabled={busy === alert.id} onClick={() => void resolve(alert.id, 'keep_both')} className="button-secondary">Keep Both</button></div>}</article>)}</div>}
      <footer className="muted mt-12 border-t border-slate-800 pt-5 text-xs">NeuroVault + Synapse V0 · local-only demo · data saved under backend/data</footer>
    </main>
  </div>
}
