import { Routes } from '@angular/router';
import { App } from './app';
import { LoginComponent } from './auth/login/login';
import { SignupComponent } from './auth/signup/signup';
import { OtpComponent } from './auth/otp/otp';
import { PinSetupComponent } from './auth/pin-setup/pin-setup';
import { CompleteProfileComponent } from './auth/complete-profile/complete-profile';
import { AuthCallbackComponent } from './auth/callback/callback';
import { WelcomeComponent } from './auth/welcome/welcome';

// '' keeps the existing resume tool as the default landing page, unchanged.
// The login/signup/PIN/OTP/Google screens are additive routes for a
// separate login-screen project, built here as a standalone module.
export const routes: Routes = [
  { path: '', component: App },
  { path: 'login', component: LoginComponent },
  { path: 'signup', component: SignupComponent },
  { path: 'otp', component: OtpComponent },
  { path: 'pin-setup', component: PinSetupComponent },
  { path: 'complete-profile', component: CompleteProfileComponent },
  { path: 'auth/callback', component: AuthCallbackComponent },
  { path: 'welcome', component: WelcomeComponent },
];
