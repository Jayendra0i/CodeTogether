# Share a local CodeTogether room

## Deploy on Render (no Cloudflare tunnel)

The repository includes `render.yaml` for a Render web service (FastAPI and
WebSockets), a static frontend, and PostgreSQL. To deploy it:

1. Push this project to a GitHub repository. Do not commit `backend/.env`.
2. In Render, choose **New → Blueprint**, connect the repository, and apply
   the `render.yaml` plan. Render builds and deploys all three services.
3. Open the frontend's `onrender.com` URL and create an account/room. The room
   invitation link can then be shared directly with collaborators.

The Blueprint currently uses Render's free plans. Free web services can take
about a minute to wake after 15 minutes idle. Free Render Postgres expires 30
days after creation; upgrade the database before then to retain room and user
data. See [Render's free instance limits](https://render.com/docs/free).

The online code runner is disabled in this Blueprint because it runs submitted
programs through Docker, and the Render web service does not include the local
Docker Desktop daemon this project expects. Collaboration, rooms, chat, and
WebSockets work; running code requires moving execution to a separate sandbox
service and configuring it.

This setup keeps the app and database on your Windows computer and gives the
frontend a temporary public HTTPS address. Keep the computer, backend, Vite,
and tunnel running while collaborators use the link.

## 1. Start the prerequisites

- Start the MySQL server configured by `backend/.env`.
- Start Docker Desktop. `backend/executor.py` uses Docker to run Python,
  JavaScript, Java, C, and C++ programs.
- Make sure `backend/.env` has the existing `MYSQL_USER`, `MYSQL_PASSWORD`,
  `DATABASE_NAME`, and `SECRET_KEY` values. Keep this file private.

## 2. Start the backend

Open PowerShell at the project root:

```powershell
.\venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Leave this terminal open. Check `http://127.0.0.1:8000/health` in a browser;
it should return `{"status":"healthy"}`. Startup also checks the MySQL
connection.

## 3. Start the frontend

Open a second PowerShell at the project root:

```powershell
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

Leave this terminal open too. Locally, open `http://localhost:5173` and sign in
to create a room. The frontend proxies API and WebSocket connections to the
backend, so the public tunnel only needs to expose port 5173.

## 4. Give the frontend a temporary public URL

Install `cloudflared` using [Cloudflare's Windows downloads](https://developers.cloudflare.com/tunnel/downloads/).
Then open a third PowerShell and run:

```powershell
cloudflared tunnel --url http://localhost:5173
```

Cloudflare prints an HTTPS address ending in `trycloudflare.com`. Open that
address yourself and create the room from there. This matters because the
invitation link uses the address in your browser.

## 5. Share the room invitation

After the room is created, its signed, room-specific invitation link appears
in the sidebar. Copy it and send it through WhatsApp or another app. Guests open
the link, enter a name and email, and select **Join room**. They do not need an
account or email verification. Invitation links expire after 30 days; guest
session tokens are limited to that room and expire after seven days.

Keep the computer, MySQL, Docker Desktop, both app terminals, and `cloudflared`
running for the session. A Quick Tunnel URL is temporary and changes when you
start a new tunnel, so create a new invitation link after restarting it.

## Notes

- Quick Tunnels are for demos and development, not production. The public URL
  grants access to the app, and anyone who receives a room invitation can edit
  that room and use its code runner. Code execution runs through the project's
  Docker sandbox on your computer.
- Do not share your `.env` file or Docker/terminal access. Stop the tunnel with
  **Ctrl+C** when you finish.
- The editor is collaborative rather than a persistent hosting service: your
  computer and database must remain online.
