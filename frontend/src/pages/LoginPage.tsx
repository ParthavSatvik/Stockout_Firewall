import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../lib/api";
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
      const resp = await api.post<TokenResponse>("/api/auth/login", { email, password });
      login(resp.access_token, resp.role);
      navigate(resp.role === "merchant" ? "/merchant" : resp.role === "supplier" ? "/supplier" : "/admin");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm mt-12">
      <Card>
        <CardHeader>
          <CardTitle>Log in to Stockout Firewall</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="space-y-3" onSubmit={handleSubmit}>
            <div className="space-y-1">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div className="space-y-1">
              <Label htmlFor="password">Password</Label>
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
              {loading ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          <div className="mt-5 border-t border-slate-100 pt-4">
            <p className="text-xs text-slate-500 mb-2">Demo accounts (password: demo1234)</p>
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
