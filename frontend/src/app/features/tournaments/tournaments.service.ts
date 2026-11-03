import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { timeout, TimeoutError } from 'rxjs';
import { Candidate, ResultCreate, Tournament, TournamentCreate, TournamentPage } from './tournament.model';
import { errorMessage } from '../participants/participants.service';

@Injectable({providedIn:'root'})
export class TournamentsService {
  private http = inject(HttpClient);
  list(page:number) { return this.http.get<TournamentPage>('/api/tournaments',{params:new HttpParams().set('page',page)}).pipe(timeout(15000)); }
  get(id:number) { return this.http.get<Tournament>(`/api/tournaments/${id}`).pipe(timeout(60000)); }
  result(id:number, matchId:string, payload:ResultCreate) { return this.http.post<Tournament>(`/api/tournaments/${id}/matches/${encodeURIComponent(matchId)}/result`,payload).pipe(timeout(15000)); }
  remove(id:number,version:number) { return this.http.delete<void>(`/api/tournaments/${id}`,{params:new HttpParams().set('version',version)}).pipe(timeout(15000)); }
  eligible() { return this.http.get<Candidate[]>('/api/tournaments/eligible').pipe(timeout(15000)); }
  create(payload:TournamentCreate) { return this.http.post<Tournament>('/api/tournaments',payload).pipe(timeout(60000)); }
}
export function tournamentError(error:unknown):string {
  if(error instanceof TimeoutError) return 'El servidor tarda demasiado. Recarga el cuadro o el listado para comprobar si la operación se completó antes de volver a intentarlo.';
  if(error instanceof HttpErrorResponse) {
    if(error.status===422 && Array.isArray(error.error?.detail)) return 'Revisa el nombre, el número de jugadores y la selección.';
    return errorMessage(error);
  }
  return 'No se pudo completar la operación. Vuelve a intentarlo.';
}
