import { Component, inject } from '@angular/core';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';

export interface ConfirmData { title: string; message: string; confirmLabel?: string; cancelLabel?: string; }

@Component({
  selector: 'app-confirm-dialog',
  imports: [MatDialogModule, MatButtonModule],
  template: `
    <h2 mat-dialog-title>{{ data.title }}</h2>
    <mat-dialog-content>{{ data.message }}</mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button [mat-dialog-close]="false">{{ data.cancelLabel || 'Cancel' }}</button>
      <button mat-flat-button class="brand-btn" [mat-dialog-close]="true">{{ data.confirmLabel || 'Confirm' }}</button>
    </mat-dialog-actions>
  `,
})
export class ConfirmDialog {
  data = inject<ConfirmData>(MAT_DIALOG_DATA);
  ref = inject(MatDialogRef<ConfirmDialog, boolean>);
}
