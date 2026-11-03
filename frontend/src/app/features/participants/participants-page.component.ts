import { HeaderComponent, Section } from '../../shared/header.component';
import { AuthService } from '../access/auth.service';
import { afterNextRender, Component, computed, inject, input, OnDestroy, output, signal, viewChild } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { Participant, ParticipantPage, StatusFilter } from './participant.model';
import { errorMessage, initials, ParticipantsService } from './participants.service';
import { ParticipantFormComponent } from './participant-form.component';

@Component({ selector: 'app-participants-page', standalone: true, imports: [HeaderComponent, DatePipe, FormsModule, ParticipantFormComponent], templateUrl: './participants-page.component.html' })
export class ParticipantsPageComponent implements OnDestroy {
  readonly startCreating = input(false);
  readonly navigate = output<Section>();
  readonly showHistory = output<number>();
  readonly auth = inject(AuthService);
  readonly api = inject(ParticipantsService);
  readonly form = viewChild.required(ParticipantFormComponent);
  readonly initials = initials;
  readonly data = signal<ParticipantPage | null>(null);
  readonly loading = signal(true);
  readonly error = signal('');
  readonly notice = signal('');
  readonly pending = signal<number | null>(null);
  readonly page = signal(1);
  readonly filter = signal<StatusFilter>('all');
  readonly search = signal('');
  readonly summary = computed(() => this.data()?.summary ?? { total: 0, active: 0, inactive: 0 });
  readonly pages = computed(() => Math.max(1, Math.ceil((this.data()?.total ?? 0) / 12)));
  readonly options: { id: StatusFilter; label: string }[] = [{id:'all',label:'Todos'},{id:'active',label:'Activos'},{id:'inactive',label:'Inactivos'}];
  private request?: Subscription;
  private searchTimer?: ReturnType<typeof setTimeout>;

  constructor() {
    this.load();
    afterNextRender(()=>{ if(this.startCreating()) this.form().open(); });
  }
  load() {
    this.request?.unsubscribe(); this.loading.set(true); this.error.set('');
    this.request = this.api.list(this.search(), this.filter(), this.page()).subscribe({
      next: data => {
        if (data.items.length === 0 && this.page() > 1) { this.page.set(Math.max(1, Math.ceil(data.total / 12))); this.load(); return; }
        this.data.set(data); this.loading.set(false);
      }, error: error => { this.error.set(errorMessage(error)); this.loading.set(false); }
    });
  }
  setFilter(filter: StatusFilter) { this.filter.set(filter); this.page.set(1); this.load(); }
  setSearch(query: string) { this.search.set(query); this.page.set(1); clearTimeout(this.searchTimer); this.searchTimer = setTimeout(() => this.load(), 250); }
  clearFilters() { clearTimeout(this.searchTimer); this.search.set(''); this.filter.set('all'); this.page.set(1); this.load(); }
  setPage(page: number) { this.page.set(page); this.load(); }
  saved(participant: Participant) { this.notice.set(`${participant.nick}: datos guardados.`); this.page.set(1); this.load(); }
  toggle(participant: Participant) {
    if (this.pending() !== null) return;
    this.pending.set(participant.id); this.error.set('');
    this.api.changeState(participant).subscribe({
      next: updated => { this.pending.set(null); this.notice.set(`${updated.nick}: ${updated.is_active ? 'activado' : 'desactivado'}.`); this.load(); },
      error: error => { this.pending.set(null); this.error.set(errorMessage(error)); }
    });
  }
  ngOnDestroy() { clearTimeout(this.searchTimer); this.request?.unsubscribe(); }
}
