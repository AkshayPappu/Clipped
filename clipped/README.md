# clipped.

Only the real ones know.

Clipped is a phone-first party game for a friend group. Someone opens a room, everyone else joins with a four-digit code, and you take turns answering prompts about your own lore. Answers stay anonymous while the room ranks them from best to worst. The server turns that order into points.

## Play locally

Python 3.11 or newer.

```bash
pip install -r clipped/requirements.txt
streamlit run clipped/app.py
```

No accounts and no API keys are required for a local room. Every browser tab on that Streamlit process shares one in-memory game. A banner on screen says when that's the case. Restarting the app wipes local rooms.

Open a second tab, join with the room code, and play. Invite links look like `http://127.0.0.1:8501/?room=4829`. Copy the invite button. Don't paste the address bar — that URL also holds your seat.

## How a round works

`lobby → prompt → voting → leaderboard → … → final results`

The phase lives in the database (or the local store). Phones do not decide it themselves.

- Everyone gets the same prompt and a countdown.
- One answer per player. You can't see anyone else's text yet.
- The phase ends when every active player has submitted, the host ends it, or the server clock hits the deadline. A missing host does not freeze a timer.
- Ranking is anonymous. Put every answer in order, best at the top, including your own. You can't change it after you lock it in.
- The leaderboard reveals authors, the place, the points, and how many rankings put that answer in each spot. The host starts the next round.
- The last round ends on a winner screen. **Play again** keeps the squad. **New room** leaves.

Host setup, before start:

- 5, 10, 15, or 20 rounds
- 30, 45, 60, or 90 seconds for answers and for ranking
- Packs: friend-group lore, exposing the group, deep cuts, brainrot, legendary moments
- Random or in-order questions
- Custom questions, including a paste of one question per line

The built-in bank has 110 prompts in [`clipped/database/seed.sql`](clipped/database/seed.sql). You need at least two players to start, and a room holds 12.

## Scoring

Players never send a score. They send an order, best to worst, and the server scores it:

1. On one ranking, first place pays 300 and last place pays 0. The spots between are even steps. Three answers pay 300, 150, and 0 from that person.
2. An answer's score is those payments added up across every ranking.
3. The highest total finishes first. The same total is a tie, and both keep the points they earned. Two people ranking opposite answers leaves both on 300.
4. Nobody ranked anything → 0.
5. No answer → 0 for that round.

## Project layout

```text
clipped/
├── app.py
├── requirements.txt
├── database/schema.sql      # tables, RLS, token-checked RPCs
├── database/seed.sql        # 110 builtin prompts
├── components/              # lobby, prompt, voting, leaderboard
├── services/                # scoring, rooms, Supabase, in-memory store
├── utils/
└── styles/theme.css
```

Entry point: `clipped/app.py`.

## Supabase

Create a project, then in the SQL editor run, in order:

1. [`clipped/database/schema.sql`](clipped/database/schema.sql)
2. [`clipped/database/seed.sql`](clipped/database/seed.sql)

The schema turns on row-level security and does not add policies for the public anon key, so that key cannot read answers or rankings. The Streamlit server uses the **service role** key and only calls RPCs. Those functions check a player session token, lock the room row, and return a view that matches the phase. Prompt views do not include other people's answers. Voting views do not include authors.

Copy the project URL and service role key into `.streamlit/secrets.toml` (do not commit it) or into the environment. [`clipped/.env.example`](clipped/.env.example):

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
APP_BASE_URL=https://your-app.streamlit.app
```

`.streamlit/secrets.toml` for Streamlit Cloud or local secrets:

```toml
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"
APP_BASE_URL = "https://your-app.streamlit.app"
```

`APP_BASE_URL` is optional. Without it, invite links use the request host.

Rooms expire 12 hours after they're created. Active room codes are unique; an expired code can be reused.

## Vercel

The site at the repository root is the Next.js app. Rooms, answers, and rankings stay in Supabase, so two phones can join the same code even though Vercel does not keep a process alive between requests. The service role key is used only by `app/api/game/route.ts`. The browser never sees it.

Leave the Vercel root directory as the repository root. Do not set it to a subfolder. Add:

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

Invite links look like `https://clipped-app.vercel.app/?room=4829`. Copy invite from the lobby. The address bar after you join does not contain your seat.

Locally:

```bash
npm install
npm run dev
```

Put the same two variables in `.env.local`. The dev server listens on port 47231.

The Streamlit app in `clipped/` still runs the same game against the same database when those variables are set.

## Streamlit Community Cloud

1. Push this repo.
2. New app, main file `clipped/app.py`.
3. Paste the same three values into the app's Secrets.
4. Deploy.

The service role key stays in Streamlit secrets. It is not in the browser bundle.

## Realtime, and what Streamlit can't do

There are no websockets. Each phone polls about every 1.5 seconds with a Streamlit fragment. Deadlines use the server clock, so a timer still expires if the host's tab is closed.

The answer box sits **outside** that polling fragment, inside a form, so typing isn't wiped every tick. A full rerun happens when the phase or round changes.

Streamlit component iframes can't reliably share the parent page's `localStorage`, so a player token is kept in a `sid` query param on **your** URL. The copied invite is only `?room=`. Refreshing keeps your seat. Sharing the address bar would share your seat — use **Copy invite link**.

Rate limiting is per action (300ms), not one bucket for the whole token. Otherwise starting the game would block the host's answer. Duplicate answers and a changed ranking are rejected even when the throttle is off. Moving cards around is local until you lock the order in.

## Tests

```bash
pytest
```

The suite covers room-code collisions, duplicate names, expired rooms, host-only actions, hidden answers, duplicate answers, locked rankings, place points and tie-breaks, unranked answers, concurrent submits, timer expiry without the host, double phase advance, reconnection, and the question bank.

Postgres checks are the SQL functions in `schema.sql`. With a local database named `clipped`:

```bash
psql -d clipped -f clipped/database/schema.sql
psql -d clipped -f clipped/database/seed.sql
```

## Troubleshooting

- **"Session expired" after a refresh on a local room.** The Streamlit process restarted and the in-memory room is gone. Create a new one, or use Supabase.
- **Invite link shows a path only.** Set `APP_BASE_URL`, or open the app from the host you want to share.
- **Copy button does nothing.** The clipboard API needs a secure context (HTTPS, or localhost). The code and the invite text can also be selected by hand.
- **Game doesn't advance.** Confirm the tab is still polling (the squad list or the timer should tick). Deadlines are server-side; give it a couple of seconds.
- **Supabase says the function doesn't exist.** Re-run `schema.sql`. In the Supabase API settings, reload the schema cache if the RPC list looks stale.
- **Anon key can read rows.** Re-run the privilege block at the bottom of `schema.sql`. There should be no policies on these tables.
- **Two people picked the same name.** Names are unique per room, ignoring case.
- **Custom questions disappeared after deploy.** They live on the room. A new Supabase project needs `seed.sql` again for the builtin bank. Custom questions are not in that file.
