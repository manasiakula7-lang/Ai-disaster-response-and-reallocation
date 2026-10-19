# How to run the system on Windows (backend → dashboard)

You need 3 terminals at the end: one for the backend, one for the dashboard, and the browser. Commands are for **PowerShell**. All of this was checked on a fresh copy of the repo.

---

## Part 1: one-time setup

### Step 1. Install the tools (skip any you already have)

| Tool | Where | Notes |
|---|---|---|
| **Git** | https://git-scm.com/download/win | defaults are fine |
| **Python 3.11 or 3.12** | https://www.python.org/downloads/ | tick **"Add python.exe to PATH"** on the first screen |
| **Node.js LTS** (20 or 22) | https://nodejs.org | defaults are fine |
| **PostgreSQL 16** | https://www.postgresql.org/download/windows/ (EDB installer) | see Step 2 |

Close and reopen PowerShell after installing, then check:

```powershell
git --version
python --version
node --version
```

### Step 2. Install PostgreSQL with PostGIS

1. Run the PostgreSQL 16 installer. Keep the defaults, port **5432**. Choose a password for the `postgres` user and **write it down**.
2. At the end, leave **"Launch Stack Builder"** ticked and click Finish.
3. In Stack Builder, pick **"PostgreSQL 16 on port 5432"**, then **Spatial Extensions → PostGIS 3.x Bundle**. Click Next and install it, saying Yes to the questions.

> Missed Stack Builder? Open it from the Start menu (PostgreSQL 16 → Application Stack Builder).

### Step 3. Create the project database

Open **"SQL Shell (psql)"** from the Start menu (PostgreSQL 16 folder). Press Enter at every prompt until it asks for the password, then type the `postgres` password from Step 2. Paste these lines:

```sql
CREATE USER relief WITH PASSWORD 'relief' SUPERUSER;
CREATE DATABASE relief OWNER relief;
\q
```

(The backend expects user `relief`, password `relief`, database `relief`. This is only for your laptop.)

### Step 4. Get the code

```powershell
cd $HOME\Downloads
git clone https://github.com/manasiakula7-lang/Ai-disaster-response-and-reallocation.git
cd Ai-disaster-response-and-reallocation
```

If you already cloned it earlier, update it instead: `cd` into the folder and run `git pull`.

### Step 5. Python environment for the backend

From the repo folder:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

- If `Activate.ps1` gives a "running scripts is disabled" error, run this once and then try again:
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
- The install downloads PyTorch, so it can take 5-10 minutes.
- Your prompt now starts with `(.venv)`. Activate it like this every time you open a new terminal for the backend.

### Step 6. Load the data into the database

```powershell
python -m backend.app.load
```

You should see a table count ending with lines like `roads 21` and `severity 364`. That's every district map, centre, tweet and result from Steps 0-6, now in PostGIS.

**Optional check:** `python -m pytest backend\tests -q` should print `12 passed`.

### Step 7. Install the dashboard

```powershell
cd frontend
npm install
cd ..
```

---

## Part 2: run it (every time)

### Terminal 1: backend

```powershell
cd $HOME\Downloads\Ai-disaster-response-and-reallocation
.venv\Scripts\Activate.ps1
uvicorn backend.app.main:app --reload
```

Leave it running. Check it in the browser:
- http://localhost:8000/health should show `"status":"ok"`
- http://localhost:8000/docs lists every endpoint, and you can try them there.

### Terminal 2: dashboard

```powershell
cd $HOME\Downloads\Ai-disaster-response-and-reallocation\frontend
npm run dev
```

### Browser

Open **http://localhost:5173**. You should see the Kerala map with the day buttons.

**To stop:** press `Ctrl + C` in each terminal.

---

## A 2-minute demo path

1. **Overview:** click Day 1 → Day 3. The districts darken as the flood peaks (Alappuzha, Ernakulam).
2. **Alerts & events:** turn on "Reports" to see the real tweets that drove replanning.
3. **Results:** switch between "Demand met" and "Worst-off district". The AI agents are fairest, and the optimiser meets slightly more demand.
4. **Simulate:** Start week → Play day 1 → close "Alappuzha – Kottayam" → Play to end. Set "Colour by" to "Share of need met".
5. **What-if:** set stock to 50% and click Run what-if.

---

## If something goes wrong

| Problem | Fix |
|---|---|
| `connection refused` / `could not connect to server` when loading | PostgreSQL isn't running. Open Services (Win+R → `services.msc`) and start **postgresql-x64-16**. |
| `password authentication failed for user "relief"` | Step 3 wasn't run, or the password differs. Redo Step 3. |
| `extension "postgis" is not available` | PostGIS isn't installed. Redo Step 2.3 (Stack Builder). |
| `ModuleNotFoundError` | The venv isn't active (no `(.venv)` in the prompt). Run `.venv\Scripts\Activate.ps1`. |
| `No module named backend` | You're not in the repo folder. `cd` to `Ai-disaster-response-and-reallocation` first. |
| Dashboard says "Can't reach the backend" | Terminal 1 isn't running, or it crashed. Check its output. |
| Port 8000 or 5173 already in use | Close the old terminal, or use `uvicorn backend.app.main:app --port 8001`. Then create `frontend\.env` with `VITE_API_URL=http://localhost:8001` and restart `npm run dev`. |
| Map shows districts but no streets underneath | The street map comes from OpenStreetMap and needs internet. Everything else works offline. |
| `pip install` fails on a network error | Your network blocked PyPI earlier (the getaddrinfo error). Try another network or a phone hotspot. |

## Using Docker instead of installing PostgreSQL (alternative to Steps 1-3)

If you have Docker Desktop: from the repo folder run `docker compose up -d db`, then continue from Step 5. This starts PostgreSQL + PostGIS with the same user, password and database.
