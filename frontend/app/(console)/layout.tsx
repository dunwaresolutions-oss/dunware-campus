"use client";

import Link from "next/link";
import Image from "next/image";
import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { isStaff, logout, whoami, type Role } from "@/lib/auth";
import { label } from "@/lib/format";
import { CommandPalette } from "@/components/CommandPalette";

const OFFICE: Role[] = ["SUPERADMIN", "ADMIN", "FRONT_DESK"];
const ADMIN: Role[] = ["SUPERADMIN", "ADMIN"];
const INSTRUCT: Role[] = ["SUPERADMIN", "ADMIN", "TEACHER", "TUTOR"];

/** [href, label, roles?] — no `roles` means every staff role sees it. */
const NAV: [string, string, Role[]?][] = [
  ["/", "Dashboard"],
  ["/people/", "Students"],
  ["/registration/", "Registration", OFFICE],
  ["/scheduling/", "Scheduling"],
  ["/attendance/", "Attendance"],
  ["/lessons/", "Lessons", INSTRUCT],
  ["/grades/", "Grades"],
  ["/booking/", "Booking"],
  ["/communication/", "Messages"],
  ["/billing/", "Billing", OFFICE],
  ["/staff/", "Staff", ADMIN],
  ["/audit/", "Audit log", ADMIN],
];

export default function ConsoleLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const { data: me, isLoading } = useQuery({ queryKey: ["me"], queryFn: whoami });

  const nav = NAV.filter(
    ([, , roles]) => !roles || (me?.role != null && roles.includes(me.role)),
  );

  useEffect(() => {
    if (isLoading) return;
    if (!isStaff(me?.role)) {
      router.replace("/login/");
      return;
    }
    if (me?.mfa_enrollment_required || (me?.must_use_mfa && !me?.mfa_verified)) {
      router.replace("/mfa/");
      return;
    }
    // a role that reaches a page not in its nav (typed URL) -> home
    const allowed = nav.some(([href]) =>
      href === "/" ? pathname === "/" : pathname.startsWith(href),
    );
    if (!allowed) router.replace("/");
  }, [isLoading, me, router, pathname, nav]);

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

        <div className="px-2.5 pt-2.5">
          <button
            onClick={() => window.dispatchEvent(new Event("campus:search"))}
            className="flex w-full items-center justify-between rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-2 text-sm text-[var(--campus-muted)] transition-colors hover:border-[var(--campus-accent)]"
          >
            <span>Search…</span>
            <kbd className="rounded border border-[var(--campus-line)] px-1.5 text-[11px]">
              Ctrl K
            </kbd>
          </button>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto p-2.5 text-sm">
          {nav.map(([href, text]) => {
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

      <CommandPalette />
    </div>
  );
}
