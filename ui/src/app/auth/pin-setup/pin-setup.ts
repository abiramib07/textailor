import { Component, OnInit, ChangeDetectorRef, inject } from '@angular/core';

import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../auth.service';

@Component({
  selector: 'app-pin-setup',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './pin-setup.html',
  styleUrl: '../auth-shared.scss',
})
export class PinSetupComponent implements OnInit {
  private auth = inject(AuthService);
  private router = inject(Router);
  private cdr = inject(ChangeDetectorRef);

  pin = '';
  confirmPin = '';
  error = '';
  loading = false;
  isReset = false;

  ngOnInit(): void {
    if (!this.auth.otpVerifiedToken || !this.auth.pendingPurpose) {
      this.router.navigate(['/login']);
      return;
    }
    this.isReset = this.auth.pendingPurpose === 'reset';
    this.cdr.detectChanges();
  }

  get valid(): boolean {
    return /^\d{4}$/.test(this.pin) && this.pin === this.confirmPin;
  }

  submit(): void {
    if (!this.valid || this.loading || !this.auth.otpVerifiedToken) return;
    this.loading = true;
    this.error = '';

    const call = this.isReset
      ? this.auth.resetPin(this.auth.otpVerifiedToken, this.pin)
      : this.auth.setPin(this.auth.otpVerifiedToken, this.pin);

    call.subscribe({
      next: () => {
        this.loading = false;
        this.auth.clearFlowState();
        this.router.navigate(['/']);
      },
      error: (err) => {
        this.loading = false;
        this.error = err?.error?.detail ?? 'Could not save PIN.';
        this.cdr.detectChanges();
      },
    });
  }
}
