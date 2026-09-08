import { api } from "./api";

export interface SearchHit {
  id: string;
  label: string;
  sublabel: string;
  route: string;
}

export interface SearchGroup {
  title: string;
  items: SearchHit[];
}

export interface SearchResult {
  query: string;
  groups: SearchGroup[];
}

/** One box for the whole console — students, guardians, staff, groups,
 *  report cards, applications. Staff only, scoped server-side. */
export function search(q: string): Promise<SearchResult> {
  return api<SearchResult>(`/search/?q=${encodeURIComponent(q)}`);
}
