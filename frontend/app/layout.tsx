import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Campus",
  description: "Daycare and small-school operations — on-site.",
};

// Without an explicit viewport, some browser/DPI combinations lay the page
// out at a fixed "desktop" width and then scale the whole render down to
// fit the window — the page (and every modal) looks tiny in a corner with
// dead space around it. This pins the layout viewport to the real window.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
