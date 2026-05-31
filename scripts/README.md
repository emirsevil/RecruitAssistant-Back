# Fair-day demo users

`seed_fair_users.py` creates 200 demo accounts for the CS fair, then writes a printable A4 sheet you can cut into individual cards to hand out.

## What it produces

After you run it, three files appear next to the script:

| File                      | What it is                                                                  |
| ------------------------- | --------------------------------------------------------------------------- |
| `fair_credentials.json`   | Source of truth — `[ { index, email, password, full_name }, ... ]`. Don't lose this; re-runs reuse it instead of regenerating passwords. |
| `fair_credentials.txt`    | Plain text dump of every credential (one per line). Backup / quick lookup.  |
| `fair_credentials.html`   | A4-printable sheet. 20 cards per page → 10 pages for 200 users.             |

Each user gets:

- **Email** — `fair001@recruitassistant.demo` … `fair200@recruitassistant.demo`
- **Password** — random 8 characters from an alphabet that excludes ambiguous symbols (`0/O`, `1/l/I`, `5/S`)
- **Full name** — `Fair Demo 001` etc.

## How to run it

From the backend repo root, with your normal Python venv active and `DATABASE_URL` pointing at the database you actually want to seed (production, staging, or local):

```bash
# default: 200 users
python scripts/seed_fair_users.py

# or a different count
python scripts/seed_fair_users.py --count 50
```

The script is **idempotent**:

- If `fair_credentials.json` already exists, it reuses those credentials. No password rotation, no surprises mid-fair.
- If a user with that email already exists in the DB, it's skipped.

So you can safely re-run if a deploy wipes the DB or you want to top up.

## Printing the A4 sheet

1. Open `scripts/fair_credentials.html` in any browser (`open scripts/fair_credentials.html` on macOS).
2. **File → Print** (or `Cmd+P`).
3. Paper size: **A4**. Margins: **Default**. Background graphics: **on** if your printer dialog has the option.
4. Print → cut along the dashed borders → hand each card out at the booth.

Each card shows: brand label, email, password (bold, monospace), and the user's index.

## Sharing with stand staff

Hand `fair_credentials.txt` to the people running the booth as a backup — they can search/filter when someone loses their slip.

## Cleanup after the fair

If you want to delete every fair user from the DB, the simplest one-liner against the DB:

```sql
DELETE FROM users WHERE email LIKE 'fair%@recruitassistant.demo';
```

Cascades will remove their workspaces, interviews, quizzes, etc.
