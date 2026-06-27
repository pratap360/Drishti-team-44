import { Component, EventEmitter, Input, Output, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ImageService } from '../core/image.service';
import { TranslatePipe } from '../core/translate.pipe';

/** Reusable photo input with camera capture + file picker + preview, compressing to base64. */
@Component({
  selector: 'app-photo-capture',
  imports: [MatButtonModule, MatIconModule, TranslatePipe],
  template: `
    <div class="photo-capture">
      <div class="preview" [class.has]="value()" (click)="cam.click()">
        @if (value()) { <img [src]="value()" alt="preview"> } @else { <span>📷</span> }
      </div>
      <div class="btns">
        <button mat-stroked-button type="button" (click)="cam.click()">
          <mat-icon>photo_camera</mat-icon> {{ 'form.takePhoto' | t }}
        </button>
        <button mat-stroked-button type="button" (click)="file.click()">
          <mat-icon>folder</mat-icon> {{ 'form.chooseFile' | t }}
        </button>
        @if (value()) {
          <button mat-stroked-button type="button" color="warn" (click)="clear()">
            <mat-icon>close</mat-icon> {{ 'form.remove' | t }}
          </button>
        }
      </div>
    </div>
    <input #cam type="file" accept="image/*" capture="environment" hidden (change)="onFile($event)">
    <input #file type="file" accept="image/*" hidden (change)="onFile($event)">
  `,
  styles: [`
    .photo-capture { display: flex; gap: 12px; align-items: flex-start; }
    .preview {
      width: 100px; height: 100px; border-radius: 12px; border: 2px dashed var(--brand-border);
      display: flex; align-items: center; justify-content: center; overflow: hidden;
      flex-shrink: 0; background: #fafafa; font-size: 36px; color: var(--brand-border); cursor: pointer;
    }
    .preview.has { border-style: solid; border-color: var(--brand-success); }
    .preview img { width: 100%; height: 100%; object-fit: cover; }
    .btns { display: flex; flex-direction: column; gap: 8px; flex: 1; }
    .btns button { justify-content: flex-start; }
  `],
})
export class PhotoCapture {
  private imageSvc = inject(ImageService);

  @Input() set photo(v: string) { this.value.set(v || ''); }
  @Output() photoChange = new EventEmitter<string>();

  value = signal('');

  async onFile(ev: Event): Promise<void> {
    const input = ev.target as HTMLInputElement;
    const f = input.files?.[0];
    if (!f) return;
    const b64 = await this.imageSvc.compress(f);
    this.value.set(b64);
    this.photoChange.emit(b64);
    input.value = '';
  }

  clear(): void {
    this.value.set('');
    this.photoChange.emit('');
  }
}
