import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Blood Inventory Intelligence & Early Warning System | Terumo BCT",
  description: "Predictive decision-support system for blood availability, demand forecasting, and redistribution in Kenya.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark h-full antialiased">
      <body className="min-h-full flex flex-col bg-[#140204] text-[#FFF6F6]">
        {children}
      </body>
    </html>
  );
}
