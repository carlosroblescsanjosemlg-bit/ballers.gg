import { Component, inject, input, output } from '@angular/core';
import { AuthService } from '../features/access/auth.service';

export type Section = 'home' | 'players' | 'tournaments' | 'statistics';
@Component({selector:'app-header',standalone:true,template:`
  <header class="site-header">
    <a href="/" (click)="$event.preventDefault(); navigate.emit('home')" class="wordmark" aria-label="Ballers.gg, inicio"><svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 2 29 9v14l-13 7L3 23V9Z"/><path d="m16 9 7 4v7l-7 4-7-4v-7ZM16 2v7m13 0-6 4m6 10-6-3m-7 10v-6M3 23l6-3M3 9l6 4"/></svg><span>ballers<span class="gg">.gg</span></span></a>
    <nav aria-label="Principal"><button class="section-link" [class.nav-current]="active() === 'home'" [attr.aria-current]="active() === 'home' ? 'page' : null" (click)="navigate.emit('home')">Inicio</button><button class="section-link" [class.nav-current]="active() === 'players'" [attr.aria-current]="active() === 'players' ? 'page' : null" (click)="navigate.emit('players')">Jugadores</button><button class="section-link" [class.nav-current]="active() === 'tournaments'" [attr.aria-current]="active() === 'tournaments' ? 'page' : null" (click)="navigate.emit('tournaments')">Torneos</button><button class="section-link" [class.nav-current]="active()==='statistics'" [attr.aria-current]="active()==='statistics'?'page':null" (click)="navigate.emit('statistics')">Estadísticas</button></nav>
    <div class="account-tools"><span>{{auth.identity()?.username}}</span><button (click)="auth.logout()" [disabled]="auth.busy()">{{auth.identity()?.mode === 'guest' ? 'Salir y descartar' : 'Cerrar sesión'}}</button></div>
  </header>
`})
export class HeaderComponent {
  readonly auth = inject(AuthService);
  readonly active = input.required<Section>();
  readonly navigate = output<Section>();
}
