# SarkariScan — Govt Job Aggregator Starter Kit

Two pieces are included:

1. **`frontend/index.html`** — a working, styled demo of the site design
   (web3.career-style dense list layout, but with its own identity: dark
   navy, saffron accent, and color-coded deadline badges since — unlike
   crypto job boards — closing dates are the single most important piece
   of information on a govt job listing).

2. **`scraper/scraper.py`** — a runnable Python scraper template with:
   - A SQLite-backed job store with de-duplication (by source + title + last date)
   - A per-source parser pattern (`parse_ssc` is a worked example against SSC)
   - A JSON export function your frontend/API can read from

## How the scraper and site connect, and how to deploy them together

The frontend now fetches `frontend/jobs_export.json` at page load (`loadJobs()`
in the script tag) and transforms each row into what the job cards need
(initials, urgency badge, tags). If that file is missing or unreachable —
e.g. you're just opening `index.html` directly by double-clicking it — it
silently falls back to demo data, so the page never looks broken while
you're setting things up.

`scraper/scraper.py` already ends with `export_json()`, which writes
`jobs_export.json` in the exact shape the frontend expects. So the whole
pipeline is: **scraper runs → writes jobs_export.json → frontend reads it
on next load.** The only remaining question is *where* that loop runs and
how often.

### Path A — fully static, free, easiest to start with

This is the right choice while you're still testing and don't have heavy
traffic yet.

1. Push this whole project to a GitHub repo.
2. The included `.github/workflows/scrape.yml` runs the scraper every 4
   hours (via GitHub Actions' free tier), copies the fresh
   `jobs_export.json` into `frontend/`, and auto-commits it.
3. Deploy the `frontend/` folder to **Vercel** or **Netlify** as a static
   site (see the "how to deploy" steps from earlier — same process).
4. Because the scraper's commit changes a file in your repo, Vercel/Netlify
   auto-redeploys on every commit — so the live site picks up new jobs
   automatically every 4 hours, with zero servers to manage.

To adjust how often it runs, edit the `cron:` line in `scrape.yml` (it uses
standard cron syntax — e.g. `0 */2 * * *` for every 2 hours).

**Limitation:** this works well up to a few thousand jobs in one JSON file,
but it's still one big client-side fetch — fine for now, but not how you'd
want to serve things once you have real scale or want per-job SEO pages
(see Path B).

### Path B — real backend, for when you're ready to scale

Once you've got real traffic and want individually indexable job pages
(important for SEO — this is most of how Freejobalert-style sites actually
rank), the shape changes to:

1. Run `scraper.py` on a small always-on server (a $5-6/mo VPS, or
   Render/Railway's free-to-cheap tiers) with a real cron job instead of
   GitHub Actions, writing into Postgres instead of SQLite.
2. Put a small API in front of it (FastAPI/Express) serving `/api/jobs`
   and `/api/jobs/:id`.
3. Rebuild the frontend in **Next.js**, with each job getting its own
   server-rendered route (`/jobs/[slug]`) using ISR (Incremental Static
   Regeneration) so pages stay fresh without rebuilding the whole site
   every time.
4. Deploy the Next.js app to Vercel (same as before) — Vercel talks to
   your API at build/request time instead of reading a static JSON file.

I can scaffold the Next.js version with ISR job pages next, whenever you're
ready to move off the static prototype — just say the word.

## How to actually run this


**Frontend demo:**
Just open `frontend/index.html` in a browser — no build step needed, it's
self-contained. This is the visual direction; the "real" version should be
rebuilt in Next.js once you're ready to scale (reasons below).

**Scraper:**
```bash
pip install requests beautifulsoup4 python-dateutil
python scraper/scraper.py
```
This environment doesn't have live network access, so I couldn't test it
against the real internet from here — run it from your own machine or
server. The SSC parser is a realistic starting template, but you should
expect to inspect the live HTML yourself (right-click → Inspect on the
notice board section) and adjust the CSS selectors, since I can't verify
today's exact markup without fetching it.

## Why Next.js for the real frontend

The demo HTML is great for nailing the visual direction fast, but for
production you want:
- **Server-side rendering / ISR** so each job gets its own indexable,
  fast-loading page (this is most of how Freejobalert-style sites actually
  rank — long-tail searches like "XYZ Recruitment 2026 last date")
- A sitemap that regenerates as new jobs are scraped
- Individual job detail pages with a short original summary paragraph
  (helps both SEO and AdSense approval — pure scraped tables read as thin
  content to both Google and AdSense reviewers)

## Suggested next steps, in order

1. **Pick 5-10 source sites** you actually want to track first (start
   narrow — e.g. SSC, one or two state PSCs, IBPS, RRB — rather than
   trying to cover everything on day one)
2. **Write and test one parser per source** against the live HTML
   (I can help you write each one if you tell me which sites, or paste
   me the HTML/URL and I'll build the parser against it)
3. **Stand up the DB + scheduler** (cron every few hours is enough to
   start; no need for real-time)
4. **Rebuild the frontend in Next.js**, using this HTML/CSS as the visual
   spec — I can scaffold that project next
5. **Add a short unique summary paragraph per job page** before applying
   for AdSense — this single thing meaningfully affects both approval odds
   and SEO ranking
6. **Submit sitemap to Google Search Console** as soon as you have even
   50-100 live job pages — don't wait for full coverage

## A few things worth deciding before you scale this

- **Legal/ToS**: skim each source site's terms before scraping at volume;
  most Indian govt sites don't explicitly forbid it, but a few do have
  rate-limit or anti-scraping clauses
- **Attribution**: always link to the official notification, and keep the
  scraped-from URL in your DB (as the template does) so you can verify or
  pull a listing if a source amends/cancels it
- **Update cadence**: last-date fields matter a lot to users — a stale
  "last date" is the fastest way to lose trust and get flagged in reviews

Tell me which source sites you want to start with and I'll write the real
parsers against their actual HTML next.
