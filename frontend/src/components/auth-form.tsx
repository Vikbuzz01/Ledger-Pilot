"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiRequest, setToken } from "@/lib/api";

type Props = { mode: "login" | "register" };

export function AuthForm({ mode }: Props) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "register") {
        await apiRequest("/api/v1/auth/register", {
          method: "POST",
          body: JSON.stringify({ email, full_name: fullName, password }),
        });
      }
      const token = await apiRequest<{ access_token: string }>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setToken(token.access_token);
      router.push("/dashboard");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to sign in. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const registering = mode === "register";
  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-gold-400">LedgerPilot</p>
        <CardTitle className="text-2xl">{registering ? "Create your account" : "Welcome back"}</CardTitle>
        <p className="text-sm text-slate-600">
          {registering ? "Set up a secure account to create your workspace." : "Sign in to your finance workspace."}
        </p>
        {!registering && process.env.NEXT_PUBLIC_DEMO_MODE === "true" && (
          <div className="mt-4 rounded-lg border border-gold-600/50 bg-gold-400/5 p-3 text-sm text-slate-800">
            <p className="font-semibold text-gold-400">Demo workspace</p>
            <p className="mt-1">Email: demo@ledgerpilot.com</p>
            <p>Password: LedgerPilot-Demo-2026!</p>
            <p className="mt-2 text-xs">Synthetic data only. Review proposed matches before approval.</p>
          </div>
        )}
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={submit}>
          {registering && (
            <label className="block space-y-1.5 text-sm font-medium">
              Full name
              <Input autoComplete="name" required maxLength={160} value={fullName} onChange={(e) => setFullName(e.target.value)} />
            </label>
          )}
          <label className="block space-y-1.5 text-sm font-medium">
            Email
            <Input type="email" autoComplete="email" required maxLength={320} value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="block space-y-1.5 text-sm font-medium">
            Password
            <Input
              type="password"
              autoComplete={registering ? "new-password" : "current-password"}
              required
              minLength={registering ? 12 : 1}
              maxLength={128}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {registering && <span className="block text-xs font-normal text-slate-500">Use at least 12 characters.</span>}
          </label>
          {error && <p role="alert" className="rounded-md bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Please wait…" : registering ? "Create account" : "Sign in"}
          </Button>
        </form>
        <p className="mt-5 text-sm text-slate-600">
          {registering ? "Already have an account? " : "New to LedgerPilot? "}
          <Link className="font-medium text-gold-400 underline-offset-4 hover:underline" href={registering ? "/login" : "/register"}>
            {registering ? "Sign in" : "Create an account"}
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
