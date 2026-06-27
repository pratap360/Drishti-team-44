import { Routes } from '@angular/router';
import { adminGuard, volunteerGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./features/landing/landing').then(m => m.Landing),
  },
  {
    path: 'family',
    loadComponent: () => import('./features/family/family').then(m => m.Family),
  },
  {
    path: 'volunteer',
    canActivate: [volunteerGuard],
    loadComponent: () => import('./features/volunteer/volunteer').then(m => m.Volunteer),
  },
  {
    path: 'control',
    canActivate: [adminGuard],
    loadComponent: () => import('./features/control/control').then(m => m.Control),
  },
  { path: '**', redirectTo: '' },
];
