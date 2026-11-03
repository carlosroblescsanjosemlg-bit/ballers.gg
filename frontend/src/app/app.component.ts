import { Component, effect, inject, signal } from '@angular/core';
import { StatisticsPageComponent } from './features/statistics/statistics-page.component';
import { Title } from '@angular/platform-browser';
import { HomePageComponent } from './features/home/home-page.component';
import { ParticipantsPageComponent } from './features/participants/participants-page.component';
import { TournamentsPageComponent } from './features/tournaments/tournaments-page.component';
import { AccessComponent } from './features/access/access.component';
import { AuthService } from './features/access/auth.service';
import { Section } from './shared/header.component';

@Component({selector:'app-root',standalone:true,imports:[StatisticsPageComponent,HomePageComponent,ParticipantsPageComponent,TournamentsPageComponent,AccessComponent],template:`
  @if(auth.loading()){<div class="access-loading" role="status">BALLERS.GG · Conectando…</div>}
  @else if(auth.identity()?.authenticated){
    @switch(section()){
      @case('statistics'){<app-statistics [playerId]="historyPlayer()" (navigate)="navigate($event)" />}
      @case('home'){<app-home (navigate)="navigate($event)" (start)="start($event)" />}
      @case('players'){<app-participants-page [startCreating]="createOnEntry()" (navigate)="navigate($event)" (showHistory)="openPlayerHistory($event)" />}
      @case('tournaments'){<app-tournaments-page [startCreating]="createOnEntry()" (navigate)="navigate($event)" />}
    }
  }
  @else if(auth.error() && !auth.identity()){<main class="access-loading"><p role="alert">{{auth.error()}}</p><button class="primary" (click)="auth.restore()">Reintentar conexión</button></main>}
  @else{<app-access />}
`})
export class AppComponent {
  readonly auth=inject(AuthService);
  readonly section=signal<Section>('home');
  readonly createOnEntry=signal(false);
  readonly historyPlayer=signal<number|null>(null);
  openPlayerHistory(id:number){this.historyPlayer.set(id);this.createOnEntry.set(false);this.section.set('statistics');}
  private title=inject(Title);
  constructor(){
    effect(()=>{
      const authenticated=this.auth.identity()?.authenticated;
      if(!authenticated){this.section.set('home');this.createOnEntry.set(false);}
      const titles={home:'Inicio',players:'Jugadores',tournaments:'Torneos',statistics:'Estadísticas'};
      this.title.setTitle('Ballers.gg · '+(authenticated?titles[this.section()]:'Acceso'));
    });
  }
  navigate(section:Section){
    this.historyPlayer.set(null);this.createOnEntry.set(false);this.section.set(section);
    requestAnimationFrame(()=>window.scrollTo({top:0,behavior:'instant'}));
  }
  start(section:'players'|'tournaments'){
    this.createOnEntry.set(true);this.section.set(section);
    requestAnimationFrame(()=>window.scrollTo({top:0,behavior:'instant'}));
  }
}
