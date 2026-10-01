# Security and privacy notes — V0

NeuroVault is meant to run on **your own computer**. Start the backend with `--host 127.0.0.1` and use the provided Vite command. Do not port-forward it or bind either service to `0.0.0.0`; there is no authentication. Ollama should also listen on localhost. Other software running as your Windows user may access local files and local ports; browser-origin restrictions are not a substitute for OS isolation.

The backend stores extracted document text, chunks, embeddings, and structured facts in `backend/data/neurovault.sqlite3`. Upload bytes are processed in memory and original binaries are not kept. The database may contain private text. It is ignored by Git and excluded from the release ZIP. Make a private backup of `backend/data` before resetting the project, and remove that folder to start with an empty knowledge base after stopping the server.

The initial embedding model is downloaded by `sentence-transformers` from Hugging Face if absent from the local cache. `pip`, `npm`, and `ollama pull` also access their normal package/model registries during setup. Indexed documents are not sent to those services. Generated questions and retrieved excerpts go to the locally configured Ollama endpoint only. The `OLLAMA_URL` setting permits loopback HTTP endpoints, preventing accidental remote inference configuration.

Files are checked by extension, declared MIME, signature or DOCX archive structure, size, and parser limits. Unknown or image-only content returns a clear error. Processing arbitrary PDF/DOCX files still depends on third-party parsers; keep dependencies updated and avoid indexing files from untrusted sources. FastAPI/Starlette may spool incoming multipart bodies before the handler applies the 10 MiB file limit; a Content-Length limit helps for normal browsers, but V0 is not a hostile-client-facing server.

Document excerpts are untrusted input to the LLM. The system prompt instructs it to ignore instructions found inside documents, and the backend accepts only source markers from retrieved evidence, but prompt injection can still distort an answer. Verify important claims by reading the cited source. Synapse decisions are explicit API actions. `Keep Existing` prevents a new structured memory from being created; it does not delete the uploaded source from retrieval.

No credentials are required. Never put keys, personal documents, `.env`, `backend/data`, virtual environments, `node_modules`, or model weights into Git or a shared ZIP. Review the contents before publishing your own copy.
