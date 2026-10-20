# Local Content Hub viewer

The local viewer serves the existing Database and File Detail pages against the dedicated Content Hub database. It runs as a separate FastAPI app, exposes GET routes only, starts PostgreSQL transactions in read-only mode, and binds to a loopback address.

From the repository root, start the viewer API with the authorized local connection file:

```powershell
python -m ai_actuarial.api.local_hub --connection-config D:/AI_actuarial_inforsearch/private/content-hub-connection.json --host 127.0.0.1 --port 8000
```

In another terminal, start the existing Vite frontend:

```powershell
npm run dev -- --host 127.0.0.1
```

Open the local address printed by Vite. The page marks itself as read only and shows Hub classifications, confirmed dates with their recorded precision, date review status, evidence, and the original Markdown variant bound to each content version. Excluded URL identities are filtered from all Hub views. Unannotated records remain visibly unannotated.

The viewer does not call the normal application factory, load its `.env` or writable Storage, run the task runtime, or expose write, task, download, preview, chat, export, or catalog routes. It does not create or migrate Hub tables.
