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
}

export interface EmailReviseResult extends EmailDraft {
  done_summary: string;
}

@Injectable({ providedIn: 'root' })
export class EmailService {
  private http = inject(HttpClient);
  private resumesSvc = inject(ResumesService);

  generate(jobPost: string, instruction: string): Observable<EmailDraft> {
    return this.http.post<EmailDraft>(`${API}/api/email/generate`, {
      job_post: jobPost,
      instruction,
      resume_id: this.resumesSvc.activeResumeId(),
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

  downloadUrl(emailId: string): string {
    return `${API}/api/email/${emailId}/download`;
  }
}
