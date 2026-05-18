# Claude Behavior Rules — cron_jobs

## After every code change
Update `README.md` to reflect what changed. Keep it current. Do not wait to be asked.

## After every user prompt
Update `plan.md` with progress notes: what was done, what's next, any decisions made.

## Token usage
If a user prompt looks expensive to execute (large exploration, many files, complex task), ask the user to refine it before proceeding.

## Product decisions
Never assume. Ask the user for clarification on every product decision before implementing.

## Response style
Concise and direct. No sycophancy. No preamble. No "Great question!" No summaries of what you just did.

## Branch discipline
All work on branch separate branch. Never push or merge to `main`. Let the user do that manually.

## Session handoff
When approaching the usage limit, append a `## Session Handoff` block to `plan.md` that contains exactly what was being worked on and the next steps — written so it can be pasted into a new session without wasting tokens re-gathering context.