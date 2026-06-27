import { Injectable, signal } from '@angular/core';
import { Lang, LANGS, LANG_LABEL, TRANSLATIONS } from './i18n';

const STORAGE_KEY = 'kumbh_lang'; // keep key for continuity with the legacy static app

@Injectable({ providedIn: 'root' })
export class LanguageService {
  readonly lang = signal<Lang>('en');

  init(): void {
    const saved = (localStorage.getItem(STORAGE_KEY) as Lang) || 'en';
    this.lang.set(LANGS.includes(saved) ? saved : 'en');
    document.documentElement.lang = this.lang();
  }

  cycle(): void {
    const idx = LANGS.indexOf(this.lang());
    this.setLang(LANGS[(idx + 1) % LANGS.length]);
  }

  setLang(l: Lang): void {
    this.lang.set(l);
    localStorage.setItem(STORAGE_KEY, l);
    document.documentElement.lang = l;
  }

  /** Label for the toggle button (shows the NEXT language to switch to). */
  nextLabel(): string {
    const idx = LANGS.indexOf(this.lang());
    return LANG_LABEL[LANGS[(idx + 1) % LANGS.length]];
  }

  /** Translate a key for the current language, falling back en → key. */
  t(key: string): string {
    const cur = TRANSLATIONS[this.lang()];
    return cur[key] ?? TRANSLATIONS.en[key] ?? key;
  }
}
