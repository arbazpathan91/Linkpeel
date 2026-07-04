# Link Preview API

Send any URL, get back clean metadata: title, description, image, favicon, and site name. Falls back across Open Graph → Twitter Cards → plain HTML tags, so it works on most of the web, not just sites that bother with OG tags.

## Try it

```
GET /preview?url=https://github.com
```

```json
{
  "url": "https://github.com/",
  "final_url": "https://github.com/",
  "title": "GitHub · Change is constant. GitHub keeps you ahead.",
  "description": "Join the world's most widely adopted, AI-powered developer platform...",
  "image": "https://images.ctfassets.net/.../GH-Homepage-Universe-img.png",
  "favicon": "https://github.com/fluidicon.png",
  "site_name": "GitHub"
}
```

Interactive docs at `/docs` once deployed.

## Run locally

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Deploy to Render (free tier)

1. Push this repo to GitHub.
2. On [render.com](https://render.com) → New → Web Service → connect the repo.
3. Render will auto-detect `render.yaml`. Or set manually:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Deploy. First request after idle may take ~30s to spin up (free tier sleeps).

## Notes on scaling this up

- The in-memory cache (`_cache` dict) resets on every restart and isn't shared across instances. Fine for a demo or single-instance free-tier deploy — swap for Redis if you add more instances or want persistence.
- No rate limiting is applied. Add one (e.g. `slowapi`) before exposing this publicly at scale, since it's easy to abuse as an open proxy for fetching arbitrary URLs.
- HTML fetch is capped at ~2MB and 8s timeout to avoid hanging on huge or slow pages.

## License

MIT — do whatever you want with it.
