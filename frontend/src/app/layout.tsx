import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LedgerPilot",
  description: "Financial reconciliation workspace",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
