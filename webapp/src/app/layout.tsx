import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Mini Market — street & shop",
  description:
    "Walk the street, open the shop, take things off the counter, stop the bus and drive it. Multiplayer for three.js.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
