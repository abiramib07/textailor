import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { ResumesService } from '../resumes/resumes.service';

const API = 'http://localhost:8000';

export interface EmailDraft {
  email_id: string;
  to: string;
  subject: string;
  body: string;
  role_title: string;
  company_name: string;
}

export interface EmailReviseResult extends EmailDraft {
  done_summary: string;
}

export interface EmailSendResult {
  email_id: string;
  to: string;
}

export interface EmailSaveResult {
  email_id: string;
  company_name: string;
  role_title: string;
  apply_later_id: string | null;
  apply_later_created: boolean;
  topics_added: string[];
  keywords_logged: number;
}

@Injectable({ providedIn: 'root' })
export class EmailService {
  private http = inject(HttpClient);
  private resumesSvc = inject(ResumesService);

  generate(jobPost: string, instruction: string, sourceUrl: string): Observable<EmailDraft> {
    return this.http.post<EmailDraft>(`${API}/api/email/generate`, {
      job_post: jobPost,
      instruction,
      resume_id: this.resumesSvc.activeResumeId(),
      source_url: sourceUrl,
    });
  }

  revise(emailId: string, instruction: string): Observable<EmailReviseResult> {
    return this.http.post<EmailReviseResult>(`${API}/api/email/revise`, {
      email_id: emailId,
      instruction,
    });
  }

  undo(emailId: string): Observable<EmailDraft> {
    return this.http.post<EmailDraft>(`${API}/api/email/undo`, { email_id: emailId });
  }

  /** Direct manual edit of to/subject/body — bypasses the LLM revise flow. */
  update(emailId: string, to: string, subject: string, body: string): Observable<EmailDraft> {
    return this.http.post<EmailDraft>(`${API}/api/email/${emailId}/update`, {
      to,
      subject,
      body,
    });
  }

  save(
    emailId: string,
    companyName: string,
    roleTitle: string,
    sourceUrl: string,
  ): Observable<EmailSaveResult> {
    return this.http.post<EmailSaveResult>(`${API}/api/email/${emailId}/save`, {
      company_name: companyName,
      role_title: roleTitle,
      source_url: sourceUrl,
    });
  }

  downloadUrl(emailId: string): string {
    return `${API}/api/email/${emailId}/download`;
  }

  send(emailId: string, to: string): Observable<EmailSendResult> {
    return this.http.post<EmailSendResult>(`${API}/api/email/${emailId}/send`, { to });
  }
}
