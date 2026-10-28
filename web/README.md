# clipped. on Vercel

This is the Next.js client. Rooms, answers, and rankings live in Supabase, so players can join the same code from different phones.

Set the Vercel project root to this `web` directory and add:

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

The service role key is read only by `app/api/game/route.ts`. It is not sent to the browser.

Locally:

```bash
npm install
npm run dev
```

Put the same two variables in `.env.local`. The dev server listens on port 47231.

Invite links look like `https://your-app.vercel.app/?room=4829`.
