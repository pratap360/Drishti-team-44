import { Pipe, PipeTransform, inject } from '@angular/core';
import { LanguageService } from './language.service';

/**
 * Usage: {{ 'landing.hero' | t }}
 * Impure so it re-evaluates when the language signal changes.
 */
@Pipe({ name: 't', pure: false })
export class TranslatePipe implements PipeTransform {
  private lang = inject(LanguageService);
  transform(key: string): string {
    // Touch the signal so change detection re-runs on language switch.
    this.lang.lang();
    return this.lang.t(key);
  }
}
