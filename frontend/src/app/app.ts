import { Component, inject, OnInit } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { AuthService } from './core/auth.service';
import { LanguageService } from './core/language.service';
import { OfflineQueueService } from './core/offline-queue.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  template: '<router-outlet />',
})
export class App implements OnInit {
  private auth = inject(AuthService);
  private lang = inject(LanguageService);
  private offline = inject(OfflineQueueService);

  ngOnInit(): void {
    this.lang.init();
    this.auth.refresh().subscribe();
    this.offline.init();
  }
}
