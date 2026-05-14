# Filing Reminders / Dashboard Refactor — Plan

## Branch
`update_deadlines` (current). User confirmed: stay on this branch.

## Goals (from text.txt selection)
1. Update Dashboard "Filing Quick Reference" content: rename `NJ Sales Tax Return` → `NJ Sales Tax Return. ST-50`; correct due-date pattern, who-files, where for every row.
2. Make the **Filing Quick Reference** + **Key Websites** sections editable tables, mirroring the Finance Tracker → Expenses tab pattern (Add / Edit / Delete / Move Up / Move Down). Persist to Firestore.
3. One-shot migration script that updates existing filings in Firestore: rename ST-50, fix due dates, refresh Notes (where-to-file + calc formulas). Skip + warn on no-match with a log file. Header comment block with usage instructions. **Do not run.**

## Confirmed scope additions (from clarifying Q&A)
- **Multi-select `assigned_to`**: refactor `filings.assigned_to` from `str` → `list[str]` so joint filings (e.g. Joint Federal 1040) live as a single row assigned to both members. Migration merges existing duplicates.
- **ST-50 due-date rule**: 20th of the month after each quarter ends — Q1→Apr 20, Q2→Jul 20, Q3→Oct 20, Q4→Jan 20 next year.
- **Notes overwrite**: migration replaces existing `notes` with the new where-to-file + calc-formula content.
- **Initial seed for new collections**: corrected values per the verified conversation.

## Implementation order
1. `assigned_to` refactor (`compliance/db.py`, Compliance page UI, `init_compliance.py`).
2. New Firestore collections + editable Dashboard tables (`quick_reference`, `key_websites`).
3. Migration script `scripts/migrate_filings.py` (dry-run by default).
4. README.md update.

## Progress notes
- 2026-05-14: Started session. Confirmed scope via multi-question round. Created task list. Drafted plan.
- 2026-05-14: Implemented `assigned_to` refactor (str → list[str]) in `compliance/db.py`, `2_LLC_Compliance.py` (filters, modals, display, CSV import), `init_compliance.py`, `seed_compliance.py`. Read path tolerates legacy str values.
- 2026-05-14: Added `quick_reference` + `key_websites` Firestore collections with full CRUD + auto-seed in `compliance/db.py`. Replaced hard-coded Dashboard sections with editable tables mirroring the Finance Tracker Expenses tab pattern (Edit / Delete / Add / Up / Down + modals).
- 2026-05-14: Wrote `scripts/migrate_filings.py`. Dry-run by default; `--apply` commits. Renames ST-50, fixes due dates (ST-50 = 20th of month after quarter end; 1040-ES = Apr 15 / Jun 16 / Sep 15 / Jan 15; annuals = year+1 except NJ Annual Report = same year), overwrites notes, merges joint duplicates with multi-member `assigned_to`. Skipped filings logged to `scripts/migration_log_<timestamp>.txt`. **Not run.**
- 2026-05-14: Updated README — Dashboard description, Assigned-to multi-select, new migration script + collections sections.
- 2026-05-14: All 4 tasks complete. Branch: `update_deadlines` (per user choice; CLAUDE.md default is `feature/filing-reminders`).
