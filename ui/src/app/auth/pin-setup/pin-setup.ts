import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../auth.service';

@Component({
  selector: 'app-pin-setup',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './pin-setup.html',
  styleUrl: '../auth-shared.scss',
})
export class PinSetupComponent implements OnInit {
  pin = '';
  confirmPin = '';
  error = '';
  loading = false;
  isReset = false;

  constructor(private auth: AuthService, private router: Router, private cdr: ChangeDetectorRef) {}

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
        this.router.navigate(['/welcome']);
      },
      error: (err) => {
        this.loading = false;
        this.error = err?.error?.detail ?? 'Could not save PIN.';
        this.cdr.detectChanges();
      },
    });
  }
}
