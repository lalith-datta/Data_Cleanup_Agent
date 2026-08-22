import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { AppHeader } from "@/components/AppHeader";
import { NewMigrationPanel } from "@/components/NewMigrationPanel";

export const metadata: Metadata = {
  title: "Migration Assistant",
  description:
    "Bring a client's data into the new system, with a human in the loop",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-neutral-50 text-neutral-900 antialiased">
        <Providers>
          <div className="flex min-h-dvh flex-col">
            <AppHeader />
            <div className="grid grid-cols-1 lg:h-[calc(100dvh-3.5rem)] lg:grid-cols-[minmax(340px,380px)_1fr]">
              {/* Left rail — persistent across list <-> detail navigation */}
              <aside className="border-b border-neutral-200 bg-white lg:border-b-0 lg:border-r lg:overflow-y-auto">
                <NewMigrationPanel />
              </aside>
              {/* Right pane — list of past migrations, or a run's detail */}
              <section className="lg:overflow-y-auto">{children}</section>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
