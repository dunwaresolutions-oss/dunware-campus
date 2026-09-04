"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { isStaff, whoami } from "@/lib/auth";

const NAV = [
  ["/", "Dashboard"],
  ["/people/", "Students"],
  ["/scheduling/", "Scheduling"],
  ["/attendance/", "Attendance"],
  ["/lessons/", "Lessons"],
  ["/grades/", "Grades"],
  ["/booking/", "Booking"],
  ["/communication/", "Messages"],
  ["/registration/", "Registration"],
  ["/billing/", "Billing"],
] as const;

export default function ConsoleLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { data: me, isLoading } = useQuery({ queryKey: ["me"], queryFn: whoami });

  useEffect(() => {
    if (!isLoading && !isStaff(me?.role)) router.replace("/login/");
  }, [isLoading, me, router]);

  if (isLoading || !isStaff(me?.role)) return null;

  return (
    <div className="min-h-screen grid grid-cols-[220px_1fr]">
      <aside className="border-r border-neutral-200 bg-white p-4">
        <div className="font-semibold">Campus</div>
        <nav className="mt-4 space-y-1 text-sm">
          {NAV.map(([href, label]) => (
            <Link
              key={href}
              href={href}
              className="block rounded px-2 py-1.5 hover:bg-neutral-100"
            >
              {label}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="p-8">{children}</main>
    </div>
  );
}
