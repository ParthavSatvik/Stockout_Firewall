// Supabase Auth over its REST API (no SDK). Only the publishable key is used here;
// secret/service keys must never be in frontend env vars.
const URL_ = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const KEY = (import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ?? import.meta.env.VITE_SUPABASE_ANON_KEY) as string | undefined;
const REFRESH_KEY = "stockout_firewall_refresh";

export const supabaseEnabled = Boolean(URL_ && KEY);

interface SessionResponse { access_token: string; refresh_token: string }

async function tokenRequest(grant: "password" | "refresh_token", body: object): Promise<string> {
  const resp = await fetch(`${URL_}/auth/v1/token?grant_type=${grant}`, {
    method: "POST",
    headers: { apikey: KEY!, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error_description ?? data.msg ?? "Sign-in failed");
  const s = data as SessionResponse;
  localStorage.setItem(REFRESH_KEY, s.refresh_token);
  return s.access_token;
}

export function supabaseSignIn(email: string, password: string): Promise<string> {
  return tokenRequest("password", { email, password });
}

/** Exchanges the stored refresh token for a new access token, or returns null. */
export async function supabaseRefresh(): Promise<string | null> {
  const refresh = localStorage.getItem(REFRESH_KEY);
  if (!supabaseEnabled || !refresh) return null;
  try {
    return await tokenRequest("refresh_token", { refresh_token: refresh });
  } catch {
    localStorage.removeItem(REFRESH_KEY);
    return null;
  }
}

export function clearSupabaseSession() {
  localStorage.removeItem(REFRESH_KEY);
}
