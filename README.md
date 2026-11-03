# Portfolio + CMS

A server-rendered personal portfolio with a private admin CMS.

**Stack:** FastAPI · Jinja2 · Tailwind (CDN) · MongoDB Atlas (PyMongo async) · Cloudinary · JWT cookies · bcrypt · slowapi · Vercel

## Features

**Public site**
- Hero with bio, tech badges, social links and a call to action (editable in the CMS)
- Projects grid with category/tag filters; detail pages with screenshots, YouTube/Vimeo video and a sandboxed live-demo iframe
- Blog and vlogs: sanitized Markdown, reading time, tags, pagination, related posts, code highlighting
- Contact form that saves to MongoDB, emails the owner, and uses a honeypot plus rate limiting
- SEO: per-page `<title>`, meta description, OpenGraph/Twitter cards, canonical URLs, `sitemap.xml`, `robots.txt`
- Responsive Cloudinary images (`f_auto,q_auto`, `srcset`, lazy loading)
- Dark/light mode that follows the OS and remembers a manual choice in `localStorage`

**Admin CMS (`/admin`)**
- Single superadmin: only `ADMIN_EMAIL` can register, and only once
- HTTP-only, `SameSite=Strict` JWT cookie; sessions end when the password changes
- Forgot password: a 6-digit OTP (HMAC-hashed, 10-minute TTL, 5 attempts) sent by email
- Projects and blog/vlog CRUD with a Markdown editor (EasyMDE), draft/published states and a featured flag
- Images upload straight from the browser to Cloudinary using signed uploads, which avoids Vercel's 4.5 MB body limit
- Dashboard stats, a message inbox and a profile editor
- Rate limits: login 10/15 min, forgot 3/15 min, reset 10/15 min, contact 5/hour

## Project structure

```
api/index.py          Vercel ASGI entrypoint (exports `app`)
core/                 app factory, config, DB client, security, rate limiter, templating
routes/               public.py · auth.py (login/register/OTP) · admin.py (CMS)
models/schemas.py     User, Project, BlogPost, OTP, Message, Profile
utils/                Cloudinary helpers, Markdown/slug/embed helpers, SMTP mailer
templates/            base, public/, admin/, partials/
static/               css/app.css, js/app.js, js/admin.js
tests/                pytest suite against an in-memory fake MongoDB
.github/workflows/    CI: runs the tests on every push and pull request
vercel.json           routes /static to the CDN, everything else to api/index.py
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

The tests use an in-memory fake database and stub out email and Cloudinary calls, so they need no `.env` and never touch real services.

## Local development

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in real values
uvicorn api.index:app --reload
```

Open http://localhost:8000, then go to **/admin/register** once to create the admin account. API docs are at `/docs` when `ENVIRONMENT=development`.

## 1. MongoDB Atlas

1. Create a free **M0** cluster at https://cloud.mongodb.com.
2. **Database Access** → add a database user with *Read and write to any database*.
3. **Network Access** → add `0.0.0.0/0`. Vercel functions don't have fixed IPs; alternatively, use the official *MongoDB Atlas* integration in the Vercel marketplace.
4. **Connect → Drivers** → copy the `mongodb+srv://…` string into `MONGO_URI`.

The app creates its collections and indexes (including a TTL index on OTPs) on first request.

## 2. Cloudinary

1. Sign up at https://cloudinary.com.
2. In the dashboard, copy the **API environment variable** (`cloudinary://KEY:SECRET@CLOUD_NAME`) into `CLOUDINARY_URL`.

Uploads are signed by the server, so no unsigned upload preset is needed. Originals are capped at 2400px wide on upload, and every delivered image uses `f_auto,q_auto` with responsive widths.

## 3. Email (OTP + contact notifications)

For Gmail:
1. Turn on 2-Step Verification for the Google account.
2. Go to https://myaccount.google.com/apppasswords and create an app password.
3. Set `SMTP_EMAIL` to the Gmail address and `SMTP_PASSWORD` to the 16-character app password.

Any SMTP provider works (SendGrid, Mailgun, Resend SMTP): change `SMTP_HOST` and `SMTP_PORT`. Port 465 uses SSL; anything else uses STARTTLS.

## 4. Push to GitHub

```bash
git init
git add .
git status            # confirm .env is NOT listed
git commit -m "Initial portfolio + CMS"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

## 5. Deploy to Vercel

1. Go to https://vercel.com/new and import the GitHub repo. Leave Framework Preset as **Other**; `vercel.json` handles the build.
2. **Settings → Environment Variables**: add every key from `.env.example` with real values, and set:
   - `ENVIRONMENT=production`, which turns on Secure cookies and HSTS and hides `/docs`
   - `SITE_URL=https://your-domain.vercel.app`, used for canonical URLs, the sitemap and OpenGraph
3. Deploy, then visit `https://your-domain/admin/register` once to create the admin account.
4. Optional: add a custom domain, then update `SITE_URL`.

Each push to `main` redeploys automatically; pull requests get preview URLs.

## License

[MIT](LICENSE)

## Security notes

- **Never commit `.env`.** `.gitignore` excludes it. If a secret is ever exposed (in a chat, a commit or a screenshot), rotate it: the Atlas user password, the Cloudinary API secret (*Settings → API Keys*), the Gmail app password and `JWT_SECRET_KEY`.
- `JWT_SECRET_KEY` must be long and random: `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
- Rate limits are kept in memory per serverless instance. For strict global limits, use Redis (for example Upstash) via `storage_uri` in `core/limiter.py`.
- CSRF: admin cookies are `SameSite=Strict`, so browsers don't send them on cross-site requests.
- Tailwind's Play CDN is convenient but compiles CSS in the browser. For best performance, switch later to the Tailwind CLI and a built `static/css` file.
