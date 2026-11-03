export type TournamentFormat = 'single_elimination' | 'double_elimination' | 'groups_knockout' | 'league';
export interface Candidate { id: number; nick: string; }
export interface Entry { entry_id: number; participant_id: number; nick: string; is_active: boolean; draw_position: number; member_ids: number[]; member_names: string[]; }
export interface TournamentSummary { id: number; name: string; format: TournamentFormat; pair_mode: PairMode; league_rounds: number; competitor_count: number; version: number; participant_count: number; created_at: string; finished_at: string | null; }
export interface MatchSlot { kind: 'participant' | 'bye' | 'source' | 'qualifier'; label: string; participant_id: number | null; }
export interface Match { id: string; code: string; position: number; state: 'scheduled' | 'bye' | 'waiting' | 'empty' | 'completed'; slots: MatchSlot[]; result: MatchResult | null; }
export interface Round { number: number; name: string; matches: Match[]; }
export interface Stage { key: string; kind: 'knockout' | 'upper' | 'lower' | 'final' | 'group' | 'league'; name: string; position: number; rounds: Round[]; participants: Entry[]; standings?: Standing[]; complete?: boolean; ready?: boolean; draw_used?: boolean; }
export interface Tournament extends TournamentSummary { participants: Entry[]; stages: Stage[]; group_qualifiers: number | null; version: number; finished_at: string | null; status: string; champion: Entry | null; completed_matches: number; }
export interface TournamentPage { items: TournamentSummary[]; total: number; page: number; page_size: number; }
export interface TournamentCreate { name: string; format: TournamentFormat; participant_count: number; pair_mode: PairMode; league_rounds: number; pairs: number[][]; participant_ids: number[]; request_key: string; }
export const FORMATS: {id:TournamentFormat;label:string;short:string;description:string}[] = [
  {id:'league',label:'Liga',short:'TODOS CONTRA TODOS',description:'Clasificación por puntos y diferencia de goles. Elige una vuelta o ida y vuelta. El primero se lleva el título.'},
  {id:'single_elimination',label:'K.O. directo',short:'K.O.',description:'Un partido, una oportunidad. El ganador avanza y el perdedor queda eliminado.'},
  {id:'double_elimination',label:'Doble oportunidad',short:'UPPER + LOWER',description:'La primera derrota te lleva al lower. El perdedor de la final del upper juega la final del lower. Sus campeones disputan una final general única.'},
  {id:'groups_knockout',label:'Grupos + K.O.',short:'GRUPOS + K.O.',description:'Grupos de 2 a 4 competidores, jugadores o parejas. Todos contra todos a una vuelta; los dos primeros pasan al K.O.'}
];
export function formatLabel(format:TournamentFormat) { return FORMATS.find(value=>value.id===format)?.label ?? format; }

export interface MatchResult { home_score: number; away_score: number; winner_participant_id: number | null; recorded_at: string; }
export interface ResultCreate { version: number; home_score: number; away_score: number; winner_participant_id: number | null; }
export interface Standing { participant_id: number; nick: string; position: number; played: number; won: number; drawn: number; lost: number; goals_for: number; goals_against: number; goal_difference: number; points: number; by_draw: boolean; }

export type PairMode = 'individual' | 'manual' | 'random';
export function pairLabel(mode:PairMode){return mode==='manual'?'Parejas elegidas':mode==='random'?'Parejas aleatorias':'Individual';}
