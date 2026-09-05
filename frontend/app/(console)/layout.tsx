"use client";

import Link from "next/link";
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
    <div className="grid min-h-screen grid-cols-[210px_1fr] bg-neutral-50">
      <aside className="flex flex-col border-r border-neutral-200 bg-white">
        <div className="border-b border-neutral-100 px-4 py-4 text-base font-semibold">
          Campus
        </div>
        <nav className="flex-1 space-y-0.5 p-2 text-sm">
          {NAV.map(([href, text]) => (
            <Link
              key={href}
              href={href}
              className={`block rounded px-3 py-2 ${
                active(href)
                  ? "bg-sky-50 font-medium text-sky-800"
                  : "text-neutral-700 hover:bg-neutral-100"
              }`}
            >
              {text}
            </Link>
          ))}
        </nav>
        <div className="border-t border-neutral-100 p-3 text-xs text-neutral-500">
          <div className="font-medium text-neutral-800">
            {me?.display_name || me?.username}
          </div>
          <div>{label(me?.role)}</div>
          <button
            onClick={async () => {
              await logout();
              router.replace("/login/");
            }}
            className="mt-2 text-sky-700 hover:underline"
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="overflow-x-hidden p-8">{children}</main>
    </div>
  );
}
