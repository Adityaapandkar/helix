# Helix Orchestrator API Server

FastAPI server that exposes the Helix multi-agent pipeline over HTTP and streams progress to clients with Server-Sent Events (SSE).

## Directory Structure

```
server/
├── __init__.py
├── app.py             # FastAPI app, CORS config, exception handlers, router wiring
├── run.py             # CLI launcher (uvicorn)
└── routes/
    ├── __init__.py
    ├── health.py      # GET / and GET /health
    ├── prompt.py      # POST /api/process — starts an orchestration run in the background
    └── stream.py      # GET /api/stream/{stream_id} (SSE), GET /api/pdb/{pdb_type}
```

## Routes

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/` | API status |
| `GET`  | `/health` | Health check |
| `POST` | `/api/process` | Body `{"prompt": "P0DP25"}`. Starts a run, returns `{"status": "success", "result": {"stream_id": "..."}}` |
| `GET`  | `/api/stream/{stream_id}` | SSE stream of `progress`, `log`, `protein_properties`, `receptor_pdb`, `binding_sites`, `molecule_properties`, `docking_results`, `keep_alive`, `status_update` and `complete` events |
| `GET`  | `/api/pdb/{receptor\|ligand\|docking}` | Raw PDB/PDBQT text for a finished run (`?stream_id=` optional, defaults to the latest stream) |

## Running the Server

```bash
# From backend/
python -m server.run

# With custom parameters
python -m server.run --host 127.0.0.1 --port 9000 --reload --log-level debug
```

## API Documentation

Once the server is running:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
