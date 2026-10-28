"use client";

import { useState } from "react";
import { PACKS, ROUNDS, TIMERS } from "@/lib/game";
import type { View } from "@/lib/types";

type Run = (body: Record<string, unknown>) => Promise<View | null>;

export function Lobby({
  view, token, busy, error, onRun, onLeave, onToast,
}: {
  view: View;
  token: string;
  busy: boolean;
  error: string;
  onRun: Run;
  onLeave: () => void;
  onToast: (message: string) => void;
}) {
  const room = view.room;
  const [customBody, setCustomBody] = useState("");
  const [importBody, setImportBody] = useState("");
  const you = view.you;

  async function saveSettings(patch: Record<string, unknown>) {
    await onRun({
      action: "settings",
      token,
      rounds: room.total_rounds,
      answerSeconds: room.answer_seconds,
      voteSeconds: room.vote_seconds,
      categories: room.categories,
      order: room.question_order,
      ...patch,
    });
  }

  function copy(value: string, message: string) {
    navigator.clipboard.writeText(value).then(() => onToast(message));
  }

  const invite = `${typeof window === "undefined" ? "" : window.location.origin}/?room=${room.code}`;

  return (
    <section>
      <p className="wordmark compact">clipped.</p>
      <p className="kicker">Room code</p>
      <div className="code-digits" aria-label={`Room code ${room.code}`}>
        {room.code.split("").map((digit, index) => <span className="digit" key={`${digit}-${index}`}>{digit}</span>)}
      </div>
      <p className="hint">Send this to the group.</p>
      <div className="row">
        <button className="btn secondary" type="button" onClick={() => copy(room.code, "Code copied.")}>Copy code</button>
        <button className="btn secondary" type="button" onClick={() => copy(invite, "Invite copied.")}>Copy invite</button>
      </div>
      <p className="hint">The invite is only the room code. Your seat stays on this phone.</p>
      {error ? <p className="error">{error}</p> : null}

      <h2 className="section">The squad <span className="count">{room.player_count}</span></h2>
      {view.players.map((person) => (
        <div className={`player${person.is_host ? " host" : ""}${person.is_away ? " away" : ""}`} key={person.id}>
          <div className="avatar">{person.display_name.slice(0, 1).toUpperCase()}</div>
          <div className="name">{person.display_name}</div>
          {person.is_host ? <span className="badge host">HOST</span> : null}
          {person.id === you.id ? <span className="badge you">YOU</span> : null}
          {person.is_away ? <span className="badge">AWAY</span> : null}
        </div>
      ))}

      {you.is_host ? (
        <>
          <h2 className="section">Setup</h2>
          <div className="stack">
            <label className="field">
              <span>Rounds</span>
              <select value={room.total_rounds} onChange={(event) => saveSettings({ rounds: Number(event.target.value) })}>
                {ROUNDS.map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </label>
            <label className="field">
              <span>Answer timer</span>
              <select value={room.answer_seconds} onChange={(event) => saveSettings({ answerSeconds: Number(event.target.value) })}>
                {TIMERS.map((value) => <option key={value} value={value}>{value} seconds</option>)}
              </select>
            </label>
            <label className="field">
              <span>Ranking timer</span>
              <select value={room.vote_seconds} onChange={(event) => saveSettings({ voteSeconds: Number(event.target.value) })}>
                {TIMERS.map((value) => <option key={value} value={value}>{value} seconds</option>)}
              </select>
            </label>
            <div className="field">
              <span>Question packs</span>
              <div className="pills">
                {PACKS.map((pack) => {
                  const on = room.categories.includes(pack.id);
                  return (
                    <button
                      key={pack.id}
                      type="button"
                      className={`pill${on ? " on" : ""}`}
                      onClick={() => {
                        const categories = on
                          ? room.categories.filter((item) => item !== pack.id)
                          : [...room.categories, pack.id];
                        saveSettings({ categories });
                      }}
                    >
                      {pack.label}
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="field">
              <span>Question order</span>
              <div className="pills">
                <button type="button" className={`pill${room.question_order === "random" ? " on" : ""}`} onClick={() => saveSettings({ order: "random" })}>Random</button>
                <button type="button" className={`pill${room.question_order === "sequential" ? " on" : ""}`} onClick={() => saveSettings({ order: "sequential" })}>In order</button>
              </div>
            </div>
          </div>
          <p className="hint">{view.deck_count} questions ready{view.deck_count < room.total_rounds ? " — not enough for the rounds you picked" : ""}.</p>
          <details className="custom">
            <summary>Custom questions{view.custom_prompts.length ? ` · ${view.custom_prompts.length}` : ""}</summary>
            <div className="inner">
              {view.custom_prompts.length === 0 ? (
                <p className="hint">Nothing in here yet. Add one question this group would actually answer, or paste a list.</p>
              ) : null}
              <form className="stack" onSubmit={async (event) => {
                event.preventDefault();
                const result = await onRun({ action: "custom", token, body: customBody });
                if (result) setCustomBody("");
              }}>
                <label className="field">
                  <span>New question</span>
                  <input value={customBody} placeholder="Ask something only this group would get" onChange={(event) => setCustomBody(event.target.value)} />
                </label>
                <button className="btn secondary" type="submit" disabled={busy}>Add question</button>
              </form>
              {view.custom_prompts.map((prompt) => (
                <div className="custom-item" key={prompt.id}>
                  <label className="row" style={{ alignItems: "center" }}>
                    <input
                      type="checkbox"
                      checked={prompt.included}
                      onChange={(event) => onRun({ action: "include", token, promptId: prompt.id, included: event.target.checked })}
                    />
                    <span>{prompt.body}</span>
                  </label>
                  <button className="btn tiny" type="button" onClick={() => onRun({ action: "deleteCustom", token, promptId: prompt.id })}>Delete</button>
                </div>
              ))}
              <form className="stack" style={{ marginTop: "0.8rem" }} onSubmit={async (event) => {
                event.preventDefault();
                const result = await onRun({ action: "import", token, body: importBody });
                if (result) {
                  setImportBody("");
                  onToast("List added.");
                }
              }}>
                <label className="field">
                  <span>Paste questions, one per line</span>
                  <textarea value={importBody} placeholder="One question per line" onChange={(event) => setImportBody(event.target.value)} style={{ minHeight: 110 }} />
                </label>
                <button className="btn secondary" type="submit" disabled={busy}>Import list</button>
              </form>
            </div>
          </details>
          <div className="stack" style={{ marginTop: "1rem" }}>
            <button className="btn primary" disabled={busy} onClick={async () => {
              const result = await onRun({ action: "start", token });
              if (result) onToast("Cook something up.");
            }}>Start game</button>
          </div>
        </>
      ) : (
        <p className="hint">Waiting for the host to start…</p>
      )}
      <button className="btn ghost" type="button" onClick={onLeave}>Leave room</button>
    </section>
  );
}
