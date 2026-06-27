import { Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { LanguageService } from '../core/language.service';

@Component({
  selector: 'app-lang-toggle',
  imports: [MatButtonModule],
  template: `
    <button mat-stroked-button type="button" class="lang-toggle" (click)="lang.cycle()"
            [attr.aria-label]="'Switch language'">
      <span>🌐</span> {{ lang.nextLabel() }}
    </button>
  `,
  styles: [`
    .lang-toggle {
      color: inherit; border-color: rgba(255,255,255,0.5);
      min-width: 0; line-height: 32px; padding: 0 10px;
    }
  `],
})
export class LangToggle {
  lang = inject(LanguageService);
}
