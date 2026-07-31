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

## Step 2: Start CASCADE

### Option A — Universal launcher (recommended, requires Python 3.11+)

```bash
python compose_up.py
```

This is all you need to run. It will automatically:
- Check for and download any missing data files from GitHub Releases (first run only)
- Create a `.env` config file with a secure secret key
- Pick a free port and start all services via Docker Compose
- Wait for the app to be ready, then open it in your browser

The three data files downloaded on first run (~810 MB total):
- `data/drug_database.sqlite` — 2.89 M compounds
- `data/drug_fingerprints.npz` — fingerprint index
- `app/models/mdrepo_predictor.pt` — trained model weights

Files that already exist are always skipped — downloads only ever happen once.

### Option B — Manual data download + direct Docker (no Python needed)

If you don't have Python, download the data files first:

**Linux / macOS** — open a terminal inside the CASCADE folder:
```bash
bash setup.sh
```

**Windows** — open PowerShell inside the CASCADE folder:
```powershell
.\setup.ps1
```

> **How to open a terminal inside the CASCADE folder:**
> - **Windows 11:** Right-click inside the folder → *Open in Terminal*
> - **Windows 10:** Shift + right-click inside the folder → *Open PowerShell window here*
> - **macOS:** Right-click the folder in Finder → *Services → New Terminal at Folder*
> - **Linux:** Right-click inside the folder → *Open in Terminal*

Then create a `.env` file and start Docker:

```bash
# Linux/macOS
cp .env.example .env
docker compose up -d
```

```powershell
# Windows
Copy-Item .env.example .env
docker compose up -d
```

Then open your browser and go to `http://localhost:7860`.

> **Note:** You must set a real `FLASK_SECRET_KEY` in your `.env` file before starting when using this path. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

---

## Step 3: Create Your Account

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

## Step 4: Shut Down

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

If port 7860 is already in use on your machine, the `compose_up.py` launcher will **automatically scan** and pick the next available port (e.g., 7861, 7862) and open it for you. 

However, if you want to manually hardcode a specific port, you can set it in your `.env` file:

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

### General Issues

| Problem | Fix |
|---|---|
| "Port already in use" | Set `HOST_PORT=8080` (or any free port) in `.env` |
| App starts but shows "model not ready" | Re-run `python compose_up.py` — it will auto-download the model file |
| Drug search returns nothing | Re-run `python compose_up.py` — it will auto-download the database |
| Download failed / incomplete file | Re-run `python compose_up.py` — incomplete files are detected and re-downloaded automatically |
| Docker says "no such service: app" | Make sure you are in the CASCADE folder when running docker commands |
| Ollama commands not working | Confirm Ollama is running on your host and `OLLAMA_ENABLED=1` is in `.env` |
| GPU not detected | Install [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) and add the `deploy` block to `docker-compose.yml` |

---

### OS-Specific Docker Engine Issues

If `python compose_up.py` fails or Docker Desktop is stuck on **"Starting the Docker Engine..."**, find your OS below:

#### Windows

**Fix 1 — Enable Hardware Virtualization (BIOS)**
Docker requires hardware virtualization. Restart your PC, hold `Shift` while clicking "Restart" to access Advanced Options, and boot into your BIOS/UEFI settings. Look for **Virtualization Technology (VT-x)** for Intel or **SVM Mode (AMD-V)** for AMD, and set it to **Enabled**.

**Fix 2 — Turn on Windows Features**
1. Search the Windows Start Menu for **"Turn Windows features on or off"**.
2. Make sure these boxes are checked:
   - **Virtual Machine Platform**
   - **Windows Subsystem for Linux**
   - **Hyper-V** *(Note: Windows Home edition will not have this. Just check the other two).*
3. Restart your PC.

**Fix 3 — Update WSL**
1. Open PowerShell **as Administrator**.
2. Run: `wsl --update`
3. Restart Docker Desktop.

#### macOS

**Fix 1 — Check Background Permissions**
1. Go to **System Settings > General > Login Items** (or Background Items).
2. Ensure any Docker-related toggles are turned **ON**.

**Fix 2 — Allocate More Memory**
PyTorch requires significant RAM. In Docker Desktop, go to **Settings > Resources**. Ensure Docker is allowed to use at least **6 GB to 8 GB of Memory**.

**Fix 3 — Reset Docker Data**
If the app opens but the engine won't start, click the **Bug/Troubleshoot icon** (top right of the Docker window). Click **Clean / Purge data** or **Reset to factory defaults**.

#### Linux

**Fix 1 — Add your user to the Docker group**
If you get a `Permission denied` socket error:
1. Run: `sudo usermod -aG docker $USER`
2. **Log out and log back in** (or restart your computer).

**Fix 2 — Start the Docker Service**
If the daemon isn't running automatically in the background:
1. Run: `sudo systemctl start docker`
2. To make it start on boot: `sudo systemctl enable docker`

---

*For full technical documentation, API reference, and security details — see [README.md](README.md).*
