import { Injectable } from '@angular/core';
import QRCode from 'qrcode';
import jsQR from 'jsqr';
import { ReportFoundPayload } from './models';

/** Compact QR share payload (back-compatible with the legacy `{t:'kr',...}` schema). */
export interface SharePayload {
  t: 'kr';
  n?: string; g?: string; a?: string; s?: string; l?: string;
  loc?: string; c?: string; d?: string; m?: string; r?: string;
}

@Injectable({ providedIn: 'root' })
export class QrService {
  /** Encode a found-person report into a compact QR payload string. */
  encodeReport(p: ReportFoundPayload): SharePayload {
    return {
      t: 'kr',
      n: p.person_name, g: p.gender, a: p.age_band, s: p.state, l: p.language,
      loc: p.found_location, c: p.reporting_center, d: p.physical_description,
      m: p.contact_mobile, r: p.remarks,
    };
  }

  decodeReport(payload: SharePayload): ReportFoundPayload {
    return {
      person_name: payload.n, gender: payload.g, age_band: payload.a, state: payload.s,
      language: payload.l, found_location: payload.loc, reporting_center: payload.c,
      physical_description: payload.d, contact_mobile: payload.m, remarks: payload.r,
    };
  }

  /** Render the payload as a QR code onto the given canvas. */
  async toCanvas(canvas: HTMLCanvasElement, payload: SharePayload): Promise<void> {
    await QRCode.toCanvas(canvas, JSON.stringify(payload), { width: 256, margin: 1 });
  }

  /**
   * Drive a live camera scan loop. Calls `onResult` with the first valid
   * Drishti payload, then stops. Returns a stop() function.
   */
  async startScan(
    video: HTMLVideoElement,
    canvas: HTMLCanvasElement,
    onResult: (p: SharePayload) => void,
    onError: (e: unknown) => void,
  ): Promise<() => void> {
    let stream: MediaStream | null = null;
    let raf = 0;
    let stopped = false;

    const stop = () => {
      stopped = true;
      if (raf) cancelAnimationFrame(raf);
      stream?.getTracks().forEach(t => t.stop());
    };

    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
      video.srcObject = stream;
      await video.play();
      const ctx = canvas.getContext('2d', { willReadFrequently: true })!;

      const tick = () => {
        if (stopped) return;
        if (video.readyState === video.HAVE_ENOUGH_DATA) {
          canvas.width = video.videoWidth;
          canvas.height = video.videoHeight;
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
          const code = jsQR(img.data, img.width, img.height);
          if (code) {
            try {
              const parsed = JSON.parse(code.data);
              if (parsed && parsed.t === 'kr') {
                stop();
                onResult(parsed as SharePayload);
                return;
              }
            } catch { /* not our QR — keep scanning */ }
          }
        }
        raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    } catch (e) {
      onError(e);
    }
    return stop;
  }
}
