import { Component, computed, inject, input, OnDestroy, OnInit, output, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Subscription, timeout } from 'rxjs';
import { HeaderComponent, Section } from '../../shared/header.component';
import { formatLabel, pairLabel, TournamentFormat, PairMode } from '../tournaments/tournament.model';
import { tournamentError } from '../tournaments/tournaments.service';

interface PlayerStats {id:number;nick:string;is_active:boolean;position:number;played:number;won:number;drawn:number;lost:number;goals_for:number;goals_against:number;goal_difference:number;titles:number;tournaments:number;win_rate:number;team_matches:number;}
interface HistoryRow {tournament_id:number;tournament_name:string;format:TournamentFormat;pair_mode:PairMode;match_id:string;code:string;stage:string;round:string;team:string;opponent:string;partner:string|null;goals_for:number;goals_against:number;outcome:'win'|'draw'|'loss';penalties:boolean;recorded_at:string;}
interface Ranking {items:PlayerStats[];total:number;page:number;page_size:number;tournaments:number;finished_tournaments:number;matches:number;}
interface History {player:PlayerStats;items:HistoryRow[];titles:{tournament_id:number;name:string;format:TournamentFormat;pair_mode:PairMode}[];total:number;page:number;page_size:number;}

@Component({selector:'app-statistics',standalone:true,imports:[HeaderComponent,DatePipe,FormsModule],templateUrl:'./statistics-page.component.html'})
export class StatisticsPageComponent implements OnInit,OnDestroy {
  readonly navigate=output<Section>();readonly playerId=input<number|null>(null);
  private readonly http=inject(HttpClient);private request?:Subscription;
  readonly ranking=signal<Ranking|null>(null);readonly history=signal<History|null>(null);
  readonly loading=signal(false);readonly error=signal('');readonly mode=signal<'ranking'|'history'>('ranking');
  readonly page=signal(1);readonly historyPage=signal(1);readonly search=signal('');private selectedId=0;
  readonly pages=computed(()=>Math.max(1,Math.ceil((this.ranking()?.total??0)/12)));
  readonly historyPages=computed(()=>Math.max(1,Math.ceil((this.history()?.total??0)/20)));
  readonly formatLabel=formatLabel;readonly pairLabel=pairLabel;
  ngOnInit(){const id=this.playerId();if(id)this.openHistory(id);else this.load();}
  load(){this.request?.unsubscribe();this.mode.set('ranking');this.loading.set(true);this.error.set('');
    this.request=this.http.get<Ranking>('/api/statistics',{params:new HttpParams().set('page',this.page()).set('q',this.search())}).pipe(timeout(60000)).subscribe({next:value=>{this.ranking.set(value);this.loading.set(false);},error:error=>{this.error.set(tournamentError(error));this.loading.set(false);}});}
  setPage(page:number){this.page.set(page);this.load();}
  find(){this.page.set(1);this.load();}
  openHistory(id:number,page=1){this.request?.unsubscribe();this.selectedId=id;this.mode.set('history');this.historyPage.set(page);this.loading.set(true);this.error.set('');
    this.request=this.http.get<History>(`/api/participants/${id}/history`,{params:new HttpParams().set('page',page)}).pipe(timeout(60000)).subscribe({next:value=>{this.history.set(value);this.loading.set(false);},error:error=>{this.error.set(tournamentError(error));this.loading.set(false);}});
    requestAnimationFrame(()=>window.scrollTo({top:0,behavior:'instant'}));}
  historyStep(page:number){this.openHistory(this.selectedId,page);}
  retry(){if(this.mode()==='ranking')this.load();else this.openHistory(this.selectedId,this.historyPage());}
  ngOnDestroy(){this.request?.unsubscribe();}
}
