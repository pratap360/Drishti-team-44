import { Injectable, inject, signal } from '@angular/core';
import { ApiService } from './api.service';
import { ReportFoundPayload } from './models';

const DB_NAME = 'kumbh_offline';
const STORE_PENDING = 'pending_reports';
const STORE_SHARES = 'received_shares';

/**
 * IndexedDB-backed offline queue for volunteer found-person reports.
 * Ported from volunteer.html: queues reports while offline, auto-syncs on reconnect.
 */
@Injectable({ providedIn: 'root' })
export class OfflineQueueService {
  private api = inject(ApiService);
  private db?: IDBDatabase;

  readonly online = signal<boolean>(navigator.onLine);
  readonly pendingCount = signal<number>(0);

  init(): void {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_PENDING))
        db.createObjectStore(STORE_PENDING, { keyPath: 'id', autoIncrement: true });
      if (!db.objectStoreNames.contains(STORE_SHARES))
        db.createObjectStore(STORE_SHARES, { keyPath: 'id', autoIncrement: true });
    };
    req.onsuccess = () => {
      this.db = req.result;
      this.refreshCount();
    };

    window.addEventListener('online', () => {
      this.online.set(true);
      this.sync();
    });
    window.addEventListener('offline', () => this.online.set(false));
  }

  private tx(store: string, mode: IDBTransactionMode): IDBObjectStore {
    return this.db!.transaction(store, mode).objectStore(store);
  }

  private refreshCount(): void {
    if (!this.db) return;
    const req = this.tx(STORE_PENDING, 'readonly').count();
    req.onsuccess = () => this.pendingCount.set(req.result);
  }

  /** Queue a found-person report locally. */
  queueReport(payload: ReportFoundPayload): Promise<void> {
    return new Promise(resolve => {
      if (!this.db) return resolve();
      const req = this.tx(STORE_PENDING, 'readwrite').add({ payload, ts: new Date().toISOString() });
      req.onsuccess = () => { this.refreshCount(); resolve(); };
      req.onerror = () => resolve();
    });
  }

  /** Store an imported QR share locally. */
  saveShare(payload: ReportFoundPayload): Promise<void> {
    return new Promise(resolve => {
      if (!this.db) return resolve();
      const req = this.tx(STORE_SHARES, 'readwrite').add({ payload, ts: new Date().toISOString() });
      req.onsuccess = () => resolve();
      req.onerror = () => resolve();
    });
  }

  private getAllPending(): Promise<{ id: number; payload: ReportFoundPayload }[]> {
    return new Promise(resolve => {
      if (!this.db) return resolve([]);
      const req = this.tx(STORE_PENDING, 'readonly').getAll();
      req.onsuccess = () => resolve(req.result as { id: number; payload: ReportFoundPayload }[]);
      req.onerror = () => resolve([]);
    });
  }

  private delete(id: number): void {
    if (!this.db) return;
    this.tx(STORE_PENDING, 'readwrite').delete(id);
  }

  /** Push all queued reports to the server. Returns count synced. */
  async sync(): Promise<number> {
    if (!navigator.onLine || !this.db) return 0;
    const pending = await this.getAllPending();
    let synced = 0;
    for (const item of pending) {
      try {
        const res = await this.api.reportFound(item.payload).toPromise();
        if (res?.ok) { this.delete(item.id); synced++; }
      } catch { /* keep for next attempt */ }
    }
    this.refreshCount();
    return synced;
  }
}
