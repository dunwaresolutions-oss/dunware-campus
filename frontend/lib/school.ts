import { api } from "./api";

export interface SchoolProfile {
  name: string;
  legal_name: string;
  motto: string;
  address_line1: string;
  address_line2: string;
  city: string;
  region: string;
  postal_code: string;
  country: string;
  address_block: string;
  phone: string;
  email: string;
  website: string;
  principal_name: string;
  principal_title: string;
  principal_user: string | null;
  principal_user_name: string;
  logo_url: string | null;
  has_signature: boolean;
  signature_url: string | null;
  report_card_footer: string;
  updated_at: string;
}

export const getSchoolProfile = () => api<SchoolProfile>("/school-profile/");

/** Text fields only — send as JSON. */
export const updateSchoolProfile = (patch: Partial<SchoolProfile>) =>
  api<SchoolProfile>("/school-profile/", {
    method: "PATCH",
    body: JSON.stringify(patch),
  });

/** Superadmin only — bind the one staff account allowed to sign report cards. */
export const designatePrincipal = (userId: string) =>
  api<SchoolProfile>("/school-profile/", {
    method: "PATCH",
    body: JSON.stringify({ principal_user: userId }),
  });

/** Replace the logo (multipart). */
export const uploadSchoolLogo = (file: File) => {
  const fd = new FormData();
  fd.append("logo", file);
  return api<SchoolProfile>("/school-profile/", { method: "PATCH", body: fd });
};

export const clearSchoolLogo = () =>
  api<SchoolProfile>("/school-profile/", { method: "DELETE" });

/** Only the designated principal (or a superadmin) may succeed here — the
 * server checks again regardless of what the UI allows. */
export const uploadSignature = (file: File) => {
  const fd = new FormData();
  fd.append("signature", file);
  return api<SchoolProfile>("/school-profile/", { method: "PATCH", body: fd });
};

export const clearSignature = () =>
  api<void>("/school-profile/signature/", { method: "DELETE" });
