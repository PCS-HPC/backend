# MONHPC Backend

> FastAPI backend for the MCS-17 HPC cluster web platform — part of a Final Year Project building a full-stack, AI-integrated high-performance computing system.

## Overview

This is the REST API server that sits between the MONHPC frontend and the cluster infrastructure. It handles authentication, Slurm job management, BeeGFS file operations, AI chat integration, and a credit system for resource accounting — all built with **FastAPI** on **Python 3.12**.

---

## Features

### Authentication & Sessions
- JWT-based login with `argon2` password hashing
- Idle session timeout with activity tracking (configurable, default 30 min)
- Token blacklisting on logout (TTL-indexed in MongoDB)
- Monash University email username derivation (`@student.monash.edu` → 8-char student ID)
- Role-based access (`user` / `admin`)

### Slurm Job Management
- List all jobs for a user (or all users if admin) via `sacct`
- Filter by status: Running, Pending, Completed, Failed, Cancelled
- Per-job detail: CPUs, GPUs, memory requested/used, runtime, exit code, node list
- stdout/stderr preview (last 200 lines) and full file download
- Uses `sacct --json` for accurate expanded output/error paths

### Job Submission
- Multi-field Slurm script generation (nodes, tasks, CPUs, GPUs, memory, walltime)
- File staging: upload supporting files to the user's BeeGFS directory before submission
- Credit cost calculation and balance check before `sbatch`
- Credit deduction and transaction recording on successful submission

### BeeGFS File Management
- Per-user directory rooted at `LOCAL_STORAGE_DIR/<username>`
- List directory contents (files + folders, sorted)
- Upload files with optional overwrite
- Create folders (with ownership set via `chown` to the OS user)
- Download files
- Delete files or folders (recursive delete requires explicit flag)
- Path traversal protection (`..`, absolute paths, and reserved characters all rejected)

### AI Chat
- Proxies requests to the NemoClaw LangGraph AI cluster (`AI_CLUSTER_URL`)
- Conversation and dialogue history stored in MongoDB
- Context window management: token estimation via Gemma 4 tokenizer API, automatic summarization when the context approaches 90k tokens
- Unsafe messages returned immediately without being saved
- File attachments passed as BeeGFS paths to the AI agent

### Admin
- User listing, creation, role and status updates
- Credit balance management and transaction history

### Observability
- Prometheus metrics endpoint (`/metrics`) via custom `PrometheusMiddleware`
- OpenTelemetry tracing with OTLP export (`OTLP_ENDPOINT`)
- Structured JSON logging via `log_config.json`

---

## Tech Stack

| Layer | Technology |
| :--- | :--- |
| Framework | FastAPI |
| Python version | 3.12 |
| Database | MongoDB (via PyMongo) |
| Auth | JWT (`PyJWT`) + Argon2 password hashing |
| LDAP | `ldap3` (OpenLDAP integration, optional) |
| HTTP client | `httpx` (async) |
| Observability | OpenTelemetry + Prometheus |
| Container | Docker / Docker Compose |

---

## Prerequisites

- Python 3.12
- A running MongoDB instance
- Access to the Slurm cluster (`sacct`, `sbatch` available on the host)
- BeeGFS mounted and accessible at the configured storage path
- *(Optional)* OpenLDAP for centralised user directory

---

## Environment Variables

Create a `.env` file in the project root:

```env
# MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=monhpc

# JWT
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

# Session
SESSION_IDLE_TIMEOUT_MINUTES=30

# AI cluster
AI_CLUSTER_URL=http://<ai-node-ip>:<port>

# File storage (BeeGFS mount point for user files)
LOCAL_STORAGE_DIR=/mnt/beegfs/user

# OpenLDAP (set to 'true' to enable)
LDAP_ACTIVATED=false

# Observability
APP_NAME=monhpc-backend
OTLP_ENDPOINT=http://localhost:4317
```

---

## Getting Started

### Local Development

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the development server
fastapi dev src/main.py
```

The API will be available at `http://127.0.0.1:8000`.  
Interactive docs: `http://127.0.0.1:8000/docs`

### Docker

```bash
docker compose up --build
```

The container exposes port `8000` and picks up environment variables from your `.env` file.

---

## API Reference

All routes are prefixed with `/api`.

| Method | Path | Description |
| :--- | :--- | :--- |
| `POST` | `/api/auth/login` | Login — returns JWT access token |
| `POST` | `/api/auth/logout` | Logout — blacklists the current token |
| `GET` | `/api/auth/me` | Get current authenticated user |
| `POST` | `/api/users/` | Register a new user |
| `GET` | `/api/slurm/jobs` | List Slurm jobs (filtered by status/days) |
| `GET` | `/api/slurm/jobs/{job_id}` | Get a single job's details |
| `GET` | `/api/slurm/stats` | Aggregate job stats |
| `GET` | `/api/slurm/jobs/{job_id}/output` | Preview last 200 lines of stdout |
| `GET` | `/api/slurm/jobs/{job_id}/error` | Preview last 200 lines of stderr |
| `GET` | `/api/slurm/jobs/{job_id}/output/download` | Download full stdout file |
| `GET` | `/api/slurm/jobs/{job_id}/error/download` | Download full stderr file |
| `POST` | `/api/jobs/submit` | Submit a Slurm job (with optional file upload) |
| `GET` | `/api/files/` | List user's BeeGFS directory |
| `POST` | `/api/files/folders` | Create a folder |
| `POST` | `/api/files/upload` | Upload a file |
| `GET` | `/api/files/download` | Download a file |
| `DELETE` | `/api/files/` | Delete a file or folder |
| `GET` | `/api/ai/convo` | List user's AI conversations |
| `POST` | `/api/ai/convo` | Start a new AI conversation |
| `GET` | `/api/ai/convo/{convo_id}` | Get conversation + dialogue history |
| `POST` | `/api/ai/convo/{convo_id}` | Continue an existing conversation |
| `DELETE` | `/api/ai/convo/{convo_id}` | Delete a conversation |
| `GET` | `/api/ai/convo/{convo_id}/context` | Get current context window usage |
| `GET` | `/api/admin/users` | List all users (admin only) |
| `GET` | `/api/credits/` | Get credit transaction history |
| `GET` | `/metrics` | Prometheus metrics scrape endpoint |

---

## Project Structure

```
backend-main/
├── src/
│   ├── main.py                    # App entry point, middleware, lifespan (MongoDB + LDAP init)
│   ├── utils.py                   # PrometheusMiddleware, OTLP setup
│   ├── api/
│   │   ├── api.py                 # Router registration
│   │   └── endpoints/
│   │       ├── auth.py            # Login, logout, JWT creation/validation, session management
│   │       ├── users.py           # User registration
│   │       ├── admin.py           # Admin user management
│   │       ├── ai.py              # AI conversation endpoints
│   │       ├── ai_credits.py      # Credit transaction endpoints
│   │       ├── files.py           # BeeGFS file manager endpoints
│   │       ├── slurm.py           # Slurm job query endpoints
│   │       └── submit.py          # Job submission endpoint
│   └── service/
│       ├── ai.py                  # AI service: prompt building, context management, summarization
│       ├── slurm.py               # sacct wrapper: job listing, parsing, formatting
│       ├── slurm_submit.py        # sbatch wrapper: script generation, job submission
│       ├── file.py                # File service: safe path resolution, uploads, ownership
│       ├── ldap.py                # OpenLDAP integration
│       └── credits.py             # Credit calculation and transaction recording
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── log_config.json                # Uvicorn structured logging config
├── example_job.json               # Example sacct --json output (for reference)
└── .python-version                # Pins Python 3.12
```

---

## MongoDB Collections

| Collection | Purpose |
| :--- | :--- |
| `users` | User accounts (email, passwordHash, role, status, creditBalance) |
| `sessions` | Active JWT sessions with idle timeout tracking |
| `blacklisted_tokens` | Logged-out tokens (TTL index on `expiresAt`) |
| `conversations` | AI conversation metadata (title, owner, summary) |
| `dialogues` | Individual AI chat messages per conversation |
| `slurm_jobs` | Credit amounts linked to submitted Slurm job IDs |
| `transactions` | Credit deduction/addition audit log |

---

## Notes

- The `requirements.txt` only pins `httpx` and a few core packages — run `pip freeze > requirements.txt` after adding new dependencies.
- CORS is currently set to allow all origins (`*`). Restrict this for production.
- The `LDAP_ACTIVATED` flag controls whether the LDAP connection is initialised at startup. If disabled, user records are managed through MongoDB directly.
- Credit costs are calculated in `service/credits.py` based on requested CPUs, GPUs, and walltime.
