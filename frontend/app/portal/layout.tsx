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
  return <div className="min-h-screen bg-neutral-50">{children}</div>;
}
