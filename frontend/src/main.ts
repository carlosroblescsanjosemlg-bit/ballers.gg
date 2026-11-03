import { sessionInterceptor } from './app/features/access/session.interceptor';
import { bootstrapApplication } from '@angular/platform-browser';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { AppComponent } from './app/app.component';
bootstrapApplication(AppComponent, { providers: [provideHttpClient(withInterceptors([sessionInterceptor]))] }).catch(console.error);
