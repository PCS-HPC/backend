# MONHPC Backend

> FastAPI backend for the MCS-17 HPC cluster web platform — part of a Final Year Project building a full-stack, AI-integrated high-performance computing system.

## Overview

This is the REST API server that sits between the MONHPC frontend and the cluster infrastructure. It handles authentication, Slurm job management, BeeGFS file operations, AI chat integration, cluster node monitoring, and a credit system for resource accounting — all built with **FastAPI** on **Python 3.12**.

---

## Features

### Authentication & Sessions
- JWT-based login with `argon2` password hashing
- Idle session timeout with activity tracking (configurable, default 30 min)
- Token blacklisting on logout (TTL-indexed in MongoDB)
- Monash University email username derivation:
  - `@student.monash.edu` → 8-character student ID (`user` role)
  - `@monash.edu` → local-part username (`admin` role on self-registration)
- Role-based access (`user`, `staff`, `admin`)
- New accounts receive a default credit balance of **5000**

### Slurm Job Management
- List jobs for a user (or all users if admin) via `sacct`
- Filter by status: Running, Pending, Completed, Failed, Cancelled
- Filter by date range (`start_date`, `end_date`) or rolling window (`days`, default 7)
- Per-job detail: CPUs, GPUs, memory requested/used, runtime, exit code, node list
- stdout/stderr preview (last 200 lines) and full file download
- Uses `sacct --json` for accurate expanded output/error paths

### Job Submission
- Multi-field Slurm script generation (nodes, tasks, CPUs, GPUs, memory, walltime)
- File staging: upload supporting files to the user's BeeGFS directory before submission
- Credit cost calculation and balance check before `sbatch`
- Credit deduction and transaction recording on successful submission
- Jobs submitted via `sudo -u <username> sbatch` from the user's storage directory
- Credit rates: **1 GPU = 10 cr/hr**, **1 CPU = 1 cr/hr**, **1 GB RAM = 0.1 cr/hr** (multiplied by walltime)

### BeeGFS File Management
- Per-user directory rooted at `LOCAL_STORAGE_DIR/<username>` (defaults to `./storage` in dev)
- List directory contents (files + folders, sorted)
- Upload files with optional overwrite
- Create folders (with ownership set via `chown` to the OS user)
- Download files
- Delete files or folders (recursive delete requires explicit flag)
- Path traversal protection (`..`, absolute paths, and reserved characters all rejected)

### AI Chat
- Proxies requests to the NemoClaw LangGraph AI cluster (`AI_CLUSTER_URL`)
- Conversation history fetched from the AI cluster (`/api/v1/history/...`), not stored in MongoDB
- LLM response sanitization (strips structural channel tags before returning to the frontend)
- File attachments uploaded to BeeGFS and passed as paths in the prompt to the AI agent
- MCP-authenticated credit charge/refund endpoints for the AI agent (`/api/credits/...`)

### Cluster Node Monitoring
- Worker node summaries from Prometheus (CPU, memory, GPU utilisation, uptime, online status)
- Per-node deep-dive metrics (GPU telemetry, core count, memory breakdown)
- CPU model lookup via SSH (`asyncssh`) for detailed hardware info
- Whitelisted worker IPs configured in `service/nodes.py`

### Admin
- List users with `user` or `staff` role (admin accounts excluded from listing)
- Credit balance management (`set`, `add`, `deduct`) with audit logging

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
| SSH | `asyncssh` (node hardware queries) |
| Observability | OpenTelemetry + Prometheus |
| Deployment | systemd unit (`monhpc-backend.service`) |

---

## Prerequisites

- Python 3.12
- A running MongoDB instance
- Access to the Slurm cluster (`sacct`, `sbatch` available on the host; backend runs `sbatch` via `sudo`)
- BeeGFS mounted and accessible at the configured storage path
- *(Optional)* OpenLDAP for centralised user directory
- *(Optional)* Prometheus with node/GPU exporters for cluster node endpoints
- *(Optional)* SSH access to worker nodes for CPU model lookup

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

# MCP token (Bearer auth for /api/credits/* endpoints used by the AI agent)
MCP_TOKEN=your-mcp-token-here

# File storage (BeeGFS mount point for user files)
LOCAL_STORAGE_DIR=/mnt/beegfs/user

# OpenLDAP (set to 'true' to enable)
LDAP_ACTIVATED=false
LDAP_DOMAIN=ldap://localhost
LDAP_ADMIN_USER=cn=admin,dc=example,dc=com
LDAP_ADMIN_PASSWORD=admin-password
LDAP_BASE_DN=dc=example,dc=com

# Cluster node monitoring
PROMETHEUS_URL=http://localhost:9090
SSH_USERNAME=cluster-admin
SSH_PASSWORD=ssh-password

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

### Production Deployment (systemd)

Production runs as a systemd service, not Docker. The unit file lives at `monhpc-backend.service`.

1. Clone the repo and create a virtualenv on the cluster node:

```bash
sudo mkdir -p /opt/monhpc
sudo git clone <repo-url> /opt/monhpc/backend
cd /opt/monhpc/backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Create `/opt/monhpc/backend/.env` (see [Environment Variables](#environment-variables) above).

3. Edit `monhpc-backend.service` if your install path differs from `/opt/monhpc/backend`, then install the unit:

```bash
sudo cp monhpc-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now monhpc-backend
```

4. Verify:

```bash
systemctl status monhpc-backend
journalctl -u monhpc-backend -f
curl http://127.0.0.1:8000/docs
```

The service runs as **root** so it can execute `sudo -u <username> sbatch` and set BeeGFS file ownership. Restrict file permissions on `.env` accordingly (`chmod 600`).

To restart after code or config changes:

```bash
sudo systemctl restart monhpc-backend
```

---

## API Reference

All routes are prefixed with `/api` unless noted.

### Auth & Users

| Method | Path | Auth | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/auth/login` | — | Login — returns JWT access token |
| `POST` | `/api/auth/logout` | Bearer | Logout — blacklists the current token |
| `GET` | `/api/auth/me` | Bearer | Get current authenticated user |
| `POST` | `/api/users/` | — | Register a new user (Monash email only) |

### Slurm Jobs

| Method | Path | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/slurm/jobs` | Bearer | List jobs (filter by `status`, `days`, `start_date`, `end_date`) |
| `GET` | `/api/slurm/jobs/{job_id}` | Bearer | Get a single job's details |
| `GET` | `/api/slurm/stats` | Bearer | Aggregate job stats for current user |
| `GET` | `/api/slurm/jobs/{job_id}/output` | Bearer | Preview last 200 lines of stdout |
| `GET` | `/api/slurm/jobs/{job_id}/error` | Bearer | Preview last 200 lines of stderr |
| `GET` | `/api/slurm/jobs/{job_id}/output/download` | Bearer | Download full stdout file |
| `GET` | `/api/slurm/jobs/{job_id}/error/download` | Bearer | Download full stderr file |
| `POST` | `/api/jobs/submit` | Bearer | Submit a Slurm job (multipart: `job_params` JSON + optional files) |

### Files

| Method | Path | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/files/` | Bearer | List user's BeeGFS directory |
| `POST` | `/api/files/folders` | Bearer | Create a folder |
| `POST` | `/api/files/upload` | Bearer | Upload a file |
| `GET` | `/api/files/download` | Bearer | Download a file |
| `DELETE` | `/api/files/` | Bearer | Delete a file or folder |

### AI Chat

| Method | Path | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/ai/convo` | Bearer | List user's AI conversations |
| `POST` | `/api/ai/convo` | Bearer | Start a new AI conversation (multipart: `message` + optional files) |
| `GET` | `/api/ai/convo/{convo_id}` | Bearer | Get conversation + dialogue history |
| `POST` | `/api/ai/convo/{convo_id}` | Bearer | Continue an existing conversation |
| `DELETE` | `/api/ai/convo/{convo_id}` | Bearer | Delete a conversation |

### Credits (MCP / AI agent)

These endpoints require `Authorization: Bearer <MCP_TOKEN>`, not a user JWT.

| Method | Path | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/credits/balance?user_id=<username>` | MCP | Get a user's credit balance |
| `POST` | `/api/credits/charge` | MCP | Deduct credits (body: `user_id`, `amount`, `job_id`) |
| `POST` | `/api/credits/refund` | MCP | Refund credits (body: `user_id`, `amount`, `job_id`) |

### Admin

| Method | Path | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/admin/users` | Admin | List users (`user` / `staff` roles) |
| `PATCH` | `/api/admin/users/{username}/credits` | Admin | Set, add, or deduct a user's credit balance |

### Cluster Nodes

These endpoints are currently **unauthenticated**.

| Method | Path | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/nodes` | — | List worker node summaries (Prometheus) |
| `GET` | `/api/nodes/{node_id}` | — | Detailed metrics for a single worker node |

### Observability

| Method | Path | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/metrics` | — | Prometheus metrics scrape endpoint |

---

## Project Structure

```
backend/
├── src/
│   ├── main.py                    # App entry point, middleware, lifespan (MongoDB + LDAP init)
│   ├── utils.py                   # PrometheusMiddleware, OTLP setup
│   ├── api/
│   │   ├── api.py                 # Router registration
│   │   └── endpoints/
│   │       ├── auth.py            # Login, logout, JWT creation/validation, session management
│   │       ├── users.py           # User registration
│   │       ├── admin.py           # Admin user listing and credit management
│   │       ├── ai.py              # AI conversation endpoints (proxy to AI cluster)
│   │       ├── ai_credits.py      # MCP credit charge/refund endpoints
│   │       ├── files.py           # BeeGFS file manager endpoints
│   │       ├── slurm.py           # Slurm job query endpoints
│   │       ├── submit.py          # Job submission endpoint
│   │       └── nodes.py           # Cluster node monitoring endpoints
│   └── service/
│       ├── ai.py                  # AI cluster proxy: chat, history, response sanitization
│       ├── slurm.py               # sacct wrapper: job listing, parsing, formatting
│       ├── slurm_submit.py        # sbatch wrapper: script generation, cost calculation, submission
│       ├── file.py                # File service: safe path resolution, uploads, ownership
│       ├── ldap.py                # OpenLDAP integration
│       ├── credits.py             # Credit balance, charge/refund, transaction recording
│       └── nodes.py               # Prometheus + SSH node metrics
├── monhpc-backend.service         # systemd unit for production deployment
├── requirements.txt               # Pinned Python dependencies
├── log_config.json                # Uvicorn structured logging config
├── example_job.json               # Example sacct --json output (for reference)
└── .python-version                # pyenv local version marker
```

---

## MongoDB Collections

| Collection | Purpose |
| :--- | :--- |
| `users` | User accounts (`email`, `username`, `passwordHash`, `role`, `status`, `creditBalance`) |
| `sessions` | Active JWT sessions with idle timeout tracking (TTL index on `expiresAt`) |
| `blacklisted_tokens` | Logged-out tokens (TTL index on `expiresAt`) |
| `credit_transactions` | Credit deduction/addition/refund audit log (job submissions, admin changes, AI agent) |
| `slurm_jobs` | Slurm job IDs linked to credit amounts and user IDs |

AI conversation history is stored by the NemoClaw AI cluster, not in this backend's MongoDB.

---

## Notes

- CORS is currently set to allow all origins (`*`). Restrict this for production.
- The `LDAP_ACTIVATED` flag controls whether the LDAP connection is initialised at startup and whether new registrations also create an OpenLDAP entry. If disabled, user records are managed through MongoDB directly.
- Credit costs for job submission are calculated in `service/slurm_submit.py` based on requested CPUs, GPUs, memory, and walltime.
- Cluster node endpoints query a hardcoded worker IP whitelist in `service/nodes.py`; update `WORKER_NODES` when the cluster topology changes.
- Job submission requires the backend process to have passwordless `sudo -u <username> sbatch` access for cluster users.
- The `/api/nodes` endpoints do not require authentication — consider adding auth before exposing in production.
