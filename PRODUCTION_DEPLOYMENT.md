# Production deployment

This document prepares a later server install. It does not deploy anything.

Do not put real passwords, secret keys, IP addresses, or domain names in this file or in Git. Use placeholders on the server and keep them in an untracked `.env`.

The shop stays a Django API plus the existing vinext frontend. Nginx will reverse-proxy both and will serve Django static and media files. There is no online payment and no remote object storage.

## 1. Required server software

- A Linux server
- Git
- Python 3.12 or newer, with `venv`
- Node.js 22.13 or newer
- Corepack (ships with Node) and pnpm 11
- PostgreSQL 16 or newer
- Nginx
- Gunicorn (installed from `backend/requirements.txt` into the virtualenv)

## 2. Expected directory layout

Use any path you control. This example uses `/srv/riwaq`.

```text
/srv/riwaq/app/                  # git checkout
/srv/riwaq/app/backend/          # Django project
/srv/riwaq/app/backend/.venv/    # Python virtualenv, not committed
/srv/riwaq/app/backend/.env      # production secrets, not committed
/srv/riwaq/app/backend/staticfiles/   # collectstatic output
/srv/riwaq/app/backend/media/         # uploaded images and invoice PDFs
/srv/riwaq/app/.env.local        # frontend build env, not committed
/srv/riwaq/app/dist/             # vinext production build
```

Local development continues to use `backend/db.sqlite3`. Do not copy that file to the server as the production database.

## 3. Required environment variables

Backend file: `/srv/riwaq/app/backend/.env`

```text
DJANGO_ENV=production
DJANGO_SECRET_KEY=<long-random-string>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=<host>
DJANGO_TIME_ZONE=Asia/Hebron
FRONTEND_URL=https://<host>
DJANGO_CSRF_TRUSTED_ORIGINS=https://<host>
DJANGO_CORS_ALLOWED_ORIGINS=https://<host>
DB_ENGINE=postgresql
DB_NAME=<db-name>
DB_USER=<db-user>
DB_PASSWORD=<db-password>
DB_HOST=127.0.0.1
DB_PORT=5432
DJANGO_USE_HTTPS=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_SSL_REDIRECT=True
```

`DJANGO_ENV=production` forces `DEBUG` off even if `DJANGO_DEBUG` is left true.

`DJANGO_USE_HTTPS=True` trusts `X-Forwarded-Proto` from Nginx and is what turns secure cookies on when the cookie flags are not set explicitly. Leave `SECURE_HSTS_SECONDS` unset until the site has served HTTPS successfully. After that, it can be set to a value such as `31536000`.

Frontend file, set before the production build: `/srv/riwaq/app/.env.local`

```text
NEXT_PUBLIC_API_BASE_URL=https://<host>
```

Use the public site origin when Nginx proxies `/api/` to Django. The value is embedded at `pnpm build` time. A later change requires a new frontend build.

Session cookies are same-site. Keep the shop and the API on one host (path proxy). A separate API host needs a later cookie review and is not part of this layout.

## 4. PostgreSQL database and user

Create a dedicated database and user. Example only:

```sql
CREATE USER <db-user> WITH PASSWORD '<db-password>';
CREATE DATABASE <db-name> OWNER <db-user>;
```

Point `DB_*` at that database. Do not run PostgreSQL on the developer machine for this project, and do not migrate the local SQLite file.

## 5. Backend install commands

```bash
cd /srv/riwaq/app
git pull
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Write `backend/.env` from `backend/.env.example` using the production values above. Do not commit it.

## 6. Frontend install and build commands

```bash
cd /srv/riwaq/app
corepack pnpm install --frozen-lockfile
corepack pnpm build
```

`NEXT_PUBLIC_API_BASE_URL` must already be the production origin before `pnpm build`.

Local development is unchanged:

```bash
corepack pnpm dev
```

That serves the shop at `http://127.0.0.1:5173` and expects Django at `http://127.0.0.1:8000`.

## 7. Django commands

From `backend/` with the virtualenv active and `backend/.env` present:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

`migrate` applies the committed shop migrations. No extra schema migration is required for this preparation.

`collectstatic` writes Django admin and app assets to `backend/staticfiles/`. Nginx serves that directory at `/static/`.

`createsuperuser` is the production staff account. Do not run `python manage.py seed_initial_data` on production. That command loads the local demo catalog, demo traders, and the known demo password. It is only for local development.

Uploaded product images, category images, and invoice PDFs belong in `backend/media/`. Nginx serves that directory at `/media/`. Django serves `/media/` itself only while `DEBUG` is true, which remains the local development behavior.

## 8. Gunicorn command

Run this from `backend/` with the virtualenv active:

```bash
gunicorn config.wsgi:application --bind 127.0.0.1:8000
```

Bind to localhost only. Nginx is the public listener. Process supervision (systemd) is a later server task.

## 9. Nginx responsibilities

Nginx is not configured in this task. When it is, it should:

- Terminate HTTPS and send `X-Forwarded-Proto: https` to Gunicorn.
- Reverse-proxy `/api/` and `/admin/` to `http://127.0.0.1:8000`.
- Serve `/static/` from `backend/staticfiles/`.
- Serve `/media/` from `backend/media/`.
- Reverse-proxy the rest of the site to the frontend process started by `corepack pnpm start`.

Do not add WhiteNoise. Nginx is the static and media server.

## 10. Deployment order

1. Install the system packages listed above.
2. Clone the repository and create `backend/.venv`.
3. Install Python requirements and frontend packages.
4. Create the PostgreSQL user and database.
5. Write `backend/.env` and `.env.local` with placeholders replaced on the server.
6. `python manage.py migrate`
7. `python manage.py collectstatic --noinput`
8. `python manage.py createsuperuser`
9. `corepack pnpm build`
10. Start Gunicorn on `127.0.0.1:8000`.
11. Start the frontend with `corepack pnpm start` (binds `127.0.0.1`; Wrangler prints the local port, commonly `8787`).
12. Point Nginx at those two local ports, `/static/`, and `/media/`.
13. Confirm HTTPS, then consider `SECURE_HSTS_SECONDS`.

## 11. Smoke-test checklist

- `https://<host>/` loads the shop in Arabic, RTL, and the English switch still works.
- Guest catalog categories and products come from the API. Prices stay hidden.
- Product and category images load from `/media/` or the bundled assets.
- `trader` / local login is not required; a real trader created in admin can sign in, see the assigned currency, and place an order.
- Guest add-to-cart still asks for login.
- Staff can open `/#admin`, and a trader cannot.
- Admin product save, invoice PDF upload, and Excel import still round-trip.
- `/static/` serves the Django admin CSS.
- Session survives a refresh. Logout clears it.
- No secret, SQLite file, or `media/` directory was committed.
