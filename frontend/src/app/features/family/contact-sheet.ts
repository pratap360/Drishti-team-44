import { Component, inject } from '@angular/core';
import { MatBottomSheetRef, MAT_BOTTOM_SHEET_DATA, MatBottomSheetModule } from '@angular/material/bottom-sheet';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar } from '@angular/material/snack-bar';
import { ApiService } from '../../core/api.service';

export interface ContactData { foundId?: number; mobile?: string; }

@Component({
  selector: 'app-contact-sheet',
  imports: [MatBottomSheetModule, MatButtonModule, MatIconModule],
  template: `
    <div class="sheet">
      <h3>Contact about this person</h3>
      <button mat-flat-button class="call" (click)="call()">
        <mat-icon>call</mat-icon> Call Lost & Found Helpline
      </button>
      <button mat-stroked-button (click)="callback()">
        <mat-icon>phone_callback</mat-icon> Request a Callback
      </button>
      <button mat-button (click)="ref.dismiss()">Cancel</button>
    </div>
  `,
  styles: [`
    .sheet { display: flex; flex-direction: column; gap: 10px; padding: 8px 4px 16px; }
    .sheet h3 { margin: 4px 0 8px; }
    .call { background: var(--brand-success); color: #fff; }
  `],
})
export class ContactSheet {
  data = inject<ContactData>(MAT_BOTTOM_SHEET_DATA);
  ref = inject(MatBottomSheetRef<ContactSheet>);
  private api = inject(ApiService);
  private snack = inject(MatSnackBar);

  call(): void { window.location.href = 'tel:1800-180-1234'; }

  callback(): void {
    if (this.data.foundId != null) {
      this.api.requestCallback(this.data.foundId).subscribe();
    }
    this.snack.open('Callback requested. The helpline will reach out.', 'OK', { duration: 3000, panelClass: 'snack-success' });
    this.ref.dismiss();
  }
}
