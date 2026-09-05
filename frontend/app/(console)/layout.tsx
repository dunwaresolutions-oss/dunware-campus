"use client";

import Link from "next/link";
import Image from "next/image";
import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { isStaff, logout, whoami } from "@/lib/auth";
import { label } from "@/lib/format";

const NAV = [
  ["/", "Dashboard"],
  ["/people/", "Students"],
  ["/registration/", "Registration"],
  ["/scheduling/", "Scheduling"],
  ["/attendance/", "Attendance"],
  ["/lessons/", "Lessons"],
  ["/grades/", "Grades"],
  ["/booking/", "Booking"],
  ["/communication/", "Messages"],
  ["/billing/", "Billing"],
  ["/staff/", "Staff"],
] as const;

export default function ConsoleLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const { data: me, isLoading } = useQuery({ queryKey: ["me"], queryFn: whoami });

  useEffect(() => {
    if (isLoading) return;
    if (!isStaff(me?.role)) router.replace("/login/");
    else if (me?.mfa_enrollment_required || (me?.must_use_mfa && !me?.mfa_verified))
      router.replace("/mfa/");
  }, [isLoading, me, router]);

  if (isLoading || !isStaff(me?.role)) return null;
  if (me?.mfa_enrollment_required || (me?.must_use_mfa && !me?.mfa_verified))
    return null;

  const active = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <div className="grid min-h-screen grid-cols-[220px_1fr]">
      <aside
        className="sticky top-0 flex h-screen flex-col border-r border-[var(--glass-border)] bg-[var(--glass-bg)] [backdrop-filter:blur(var(--glass-blur))_saturate(160%)]"
      >
        <div className="flex items-center gap-2.5 border-b border-[var(--campus-line)] px-4 py-4">
          <Image
            src="/icon.png"
            alt=""
            width={26}
            height={26}
            className="rounded-md"
          />
          <span className="text-base font-semibold tracking-tight">Campus</span>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto p-2.5 text-sm">
          {NAV.map(([href, text]) => {
            const on = active(href);
            return (
              <Link
                key={href}
                href={href}
                className={`group relative flex items-center rounded-lg px-3 py-2 transition-all duration-150 ${
                  on
                    ? "bg-[var(--campus-accent-soft)] font-medium text-[var(--campus-accent)]"
                    : "text-[var(--campus-fg)]/80 hover:bg-black/[0.03] hover:pl-3.5 dark:hover:bg-white/[0.04]"
                }`}
              >
                <span
                  className={`absolute left-0 top-1/2 h-4 w-1 -translate-y-1/2 rounded-r-full bg-[var(--campus-accent)] transition-all duration-200 ${
                    on ? "opacity-100" : "opacity-0"
                  }`}
                />
                {text}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-[var(--campus-line)] p-3.5 text-xs">
          <div className="font-medium text-[var(--campus-fg)]">
            {me?.display_name || me?.username}
          </div>
          <div className="text-[var(--campus-muted)]">{label(me?.role)}</div>
          <button
            onClick={async () => {
              await logout();
              router.replace("/login/");
            }}
            className="mt-2 font-medium text-[var(--campus-accent)] transition-colors hover:text-[var(--campus-accent-strong)]"
          >
            Sign out
          </button>
        </div>
      </aside>

      <main className="overflow-x-hidden px-8 py-8">
        <div key={pathname} className="campus-enter mx-auto max-w-6xl">
          {children}
        </div>
      </main>
    </div>
  );
}
