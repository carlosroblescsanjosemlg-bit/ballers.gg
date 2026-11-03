export interface Participant {
  id: number;
  nick: string;
  is_active: boolean;
  has_logo: boolean;
  created_at: string;
  updated_at: string;
  version: number;
}
export interface ParticipantPage {
  items: Participant[];
  total: number;
  page: number;
  page_size: number;
  summary: { total: number; active: number; inactive: number };
}
export type StatusFilter = 'all' | 'active' | 'inactive';
