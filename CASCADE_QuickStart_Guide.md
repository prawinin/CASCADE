# CASCADE Quick Start Guide

This guide walks you through getting **CASCADE** running on your computer from scratch — no programming experience required. For full technical documentation, see the [README](README.md).

---

## Prerequisites

You need one piece of software before anything else:

- **Docker Desktop** — the engine that runs everything inside isolated containers so you never have to install Python, Redis, or any dependencies manually.
  Download it free from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/).
  After installing, open Docker Desktop and make sure it shows **"Engine running"** in the bottom-left before you continue.

---

## Step 1: Download the Code

### Option A — Point-and-click (easiest)

1. Go to [github.com/prawinin/CASCADE](https://github.com/prawinin/CASCADE)
2. Click the green **`<> Code`** button → **Download ZIP**
3. Extract the ZIP to somewhere convenient (e.g. your Desktop)

### Option B — Terminal (fastest, if you have Git)

```bash
git clone https://github.com/prawinin/CASCADE.git
cd CASCADE
```

---

## Step 2: Download Data Files

CASCADE needs three large files (drug database, fingerprints, trained model) that are too big to include in the code download. Run the script for your operating system — it downloads everything automatically.

**Linux / macOS** — open a terminal inside the CASCADE folder:
```bash
bash setup.sh
```

**Windows** — open PowerShell inside the CASCADE folder:
```powershell
.\setup.ps1
```

If a file already exists it is skipped. The download is about 810 MB total and only happens once.

> **How to open a terminal inside the CASCADE folder:**
> - **Windows 11:** Right-click inside the folder → *Open in Terminal*
> - **Windows 10:** Shift + right-click inside the folder → *Open PowerShell window here*
> - **macOS:** Right-click the folder in Finder → *Services → New Terminal at Folder*
> - **Linux:** Right-click inside the folder → *Open in Terminal*

---

## Step 3: Start CASCADE

### Option A — Universal launcher (recommended, requires Python 3.11+)

```bash
python compose_up.py
```

This automatically:
- Creates a `.env` config file on first run
- Generates a secure secret key for you
- Picks a free port and starts all services
- Opens the app in your browser

### Option B — Direct Docker command

```bash
docker compose up -d
```

Then open your browser and go to `http://localhost:7860`.

> If using Option B for the first time, you must first create a `.env` file:
> - **Linux/macOS:** `cp .env.example .env`
> - **Windows:** `Copy-Item .env.example .env`

---

## Step 4: Create Your Account

On first run, registration is open. Go to `http://localhost:7860` and sign up. Once you have created all the accounts you need, you can close registration so no one else can sign up:

1. Open the `.env` file in any text editor
2. Change this line:
   ```
   REGISTRATION_ENABLED=1
   ```
   to:
   ```
   REGISTRATION_ENABLED=0
   ```
3. Restart the app: `docker compose restart app`

---

## Step 5: Shut Down

When you are done:

```bash
docker compose down
```

Next time you start, Docker reuses the cached build so it starts in seconds.

---

## Advanced Configuration

All settings live in the `.env` file in the CASCADE folder. Open it with any text editor (Notepad, VS Code, etc.) and change values as needed, then restart with `docker compose restart app`.

### Enable GPU inference (NVIDIA)

By default CASCADE runs on CPU. If you have an NVIDIA GPU with CUDA drivers installed:

1. Edit `.env`:
   ```env
   MODEL_DEVICE=cuda
   ```
2. Edit `docker-compose.yml` — add a `deploy` block under the `app` service:
   ```yaml
   services:
     app:
       ...
       deploy:
         resources:
           reservations:
             devices:
               - driver: nvidia
                 count: 1
                 capabilities: [gpu]
   ```
   Do the same for `celery_worker` if you want GPU in background tasks.
3. Restart: `docker compose up -d`

> You must have the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) installed on your host machine.

---

### Enable Ollama (local AI assistant)

Ollama lets you type plain-English commands into the 3D viewer ("show the binding pocket in red", "rotate to face the ligand").

1. Install Ollama from [ollama.com](https://ollama.com)
2. Pull a model:
   ```bash
   ollama pull qwen2.5-coder:7b
   ```
3. Edit `.env`:
   ```env
   OLLAMA_ENABLED=1
   OLLAMA_API_URL=http://host.docker.internal:11434
   OLLAMA_MODEL=qwen2.5-coder:7b
   ```
4. Restart: `docker compose restart app celery_worker`

`host.docker.internal` is a special address that lets the container reach Ollama running on your machine. On Linux you may need to replace it with your host IP (`hostname -I | awk '{print $1}'`).

You can swap the model for any Ollama-compatible one — lighter models like `llama3.2:1b` use less RAM:
```env
OLLAMA_MODEL=llama3.2:1b
```

---

### Enable GNINA docking

GNINA is a deep-learning molecular docking engine. It is not included in the default install.

1. Download the `gnina` binary from [github.com/gnina/gnina/releases](https://github.com/gnina/gnina/releases) and place it in the CASCADE folder
2. Edit `.env`:
   ```env
   GNINA_ENABLED=1
   GNINA_PATH=./gnina
   ```
3. Restart: `docker compose restart app celery_worker`

---

### Change the port

If port 7860 is already in use on your machine:

```env
HOST_PORT=8080
```

Then access the app at `http://localhost:8080`.

---

### Tune performance (CPU / RAM)

| Setting | What it does | Default |
|---|---|---|
| `WEB_CONCURRENCY` | Number of Gunicorn worker processes | `1` |
| `GUNICORN_THREADS` | Threads per worker | `2` |
| `MOLECULE_SIZE_LIMIT` | Max atoms per molecule | `200` |
| `SMILES_LENGTH_LIMIT` | Max SMILES string length | `2000` |

On a machine with 8+ cores and 16 GB RAM you can safely set:
```env
WEB_CONCURRENCY=2
GUNICORN_THREADS=4
```

---

### Store data outside the CASCADE folder

If you want the database files on a different drive or shared path:

```env
CASCADE_DATA_HOST_PATH=/mnt/data/cascade-data
CASCADE_MODELS_HOST_PATH=/mnt/data/cascade-models
```

The paths must exist and be readable by Docker before you start.

---

### Close public registration after setup

```env
REGISTRATION_ENABLED=0
```

Restart with `docker compose restart app`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "Port already in use" | Set `HOST_PORT=8080` (or any free port) in `.env` |
| App starts but shows "model not ready" | Check `app/models/mdrepo_predictor.pt` exists — re-run `setup.sh` |
| Drug search returns nothing | Check `data/drug_database.sqlite` exists — re-run `setup.sh` |
| Docker says "no such service: app" | Make sure you are in the CASCADE folder when running docker commands |
| Ollama commands not working | Confirm Ollama is running on your host and `OLLAMA_ENABLED=1` is in `.env` |
| GPU not detected | Install [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) and add the `deploy` block to `docker-compose.yml` |

---

*For full technical documentation, API reference, and security details — see [README.md](README.md).*
