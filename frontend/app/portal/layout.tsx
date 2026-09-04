"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { whoami } from "@/lib/auth";

export default function PortalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { data: me, isLoading } = useQuery({ queryKey: ["me"], queryFn: whoami });

  useEffect(() => {
    if (!isLoading && !me) router.replace("/login/");
  }, [isLoading, me, router]);

  if (isLoading || !me) return null;

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <header className="mb-8 flex items-center justify-between">
        <span className="font-semibold">Campus — Family Portal</span>
        <span className="text-sm text-neutral-500">{me.display_name}</span>
      </header>
      {children}
    </div>
  );
}
