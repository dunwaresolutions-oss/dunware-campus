import { api } from "./api";

export type TemplateKind =
  | "INCIDENT"
  | "REPORT_CARD"
  | "ABSENCE"
  | "ANNOUNCEMENT"
  | "GENERAL";

export interface MessageTemplate {
  id: number;
  key: string;
  name: string;
  kind: TemplateKind;
  subject: string;
  body: string;
  description: string;
  active: boolean;
  is_system: boolean;
  updated_at: string;
}

export interface TokenGroup {
  group: string;
  tokens: { name: string; label: string; example: string }[];
}

export const tokenPalette = (kind: string) =>
  api<TokenGroup[]>(`/message-templates/tokens/?kind=${encodeURIComponent(kind)}`);

export const previewTemplate = (
  id: number,
  subject: string,
  body: string,
  student?: string,
) =>
  api<{ subject: string; body: string }>(
    `/message-templates/${id}/preview/`,
    { method: "POST", body: JSON.stringify({ subject, body, student }) },
  );
