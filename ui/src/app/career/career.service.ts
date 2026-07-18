import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { ResumesService } from '../resumes/resumes.service';

const API = 'http://localhost:8000/api/career';

export interface PersonalInfoEntry {
  key: string;
  value: string;
}

export interface ApplyLaterEntry {
  id: string;
  url: string;
  company_name: string;
  notes: string;
  applied: number;
  created_at: number;
}

export interface JobPostEntry {
  id: string;
  url: string;
  company_name: string;
  role_title: string;
  raw_text: string;
  created_at: number;
  attachment_count: number;
}

export interface AttachmentEntry {
  id: string;
  created_at: number;
}

export interface InterviewTopicEntry {
  id: string;
  company_name: string;
  topic: string;
  covered: number;
  github_url: string;
  youtube_url: string;
  notes: string;
  created_at: number;
}

export interface TopicMapEntry {
  keyword: string;
  category: string;
  years_bucket: string;
  frequency: number;
}

@Injectable({ providedIn: 'root' })
export class CareerService {
  private http = inject(HttpClient);
  private resumesSvc = inject(ResumesService);
  private opts = { withCredentials: true };

  private get resumeId(): string {
    return this.resumesSvc.activeResumeId() ?? '';
  }

  private resumeParams(extra: Record<string, string> = {}): { params: HttpParams } {
    let params = new HttpParams().set('resume_id', this.resumeId);
    for (const [k, v] of Object.entries(extra)) {
      if (v) params = params.set(k, v);
    }
    return { params };
  }

  // ── Personal info ──────────────────────────────────────────────
  getPersonalInfo(): Observable<{ entries: PersonalInfoEntry[] }> {
    return this.http.get<{ entries: PersonalInfoEntry[] }>(`${API}/personal-info`, {
      ...this.opts,
      ...this.resumeParams(),
    });
  }

  setPersonalInfo(key: string, value: string): Observable<PersonalInfoEntry> {
    return this.http.put<PersonalInfoEntry>(
      `${API}/personal-info`,
      { resume_id: this.resumeId, key, value },
      this.opts,
    );
  }

  deletePersonalInfo(key: string): Observable<{ ok: boolean }> {
    return this.http.delete<{ ok: boolean }>(`${API}/personal-info/${key}`, {
      ...this.opts,
      ...this.resumeParams(),
    });
  }

  // ── Apply later ────────────────────────────────────────────────
  listApplyLater(): Observable<{ entries: ApplyLaterEntry[] }> {
    return this.http.get<{ entries: ApplyLaterEntry[] }>(`${API}/apply-later`, {
      ...this.opts,
      ...this.resumeParams(),
    });
  }

  createApplyLater(url: string, companyName: string, notes: string): Observable<{ entry: ApplyLaterEntry }> {
    return this.http.post<{ entry: ApplyLaterEntry }>(
      `${API}/apply-later`,
      { resume_id: this.resumeId, url, company_name: companyName, notes },
      this.opts,
    );
  }

  updateApplyLater(id: string, applied?: boolean, notes?: string): Observable<{ entry: ApplyLaterEntry }> {
    return this.http.patch<{ entry: ApplyLaterEntry }>(
      `${API}/apply-later/${id}`,
      { applied, notes },
      this.opts,
    );
  }

  deleteApplyLater(id: string): Observable<{ ok: boolean }> {
    return this.http.delete<{ ok: boolean }>(`${API}/apply-later/${id}`, this.opts);
  }

  // ── Job post / LinkedIn archive ───────────────────────────────
  listJobPosts(): Observable<{ entries: JobPostEntry[] }> {
    return this.http.get<{ entries: JobPostEntry[] }>(`${API}/posts`, {
      ...this.opts,
      ...this.resumeParams(),
    });
  }

  createJobPost(
    url: string,
    companyName: string,
    roleTitle: string,
    rawText: string,
  ): Observable<{ entry: JobPostEntry }> {
    return this.http.post<{ entry: JobPostEntry }>(
      `${API}/posts`,
      { resume_id: this.resumeId, url, company_name: companyName, role_title: roleTitle, raw_text: rawText },
      this.opts,
    );
  }

  deleteJobPost(id: string): Observable<{ ok: boolean }> {
    return this.http.delete<{ ok: boolean }>(`${API}/posts/${id}`, this.opts);
  }

  uploadAttachment(postId: string, file: Blob, filename: string): Observable<{ attachment_id: string }> {
    const form = new FormData();
    form.append('file', file, filename);
    return this.http.post<{ attachment_id: string }>(
      `${API}/posts/${postId}/attachments`,
      form,
      this.opts,
    );
  }

  listAttachments(postId: string): Observable<{ entries: AttachmentEntry[] }> {
    return this.http.get<{ entries: AttachmentEntry[] }>(`${API}/posts/${postId}/attachments`, this.opts);
  }

  attachmentUrl(postId: string, attachmentId: string): string {
    return `${API}/posts/${postId}/attachments/${attachmentId}`;
  }

  deleteAttachment(postId: string, attachmentId: string): Observable<{ ok: boolean }> {
    return this.http.delete<{ ok: boolean }>(
      `${API}/posts/${postId}/attachments/${attachmentId}`,
      this.opts,
    );
  }

  // ── Interview prep ─────────────────────────────────────────────
  listInterviewTopics(companyName?: string): Observable<{ entries: InterviewTopicEntry[] }> {
    return this.http.get<{ entries: InterviewTopicEntry[] }>(`${API}/interview-topics`, {
      ...this.opts,
      ...this.resumeParams({ company_name: companyName ?? '' }),
    });
  }

  listInterviewCompanies(): Observable<{ companies: string[] }> {
    return this.http.get<{ companies: string[] }>(`${API}/interview-topics/companies`, {
      ...this.opts,
      ...this.resumeParams(),
    });
  }

  createInterviewTopic(
    companyName: string,
    topic: string,
    githubUrl: string,
    youtubeUrl: string,
    notes: string,
  ): Observable<{ entry: InterviewTopicEntry }> {
    return this.http.post<{ entry: InterviewTopicEntry }>(
      `${API}/interview-topics`,
      {
        resume_id: this.resumeId,
        company_name: companyName,
        topic,
        github_url: githubUrl,
        youtube_url: youtubeUrl,
        notes,
      },
      this.opts,
    );
  }

  updateInterviewTopic(
    id: string,
    fields: Partial<{ covered: boolean; github_url: string; youtube_url: string; notes: string }>,
  ): Observable<{ entry: InterviewTopicEntry }> {
    return this.http.patch<{ entry: InterviewTopicEntry }>(`${API}/interview-topics/${id}`, fields, this.opts);
  }

  deleteInterviewTopic(id: string): Observable<{ ok: boolean }> {
    return this.http.delete<{ ok: boolean }>(`${API}/interview-topics/${id}`, this.opts);
  }

  // ── Topic mapping ──────────────────────────────────────────────
  getTopicMap(yearsBucket?: string): Observable<{ entries: TopicMapEntry[] }> {
    return this.http.get<{ entries: TopicMapEntry[] }>(`${API}/topic-map`, {
      ...this.opts,
      ...this.resumeParams({ years_bucket: yearsBucket ?? '' }),
    });
  }

  getYearsBuckets(): Observable<{ buckets: string[] }> {
    return this.http.get<{ buckets: string[] }>(`${API}/topic-map/buckets`, {
      ...this.opts,
      ...this.resumeParams(),
    });
  }
}
