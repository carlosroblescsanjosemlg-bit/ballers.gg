import { Injectable, inject, signal } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom, timeout, TimeoutError } from 'rxjs';
import { errorMessage } from '../participants/participants.service';

interface Identity { authenticated: boolean; mode: 'account' | 'guest' | null; username: string | null; }
@Injectable({providedIn: 'root'})
export class AuthService {
  private http = inject(HttpClient);
  readonly identity = signal<Identity | null>(null);
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly error = signal('');
  constructor() { queueMicrotask(() => void this.restore()); }
  async restore() {
    this.loading.set(true); this.error.set('');
    try {
      let identity = await firstValueFrom(this.http.get<Identity>('/api/auth/session').pipe(timeout(15000)));
      if (identity.mode === 'guest' && !sessionStorage.getItem('ballers-guest')) {
        identity = await firstValueFrom(this.http.post<Identity>('/api/auth/logout', {}).pipe(timeout(15000)));
      }
      this.identity.set(identity);
    } catch (error) { this.error.set(this.accessError(error)); }
    finally { this.loading.set(false); }
  }
  async enter(action: 'login' | 'register' | 'guest', username = '', password = '') {
    if (this.busy()) return;
    this.busy.set(true); this.error.set('');
    try {
      const identity = await firstValueFrom(this.http.post<Identity>('/api/auth/' + action, {username, password}).pipe(timeout(15000)));
      if (identity.mode === 'guest') sessionStorage.setItem('ballers-guest', '1');
      else sessionStorage.removeItem('ballers-guest');
      this.identity.set(identity);
    } catch (error) { this.error.set(this.accessError(error)); }
    finally { this.busy.set(false); }
  }
  async logout() {
    if (this.busy()) return;
    this.busy.set(true); this.error.set('');
    try {
      const identity = await firstValueFrom(this.http.post<Identity>('/api/auth/logout', {}).pipe(timeout(15000)));
      sessionStorage.removeItem('ballers-guest'); this.identity.set(identity);
    } catch (error) { this.error.set(this.accessError(error)); }
    finally { this.busy.set(false); }
  }
  private accessError(error: unknown): string {
    if (error instanceof TimeoutError) {
      return 'El servidor tarda demasiado en responder. Comprueba que Main.py sigue funcionando. Si estabas creando una cuenta, prueba a iniciar sesión antes de repetir el registro: la cuenta podría haberse creado.';
    }
    return error instanceof HttpErrorResponse ? errorMessage(error) : 'No se pudo completar el acceso. Vuelve a intentarlo.';
  }

}
