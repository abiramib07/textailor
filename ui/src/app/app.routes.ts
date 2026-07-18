import { Routes } from '@angular/router';
import { App } from './app';
import { LoginComponent } from './auth/login/login';
import { SignupComponent } from './auth/signup/signup';
import { OtpComponent } from './auth/otp/otp';
import { PinSetupComponent } from './auth/pin-setup/pin-setup';
import { CompleteProfileComponent } from './auth/complete-profile/complete-profile';
import { AuthCallbackComponent } from './auth/callback/callback';
import { WelcomeComponent } from './auth/welcome/welcome';
import { authGuard } from './auth/auth.guard';

// '' is now gated — unauthenticated visitors are redirected to /login,
// and every login path (PIN, PIN-setup, Google callback) lands straight
// back on the resume tool instead of an intermediate /welcome screen.
// /welcome is kept as a reachable "account" page, just not the default
// post-login destination anymore.
export const routes: Routes = [
  { path: '', component: App, canActivate: [authGuard] },
  { path: 'login', component: LoginComponent },
  { path: 'signup', component: SignupComponent },
  { path: 'otp', component: OtpComponent },
  { path: 'pin-setup', component: PinSetupComponent },
  { path: 'complete-profile', component: CompleteProfileComponent },
  { path: 'auth/callback', component: AuthCallbackComponent },
  { path: 'welcome', component: WelcomeComponent },
];
