import { ChangeDetectorRef, Component, ElementRef, inject, output, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Participant } from './participant.model';
import { errorMessage, initials, ParticipantsService } from './participants.service';

@Component({ selector: 'app-participant-form', standalone: true, imports: [FormsModule], templateUrl: './participant-form.component.html' })
export class ParticipantFormComponent {
  private readonly api = inject(ParticipantsService);
  private readonly changeDetector = inject(ChangeDetectorRef);
  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');
  private readonly nickInput = viewChild.required<ElementRef<HTMLInputElement>>('nickInput');
  readonly saved = output<Participant>();
  readonly busy = signal(false);
  readonly error = signal('');
  readonly initials = initials;
  editing: Participant | null = null;
  nick = '';
  isActive = true;
  file: File | null = null;
  preview = '';
  removeLogo = false;

  open(participant: Participant | null = null) {
    this.releasePreview(); this.editing = participant; this.nick = participant?.nick ?? '';
    this.isActive = participant?.is_active ?? true; this.file = null; this.removeLogo = false; this.error.set('');
    this.preview = participant?.has_logo ? this.api.logoUrl(participant) : '';
    this.changeDetector.detectChanges();
    this.dialog().nativeElement.showModal();
    this.nickInput().nativeElement.focus();
  }
  close() { if (!this.busy()) { this.dialog().nativeElement.close(); this.releasePreview(); } }
  cancel(event: Event) { event.preventDefault(); this.close(); }
  backdrop(event: MouseEvent) { if (event.target === this.dialog().nativeElement) this.close(); }
  private releasePreview() { if (this.preview.startsWith('blob:')) URL.revokeObjectURL(this.preview); this.preview = ''; }
  selectLogo(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    input.value = '';
    if (file.size > 2 * 1024 * 1024 || !['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
      this.error.set('Selecciona un PNG, JPG o WebP de hasta 2 MB.'); return;
    }
    this.releasePreview(); this.file = file; this.preview = URL.createObjectURL(file); this.removeLogo = false; this.error.set('');
  }
  clearLogo() { this.releasePreview(); this.file = null; this.removeLogo = true; }
  save() {
    if (this.busy()) return;
    if (this.nick.trim().length < 2 || this.nick.trim().length > 24) { this.error.set('El nick debe tener entre 2 y 24 caracteres.'); return; }
    this.busy.set(true); this.error.set('');
    this.api.save(this.editing, this.nick, this.isActive, this.file, this.removeLogo).subscribe({
      next: participant => { this.busy.set(false); this.close(); this.saved.emit(participant); },
      error: error => { this.busy.set(false); this.error.set(errorMessage(error)); }
    });
  }
}
