import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Maliyet Platformu",
  description: "Türkiye odaklı sektör bazlı maliyet ve kârlılık platformu.",
};

interface RootLayoutProps {
  readonly children: ReactNode;
}

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="tr">
      <body>{children}</body>
    </html>
  );
}
