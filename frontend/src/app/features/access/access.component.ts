import { Component, inject, signal } from '@angular/core';
import { FormsModule, NgForm } from '@angular/forms';
import { AuthService } from './auth.service';

@Component({selector:'app-access', standalone:true, imports:[FormsModule], templateUrl:'./access.component.html'})
export class AccessComponent {
  readonly auth = inject(AuthService);
  readonly register = signal(false);
  username = ''; password = ''; confirmation = '';
  switchMode() { this.register.update(value => !value); this.auth.error.set(''); this.password = ''; this.confirmation = ''; }
  submit(form: NgForm) {
    if (this.auth.busy()) return;
    form.control.markAllAsTouched();
    if (form.invalid) { this.auth.error.set('Revisa los campos marcados antes de continuar.'); return; }
    if (this.register() && this.password !== this.confirmation) { this.auth.error.set('Las contraseñas no coinciden.'); return; }
    void this.auth.enter(this.register() ? 'register' : 'login', this.username, this.password);
  }
}
