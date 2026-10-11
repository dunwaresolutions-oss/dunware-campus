import { api } from "./api";

export interface GuardianDetail {
  id: string;
  school_id: string;
  school_name: string;
  school_district: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  children: {
    student_id: string | null; name: string; student_number: string;
    status: string; relationship: string;
  }[];
}

export const getGuardian = (id: string) => api<GuardianDetail>(`/central/guardians/${id}/`);
