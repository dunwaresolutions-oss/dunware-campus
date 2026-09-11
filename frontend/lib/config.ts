import { api } from "./api";

export interface SiteConfig {
  country: string;
  currency: string;
  currency_symbol: string;
  locale: string;
  collects_fees: boolean;
  deployment_mode: "SINGLE" | "SCHOOL" | "HEADQUARTERS";
  currency_locked: boolean;
  currency_options: { code: string; symbol: string; name: string }[];
  country_currencies: Record<string, string[]>;
}

export const getSiteConfig = () => api<SiteConfig>("/config/");

export const updateSiteConfig = (patch: Partial<SiteConfig>) =>
  api<SiteConfig>("/config/", { method: "PATCH", body: JSON.stringify(patch) });
