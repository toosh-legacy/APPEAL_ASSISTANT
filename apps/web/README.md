# Web app (Next.js)

```bash
npm install          # PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 to avoid a browser download
npm run dev          # http://localhost:3100 (API must run on :8000)
npm run gen:api      # regenerate src/lib/api-types.ts from packages/schemas/openapi.json
npx playwright test  # e2e + axe on desktop and mobile, using the installed Chrome
```

| Route | Purpose |
|---|---|
| `/` | Landing: how it works, privacy promise, sources |
| `/start` | Paste or upload + consent |
| `/cases/[id]/confirm` | Editable facts with confidence + hints |
| `/cases/[id]` | Progress (SSE), explanation / category picker, deadline + .ics, similar cases, letter editor, evidence kit |
| `/sources/[chunkId]` | Full source passage for a footnote |
| `/about/data` | Datasets, licenses, attribution, limitations |
| `/insights/insurers` | Insurer insights (feature-flagged; D3) |

The case access token is kept in `localStorage` (`case:<id>`), so reopening the case URL in the same browser resumes the view.
