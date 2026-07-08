import { Component, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './login.html',
  styleUrl: '../auth-shared.scss',
})
export class LoginComponent {
  identifier = '';
  pin = '';
  error = '';
  loading = false;

  forgotMode = false;
  forgotMobile = '';
  forgotError = '';
  forgotLoading = false;

  constructor(private auth: AuthService, private router: Router, private cdr: ChangeDetectorRef) {}

  submit(): void {
    if (!this.identifier.trim() || !/^\d{4}$/.test(this.pin) || this.loading) return;
    this.loading = true;
    this.error = '';

    this.auth.pinLogin(this.identifier.trim(), this.pin).subscribe({
      next: () => {
        this.loading = false;
        this.router.navigate(['/welcome']);
      },
      error: (err) => {
        this.loading = false;
        this.error = err?.error?.detail ?? 'Login failed. Please try again.';
        this.cdr.detectChanges();
      },
    });
  }

  continueWithGoogle(): void {
    window.location.href = this.auth.googleLoginUrl();
  }

  toggleForgot(): void {
    this.forgotMode = !this.forgotMode;
    this.forgotError = '';
    this.cdr.detectChanges();
  }

  sendResetOtp(): void {
    if (!this.forgotMobile.trim() || this.forgotLoading) return;
    this.forgotLoading = true;
    this.forgotError = '';

    this.auth.sendOtp(this.forgotMobile.trim(), 'reset').subscribe({
      next: (res) => {
        this.forgotLoading = false;
        this.auth.pendingMobile = this.forgotMobile.trim();
        this.auth.pendingPurpose = 'reset';
        this.auth.devOtpHint = res.dev_otp;
        this.router.navigate(['/otp']);
      },
      error: (err) => {
        this.forgotLoading = false;
        this.forgotError = err?.error?.detail ?? 'Could not send code.';
        this.cdr.detectChanges();
      },
    });
  }
}
