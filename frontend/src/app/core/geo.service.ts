import { Injectable } from '@angular/core';

/** Browser geolocation helper for the "GPS" buttons. */
@Injectable({ providedIn: 'root' })
export class GeoService {
  getCurrentPosition(): Promise<{ lat: number; lng: number }> {
    return new Promise((resolve, reject) => {
      if (!('geolocation' in navigator)) return reject(new Error('Geolocation unavailable'));
      navigator.geolocation.getCurrentPosition(
        pos => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
        err => reject(err),
        { enableHighAccuracy: true, timeout: 10000 },
      );
    });
  }
}
