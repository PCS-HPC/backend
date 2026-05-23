# MONHPC Frontend

> React/TypeScript web interface for the MCS-17 HPC cluster — part of a Final Year Project building a full-stack, AI-integrated high-performance computing platform.

## Overview

This is the user-facing web application for MONHPC. It provides a unified interface for submitting and monitoring Slurm jobs, managing files on the BeeGFS shared filesystem, and interacting with the cluster's AI chat agent — all behind a JWT-authenticated session.

Built with **TanStack Start** (React 19, file-based routing, SSR-capable), **Tailwind CSS v4**, and **Bun** as the runtime and package manager.

---

## Features

### Dashboard
- Live Slurm job table with status filtering (Running, Pending, Completed, Failed, Cancelled)
- Per-job stdout/stderr viewer with inline output preview
- Job stats summary (total jobs, breakdown by status and type)
- Credit balance display per job

### Job Submission
- Multi-step wizard: choose mode → configure script in editor → confirm → submit
- Monaco-style script editor with syntax highlighting
- Confirmation step showing resource summary before submission

### AI Chat
- Conversational interface backed by a LangGraph AI agent
- Safety-checked responses via Llama Guard 4
- Supports attaching files (up to 10 per message) as HPC uploads or chat context
- Conversation history with sidebar navigation between past chats
- Context window usage indicator per conversation
- LaTeX math rendering (KaTeX) and Markdown with syntax highlighting

### Storage (BeeGFS File Manager)
- Browse, upload, download, and delete files/folders on the user's BeeGFS directory (`/mnt/beegfs/user/<user_id>`)
- Path breadcrumb navigation with alias to `/` for the user root
- Quick Look preview modal for text/code/image files
- Multi-select with bulk download (zip) and bulk delete
- Recursive folder upload preserving directory structure
- Right-click context menu with context-aware actions
- High-friction deletion modal to prevent accidental data loss

### Admin Panel
- User management (create, view, update roles and status)
- Credit balance management

### Auth
- JWT-based login with token stored in `localStorage`
- Auto-redirect on session expiry
- Global auth guard in root layout — unauthenticated users see only the login screen

---

## Tech Stack

| Layer | Technology |
| :--- | :--- |
| Framework | [TanStack Start](https://tanstack.com/start) (React 19) |
| Routing | TanStack Router (file-based) |
| Styling | Tailwind CSS v4 |
| Animations | Motion (Framer Motion v12) |
| Markdown | react-markdown + remark-gfm + remark-math + KaTeX |
| Syntax highlighting | react-syntax-highlighter |
| Icons | Lucide React |
| Linting/Formatting | Biome |
| Runtime & Package Manager | Bun |
| Build tool | Vite 8 |
| Testing | Vitest + Testing Library |

---

## Getting Started

### Prerequisites

- [Bun](https://bun.sh) installed (`>= 1.3`)
- A running MONHPC backend (FastAPI) — set the URL via environment variable

### Environment Variables

Create a `.env` file at the project root:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Defaults to `http://127.0.0.1:8000` if not set.

### Install & Run

```bash
bun install
bun --bun run dev
```

The app runs on [http://localhost:3000](http://localhost:3000) by default.

### Build for Production

```bash
bun --bun run build
```

### Preview Production Build

```bash
bun --bun run preview
```

---

## Testing

```bash
bun --bun run test
```

Uses [Vitest](https://vitest.dev/) with jsdom and Testing Library.

---

## Linting & Formatting

This project uses [Biome](https://biomejs.dev/) for linting and formatting:

```bash
bun --bun run lint      # Lint
bun --bun run format    # Format
bun --bun run check     # Lint + format check combined
```

---

## Project Structure

```
frontend-new/
├── api/
│   └── server.js                  # Lightweight local API dev server
├── public/
│   ├── favicon.svg
│   └── manifest.json
├── src/
│   ├── lib/                       # API client modules
│   │   ├── api.ts                 # Base fetch wrapper + ApiError
│   │   ├── auth.ts                # Login, logout, session management
│   │   ├── chat.ts                # AI conversation API
│   │   ├── files.ts               # BeeGFS file manager API
│   │   ├── jobs.ts                # Slurm job API
│   │   ├── submit.ts              # Job submission API
│   │   └── admin.ts               # Admin user management API
│   ├── components/
│   │   └── Sidebar.tsx            # Collapsible nav (Chat, Dashboard, Storage)
│   ├── routes/
│   │   ├── __root.tsx             # Root layout + global auth guard
│   │   ├── index.tsx              # Dashboard (job list + stats)
│   │   ├── login.tsx              # Login page
│   │   ├── chat.tsx               # Chat route wrapper
│   │   ├── chat/
│   │   │   ├── index.tsx          # New conversation / landing
│   │   │   └── $convoId.tsx       # Active conversation view
│   │   ├── submit.tsx             # Job submission wizard
│   │   ├── submit/
│   │   │   ├── -submit.types.ts
│   │   │   └── step/
│   │   │       ├── -ModeStep.tsx
│   │   │       ├── -EditorStep.tsx
│   │   │       ├── -ConfirmStep.tsx
│   │   │       └── -SuccessStep.tsx
│   │   ├── storage.tsx            # BeeGFS file manager
│   │   └── admin.tsx              # Admin panel
│   ├── router.tsx                 # Router setup
│   ├── routeTree.gen.ts           # Auto-generated route tree
│   └── styles.css                 # Global styles + Tailwind import
├── biome.json
├── vite.config.ts
├── tsconfig.json
├── vercel.json                    # Vercel deployment config
└── package.json
```

---

## API Integration

All API calls go through `src/lib/api.ts`, which attaches the JWT `Authorization` header automatically from `localStorage`. The base URL is configured via `VITE_API_BASE_URL`.

Key API modules:

| Module | Backend Prefix | Purpose |
| :--- | :--- | :--- |
| `auth.ts` | `/api/auth` | Login, logout, register |
| `jobs.ts` | `/api/slurm` | List/get/output Slurm jobs |
| `chat.ts` | `/api/ai` | AI conversations and dialogues |
| `files.ts` | `/api/files` | BeeGFS directory + file operations |
| `admin.ts` | `/api/users` | User administration |

---

## Deployment

A `vercel.json` is included for deployment on Vercel. Set `VITE_API_BASE_URL` in the Vercel project environment variables to point to your backend.

For other platforms, the standard Vite build output in `dist/` can be served by any static host or Node server.
