"use client";

import { useEffect, useState } from "react";
import { clock, ordinal, packLabel, placeLabel, placePoints, revealTone, secondsLeft } from "@/lib/game";
import type { Reveal, Standing, View } from "@/lib/types";

type Run = (body: Record<string, unknown>) => Promise<View | null>;

export function Round({
  view, token, busy, error, onRun, onLeave,
}: {
  view: View;
  token: string;
  busy: boolean;
  error: string;
  onRun: Run;
  onLeave: () => void;
}) {
  const status = view.room.status;
  return (
    <section>
      <p className="wordmark compact">clipped.</p>
      {error ? <p className="error">{error}</p> : null}
      {status === "prompt" && view.prompt ? <Prompt view={view} token={token} busy={busy} onRun={onRun} /> : null}
      {status === "voting" && view.voting ? <Voting view={view} token={token} busy={busy} onRun={onRun} /> : null}
      {status === "leaderboard" && view.leaderboard ? <Board view={view} token={token} busy={busy} onRun={onRun} /> : null}
      {status === "final_results" && view.final ? <Final view={view} token={token} busy={busy} onRun={onRun} onLeave={onLeave} /> : null}
      {status === "expired" ? <p className="hint">This room expired.</p> : null}
      {status !== "final_results" ? <HostTools view={view} token={token} busy={busy} onRun={onRun} /> : null}
      {status !== "final_results" ? <button className="btn ghost" type="button" onClick={onLeave}>Leave room</button> : null}
    </section>
  );
}

function RoundLabel({ number, total, category }: { number: number; total: number; category: string | null }) {
  const extra = packLabel(category);
  return <p className="round-pill">Round {number} / {total}{extra && extra !== "Custom" ? ` · ${extra}` : ""}</p>;
}

function Timer({ view, total }: { view: View; total: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(id);
  }, []);
  const deadline = view.room.phase_deadline;
  const left = secondsLeft(view.server_now, deadline, now);
  const ratio = total <= 0 ? 0 : Math.min(1, left / total);
  return (
    <div>
      <div className="timer-row">
        <span className="eyebrow">Time left</span>
        <span className="timer-num">{clock(left)}</span>
      </div>
      <div className="track"><div className={`fill${left <= 10 ? " low" : ""}`} style={{ width: `${ratio * 100}%` }} /></div>
    </div>
  );
}

function Prompt({ view, token, busy, onRun }: { view: View; token: string; busy: boolean; onRun: Run }) {
  const prompt = view.prompt!;
  const [draft, setDraft] = useState("");
  return (
    <>
      <RoundLabel number={prompt.round_number} total={prompt.total_rounds} category={prompt.category} />
      <h2 className="question">{prompt.question}</h2>
      <Timer view={view} total={view.room.answer_seconds} />
      <p className="progress"><b>{prompt.submitted_count}/{prompt.player_count}</b> players submitted</p>
      {prompt.your_answer ? (
        <div className="locked"><p className="kicker">Locked in</p><p className="body">{prompt.your_answer}</p></div>
      ) : (
        <form className="stack" onSubmit={async (event) => {
          event.preventDefault();
          await onRun({ action: "answer", token, body: draft });
        }}>
          <label className="field">
            <span>Your answer</span>
            <textarea
              value={draft}
              maxLength={280}
              placeholder="Say the thing the group chat would screenshot."
              onChange={(event) => setDraft(event.target.value)}
            />
          </label>
          <button className="btn primary" disabled={busy} type="submit">Lock it in</button>
        </form>
      )}
      <p className="hint">Answers stay anonymous until the receipts drop.</p>
    </>
  );
}

function Voting({ view, token, busy, onRun }: { view: View; token: string; busy: boolean; onRun: Run }) {
  const voting = view.voting!;
  const key = `${view.room.id}:${voting.round_number}`;
  const [orderKey, setOrderKey] = useState("");
  const [order, setOrder] = useState<string[]>([]);
  useEffect(() => {
    if (orderKey === key || voting.your_order) return;
    setOrderKey(key);
    setOrder(voting.answers.map((answer) => answer.id));
  }, [key, orderKey, voting.answers, voting.your_order]);
  const shown = voting.your_order || order;
  const known = new Map(voting.answers.map((answer) => [answer.id, answer]));

  function move(index: number, direction: -1 | 1) {
    const next = shown.slice();
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    const [item] = next.splice(index, 1);
    next.splice(target, 0, item);
    setOrder(next);
  }

  return (
    <>
      <RoundLabel number={voting.round_number} total={voting.total_rounds} category={voting.category} />
      <h2 className="question">{voting.question}</h2>
      <p className="hint">Best on top, worst on the bottom.</p>
      <Timer view={view} total={view.room.vote_seconds} />
      <p className="progress"><b>{voting.rankings_in}/{voting.rankings_needed}</b> rankings in</p>
      <p className="hint">Use the arrows. The number is what this spot pays. Every ranking in the room gets added up.</p>
      {shown.map((id, index) => {
        const answer = known.get(id);
        if (!answer) return null;
        return (
          <div key={id}>
            <div className="card">
              <div className="top">
                <span className="rank-no">{String(index + 1).padStart(2, "0")}</span>
                <span className="pay">+{placePoints(index + 1, shown.length)}</span>
              </div>
              <p className="body">{answer.body}</p>
              {answer.is_own ? <span className="yours">YOURS</span> : null}
            </div>
            {voting.your_order ? null : (
              <div className="row">
                <button className="btn tiny" type="button" disabled={index === 0} onClick={() => move(index, -1)}>Move up</button>
                <button className="btn tiny" type="button" disabled={index === shown.length - 1} onClick={() => move(index, 1)}>Move down</button>
              </div>
            )}
          </div>
        );
      })}
      {voting.your_order ? (
        <p className="hint">Order&apos;s locked.</p>
      ) : (
        <button className="btn primary" disabled={busy || shown.length === 0} onClick={() => onRun({ action: "rank", token, order: shown })}>
          Lock in this order
        </button>
      )}
    </>
  );
}

function Board({ view, token, busy, onRun }: { view: View; token: string; busy: boolean; onRun: Run }) {
  const board = view.leaderboard!;
  return (
    <>
      <RoundLabel number={board.round_number} total={board.total_rounds} category={board.category} />
      <p className="eyebrow">The receipts are in</p>
      <h2 className="question">{board.question}</h2>
      <p className="hint">Each ranking pays the spot it put this answer in. The total is the score.</p>
      {board.reveals.length === 0 ? <p className="hint">Nobody locked an answer in.</p> : null}
      {board.reveals.map((reveal) => <Receipt key={`${reveal.author}-${reveal.body}`} reveal={reveal} />)}
      <h2 className="section">Standings</h2>
      <Standings rows={board.standings} showRound={board.round_number > 1} />
      {view.you.is_host ? (
        <button className="btn primary" disabled={busy} onClick={() => onRun({ action: "next", token })}>
          {board.is_final_round ? "Show the winner" : "Next round"}
        </button>
      ) : <p className="hint">Waiting for the host…</p>}
    </>
  );
}

function Receipt({ reveal }: { reveal: Reveal }) {
  const tone = revealTone(reveal);
  const spots = reveal.spots || [];
  return (
    <article className={`reveal ${tone}`}>
      <div className="top">
        <span className={`verdict ${tone}`}>{placeLabel(reveal)}</span>
        <span className="pay">+{reveal.points}</span>
      </div>
      <p className="body">{reveal.body}</p>
      <p className="byline">{reveal.author}</p>
      {spots.some((count) => count > 0) ? (
        <div className="spots">
          {spots.map((count, index) => (
            <span className={`spot${count === 0 ? " quiet" : ""}`} key={ordinal(index + 1)}>
              <i>{ordinal(index + 1)}</i>
              <b>{count}</b>
            </span>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function Standings({ rows, showRound }: { rows: Standing[]; showRound: boolean }) {
  return (
    <div>
      {rows.map((row) => (
        <div className="standing" key={row.display_name}>
          <span>{row.rank}</span>
          <span>
            {row.display_name}
            {showRound && row.delta ? <span className={`delta${row.delta < 0 ? " down" : ""}`}>{row.delta > 0 ? "▲" : "▼"}{Math.abs(row.delta)}</span> : null}
          </span>
          <span className="pts">{row.points.toLocaleString()}</span>
        </div>
      ))}
    </div>
  );
}

function Final({ view, token, busy, onRun, onLeave }: { view: View; token: string; busy: boolean; onRun: Run; onLeave: () => void }) {
  const final = view.final!;
  const title = final.tied ? "It's a tie" : final.winners[0] || "Nobody";
  const points = final.standings[0]?.points || 0;
  return (
    <>
      <p className="eyebrow">Absolutely clipped.</p>
      <h2 className="question">{title}</h2>
      <p className="hint">{points.toLocaleString()} points. {final.tied ? "Shared the top." : "Takes the room."}</p>
      <h2 className="section">Final rankings</h2>
      <Standings rows={final.standings} showRound={false} />
      {final.best_answer ? (
        <article className="reveal gem">
          <p className="kicker">Best-rated answer</p>
          <p className="body">{final.best_answer.body}</p>
          <p className="byline">{final.best_answer.author} · {final.best_answer.points.toLocaleString()}</p>
        </article>
      ) : null}
      <div className="stack">
        {view.you.is_host ? <button className="btn primary" disabled={busy} onClick={() => onRun({ action: "again", token })}>Play again</button> : <p className="hint">Waiting for the host…</p>}
        <button className="btn ghost" type="button" onClick={onLeave}>New room</button>
      </div>
    </>
  );
}

function HostTools({ view, token, busy, onRun }: { view: View; token: string; busy: boolean; onRun: Run }) {
  const [confirm, setConfirm] = useState(false);
  const status = view.room.status;
  if (!view.you.is_host) return null;
  return (
    <div className="stack" style={{ marginTop: "0.4rem" }}>
      {status === "prompt" || status === "voting" ? (
        <button className="btn secondary" disabled={busy} onClick={() => onRun({ action: "skip", token })}>End phase early</button>
      ) : null}
      {confirm ? (
        <>
          <p className="hint">End the game for everyone?</p>
          <button className="btn primary" disabled={busy} onClick={() => onRun({ action: "end", token })}>Yes, end it</button>
          <button className="btn ghost" type="button" onClick={() => setConfirm(false)}>Never mind</button>
        </>
      ) : status !== "lobby" && status !== "expired" ? (
        <button className="btn ghost" type="button" onClick={() => setConfirm(true)}>End game</button>
      ) : null}
    </div>
  );
}
