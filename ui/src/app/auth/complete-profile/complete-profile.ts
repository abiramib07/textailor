import { Component, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../auth.service';

@Component({
  selector: 'app-complete-profile',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './complete-profile.html',
  styleUrl: '../auth-shared.scss',
})
export class CompleteProfileComponent {
  mobile_number = '';
  error = '';
  loading = false;

  constructor(private auth: AuthService, private router: Router, private cdr: ChangeDetectorRef) {}

  submit(): void {
    if (!this.mobile_number.trim() || this.loading) return;
    this.loading = true;
    this.error = '';

    this.auth.sendOtp(this.mobile_number.trim(), 'complete_profile').subscribe({
      next: (res) => {
        this.loading = false;
        this.auth.pendingMobile = this.mobile_number.trim();
        this.auth.pendingPurpose = 'complete_profile';
        this.auth.devOtpHint = res.dev_otp;
        this.router.navigate(['/otp']);
      },
      error: (err) => {
        this.loading = false;
        this.error = err?.error?.detail ?? 'Could not send code.';
        this.cdr.detectChanges();
      },
    });
  }

  skip(): void {
    this.router.navigate(['/welcome']);
  }
}
