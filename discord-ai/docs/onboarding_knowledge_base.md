# Local Documentation Knowledge Base for Onboarding & Environment Setup

## Environment Setup Guide

### 1. Python Environment Setup
- **Required Python Version:** Python 3.10 or higher.
- **Virtual Environment Creation:**
  ```bash
  python -m venv venv
  # On Windows:
  .\venv\Scripts\activate
  # On macOS/Linux:
  source venv/bin/activate
  ```
- **Installing Dependencies:**
  ```bash
  pip install -r requirements.txt
  ```

### 2. Discord Bot Setup
- Go to [Discord Developer Portal](https://discord.com/developers/applications).
- Create a new Application and add a Bot user.
- Under **Privileged Gateway Intents**, enable **Message Content Intent**.
- Copy the Bot Token into your `.env` file (`DISCORD_TOKEN=...`).
- Invite the bot to your test server with `bot` and `application.commands` scopes.

### 3. Database Configuration
- The project uses **SQLite** (`app.db`) managed via **SQLAlchemy**.
- No additional database server installation is required.

### 4. Common Onboarding Issues & Troubleshooting
- **`ModuleNotFoundError: No module named 'fastapi'`**: Ensure your virtual environment is activated before running the project.
- **Discord Bot not reading messages**: Ensure **Message Content Intent** is enabled in the Discord Developer Portal.
- **Channel Names**: Ensure server channels match `.env` (`onboarding-help` and `doc-approvals`).


### Section: Common Onboarding Issues & Troubleshooting (Admin Approved: 2026-08-30 07:31 UTC)
📚 New Hire FAQ – FastAPI, Python Environment, & Groq Integration  

Last updated: 2026‑08‑30  

---  

1️⃣ Running the FastAPI server (with database connection)

| Situation | Recommended command | Why it helps |
|-----------|---------------------|--------------|
| Standard local development (SQLite or a local PostgreSQL instance) | \n# Activate venv first (see §2)\nuvicorn app.main:app --host 0.0.0.0 --port 8000 --reload\n | `--reload` restarts the server on code changes. |
| Docker‑compose environment (the DB is a separate container) | \n# Ensure the .env file points to the compose network DB URL\ndocker compose up --build\n | Docker will start the API and DB together, handling networking for you. |
| Explicit DB URL override (e.g., you’re using a remote RDS instance) | \nexport DATABASEURL=postgresql://user:password@db-host:5432/dbname\nuvicorn app.main:app --reload\n | Setting `DATABASEURL` before launching forces FastAPI to use the supplied connection string. |

Common “database issue” crash symptoms & quick fixes  

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `psycopg2.OperationalError: could not connect to server` | DB host/port unreachable or wrong credentials | Verify `DATABASE_URL` (or `.env` entry) and that the DB container/service is running. |
| `sqlalchemy.exc.NoSuchTableError` | Migrations haven’t been applied | Run the migration command: `alembic upgrade head` (or `python -m alembic upgrade head`). |
| `sqlite3.OperationalError: database is locked` | Two processes trying to write to the same SQLite file | Stop any stray processes, or switch to PostgreSQL for concurrent dev work. |

---  

2️⃣ Activating the Python virtual environment  

a. Create the environment (once)

From the repository root
python3 -m venv .venv

> Tip: Use the same Python version that the project specifies in `pyproject.toml` / `requirements.txt` (currently 3.11.x).

b. Activate it  

| OS | Command |
|----|---------|
| macOS / Linux | \nsource .venv/bin/activate\n |
| Windows (PowerShell) | \n.venv\Scripts\Activate.ps1\n |
| Windows (cmd.exe) | \n.venv\Scripts\activate.bat\n |

c. Verify activation  

which python   # macOS/Linux → should point to .venv/bin/python
where python   # Windows → should point to .venv\Scripts\python.exe
  

If you see a “permission denied” or “execution policy” error on Windows, run:

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

---  

3️⃣ Installing requirements – pip errors  

Typical error patterns & remedies  

| Error message | Why it happens | Fix |
|---------------|----------------|-----|
| `ERROR: Could not find a version that satisfies the requirement …` | Incompatible Python version or typo in `requirements.txt` | Ensure you’re using Python 3.11+. Run `python -m pip install --upgrade pip` first. |
| `PermissionError: [Errno 13] Permission denied` | Trying to install globally without admin rights | Activate the venv first (see §2) or use `--user`. |
| `Failed building wheel for <package>` | Missing system‑level build tools (e.g., `gcc`, `make`, `libpq-dev`) | Install required dev packages: <br>Ubuntu/Debian: `sudo apt-get install build-essential libpq-dev` <br>macOS: `xcode-select --install` |
| `SSL: CERTIFICATEVERIFYFAILED` | Out‑of‑date `certifi` or corporate MITM proxy | Upgrade certifi: `python -m pip install --upgrade certifi` or configure `PIP_CERT` to point at your corporate cert. |

Recommended install workflow  

1️⃣ Activate venv
source .venv/bin/activate   # (or the Windows equivalent)

2️⃣ Upgrade pip & setuptools (helps avoid many errors)
python -m pip install --upgrade pip setuptools wheel

3️⃣ Install the project deps
pip install -r requirements.txt

If you still hit an error, run the install with `-v` (verbose) to see the exact cause:

pip install -r requirements.txt -v

---  

4️⃣ Generating a Groq API key  

1. Log in to the Groq Console – https://console.groq.com  
2. In the left‑hand navigation, click “API Keys”.  
3. Press “Create New Key”.  
    Give it a descriptive name (e.g., “fastapi‑dev‑key”*).  
   * Choose the appropriate scopes (default “read‑write” is sufficient for most internal services).  
4. Click “Create” – the key will be displayed once only.  
5. Copy the key to a secure location (password manager, secret store, etc.).  

> Never commit the raw key to source control. Use environment variables or a secrets manager instead.

---  

5️⃣ Supplying the Groq API key to your FastAPI service  

Option A – Environment variable (recommended)

export GROQAPIKEY="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
uvicorn app.main:app --reload

Add the variable to your `.env` file (loaded by `python-dotenv` or `pydantic` settings):

.env (do NOT commit!)
GROQAPIKEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx

Option B – Pydantic Settings (if you prefer a config class)

app/config.py
from pydantic import BaseSettings, Field

class Settings(BaseSettings):
    groqapikey: str = Field(..., env="GROQAPIKEY")

    class Config:
        env_file = ".env"

settings = Settings()

Then inject `settings.groqapikey` wherever you instantiate the Groq client.

Option C – Secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.)

Retrieve the secret at startup and set `os.environ["GROQAPIKEY"]` before creating the client.

---  

6️⃣ Groq client model string for Python  

The Groq Python SDK expects the model name as a string. The current production‑grade model is:

model = "mixtral-8x7b-32768"

Example usage:

import groq

client = groq.Groq(
    apikey=os.getenv("GROQAPI_KEY")
)

response = client.chat.completions.create(
    model="mixtral-8x7b-32768",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user",   "content": "Explain the difference between TCP and UDP."}
    ],
    temperature=0.7,
    max_tokens=1024,
)

print(response.choices[0].message.content)

> Note: If Groq releases a newer model, update the string accordingly and bump the version in `requirements.txt` (e.g., `groq>=0.5.0`).  

---  

7️⃣ Quick‑start checklist for a new hire  

1. Clone the repo → `git clone …`  
2. Create & activate venv (see §2).  
3. Install deps (`pip install -r requirements.txt`).  
4. Create a `.env` (copy from `.env.example` and fill in):  
      DATABASE_URL=postgresql://...
   GROQAPIKEY=sk-...
     
5. Run migrations (if applicable): `alembic upgrade head`.  
6. Start the API: `uvicorn app.main:app --reload`.  
7. Verify: `curl http://localhost:8000/health` should return `{"status":"ok"}`.  

---  

📌 Got more questions?

- Slack channel: `#backend-help`  
- Docs repo: https://github.com/your‑org/internal‑docs  
- Groq support: support@groq.com  

Happy coding! 🚀


### Section: Common Onboarding Issues & Troubleshooting (Admin Approved: 2026-08-30 07:37 UTC)
📚 New Hire FAQ – FastAPI, Python Environment, & Groq Integration  

Last updated: 2026‑08‑30  

---  

1️⃣ Running the FastAPI server (with database connection)

| Situation | Recommended command | Why it helps |
|-----------|---------------------|--------------|
| Standard local development (SQLite or a local PostgreSQL instance) | \n# Activate venv first (see §2)\nuvicorn app.main:app --host 0.0.0.0 --port 8000 --reload\n | `--reload` restarts the server on code changes. |
| Docker‑compose environment (the DB is a separate container) | \n# Ensure the .env file points to the compose network DB URL\ndocker compose up --build\n | Docker will start the API and DB together, handling networking for you. |
| Explicit DB URL override (e.g., you’re using a remote RDS instance) | \nexport DATABASEURL=postgresql://user:password@db-host:5432/dbname\nuvicorn app.main:app --reload\n | Setting `DATABASEURL` before launching forces FastAPI to use the supplied connection string. |

Common “database issue” crash symptoms & quick fixes  

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `psycopg2.OperationalError: could not connect to server` | DB host/port unreachable or wrong credentials | Verify `DATABASE_URL` (or `.env` entry) and that the DB container/service is running. |
| `sqlalchemy.exc.NoSuchTableError` | Migrations haven’t been applied | Run the migration command: `alembic upgrade head` (or `python -m alembic upgrade head`). |
| `sqlite3.OperationalError: database is locked` | Two processes trying to write to the same SQLite file | Stop any stray processes, or switch to PostgreSQL for concurrent dev work. |

---  

2️⃣ Activating the Python virtual environment  

a. Create the environment (once)

From the repository root
python3 -m venv .venv

> Tip: Use the same Python version that the project specifies in `pyproject.toml` / `requirements.txt` (currently 3.11.x).

b. Activate it  

| OS | Command |
|----|---------|
| macOS / Linux | \nsource .venv/bin/activate\n |
| Windows (PowerShell) | \n.venv\Scripts\Activate.ps1\n |
| Windows (cmd.exe) | \n.venv\Scripts\activate.bat\n |

c. Verify activation  

which python   # macOS/Linux → should point to .venv/bin/python
where python   # Windows → should point to .venv\Scripts\python.exe
  

If you see a “permission denied” or “execution policy” error on Windows, run:

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

---  

3️⃣ Installing requirements – pip errors  

Typical error patterns & remedies  

| Error message | Why it happens | Fix |
|---------------|----------------|-----|
| `ERROR: Could not find a version that satisfies the requirement …` | Incompatible Python version or typo in `requirements.txt` | Ensure you’re using Python 3.11+. Run `python -m pip install --upgrade pip` first. |
| `PermissionError: [Errno 13] Permission denied` | Trying to install globally without admin rights | Activate the venv first (see §2) or use `--user`. |
| `Failed building wheel for <package>` | Missing system‑level build tools (e.g., `gcc`, `make`, `libpq-dev`) | Install required dev packages: <br>Ubuntu/Debian: `sudo apt-get install build-essential libpq-dev` <br>macOS: `xcode-select --install` |
| `SSL: CERTIFICATEVERIFYFAILED` | Out‑of‑date `certifi` or corporate MITM proxy | Upgrade certifi: `python -m pip install --upgrade certifi` or configure `PIP_CERT` to point at your corporate cert. |

Recommended install workflow  

1️⃣ Activate venv
source .venv/bin/activate   # (or the Windows equivalent)

2️⃣ Upgrade pip & setuptools (helps avoid many errors)
python -m pip install --upgrade pip setuptools wheel

3️⃣ Install the project deps
pip install -r requirements.txt

If you still hit an error, run the install with `-v` (verbose) to see the exact cause:

pip install -r requirements.txt -v

---  

4️⃣ Generating a Groq API key  

1. Log in to the Groq Console – https://console.groq.com  
2. In the left‑hand navigation, click “API Keys”.  
3. Press “Create New Key”.  
    Give it a descriptive name (e.g., “fastapi‑dev‑key”*).  
   * Choose the appropriate scopes (default “read‑write” is sufficient for most internal services).  
4. Click “Create” – the key will be displayed once only.  
5. Copy the key to a secure location (password manager, secret store, etc.).  

> Never commit the raw key to source control. Use environment variables or a secrets manager instead.

---  

5️⃣ Supplying the Groq API key to your FastAPI service  

Option A – Environment variable (recommended)

export GROQAPIKEY="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
uvicorn app.main:app --reload

Add the variable to your `.env` file (loaded by `python-dotenv` or `pydantic` settings):

.env (do NOT commit!)
GROQAPIKEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx

Option B – Pydantic Settings (if you prefer a config class)

app/config.py
from pydantic import BaseSettings, Field

class Settings(BaseSettings):
    groqapikey: str = Field(..., env="GROQAPIKEY")

    class Config:
        env_file = ".env"

settings = Settings()

Then inject `settings.groqapikey` wherever you instantiate the Groq client.

Option C – Secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.)

Retrieve the secret at startup and set `os.environ["GROQAPIKEY"]` before creating the client.

---  

6️⃣ Groq client model string for Python  

The Groq Python SDK expects the model name as a string. The current production‑grade model is:

model = "mixtral-8x7b-32768"

Example usage:

import groq

client = groq.Groq(
    apikey=os.getenv("GROQAPI_KEY")
)

response = client.chat.completions.create(
    model="mixtral-8x7b-32768",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user",   "content": "Explain the difference between TCP and UDP."}
    ],
    temperature=0.7,
    max_tokens=1024,
)

print(response.choices[0].message.content)

> Note: If Groq releases a newer model, update the string accordingly and bump the version in `requirements.txt` (e.g., `groq>=0.5.0`).  

---  

7️⃣ Quick‑start checklist for a new hire  

1. Clone the repo → `git clone …`  
2. Create & activate venv (see §2).  
3. Install deps (`pip install -r requirements.txt`).  
4. Create a `.env` (copy from `.env.example` and fill in):  
      DATABASE_URL=postgresql://...
   GROQAPIKEY=sk-...
     
5. Run migrations (if applicable): `alembic upgrade head`.  
6. Start the API: `uvicorn app.main:app --reload`.  
7. Verify: `curl http://localhost:8000/health` should return `{"status":"ok"}`.  

---  

📌 Got more questions?

- Slack channel: `#backend-help`  
- Docs repo: https://github.com/your‑org/internal‑docs  
- Groq support: support@groq.com  

Happy coding! 🚀
