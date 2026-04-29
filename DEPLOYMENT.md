# Deploying to Render

The `render.yaml` blueprint deploys two free-tier web services:

- **`pdf-agent-api`** — FastAPI backend
- **`pdf-agent-ui`** — Next.js frontend

Free tier: services sleep after 15 min of inactivity; the first request after
sleep takes ~30 seconds to wake. Fine for demos.

## Step by step

### 1. Sign up

Go to https://render.com and sign in with GitHub. Authorise Render to read your
`PDF-agent` repo.

### 2. Apply the blueprint

Dashboard → **New +** → **Blueprint** → select the `PDF-agent` repo → it picks
up `render.yaml` automatically → **Apply**.

Render now creates both services. The first build will take a few minutes.

### 3. Set the secret env vars

The blueprint marks `OPENAI_API_KEY`, `PINECONE_API_KEY`, `COHERE_API_KEY`, and
`LANGSMITH_API_KEY` as `sync: false` — Render asks you to enter these in the
dashboard during the apply step (or under each service's **Environment** tab).

Required: `OPENAI_API_KEY`, `PINECONE_API_KEY`.
Optional but recommended: `COHERE_API_KEY` (reranker), `LANGSMITH_API_KEY` (traces).

### 4. Wire the UI to the API

Once `pdf-agent-api` deploys, copy its URL — something like
`https://pdf-agent-api.onrender.com`.

Open `pdf-agent-ui` → **Environment** → set:

```
NEXT_PUBLIC_API_URL = https://pdf-agent-api.onrender.com
```

Then **Manual Deploy → Clear build cache & deploy**. Next.js bakes
`NEXT_PUBLIC_*` into the bundle at build time, so the UI must rebuild after
the API URL changes.

### 5. Open the UI URL

You'll get something like `https://pdf-agent-ui.onrender.com`. Upload a PDF
and chat.

## Caveats on the free tier

- **Ephemeral filesystem.** Uploaded PDFs are saved to `data/uploads/` on the
  API container. Free-tier disks reset on every restart, so a PDF uploaded
  yesterday won't be servable today via `/pdf/{id}/raw`. The chunks survive
  in Pinecone, so chat still works on previously-indexed docs, but the PDF
  preview will 404. For persistence, attach a Render Disk (paid) or move
  uploads to S3 / R2.
- **Cold starts.** First request after sleep takes 20-40 seconds. Upgrade to a
  paid plan to keep the service warm.
- **Cohere trial key.** 10 RPM. The agent gracefully falls back to the
  unranked top-K if rate-limited.
