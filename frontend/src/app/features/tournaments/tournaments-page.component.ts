import { ParticipantFormComponent } from '../participants/participant-form.component';
import { Participant } from '../participants/participant.model';
import { ChangeDetectorRef, Component, computed, ElementRef, inject, input, OnDestroy, OnInit, output, signal, viewChild } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule, NgForm } from '@angular/forms';
import { Subscription } from 'rxjs';
import { HeaderComponent, Section } from '../../shared/header.component';
import { AuthService } from '../access/auth.service';
import { Candidate, FORMATS, Match, PairMode, Stage, Tournament, TournamentFormat, TournamentPage, TournamentSummary, formatLabel, pairLabel } from './tournament.model';
import { TournamentsService, tournamentError } from './tournaments.service';
import { initials } from '../participants/participants.service';

@Component({selector:'app-tournaments-page',standalone:true,imports:[HeaderComponent,FormsModule,DatePipe,ParticipantFormComponent],templateUrl:'./tournaments-page.component.html'})
export class TournamentsPageComponent implements OnDestroy, OnInit {
  readonly auth=inject(AuthService);
  readonly api=inject(TournamentsService);
  readonly startCreating=input(false);
  readonly navigate=output<Section>();
  readonly playerForm=viewChild.required(ParticipantFormComponent);
  readonly formats=FORMATS;
  readonly formatLabel=formatLabel;
  readonly pairLabel=pairLabel;
  readonly initials=initials;
  readonly mode=signal<'list'|'create'|'detail'>('list');
  readonly data=signal<TournamentPage|null>(null);
  readonly detail=signal<Tournament|null>(null);
  readonly error=signal('');
  readonly submitted=signal(false);
  readonly validationError=signal(false);
  readonly notice=signal('');
  readonly loading=signal(false);
  readonly saving=signal(false);
  readonly candidatesLoading=signal(false);
  readonly candidates=signal<Candidate[]>([]);
  readonly selected=signal<Set<number>>(new Set());
  readonly search=signal('');
  readonly page=signal(1);
  readonly pages=computed(()=>Math.max(1,Math.ceil((this.data()?.total??0)/12)));
  readonly filtered=computed(()=>this.candidates().filter(p=>p.nick.toLocaleLowerCase().includes(this.search().toLocaleLowerCase())));
  name=''; format:TournamentFormat='single_elimination'; playerCount:number|null=8;
  pairMode:PairMode='individual'; leagueRounds=1;
  readonly pairRows=computed(()=>{const ids=[...this.selected()];return Array.from({length:Math.ceil(ids.length/2)},(_,i)=>ids.slice(i*2,i*2+2));});
  readonly pairChoices=computed(()=>[...this.selected()].map(id=>this.candidates().find(p=>p.id===id)!).filter(Boolean));
  readonly leagueDay=signal(1);
  visibleRounds(stage:Stage){return stage.kind==='league'?stage.rounds.filter(r=>r.number===this.leagueDay()):stage.rounds;}
  swapPair(index:number,id:number){const ids=[...this.selected()];const other=ids.indexOf(id);if(other<0)return;[ids[index],ids[other]]=[ids[other],ids[index]];this.selected.set(new Set(ids));}
  readonly drawActive=signal(false);
  readonly drawIndex=signal(-1);
  readonly drawRunning=signal(false);
  readonly drawItems=signal<{title:string;left:string;right:string}[]>([]);
  private drawTimer?:ReturnType<typeof setTimeout>;
  startDraw(value:Tournament){
    const items:{title:string;left:string;right:string}[]=[];
    if(value.pair_mode==='random')value.participants.forEach(p=>items.push({title:'PAREJA',left:p.member_names[0],right:p.member_names[1]}));
    for(const stage of value.stages){
      if(stage.kind==='lower'||stage.kind==='final'||(value.format==='groups_knockout'&&stage.kind==='knockout'))continue;
      if(stage.kind==='group')items.push({title:stage.name,left:stage.participants.map(p=>p.nick).join(' · '),right:'Dos plazas para el K.O.'});
      else for(const match of stage.rounds[0]?.matches??[])items.push({title:stage.kind==='league'?'PRIMERA JORNADA':'ENFRENTAMIENTO',left:match.slots[0].label,right:match.slots[1].label});
    }
    this.drawItems.set(items);this.drawActive.set(items.length>0);this.replayDraw();
  }
  private scheduleDraw(delay=2100){
    clearTimeout(this.drawTimer);
    this.drawTimer=setTimeout(()=>{
      if(!this.drawActive()||!this.drawRunning())return;
      // No consumir la presentación mientras la pestaña esté oculta.
      if(document.hidden){this.scheduleDraw(500);return;}
      this.drawIndex.update(index=>Math.min(index+1,this.drawItems().length-1));
      if(this.drawIndex()+1>=this.drawItems().length)this.drawRunning.set(false);
      else this.scheduleDraw();
    },delay);
  }
  replayDraw(){
    clearTimeout(this.drawTimer);this.drawIndex.set(-1);this.drawRunning.set(this.drawItems().length>0);
    requestAnimationFrame(()=>{if(this.drawActive()&&this.drawRunning())this.scheduleDraw(650);});
  }
  toggleDraw(){
    this.drawRunning.update(running=>!running);
    if(this.drawRunning())this.scheduleDraw(400);else clearTimeout(this.drawTimer);
  }
  revealAllDraw(){clearTimeout(this.drawTimer);this.drawRunning.set(false);this.drawIndex.set(this.drawItems().length-1);}
  finishDraw(){clearTimeout(this.drawTimer);this.drawRunning.set(false);this.drawActive.set(false);this.scrollTop();}

  readonly resultDialog=viewChild.required<ElementRef<HTMLDialogElement>>('resultDialog');
  readonly chosenMatch=signal<Match|null>(null);
  readonly resultError=signal('');
  readonly resultBusy=signal(false);
  readonly resultGroup=signal(false);
  readonly confetti=Array.from({length:28},(_,i)=>i);
  private readonly changeDetector=inject(ChangeDetectorRef);
  homeScore:number|null=null; awayScore:number|null=null; penaltyWinner:number|null=null;
  private resultRequest?:Subscription;
  openResult(stage:Stage,match:Match) {
    if(this.detail()?.finished_at || match.state!=='scheduled') return;
    this.chosenMatch.set(match); this.resultGroup.set(stage.kind==='group'||stage.kind==='league');
    this.homeScore=null;this.awayScore=null;this.penaltyWinner=null;this.resultError.set('');
    this.changeDetector.detectChanges();this.resultDialog().nativeElement.showModal();
  }
  closeResult() { if(!this.resultBusy()) this.resultDialog().nativeElement.close(); }
  cancelResult(event:Event) { if(this.resultBusy()) event.preventDefault(); }
  saveResult(form:NgForm) {
    if(this.resultBusy())return;
    form.control.markAllAsTouched();this.resultError.set('');
    if(form.invalid || this.homeScore===null || this.awayScore===null || !Number.isInteger(this.homeScore) || !Number.isInteger(this.awayScore)) {
      this.resultError.set('Introduce los dos marcadores con números enteros entre 0 y 99.');return;
    }
    const match=this.chosenMatch(), tournament=this.detail(); if(!match || !tournament)return;
    const tied=this.homeScore===this.awayScore;
    if(tied && !this.resultGroup() && !this.penaltyWinner){this.resultError.set('Selecciona al ganador por penaltis.');return;}
    this.resultBusy.set(true);
    this.resultRequest=this.api.result(tournament.id,match.id,{version:tournament.version,home_score:this.homeScore,away_score:this.awayScore,
      winner_participant_id:tied&&!this.resultGroup()?this.penaltyWinner:null}).subscribe({next:value=>{
        this.resultBusy.set(false);this.resultDialog().nativeElement.close();this.detail.set(value);
        const drew=value.stages.some(s=>s.draw_used&&!tournament.stages.find(old=>old.key===s.key)?.draw_used);
        this.notice.set(value.finished_at?'Torneo finalizado. ¡Ya tenemos campeón!':drew?'Desempate por sorteo realizado: había empate a puntos y diferencia de goles. Consulta el orden definitivo en el grupo.':'Resultado guardado. Las plazas y clasificaciones se han actualizado.');
        if(value.finished_at) requestAnimationFrame(()=>document.querySelector('.champion-celebration')?.scrollIntoView({behavior:'smooth',block:'center'}));
      },error:error=>{this.resultBusy.set(false);this.resultError.set(tournamentError(error));}});
  }
  reloadResult() { this.closeResult();this.openDetail(this.detailId); }
  readonly deleteDialog=viewChild.required<ElementRef<HTMLDialogElement>>('deleteDialog');
  readonly deleteTarget=signal<TournamentSummary|null>(null);
  readonly deleting=signal(false);
  readonly deleteError=signal('');
  private deleteRequest?:Subscription;
  openDelete(tournament:TournamentSummary) {
    this.deleteTarget.set(tournament);this.deleteError.set('');
    this.changeDetector.detectChanges();this.deleteDialog().nativeElement.showModal();
  }
  closeDelete() { if(!this.deleting())this.deleteDialog().nativeElement.close(); }
  cancelDelete(event:Event) { if(this.deleting())event.preventDefault(); }
  confirmDelete() {
    const target=this.deleteTarget();if(!target||this.deleting())return;
    this.deleting.set(true);this.deleteError.set('');
    this.deleteRequest=this.api.remove(target.id,target.version).subscribe({next:()=>{
      this.deleting.set(false);this.deleteDialog().nativeElement.close();this.detail.set(null);
      this.loadList();this.notice.set(`Torneo «${target.name}» eliminado. Tus jugadores siguen en la plantilla.`);
    },error:error=>{this.deleting.set(false);this.deleteError.set('No se ha podido confirmar la eliminación. '+tournamentError(error));}});
  }
  refreshAfterDeleteError() { this.closeDelete();this.retry(); }
  private request?:Subscription;
  private saveRequest?:Subscription;
  private requestKey='';
  private lastSubmission='';
  private detailId=0;
  ngOnInit() { if(this.startCreating()) this.openCreate(); else this.loadList(); }
  scrollTop() { requestAnimationFrame(()=>window.scrollTo({top:0,behavior:'instant'})); }
  loadList() {
    this.finishDraw();this.scrollTop();
    this.request?.unsubscribe(); this.mode.set('list'); this.loading.set(true); this.error.set('');
    this.request=this.api.list(this.page()).subscribe({next:data=>{const last=Math.max(1,Math.ceil(data.total/12));if(this.page()>last){this.page.set(last);this.loadList();return;}this.data.set(data);this.loading.set(false);},error:error=>{this.error.set(tournamentError(error));this.loading.set(false);}});
  }
  changePage(page:number) { this.page.set(page);this.loadList(); }
  openCreate() {
    this.scrollTop();
    this.mode.set('create');this.submitted.set(false);this.validationError.set(false);this.loading.set(false);this.error.set('');this.notice.set('');this.name='';this.format='single_elimination';this.playerCount=8;this.pairMode='individual';this.leagueRounds=1;this.finishDraw();
    this.selected.set(new Set());this.search.set('');this.requestKey='';this.lastSubmission='';this.loadCandidates();
  }
  loadCandidates() {
    this.request?.unsubscribe();this.validationError.set(false);this.candidatesLoading.set(true);this.error.set('');
    this.request=this.api.eligible().subscribe({next:players=>{
      const allowed=new Set(players.map(p=>p.id));this.selected.update(ids=>new Set([...ids].filter(id=>allowed.has(id))));
      this.candidates.set(players);this.candidatesLoading.set(false);
    },error:error=>{this.error.set(tournamentError(error));this.candidatesLoading.set(false);}});
  }
  openPlayerForm() { if(!this.saving()) this.playerForm().open(); }
  participantCreated(player:Participant) {
    this.search.set('');
    if(player.is_active) {
      this.candidates.update(players=>[...players.filter(p=>p.id!==player.id),{id:player.id,nick:player.nick}].sort((a,b)=>a.nick.localeCompare(b.nick)));
      if(this.selected().size<this.capacity()) {
        this.selected.update(ids=>new Set([...ids,player.id]));
        this.notice.set(`${player.nick}: jugador creado y seleccionado para el torneo.`);
      } else {
        this.notice.set(`${player.nick}: jugador creado. Ya has cubierto las plazas; desmarca a otro jugador o amplía las plazas para seleccionarlo.`);
      }
    } else {
      this.notice.set(`${player.nick}: creado como inactivo. Solo los jugadores activos pueden participar en el torneo.`);
    }
    // Actualizar la plantilla sin reiniciar los datos ni la selección del torneo.
    this.loadCandidates();
  }
  toggle(id:number) {
    if(this.saving())return;
    const ids=new Set(this.selected());
    if(ids.has(id))ids.delete(id);
    else { if(ids.size>=this.capacity()){this.error.set('Ya has seleccionado todos los jugadores del torneo. Cambia el número de jugadores o desmarca uno.');return;} ids.add(id); }
    this.selected.set(ids);this.error.set('');
  }
  clearSelection() { this.selected.set(new Set()); }
  selectAll() { if(this.candidates().length<=this.capacity()) this.selected.set(new Set(this.candidates().map(p=>p.id))); }
  capacity() { return Number.isInteger(this.playerCount) ? Math.min(128,Math.max(0,this.playerCount??0)) : 0; }
  nameError():string {
    const name=this.name.normalize('NFKC').trim();
    if(!name) return 'Escribe el nombre del torneo.';
    if(name.length<3 || name.length>80) return 'El nombre del torneo debe tener entre 3 y 80 caracteres.';
    if(/\p{C}/u.test(name)) return 'El nombre no puede contener caracteres de control.';
    return '';
  }
  countError():string {
    if(this.playerCount===null || !Number.isFinite(this.playerCount)) return 'Indica el número de jugadores.';
    if(!Number.isInteger(this.playerCount)) return 'El número de jugadores debe ser entero.';
    if(this.playerCount<2 || this.playerCount>128) return 'El número de jugadores debe estar entre 2 y 128.';
    if(this.pairMode!=='individual' && (this.playerCount<4 || this.playerCount%2!==0)) return 'Las parejas necesitan un número par de jugadores, al menos cuatro.';
    return '';
  }
  showValidationError(message:string,id:string) {
    this.validationError.set(true);this.error.set(message);
    requestAnimationFrame(()=>{
      const field=document.getElementById(id);
      field?.focus({preventScroll:true});
      field?.scrollIntoView({behavior:'smooth',block:'center'});
    });
  }
  clearValidationMessage() { if(this.validationError()){this.error.set('');this.validationError.set(false);} }
  submit(form:NgForm) {
    if(this.saving())return;
    form.control.markAllAsTouched();this.submitted.set(true);this.error.set('');
    if(this.nameError()){this.showValidationError(this.nameError(),'tournament-name');return;}
    if(this.countError()){this.showValidationError(this.countError(),'player-count');return;}
    // También estrecha los tipos antes de construir los datos para la API.
    if(this.playerCount===null) return;
    if(form.invalid){
      const labels:Record<string,string>={name:'nombre del torneo',playerCount:'número de jugadores',format:'formato',search:'búsqueda de jugadores'};
      const invalid=Object.keys(form.controls).find(key=>form.controls[key].invalid) ?? 'name';
      const ids:Record<string,string>={name:'tournament-name',playerCount:'player-count',format:'tournament-format',search:'tournament-player-search'};
      this.showValidationError(`Revisa el campo ${labels[invalid]??invalid}.`,ids[invalid]??'tournament-name');return;
    }
    const ids=[...this.selected()].sort((a,b)=>a-b);
    if(ids.length!==this.playerCount){this.showValidationError(`Selecciona exactamente ${this.playerCount} jugadores. Ahora tienes ${ids.length} seleccionados.`,'tournament-player-selection');return;}
    this.validationError.set(false);
    const ordered=[...this.selected()];
    const pairs=this.pairMode==='manual'?Array.from({length:ordered.length/2},(_,i)=>ordered.slice(i*2,i*2+2)):[];
    const values={name:this.name.trim(),format:this.format,pair_mode:this.pairMode,league_rounds:this.format==='league'?this.leagueRounds:1,pairs,participant_count:this.playerCount,participant_ids:ids};
    const fingerprint=JSON.stringify(values);
    if(fingerprint!==this.lastSubmission){this.lastSubmission=fingerprint;this.requestKey=crypto.randomUUID();}
    this.saving.set(true);
    this.saveRequest=this.api.create({...values,request_key:this.requestKey}).subscribe({next:detail=>{
      this.saving.set(false);this.loading.set(false);this.detailId=detail.id;this.detail.set(detail);this.mode.set('detail');this.scrollTop();this.notice.set('Torneo creado. El sorteo y sus enfrentamientos ya están guardados.');this.leagueDay.set(1);this.startDraw(detail);
    },error:error=>{this.saving.set(false);this.error.set(tournamentError(error));}});
  }
  openDetail(id:number) {
    this.scrollTop();
    this.finishDraw();this.leagueDay.set(1);this.request?.unsubscribe();this.detailId=id;this.mode.set('detail');this.loading.set(true);this.detail.set(null);this.error.set('');this.notice.set('');
    this.request=this.api.get(id).subscribe({next:value=>{this.detail.set(value);this.loading.set(false);},error:error=>{this.error.set(tournamentError(error));this.loading.set(false);}});
  }
  retry() { if(this.mode()==='create')this.loadCandidates();else if(this.mode()==='detail')this.openDetail(this.detailId);else this.loadList(); }
  ngOnDestroy() { clearTimeout(this.drawTimer);this.request?.unsubscribe();this.saveRequest?.unsubscribe();this.resultRequest?.unsubscribe();this.deleteRequest?.unsubscribe(); }
}
