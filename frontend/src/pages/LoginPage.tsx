import { useState } from "react";
import { useT } from "../lib/i18n";
import { useNavigate } from "react-router-dom";
import { ApiError, api, setSession } from "../lib/api";
import { supabaseEnabled, supabaseSignIn } from "../lib/supabase";
import { useAuth } from "../lib/auth";
import type { UserRole } from "../lib/types";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Input, Label } from "../components/ui/input";

interface TokenResponse {
  access_token: string;
  role: UserRole;
  user_id: string;
}

const DEMO_ACCOUNTS: { label: string; email: string }[] = [
  { label: "Merchant — Ganesh Kirana", email: "merchant1@example.com" },
  { label: "Supplier — Anand Wholesale Grains", email: "anand@example.com" },
  { label: "Supplier — NewCo Supplies (new, low confidence)", email: "newco@example.com" },
  { label: "Admin — Control Tower", email: "admin@example.com" },
];
export function LoginPage() {
  const { t } = useT();
  const [email, setEmail] = useState("merchant1@example.com");
  const [password, setPassword] = useState("demo1234");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      let resp: { access_token: string; role: TokenResponse["role"] };
      if (supabaseEnabled) {
        // Supabase verifies the password; our backend decides the role from its own records.
        const accessToken = await supabaseSignIn(email, password);
        setSession(accessToken, "");
        const me = await api.get<{ role: TokenResponse["role"] }>("/api/auth/me");
        resp = { access_token: accessToken, role: me.role };
      } else {
        resp = await api.post<TokenResponse>("/api/auth/login", { email, password });
      }
      login(resp.access_token, resp.role);
      navigate(resp.role === "merchant" ? "/merchant" : resp.role === "supplier" ? "/supplier" : "/admin");
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : t("login.failed"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm mt-12">
      <Card>
        <CardHeader>
          <CardTitle>{t("login.title")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="space-y-3" onSubmit={handleSubmit}>
            <div className="space-y-1">
              <Label htmlFor="email">{t("login.email")}</Label>
              <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div className="space-y-1">
              <Label htmlFor="password">{t("login.password")}</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {error && <p className="text-xs text-red-600">{error}</p>}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? t("login.signingIn") : t("login.signIn")}
            </Button>
          </form>

          <div className="mt-5 border-t border-slate-100 pt-4">
            <p className="text-xs text-slate-500 mb-2">{t("login.demoAccounts")}</p>
            <div className="space-y-1">
              {DEMO_ACCOUNTS.map((acc) => (
                <button
                  key={acc.email}
                  type="button"
                  className="block w-full text-left text-xs text-brand-600 hover:underline"
                  onClick={() => {
                    setEmail(acc.email);
                    setPassword("demo1234");
                  }}
                >
                  {acc.label} ({acc.email})
                </button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
