import { AuthForm } from "@/components/auth-form";

export default function LoginPage() {
  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-4 py-12">
      <div aria-hidden="true" className="pointer-events-none absolute -left-32 top-1/4 h-80 w-80 rounded-full bg-gold-400/5 blur-3xl" />
      <AuthForm mode="login" />
    </main>
  );
}
