"use client";

import { useCallback, useEffect, useState } from "react";
import { TOKEN_KEY, play } from "@/lib/client";
import { isView, type GameResult, type View } from "@/lib/types";
import { Lobby } from "@/components/lobby";
import { Round } from "@/components/round";

type Screen = "landing" | "create" | "join";

export function GameApp() {
  const [screen, setScreen] = useState<Screen>("landing");
  const [token, setToken] = useState<string | null>(null);
  const [view, setView] = useState<View | null>(null);
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [inviteCode, setInviteCode] = useState("");
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [toast, setToast] = useState("");

  const seat = useCallback((next: string, nextView: View) => {
    localStorage.setItem(TOKEN_KEY, next);
    setToken(next);
    setView(nextView);
    setScreen("landing");
    setError("");
    const url = new URL(window.location.href);
    url.searchParams.delete("room");
    window.history.replaceState({}, "", url.pathname);
  }, []);

  const run = useCallback(async (body: Record<string, unknown>) => {
    setBusy(true);
    setError("");
    const result = await play(body);
    setBusy(false);
    if (!isView(result)) {
      setError(result.error || "Something went wrong.");
      return null;
    }
    if (result.token) seat(result.token, result);
    else setView(result);
    return result;
  }, [seat]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const room = (params.get("room") || "").replace(/\D/g, "").slice(0, 4);
    setInviteCode(room);
    if (room) setCode(room);
    const saved = localStorage.getItem(TOKEN_KEY);
    if (!saved) {
      if (room) setScreen("join");
      setBooting(false);
      return;
    }
    play({ action: "sync", token: saved }).then((result) => {
      if (isView(result)) {
        setToken(saved);
        setView(result);
      } else {
        localStorage.removeItem(TOKEN_KEY);
        if (room) setScreen("join");
        if (result.error && result.error !== "Session expired. Join again.") setError(result.error);
      }
      setBooting(false);
    });
  }, []);

  useEffect(() => {
    if (!token) return;
    let stop = false;
    const tick = async () => {
      const result: GameResult = await play({ action: "sync", token });
      if (stop) return;
      if (isView(result)) setView(result);
      else if (result.error === "Session expired. Join again." || result.error === "This room expired.") {
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
        setView(null);
        setError(result.error);
      }
    };
    const id = window.setInterval(tick, 1500);
    return () => {
      stop = true;
      window.clearInterval(id);
    };
  }, [token]);

  useEffect(() => {
    if (!toast) return;
    const id = window.setTimeout(() => setToast(""), 2200);
    return () => window.clearTimeout(id);
  }, [toast]);

  async function createRoom() {
    const result = await run({ action: "create", name });
    if (result) setToast("Room's open.");
  }

  async function joinRoom() {
    const result = await run({ action: "join", name, code });
    if (result) setToast("You're in.");
  }

  async function leave() {
    if (token) await play({ action: "leave", token });
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setView(null);
    setScreen("landing");
  }

  return (
    <main className="app">
      {view ? (
        view.room.status === "lobby" ? (
          <Lobby view={view} token={token || ""} busy={busy} error={error} onRun={run} onLeave={leave} onToast={setToast} />
        ) : (
          <Round view={view} token={token || ""} busy={busy} error={error} onRun={run} onLeave={leave} />
        )
      ) : booting ? (
        <p className="hint">Reconnecting…</p>
      ) : screen === "create" ? (
        <NameScreen
          title="What should we call you?"
          name={name}
          setName={setName}
          error={error}
          busy={busy}
          submit="Create room"
          onSubmit={createRoom}
          onBack={() => { setScreen("landing"); setError(""); }}
        />
      ) : screen === "join" ? (
        <JoinScreen
          name={name}
          setName={setName}
          code={code || inviteCode}
          setCode={setCode}
          error={error}
          busy={busy}
          onSubmit={joinRoom}
          onBack={() => { setScreen("landing"); setError(""); }}
        />
      ) : (
        <section>
          <h1 className="wordmark">clipped.</h1>
          <p className="lede">Only the real ones know. Open a room, send the code, and rank the answers only this group would get.</p>
          {error ? <p className="error">{error}</p> : null}
          <div className="stack">
            <button className="btn primary" onClick={() => { setError(""); setScreen("create"); }}>Create room</button>
            <button className="btn secondary" onClick={() => { setError(""); setScreen("join"); }}>Join room</button>
          </div>
        </section>
      )}
      {toast ? <div className="toast">{toast}</div> : null}
    </main>
  );
}

function NameScreen({
  title, name, setName, error, busy, submit, onSubmit, onBack,
}: {
  title: string;
  name: string;
  setName: (value: string) => void;
  error: string;
  busy: boolean;
  submit: string;
  onSubmit: () => void;
  onBack: () => void;
}) {
  return (
    <section>
      <p className="wordmark compact">clipped.</p>
      <h2 className="question">{title}</h2>
      {error ? <p className="error">{error}</p> : null}
      <form className="stack" onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
        <input value={name} maxLength={20} placeholder="Your name" onChange={(event) => setName(event.target.value)} autoFocus />
        <button className="btn primary" disabled={busy} type="submit">{submit}</button>
        <button className="btn ghost" type="button" onClick={onBack}>Back</button>
      </form>
    </section>
  );
}

function JoinScreen({
  name, setName, code, setCode, error, busy, onSubmit, onBack,
}: {
  name: string;
  setName: (value: string) => void;
  code: string;
  setCode: (value: string) => void;
  error: string;
  busy: boolean;
  onSubmit: () => void;
  onBack: () => void;
}) {
  return (
    <section>
      <p className="wordmark compact">clipped.</p>
      <h2 className="question">Got a code?</h2>
      {error ? <p className="error">{error}</p> : null}
      <form className="stack" onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
        <label className="field">
          <span>Room code</span>
          <input
            value={code}
            inputMode="numeric"
            maxLength={4}
            placeholder="4829"
            onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 4))}
            autoFocus
          />
        </label>
        <label className="field">
          <span>Display name</span>
          <input value={name} maxLength={20} placeholder="Your name" onChange={(event) => setName(event.target.value)} />
        </label>
        <button className="btn primary" disabled={busy} type="submit">Join room</button>
        <button className="btn ghost" type="button" onClick={onBack}>Back</button>
      </form>
    </section>
  );
}
