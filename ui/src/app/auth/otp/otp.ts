import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../auth.service';

@Component({
  selector: 'app-otp',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './otp.html',
  styleUrl: '../auth-shared.scss',
})
export class OtpComponent implements OnInit {
  otp = '';
  error = '';
  loading = false;
  resendLoading = false;
  resendCooldown = 0;
  mobile: string | null = null;

  private cooldownTimer: ReturnType<typeof setInterval> | null = null;

  constructor(private auth: AuthService, private router: Router, private cdr: ChangeDetectorRef) {}

  ngOnInit(): void {
    if (!this.auth.pendingMobile || !this.auth.pendingPurpose) {
      // Flow state lost (e.g. page refresh) — start over.
      this.router.navigate(['/login']);
      return;
    }
    this.mobile = this.auth.pendingMobile;
    this.startCooldown();
    this.cdr.detectChanges();
  }

  get purposeLabel(): string {
    switch (this.auth.pendingPurpose) {
      case 'signup': return 'Verify your mobile number';
      case 'reset': return 'Reset your PIN';
      case 'complete_profile': return 'Confirm your mobile number';
      default: return 'Enter verification code';
    }
  }

  get devOtpHint(): string | null {
    return this.auth.devOtpHint;
  }

  submit(): void {
    if (!/^\d{6}$/.test(this.otp) || this.loading || !this.mobile || !this.auth.pendingPurpose) return;
    this.loading = true;
    this.error = '';

    this.auth.verifyOtp(this.mobile, this.otp, this.auth.pendingPurpose).subscribe({
      next: (res) => {
        this.loading = false;
        this.auth.otpVerifiedToken = res.otp_verified_token;

        if (this.auth.pendingPurpose === 'complete_profile') {
          this.auth.completeMobile(res.otp_verified_token).subscribe({
            next: () => {
              this.auth.clearFlowState();
              this.router.navigate(['/welcome']);
            },
            error: (err) => {
              this.error = err?.error?.detail ?? 'Could not save mobile number.';
              this.cdr.detectChanges();
            },
          });
        } else {
          this.router.navigate(['/pin-setup']);
        }
      },
      error: (err) => {
        this.loading = false;
        this.error = err?.error?.detail ?? 'Verification failed.';
        this.cdr.detectChanges();
      },
    });
  }

  resend(): void {
    if (this.resendCooldown > 0 || this.resendLoading || !this.mobile || !this.auth.pendingPurpose) return;
    this.resendLoading = true;
    this.error = '';

    this.auth.sendOtp(this.mobile, this.auth.pendingPurpose).subscribe({
      next: (res) => {
        this.resendLoading = false;
        this.auth.devOtpHint = res.dev_otp;
        this.startCooldown();
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.resendLoading = false;
        this.error = err?.error?.detail ?? 'Could not resend code.';
        this.cdr.detectChanges();
      },
    });
  }

  private startCooldown(): void {
    this.resendCooldown = 60;
    if (this.cooldownTimer) clearInterval(this.cooldownTimer);
    this.cooldownTimer = setInterval(() => {
      this.resendCooldown--;
      if (this.resendCooldown <= 0 && this.cooldownTimer) {
        clearInterval(this.cooldownTimer);
        this.cooldownTimer = null;
      }
      this.cdr.detectChanges();
    }, 1000);
  }
}
