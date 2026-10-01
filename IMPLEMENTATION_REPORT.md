# NeuroVault + Synapse V0 — implementation report

## Works

- PDF, DOCX, and UTF-8 TXT extraction with file validation and limits; extracted text, metadata, chunks, 384-dimensional embeddings, and structured memory are kept in SQLite.
- Local `all-MiniLM-L6-v2` embeddings, FAISS similarity search rebuilt from SQLite after restart, and a local Ollama Q&A path with validated source citations and a clear missing-model message.
- Deterministic ChangeGuard classifications: new, duplicate, related, potential update, and contradiction. Potential updates and contradictions create pending alerts. Accept Update, Keep Existing, and Keep Both are explicit, persisted decisions.
- A React dashboard for documents, source inspection, questions, memory, and Synapse alerts. The two synthetic sample files demonstrate a deadline extension.

## Verified here

- Backend: **19 tests passed** on Python 3.12, with one upstream test-client deprecation warning; `pip check` reported no broken requirements.
- Frontend: `npm run typecheck` and `npm run build` passed.
- Real embedding model loaded from cache and produced a normalized `(1, 384)` vector. A synthetic two-file integration run with real embeddings and FAISS produced a `POTENTIAL_UPDATE`, a cited mock answer, and persisted documents/alert after service restart.
- Uvicorn localhost HTTP smoke test returned `200` for health and dashboard; health explained the missing Ollama model. The staged source files passed a credential-pattern and accidental-binary scan. Release ZIP is checked separately for excluded artifacts.
- `npm audit` and a local Python dependency audit found **zero known advisories** with the final pinned versions in this test environment.

## Not verified here

- Ollama is not installed in this environment. Live Qwen output and answer quality have not been tested; automated Q&A tests use a mock local LLM.
- Windows installation and UI click-through need to be confirmed on the target laptop. The included setup commands were checked against the project scripts and dependency versions.

## Known limits

- No OCR; structured facts use a narrow English rule set. Retrieval uses four excerpts and a simple similarity cutoff.
- A memory decision does not erase an uploaded document: Q&A can still retrieve conflicting source text. Check sources when facts are disputed. No authentication; keep all services bound to localhost.

## Next commands on Windows

From the extracted project folder, use three PowerShell terminals:

```powershell
# Terminal 1 — backend
cd .\backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2 — local model (install and start Ollama first)
ollama pull qwen2.5:3b
```

```powershell
# Terminal 3 — frontend
cd .\frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`, upload both files from `sample-data`, review Synapse Alerts, ask the sample question, then restart the backend to verify persistence. See README for detailed setup, Python 3.12 fallback, tests, and security notes.
