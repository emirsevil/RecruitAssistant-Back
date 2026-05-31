"""Seed script for the CS fair demo.

Creates a configurable number of demo accounts (default 200) with predictable
emails and random easy-to-type passwords. Idempotent: if the credentials JSON
already exists next to this script, it reuses those credentials so re-running
the script is safe — no users are recreated or have their passwords rotated.

Outputs three files in the same directory as this script:
  - fair_credentials.json  — source of truth (email/password pairs)
  - fair_credentials.txt   — flat list for sharing
  - fair_credentials.html  — printable A4 sheet (open in browser → Print)

Run from the backend root:
    python -m scripts.seed_fair_users
or:
    python scripts/seed_fair_users.py

Optionally pass a custom count:
    python scripts/seed_fair_users.py --count 50
"""

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

# Make sure we can import the app modules when run as a script from the backend root.
THIS_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = THIS_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from database import SessionLocal  # noqa: E402
from crud.user import create_user, get_user_by_email  # noqa: E402
from schemas.user import UserCreate  # noqa: E402


# Excludes ambiguous characters (0/O, 1/l/I, 5/S) so passwords are easy to read
# off a printed slip and type without errors.
PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
PASSWORD_LENGTH = 8

EMAIL_DOMAIN = "recruitassistant.demo"


def make_password() -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH))


def make_email(index: int) -> str:
    return f"fair{index:03d}@{EMAIL_DOMAIN}"


def make_full_name(index: int) -> str:
    return f"Fair Demo {index:03d}"


def load_or_generate_credentials(count: int, json_path: Path) -> list[dict]:
    """Reuse existing credentials when available; otherwise generate fresh ones."""
    if json_path.exists():
        with json_path.open("r", encoding="utf-8") as f:
            existing = json.load(f)
        if isinstance(existing, list) and len(existing) >= count:
            print(f"  → Reusing {count} credentials from {json_path.name}")
            return existing[:count]
        print(f"  → {json_path.name} has fewer than {count} entries; regenerating.")

    creds = [
        {
            "index": i,
            "email": make_email(i),
            "password": make_password(),
            "full_name": make_full_name(i),
        }
        for i in range(1, count + 1)
    ]
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(creds, f, indent=2, ensure_ascii=False)
    print(f"  → Wrote {count} fresh credentials to {json_path.name}")
    return creds


def insert_users(creds: list[dict]) -> tuple[int, int]:
    """Insert each user into the DB. Skips users that already exist by email."""
    created = 0
    skipped = 0
    db = SessionLocal()
    try:
        for c in creds:
            existing = get_user_by_email(db, email=c["email"])
            if existing:
                skipped += 1
                continue
            create_user(
                db=db,
                user=UserCreate(
                    email=c["email"],
                    password=c["password"],
                    full_name=c["full_name"],
                ),
            )
            created += 1
    finally:
        db.close()
    return created, skipped


def write_text(creds: list[dict], path: Path) -> None:
    lines = [
        "RecruitAssistant — CS Fair Demo Credentials",
        "=" * 50,
        "",
    ]
    for c in creds:
        lines.append(f"#{c['index']:03d}  {c['email']:<40}  {c['password']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  → Wrote {path.name}")


def write_html(creds: list[dict], path: Path) -> None:
    """Printable A4 sheet — 4 columns × 5 rows = 20 tickets per page."""
    cards = []
    for c in creds:
        cards.append(
            f"""
        <div class="card">
          <div class="brand-row">
            <span class="brand">RecruitAssistant</span>
            <span class="site">recruitassistant.net</span>
          </div>
          <div class="row"><span class="label">Email</span><span class="val">{c['email']}</span></div>
          <div class="row"><span class="label">Password</span><span class="val pw">{c['password']}</span></div>
          <div class="footer">#{c['index']:03d} · CS Fair Demo</div>
        </div>"""
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>RecruitAssistant — Fair Credentials</title>
<style>
  @page {{ size: A4; margin: 10mm; }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: ui-sans-serif, system-ui, "Segoe UI", Roboto, "Helvetica Neue", Arial;
    margin: 0;
    color: #1a1a1a;
    background: #f5f5f5;
  }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    grid-auto-rows: 50mm;
    gap: 4mm;
    padding: 6mm;
  }}
  .card {{
    border: 1px dashed #999;
    border-radius: 6px;
    padding: 6px 8px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    background: white;
    page-break-inside: avoid;
    break-inside: avoid;
  }}
  .brand-row {{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 6px;
  }}
  .brand {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
    color: #5b6b3a;
    text-transform: uppercase;
  }}
  .site {{
    font-size: 9px;
    font-weight: 600;
    color: #5b6b3a;
    font-family: "SF Mono", "Menlo", "Consolas", monospace;
  }}
  .row {{
    display: flex;
    flex-direction: column;
    gap: 1px;
    font-size: 11px;
  }}
  .label {{
    font-size: 8px;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.4px;
  }}
  .val {{
    font-family: "SF Mono", "Menlo", "Consolas", monospace;
    font-size: 11px;
    word-break: break-all;
  }}
  .pw {{
    font-weight: 700;
    font-size: 13px;
    color: #2d3a13;
  }}
  .footer {{
    font-size: 8px;
    color: #999;
    text-align: right;
  }}
  @media print {{
    body {{ background: white; }}
    .grid {{ padding: 0; }}
    .card {{ border-color: #bbb; }}
  }}
</style>
</head>
<body>
  <div class="grid">{''.join(cards)}</div>
</body>
</html>"""
    path.write_text(html, encoding="utf-8")
    print(f"  → Wrote {path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed CS-fair demo users.")
    parser.add_argument("--count", type=int, default=200, help="how many users to create (default: 200)")
    args = parser.parse_args()

    json_path = THIS_DIR / "fair_credentials.json"
    txt_path = THIS_DIR / "fair_credentials.txt"
    html_path = THIS_DIR / "fair_credentials.html"

    print(f"Seeding {args.count} fair users…")
    creds = load_or_generate_credentials(args.count, json_path)

    print("Inserting into DB…")
    created, skipped = insert_users(creds)
    print(f"  → Created: {created}   Already existed: {skipped}")

    print("Writing distribution files…")
    write_text(creds, txt_path)
    write_html(creds, html_path)

    print("\nDone.")
    print(f"  • Open {html_path.name} in a browser → Print → A4 to hand out the slips.")
    print(f"  • {txt_path.name} contains a flat backup of every credential.")
    print(f"  • Re-running this script is safe; existing users are skipped.")


if __name__ == "__main__":
    main()
