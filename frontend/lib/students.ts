import { list } from "./resource";
import type { SearchOption } from "@/components/SearchSelect";

interface StudentHit {
  id: string;
  display_name: string;
  student_number?: string;
  primary_group_name?: string;
}

/** Type-to-search students — for a SearchSelect field, not a giant <select>. */
export async function searchStudents(term: string): Promise<SearchOption[]> {
  const q = term.trim();
  if (!q) return [];
  const page = await list<StudentHit>("students", { q });
  return page.results.map((s) => ({
    value: s.id,
    label: s.display_name,
    sublabel: [s.student_number, s.primary_group_name].filter(Boolean).join(" · "),
  }));
}

interface GuardianLinkHit {
  id: string;
  student: string;
  guardian: string;
  guardian_name?: string;
  is_primary_contact: boolean;
}

/** The primary-contact guardian for a student (else their first guardian),
 * for auto-filling "who does this bill go to" once a student is picked. */
export async function primaryGuardianForStudent(
  studentId: string,
): Promise<{ id: string; label: string } | null> {
  if (!studentId) return null;
  const page = await list<GuardianLinkHit>("guardian-links", { student: studentId });
  const links = page.results;
  if (!links.length) return null;
  const primary = links.find((l) => l.is_primary_contact) ?? links[0];
  return { id: primary.guardian, label: primary.guardian_name || "" };
}
