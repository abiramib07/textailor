import { Component, ChangeDetectorRef, inject } from '@angular/core';

import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../auth.service';

@Component({
  selector: 'app-signup',
  standalone: true,
  imports: [FormsModule, RouterLink],
  templateUrl: './signup.html',
  styleUrl: '../auth-shared.scss',
})
export class SignupComponent {
  private auth = inject(AuthService);
  private router = inject(Router);
  private cdr = inject(ChangeDetectorRef);

  name = '';
  mobile_number = '';
  email = '';
  error = '';
  loading = false;

  get valid(): boolean {
    return (
      this.name.trim().length > 0 &&
      this.mobile_number.trim().length > 0 &&
      this.email.trim().length > 0
    );
  }

  submit(): void {
    if (!this.valid || this.loading) return;
    this.loading = true;
    this.error = '';

    this.auth.signup(this.name.trim(), this.mobile_number.trim(), this.email.trim()).subscribe({
      next: (res) => {
        this.loading = false;
        this.auth.pendingMobile = res.mobile_number;
        this.auth.pendingPurpose = 'signup';
        this.auth.devOtpHint = res.dev_otp;
        this.router.navigate(['/otp']);
      },
      error: (err) => {
        this.loading = false;
        this.error = err?.error?.detail ?? 'Signup failed. Please try again.';
        this.cdr.detectChanges();
      },
    });
  }
}
