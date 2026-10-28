export const ROUNDS = [5, 10, 15, 20] as const;
export const TIMERS = [30, 45, 60, 90] as const;

export const PACKS = [
  { id: "lore", label: "Friend group lore" },
  { id: "exposing", label: "Exposing the group" },
  { id: "deep_cuts", label: "Deep cuts" },
  { id: "brainrot", label: "Brainrot and chaos" },
  { id: "legendary", label: "Legendary moments" },
] as const;

const PACK_LABELS: Record<string, string> = {
  lore: "Friend group lore",
  exposing: "Exposing the group",
  deep_cuts: "Deep cuts",
  brainrot: "Brainrot and chaos",
  legendary: "Legendary moments",
  custom: "Custom",
};

export function packLabel(key: string | null | undefined) {
  if (!key) return "";
  return PACK_LABELS[key] || key;
}

export function placePoints(place: number, count: number) {
  if (count <= 0 || place <= 0) return 0;
  if (count === 1) return 300;
  return Math.floor((300 * (count - place) + Math.floor((count - 1) / 2)) / (count - 1));
}

export function ordinal(place: number) {
  const mod100 = place % 100;
  const mod10 = place % 10;
  const suffix =
    mod100 >= 11 && mod100 <= 13
      ? "th"
      : mod10 === 1
        ? "st"
        : mod10 === 2
          ? "nd"
          : mod10 === 3
            ? "rd"
            : "th";
  return `${place}${suffix}`;
}

export function secondsLeft(serverNow: string, deadline: string | null, now = Date.now()) {
  if (!deadline) return 0;
  const skew = now - Date.parse(serverNow);
  const end = Date.parse(deadline);
  return Math.max(0, Math.ceil((end - (now - skew)) / 1000 - 1e-6));
}

export function clock(total: number) {
  const safe = Math.max(0, total);
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export function revealTone(reveal: { place: number; tied: boolean }) {
  if (reveal.place === 1 && !reveal.tied) return "gem";
  if (reveal.tied) return "common";
  if (reveal.place <= 0) return "none";
  return "lower";
}

export function placeLabel(reveal: { place: number; tied: boolean }) {
  if (reveal.place <= 0) return "No rankings";
  if (reveal.tied) return `Tied · ${ordinal(reveal.place)}`;
  return ordinal(reveal.place);
}
