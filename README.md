# Sorkins

A local-first screenwriting workspace. Screenplays and Story Bible entries are stored in a SQLite database on this computer. The editor works without Ollama; local AI is an optional assistant.

## Run on Windows

Requirements: Node.js 20.19+ (or 22.12+) and Python 3.10+.

1. Install frontend packages: `npm install`
2. Install API packages: `python -m pip install -r backend\requirements.txt`
3. In PowerShell, start the API: `.\backend\run.ps1`
4. In another window, start the editor: `npm run dev`
5. Open the Vite URL shown in the terminal (normally `http://localhost:5173`).

On first startup, Alembic creates the database under `backend\data\sorkins.db`. Set `SORKINS_DATA_DIR` to use another directory. To use Ollama, start it separately and configure the API process environment; see [backend/.env.example](./backend/.env.example). Defaults use `qwen3-vl:4b`, CPU inference, a 6,144-token context, low thinking mode, a 4,096-token structured-output limit, and a 1,800-second read timeout. The UI shows streamed assistant text and offers retries for failed requests. No model is downloaded by the app.

## Included in this first implementation

- Project, act, and scene creation; scene selection, deletion, and reordering.
- Structured screenplay elements and local autosave.
- Local Story Bible facts with writer-confirmed status, provenance, editing, and decision history.
- Structured Story Bible sections for characters, relationships, conflicts, locations, and timeline events.
- Optional deterministic continuity review using confirmed entities and explicit timeline positions; writers review every finding.
- Literal premise extraction and deterministic gap questions work without Ollama; structured narrative interpretation uses a configured local Ollama model when available.
- Ollama assistant requests with only confirmed project facts and non-dialogue scene text in context.
- Fountain and plain-text import, Fountain export, and browser print / save-to-PDF.
- A sample project available from the welcome screen.

This is an early usable foundation, not a feature-complete Final Draft replacement. Continuity checks are deliberately narrow: they use exact character cues, confirmed locations, and explicitly comparable timeline positions; they do not infer vague dates, relationship changes, object continuity, or semantic plot holes. Story Bible editing covers the structured fields currently modeled; low-level source-reference metadata and scene-to-event links are not exposed. Premise analysis is conservatively checked against cited premise text, but semantic quality still depends on the selected local model; the benchmarked candidates did not meet the reliability bar. See [DEVELOPMENT.md](./DEVELOPMENT.md) for validation details and known limitations. PDF/DOCX/FDX import, FDX export, true screenplay page-break pagination, and act reordering are not implemented yet.

## Tests

`npm run build` type-checks and builds the frontend. Backend tests: `python -m unittest discover -s backend\tests`.
