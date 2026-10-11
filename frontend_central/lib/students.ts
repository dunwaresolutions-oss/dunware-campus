import { api } from "./api";

export interface StudentDetail {
  id: string;
  school_id: string;
  school_name: string;
  school_district: string;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  student_number: string;
  status: string;
  primary_group_name: string | null;
  enrolments: { group_name: string; start_date: string; end_date: string | null; status: string }[];
  attendance: {
    term_source_id: string; present: number; absent: number; late: number;
    present_pct: number | null;
  }[];
  guardians: {
    id: string; name: string; email: string; phone: string; relationship: string;
  }[];
  consents: { kind: string; version: string; granted: boolean; recorded_at: string }[];
  report_cards: { term_source_id: string; status: string }[];
}

export const getStudent = (id: string) => api<StudentDetail>(`/central/students/${id}/`);
