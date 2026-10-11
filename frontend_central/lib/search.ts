import { api } from "./api";

export interface SearchResults {
  students: {
    id: string; school_id: string; school_name: string; name: string;
    student_number: string; status: string;
  }[];
  guardians: {
    id: string; school_id: string; school_name: string; name: string; email: string;
  }[];
  staff: {
    id: string; school_id: string; school_name: string; username: string; role: string;
  }[];
}

export const search = (q: string) =>
  api<SearchResults>(`/central/search/?q=${encodeURIComponent(q)}`);
