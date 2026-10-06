# Medha

Medha is a full-stack AI chat application. The backend is FastAPI with PostgreSQL, JWT authentication, persistent user-owned conversations, and a LangGraph chat service. The frontend is a Next.js app with sign-in, registration, streaming chat, and a conversation sidebar.

## Current features

- Register, sign in, refresh and revoke sessions.
- Access-token protected user profile and chat endpoints.
- Create, list, read and delete conversations belonging to the signed-in user.
- Store conversation messages in PostgreSQL.
- Stream assistant responses from the FastAPI API.
- Use the calculator tool; web search is available when `TAVILY_API_KEY` is configured.
- Use Gemini through the Google Generative AI integration.

PDF upload, text extraction, embeddings, vector storage and document-based RAG are **not implemented yet**. `DOCUMENT_EMBEDDING_MODEL` may be present in a local environment, but the current application does not use it.

## Repository layout

```text
agentic-chatbot/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # Auth, chat and conversation routes
│   │   ├── core/            # App creation and environment settings
│   │   ├── db/              # SQLAlchemy base and database sessions
│   │   ├── models/          # Users, refresh tokens and conversations
│   │   ├── schemas/         # Pydantic request/response schemas
│   │   ├── security/        # Password hashing and JWT helpers
│   │   └── services/        # Auth, conversation and chat logic
│   ├── alembic/             # Database migration environment and revisions
│   ├── tests/
│   ├── .env.example
│   └── requirements.txt
└── frontend/
    ├── app/                 # Next.js App Router and API route handlers
    ├── components/
    │   ├── auth/
    │   └── chat/
    ├── lib/                 # API and auth clients
    └── .env.example
```

## Prerequisites

- Python 3.11 or newer
- Node.js 20 or newer and npm
- PostgreSQL
- A Google Gemini API key
- Optional: a Tavily API key to enable web search

## Configure the backend

Open a terminal in `backend/`, create a virtual environment, install dependencies and prepare the environment file:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend/.env` and provide your PostgreSQL credentials and API keys. Example configuration:

```dotenv
DATABASE_URL=postgresql+psycopg2://postgres:your-password@localhost:5432/agentic_chatbot
SECRET_KEY=replace-with-a-long-random-secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=30

GOOGLE_API_KEY=your-google-api-key
GEMINI_MODEL=gemini-3.5-flash
TAVILY_API_KEY=your-tavily-api-key
LLM_TEMPERATURE=0.7
MAX_OUTPUT_TOKENS=
CORS_ORIGINS=["http://localhost:3000"]
```

Create the `agentic_chatbot` PostgreSQL database if it does not exist. Apply migrations from the `backend/` directory:

```powershell
python -m alembic upgrade head
```

Start the API from the same directory:

```powershell
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The backend API documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs).

### Backend environment variables

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection URL |
| `SECRET_KEY` | Secret used to sign JWT access tokens |
| `JWT_ALGORITHM` | JWT signing algorithm; defaults to `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime; defaults to 15 minutes |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh-token lifetime; defaults to 30 days |
| `GOOGLE_API_KEY` | Gemini API credential |
| `GEMINI_MODEL` | Gemini model name |
| `TAVILY_API_KEY` | Optional web-search credential; search is disabled when unset |
| `LLM_TEMPERATURE` | Model temperature |
| `MAX_OUTPUT_TOKENS` | Optional model output limit |
| `CORS_ORIGINS` | JSON-style list of allowed browser origins |

Never commit `.env` files or real credentials. Use strong, independently generated secrets for deployed environments.

## Configure and run the frontend

Open a second terminal in `frontend/`:

```powershell
npm ci
Copy-Item .env.example .env.local
```

Set the API URLs in `frontend/.env.local`:

```dotenv
AUTH_API_URL=http://localhost:8000/api/v1
AUTH_REFRESH_TOKEN_EXPIRE_DAYS=30
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

`AUTH_API_URL` is used by the Next.js server-side authentication proxy. `NEXT_PUBLIC_API_URL` is used by the browser for authenticated chat requests and the health check. The refresh-cookie lifetime should match the backend's `REFRESH_TOKEN_EXPIRE_DAYS`.

Run the development server:

```powershell
npm run dev
```

Visit [http://localhost:3000](http://localhost:3000). The frontend includes registration and login screens; successful login opens the chat workspace.

For production, deploy the frontend with a Next.js runtime that supports route handlers, configure the API URLs for your deployment, use HTTPS, and add the deployed frontend origin to the backend's `CORS_ORIGINS`. The refresh token is placed in an HttpOnly cookie by the Next.js authentication proxy; the short-lived access token is kept in frontend memory.

## API overview

All endpoints below are under `/api/v1`.

### Authentication

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/auth/register` | Create an account |
| `POST` | `/auth/login` | Sign in and receive access and refresh tokens |
| `POST` | `/auth/refresh` | Rotate a refresh token and issue a new access token |
| `POST` | `/auth/logout` | Revoke a refresh token |
| `GET` | `/auth/me` | Return the authenticated user's profile |

### Conversations

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/conversations` | Create a conversation |
| `GET` | `/conversations` | List the authenticated user's conversations |
| `GET` | `/conversations/{thread_id}` | Read one conversation and its stored messages |
| `DELETE` | `/conversations/{thread_id}` | Delete an owned conversation |

### Chat

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/chat` | Send a message and receive a complete response |
| `POST` | `/chat/stream` | Send a message and receive a Server-Sent Events response |
| `GET` | `/health` | Check API health |

Chat requests require a `thread_id` created through `/conversations` and a valid Bearer access token. The API verifies that the conversation belongs to the current user before processing a message.

Example non-streaming request:

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "thread_id": "YOUR_CONVERSATION_ID",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

## Database migrations

Migrations are managed with Alembic; the application does not create production tables with `Base.metadata.create_all()`.

Run the latest migrations:

```powershell
cd backend
python -m alembic upgrade head
```

Show the current migration revision:

```powershell
python -m alembic current
```

## Tests and frontend checks

Run backend tests from `backend/`:

```powershell
python -m pytest
```

Run frontend lint and production build from `frontend/`:

```powershell
npm run lint
npm run build
```

## Conversation persistence note

PostgreSQL stores conversation records and chat messages and is the source of truth for the frontend sidebar. The LangGraph graph currently runs without a PostgreSQL checkpointer; durable conversation history is loaded from PostgreSQL and passed to the chat service for each request.
