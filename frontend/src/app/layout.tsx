import type { Metadata } from "next";
import "./globals.css";
import "./workspace.css";
import "./data.css";
import "./twin.css";

export const metadata: Metadata = {
  title: "NEXORA TWIN · Business intelligence",
  description: "Understand Your Business. Simulate Your Future.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><a className="skip-link" href="#main-content">Skip to main content</a>{children}</body></html>;
}
