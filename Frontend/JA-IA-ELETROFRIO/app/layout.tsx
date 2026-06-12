import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Eletrofrio Operações",
  description: "Monitoramento operacional de refrigeração",
  icons: {
    icon: [
      { url: "/favicon.png", type: "image/png" },
      { url: "/eletrofrio-mini.png", type: "image/png" },
    ],
    apple: "/eletrofrio-mini.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
