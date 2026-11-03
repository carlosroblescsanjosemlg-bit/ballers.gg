import { Component, inject, output } from '@angular/core';
import { HeaderComponent, Section } from '../../shared/header.component';
import { AuthService } from '../access/auth.service';

@Component({selector:'app-home',standalone:true,imports:[HeaderComponent],templateUrl:'./home-page.component.html'})
export class HomePageComponent {
  readonly auth = inject(AuthService);
  readonly navigate = output<Section>();
  readonly start = output<'players' | 'tournaments'>();
}
