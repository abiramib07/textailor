import { Component, ChangeDetectorRef, inject } from '@angular/core';

import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../auth.service';

@Component({
  selector: 'app-complete-profile',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './complete-profile.html',
  styleUrl: '../auth-shared.scss',
})
export class CompleteProfileComponent {
  private auth = inject(AuthService);
  private router = inject(Router);
  private cdr = inject(ChangeDetectorRef);

  mobile_number = '';
  error = '';
  loading = false;

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
    this.router.navigate(['/']);
  }
}
