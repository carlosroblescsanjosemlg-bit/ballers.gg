import { inject } from '@angular/core';
import { HttpInterceptorFn } from '@angular/common/http';
import { catchError, throwError } from 'rxjs';
import { AuthService } from './auth.service';
export const sessionInterceptor: HttpInterceptorFn = (request, next) => {
  const auth = inject(AuthService);
  return next(request).pipe(catchError(error => {
    if (error.status === 401 && !request.url.startsWith('/api/auth/')) {
      auth.identity.set({authenticated:false, mode:null, username:null});
      auth.error.set('Tu sesión ha terminado. Vuelve a entrar para continuar.');
    }
    return throwError(() => error);
  }));
};
