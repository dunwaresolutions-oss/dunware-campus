import { api } from "./api";

export type IEPStatus = "DRAFT" | "ACTIVE" | "UNDER_REVIEW" | "ARCHIVED";

export interface IEP {
  id: string;
  student: string;
  student_name?: string;
  school_year: string;
  status: IEPStatus;
  primary_concern: string;
  start_date: string | null;
  review_date: string | null;
  end_date: string | null;
  strengths: string;
  needs: string;
  summary: string;
  case_manager: string | null;
  case_manager_name?: string;
  goal_count?: number;
  updated_at: string;
}

export const iepDocument = (id: string) =>
  api<{ html: string }>(`/ieps/${id}/document/`);

export const IEP_STATUS: IEPStatus[] = ["DRAFT", "ACTIVE", "UNDER_REVIEW", "ARCHIVED"];

export const GOAL_AREAS = [
  "READING", "WRITING", "MATH", "COMMUNICATION", "SOCIAL_EMOTIONAL",
  "BEHAVIOUR", "MOTOR", "ORGANISATION", "LIFE_SKILLS", "OTHER",
];
export const GOAL_PROGRESS = [
  "NOT_STARTED", "EMERGING", "PROGRESSING", "MET", "DISCONTINUED",
];
export const ACC_CATEGORIES = [
  "PRESENTATION", "RESPONSE", "SETTING", "TIMING", "ASSISTIVE_TECH", "OTHER",
];
export const REVIEW_OUTCOMES = ["CONTINUE", "REVISE", "EXIT", "REFER"];
