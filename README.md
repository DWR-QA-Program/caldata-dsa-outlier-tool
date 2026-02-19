# webapp-testing

Simple PyShiny app for infrastructure testing.

## Run locally with uv (Python 3.10 pinned)

```powershell
uv python install 3.10
uv venv --python 3.10
.\.venv\Scripts\Activate.ps1
uv sync
uv run shiny run --reload --host 127.0.0.1 --port 8081 app.py
```

Open `http://127.0.0.1:8081`.

## Run with Docker

```powershell
docker build -t webapp-testing .
docker run --rm -p 8000:8000 webapp-testing
```

Then open `http://127.0.0.1:8000`.

## Azure Web App startup command

Use `startup.sh` as the startup command.

Example startup command:

```bash
bash /home/site/wwwroot/startup.sh
```