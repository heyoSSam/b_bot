# b_bot

## Environment variables

Create a `.env` file in the project root and add your configuration values.

Example `.env`:

```env
TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
REQUIRED_CHANNEL_USERNAME="t.me/your_channel_username"

POSTGRES_DB=your_dbname
POSTGRES_USER=your_username
POSTGRES_PASSWORD=your_password
DATABASE_URL=your_url
```

## Database migrations

Create and apply schema changes with Alembic instead of creating tables from the bot runtime.

Apply the current schema:

```bash
alembic upgrade head
```

If the database already contains the current schema from the old runtime `create_all()` flow, mark the initial revision first:

```bash
alembic stamp 20260604_000001
```

Create a new migration after model changes:

```bash
alembic revision --autogenerate -m "describe change"
```
