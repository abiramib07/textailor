import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface UserProfile {
  id: string;
  name: string;
  email: string;
  mobile_number: string | null;
  mobile_verified: boolean;
  has_pin: boolean;
  google_linked: boolean;
}

export type OtpPurpose = 'signup' | 'reset' | 'complete_profile';

const API_BASE = 'http://localhost:8000/api/auth';
const OPTS = { withCredentials: true };

@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);

  // Transient flow state carried between the signup/otp/pin-setup screens.
  // Lost on a hard refresh by design — mid-flow reload just restarts the step.
  pendingMobile: string | null = null;
  pendingPurpose: OtpPurpose | null = null;
  otpVerifiedToken: string | null = null;
  devOtpHint: string | null = null;

  signup(
    name: string,
    mobile_number: string,
    email: string,
  ): Observable<{ mobile_number: string; message: string; dev_otp: string | null }> {
    return this.http.post<{ mobile_number: string; message: string; dev_otp: string | null }>(
      `${API_BASE}/signup`,
      { name, mobile_number, email },
      OPTS,
    );
  }

  sendOtp(
    mobile_number: string,
    purpose: OtpPurpose,
  ): Observable<{ message: string; dev_otp: string | null }> {
    return this.http.post<{ message: string; dev_otp: string | null }>(
      `${API_BASE}/otp/send`,
      { mobile_number, purpose },
      OPTS,
    );
  }

  verifyOtp(
    mobile_number: string,
    otp: string,
    purpose: OtpPurpose,
  ): Observable<{ otp_verified_token: string }> {
    return this.http.post<{ otp_verified_token: string }>(
      `${API_BASE}/otp/verify`,
      { mobile_number, otp, purpose },
      OPTS,
    );
  }

  setPin(otp_verified_token: string, pin: string): Observable<{ user: UserProfile }> {
    return this.http.post<{ user: UserProfile }>(
      `${API_BASE}/pin/set`,
      { otp_verified_token, pin },
      OPTS,
    );
  }

  resetPin(otp_verified_token: string, pin: string): Observable<{ user: UserProfile }> {
    return this.http.post<{ user: UserProfile }>(
      `${API_BASE}/pin/reset`,
      { otp_verified_token, pin },
      OPTS,
    );
  }

  pinLogin(identifier: string, pin: string): Observable<{ user: UserProfile }> {
    return this.http.post<{ user: UserProfile }>(
      `${API_BASE}/pin/login`,
      { identifier, pin },
      OPTS,
    );
  }

  completeMobile(otp_verified_token: string): Observable<{ user: UserProfile }> {
    return this.http.post<{ user: UserProfile }>(
      `${API_BASE}/complete-mobile`,
      { otp_verified_token },
      OPTS,
    );
  }

  me(): Observable<{ user: UserProfile }> {
    return this.http.get<{ user: UserProfile }>(`${API_BASE}/me`, OPTS);
  }

  logout(): Observable<{ ok: boolean }> {
    return this.http.post<{ ok: boolean }>(`${API_BASE}/logout`, {}, OPTS);
  }

  googleLoginUrl(): string {
    return `${API_BASE}/google/login`;
  }

  clearFlowState(): void {
    this.pendingMobile = null;
    this.pendingPurpose = null;
    this.otpVerifiedToken = null;
    this.devOtpHint = null;
  }
}
