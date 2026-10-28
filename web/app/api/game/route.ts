import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

type Payload = Record<string, unknown>;

const GENERIC = "The server could not reach the game. Try again.";

function rpcCall(body: Payload): { name: string; params: Payload } | null {
  const token = typeof body.token === "string" ? body.token : "";
  switch (body.action) {
    case "create":
      return { name: "create_room", params: { p_display_name: body.name } };
    case "join":
      return { name: "join_room", params: { p_code: body.code, p_display_name: body.name } };
    case "sync":
      return { name: "sync_room", params: { p_token: token } };
    case "leave":
      return { name: "leave_room", params: { p_token: token } };
    case "settings":
      return {
        name: "update_settings",
        params: {
          p_token: token,
          p_total_rounds: body.rounds,
          p_answer_seconds: body.answerSeconds,
          p_vote_seconds: body.voteSeconds,
          p_categories: body.categories,
          p_question_order: body.order,
        },
      };
    case "custom":
      return {
        name: "save_custom_prompt",
        params: { p_token: token, p_body: body.body, p_prompt_id: body.promptId ?? null },
      };
    case "deleteCustom":
      return { name: "delete_custom_prompt", params: { p_token: token, p_prompt_id: body.promptId } };
    case "include":
      return {
        name: "set_prompt_included",
        params: { p_token: token, p_prompt_id: body.promptId, p_included: body.included },
      };
    case "import":
      return { name: "import_prompts", params: { p_token: token, p_raw: body.body } };
    case "start":
      return { name: "start_game", params: { p_token: token } };
    case "answer":
      return { name: "submit_answer", params: { p_token: token, p_body: body.body } };
    case "rank":
      return { name: "submit_ranking", params: { p_token: token, p_order: body.order } };
    case "skip":
      return { name: "skip_phase", params: { p_token: token } };
    case "next":
      return { name: "next_round", params: { p_token: token } };
    case "again":
      return { name: "play_again", params: { p_token: token } };
    case "end":
      return { name: "end_game", params: { p_token: token } };
    default:
      return null;
  }
}

function normalize(data: unknown): { ok: boolean; error?: string } {
  let value = data;
  if (Array.isArray(value)) value = value[0];
  if (typeof value === "string") {
    try {
      value = JSON.parse(value);
    } catch {
      return { ok: false, error: GENERIC };
    }
  }
  if (value && typeof value === "object" && "ok" in value) {
    return value as { ok: boolean; error?: string };
  }
  return { ok: false, error: GENERIC };
}

export async function POST(request: Request) {
  const url = process.env.SUPABASE_URL?.trim();
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY?.trim();
  if (!url || !key) {
    return NextResponse.json({ ok: false, error: "Supabase is not configured on the server." }, { status: 500 });
  }

  let body: Payload;
  try {
    body = (await request.json()) as Payload;
  } catch {
    return NextResponse.json({ ok: false, error: GENERIC }, { status: 400 });
  }

  const call = rpcCall(body);
  if (!call) {
    return NextResponse.json({ ok: false, error: GENERIC }, { status: 400 });
  }

  try {
    const response = await fetch(`${url}/rest/v1/rpc/${call.name}`, {
      method: "POST",
      headers: {
        apikey: key,
        Authorization: `Bearer ${key}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(call.params),
      cache: "no-store",
    });
    const data: unknown = await response.json().catch(() => null);
    const result = normalize(data);
    if (!response.ok && result.ok !== false) {
      console.error("game rpc failed", call.name, response.status);
      return NextResponse.json({ ok: false, error: GENERIC }, { status: 502 });
    }
    return NextResponse.json(result);
  } catch (error) {
    console.error("game rpc unreachable", call.name, error);
    return NextResponse.json({ ok: false, error: GENERIC }, { status: 502 });
  }
}
