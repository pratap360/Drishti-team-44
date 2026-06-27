import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { AuthService } from '../auth.service';
import { Role } from '../models';

function guardFor(allowed: Role[]): CanActivateFn {
  return () => {
    const auth = inject(AuthService);
    const router = inject(Router);

    const decide = (user: { role: Role } | null): boolean | ReturnType<Router['createUrlTree']> => {
      if (user && allowed.includes(user.role)) return true;
      // Not authorised — bounce to landing, which surfaces the login modal.
      return router.createUrlTree(['/']);
    };

    const current = auth.user();
    if (current !== undefined) {
      return decide(current);
    }
    // Session not yet resolved — resolve then decide.
    return auth.refresh().pipe(map(decide)) as Observable<boolean | ReturnType<Router['createUrlTree']>>;
  };
}

export const adminGuard: CanActivateFn = guardFor(['admin']);
export const volunteerGuard: CanActivateFn = guardFor(['volunteer', 'admin']);
