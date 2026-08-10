import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { ResumesService } from '../../resumes/resumes.service';

const API = 'http://localhost:8000/api/credentials';
const OPTS = { withCredentials: true };

export interface CredentialEntry {
  id: string;
  resume_id: string;
  company_name: string;
  site_url: string;
  login_email: string;
  username: string;
  notes: string;
  has_password: boolean;
  created_at: number;
  updated_at: number;
}

export type CredentialFields = Partial<{
  company_name: string;
  site_url: string;
  login_email: string;
  username: string;
  password: string;
  notes: string;
}>;

/**
 * Typed HTTP client for `/api/credentials/*` — encrypted job-account
 * credentials. Gated behind login (unlike `CareerService`'s routes), so
 * every call passes `withCredentials: true` to send the session cookie,
 * matching `AuthService`.
 */
@Injectable({ providedIn: 'root' })
export class JobCredentialsService {
  private http = inject(HttpClient);
  private resumesSvc = inject(ResumesService);

  private get resumeId(): string {
    return this.resumesSvc.activeResumeId() ?? '';
  }

  list(): Observable<{ entries: CredentialEntry[] }> {
    return this.http.get<{ entries: CredentialEntry[] }>(API, {
      ...OPTS,
      params: { resume_id: this.resumeId },
    });
  }

  create(fields: {
    company_name: string;
    site_url: string;
    login_email: string;
    username: string;
    password: string;
    notes: string;
  }): Observable<{ entry: CredentialEntry }> {
    return this.http.post<{ entry: CredentialEntry }>(
      API,
      { resume_id: this.resumeId, ...fields },
      OPTS,
    );
  }

  update(id: string, fields: CredentialFields): Observable<{ entry: CredentialEntry }> {
    return this.http.patch<{ entry: CredentialEntry }>(`${API}/${id}`, fields, OPTS);
  }

  delete(id: string): Observable<{ ok: boolean }> {
    return this.http.delete<{ ok: boolean }>(`${API}/${id}`, OPTS);
  }

  /** Decrypt and return one credential's password — only call this in
   * response to an explicit user action (e.g. clicking "Show"), never
   * eagerly for the whole list. */
  reveal(id: string): Observable<{ password: string }> {
    return this.http.get<{ password: string }>(`${API}/${id}/reveal`, OPTS);
  }
}
