export const AGE_BANDS = ['0-12', '13-17', '18-40', '41-60', '61-70', '71-80', '80+'];
export const GENDERS = ['Unknown', 'Male', 'Female'];

export const RELATIONSHIPS = ['Parent', 'Spouse', 'Child', 'Sibling', 'Relative', 'Friend', 'Guardian'];

export const HELPLINES = [
  { label: 'Kumbh Helpline', number: '1920' },
  { label: 'Police', number: '100' },
  { label: 'Child Helpline', number: '1098' },
  { label: 'Women Helpline', number: '1091' },
  { label: 'Lost & Found', number: '1800-180-1234' },
];

/** Map a backend status string to a CSS badge class. */
export function badgeClass(status?: string): string {
  switch ((status || '').toLowerCase()) {
    case 'pending': return 'badge-pending';
    case 'searching': return 'badge-searching';
    case 'matched': return 'badge-matched';
    case 'reunited': return 'badge-reunited';
    case 'unresolved': return 'badge-unresolved';
    case 'transferred to hospital': return 'badge-hospital';
    default: return 'badge-pending';
  }
}
