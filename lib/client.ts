import type { GameResult } from "./types";

export const TOKEN_KEY = "clipped.token";

export async function play(body: Record<string, unknown>): Promise<GameResult> {
  try {
    const response = await fetch("/api/game", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return (await response.json()) as GameResult;
  } catch {
    return { ok: false, error: "The server could not reach the game. Try again." };
  }
}
