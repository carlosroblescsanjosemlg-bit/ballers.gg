import { inject, Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Participant, ParticipantPage, StatusFilter } from './participant.model';

@Injectable({ providedIn: 'root' })
export class ParticipantsService {
  private readonly http = inject(HttpClient);
  list(query: string, status: StatusFilter, page: number) {
    const params = new HttpParams().set('q', query).set('status', status).set('page', page).set('page_size', 12);
    return this.http.get<ParticipantPage>('/api/participants', { params });
  }
  save(participant: Participant | null, nick: string, active: boolean, logo: File | null, remove: boolean) {
    const body = new FormData();
    body.append('nick', nick); body.append('is_active', String(active));
    if (logo) body.append('logo', logo);
    if (participant) { body.append('version', String(participant.version)); body.append('remove_logo', String(remove)); }
    return participant ? this.http.put<Participant>(`/api/participants/${participant.id}`, body)
      : this.http.post<Participant>('/api/participants', body);
  }
  changeState(participant: Participant) {
    return this.http.patch<Participant>(`/api/participants/${participant.id}/state`, { is_active: !participant.is_active, version: participant.version });
  }
  logoUrl(participant: Participant) { return `/api/participants/${participant.id}/logo?v=${participant.version}`; }
}

export function errorMessage(error: HttpErrorResponse): string {
  if (typeof error.error?.detail === 'string') return error.error.detail;
  if (error.status === 0 || error.status === 502 || error.status === 504) {
    return 'No se puede conectar con el servidor. Ejecuta Main.py y mantén abierta su terminal mientras utilizas Ballers.gg.';
  }
  return 'No se pudo completar la operación. Revisa los mensajes de la terminal de Main.py y vuelve a intentarlo.';
}
export function initials(nick: string) { return Array.from(nick.trim()).slice(0, 2).join('').toUpperCase() || 'BG'; }
