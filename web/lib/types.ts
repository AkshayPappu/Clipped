export type Player = {
  id: string;
  display_name: string;
  is_host: boolean;
  is_away: boolean;
};

export type Room = {
  id: string;
  code: string;
  status: string;
  phase_deadline: string | null;
  current_round: number;
  total_rounds: number;
  answer_seconds: number;
  vote_seconds: number;
  categories: string[];
  question_order: "random" | "sequential" | string;
  player_count: number;
};

export type PromptPhase = {
  round_number: number;
  total_rounds: number;
  question: string;
  category: string | null;
  submitted_count: number;
  player_count: number;
  your_answer: string | null;
  deadline: string | null;
};

export type VoteAnswer = {
  id: string;
  body: string;
  is_own: boolean;
};

export type VotingPhase = {
  round_number: number;
  total_rounds: number;
  question: string;
  category: string | null;
  deadline: string | null;
  rankings_in: number;
  rankings_needed: number;
  your_order: string[] | null;
  answers: VoteAnswer[];
};

export type Reveal = {
  body: string;
  author: string;
  place: number;
  points: number;
  tied: boolean;
  spots: number[];
};

export type Standing = {
  rank: number;
  display_name: string;
  points: number;
  firsts: number;
  round_points: number;
  delta: number;
};

export type Leaderboard = {
  round_number: number;
  total_rounds: number;
  is_final_round: boolean;
  question: string;
  category: string | null;
  reveals: Reveal[];
  standings: Standing[];
};

export type FinalPhase = {
  winners: string[];
  tied: boolean;
  standings: Standing[];
  best_answer: { body: string; author: string; points: number; place: number } | null;
  firsts: number;
  total_answers: number;
};

export type CustomPrompt = {
  id: string;
  body: string;
  included: boolean;
};

export type View = {
  ok: true;
  token?: string;
  local_mode?: boolean;
  server_now: string;
  room: Room;
  you: { id: string; display_name: string; is_host: boolean };
  players: Player[];
  prompt: PromptPhase | null;
  voting: VotingPhase | null;
  leaderboard: Leaderboard | null;
  final: FinalPhase | null;
  custom_prompts: CustomPrompt[];
  deck_count: number;
};

export type Fail = { ok: false; error?: string };

export type GameResult = View | Fail;

export function isView(value: GameResult | null): value is View {
  return Boolean(value && value.ok);
}
