import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { ResumesService } from './resumes/resumes.service';

const API = 'http://localhost:8000';

export interface PipelineStep {
  name: string;
  status: 'pending' | 'running' | 'done' | 'error';
  detail: string;
  elapsed: string | null;
}

export interface TaskStatus {
  task_id: string;
  status: 'pending' | 'running' | 'done' | 'error';
  steps: PipelineStep[];
  score: number | null;
  verdict: string | null;
  error: string | null;
  has_pdf: boolean;
}

export interface ChatPlanResult {
  plan_id: string;
  intent_type: string;
  summary: string;
  changes_preview: string[];
  questions: string[];
  confidence: string;
}

export interface ChatEditResult {
  edit_id: string;
  success: boolean;
  done_summary: string;
  has_pdf: boolean;
  error: string | null;
}

export interface ScoreReport {
  overall_score: number;
  required_score: number;
  preferred_score: number;
  required_found: string[];
  required_missing: string[];
  preferred_found: string[];
  preferred_missing: string[];
  needs_metric_count: number;
  job_title: string;
  verdict: string;
}

export interface BoostResult {
  boost_id: string | null;
  score: number;
  verdict: string;
  has_pdf: boolean;
  message?: string;
}

export interface VerifierKeyword {
  keyword: string;
  status: 'exact' | 'semantic' | 'missing';
  evidence: string;
  required: boolean;
}

export interface VerifierResult {
  keywords: VerifierKeyword[];
}

export interface ExplainResult {
  keyword: string;
  status: 'exact' | 'semantic' | 'missing';
  evidence: string;
}

export interface HistoryEntry {
  id: string;
  company_name: string;
  job_title: string | null;
  job_url: string | null;
  pdf_path: string;
  ats_score: number | null;
  verdict: string | null;
  applied_date: string | null;
  created_at: number;
}

@Injectable({ providedIn: 'root' })
export class ResumeService {
  private http = inject(HttpClient);
  private resumesSvc = inject(ResumesService);

  private get resumeId(): string | null {
    return this.resumesSvc.activeResumeId();
  }

  generate(jd: string): Observable<{ task_id: string }> {
    return this.http.post<{ task_id: string }>(`${API}/api/generate`, {
      jd,
      resume_id: this.resumeId,
    });
  }

  getStatus(taskId: string): Observable<TaskStatus> {
    return this.http.get<TaskStatus>(`${API}/api/status/${taskId}`);
  }

  pdfUrl(taskId: string): string {
    return `${API}/api/pdf/${taskId}`;
  }

  /** Defaults to the app-wide active resume; pass `resumeId` to target a specific
   * one instead (e.g. a resume still being curated in the Import tab). */
  templateUrl(resumeId?: string): string {
    const rid = resumeId ?? this.resumeId;
    return rid ? `${API}/api/template?resume_id=${encodeURIComponent(rid)}` : `${API}/api/template`;
  }

  chatPlan(message: string, resumeId?: string): Observable<ChatPlanResult> {
    return this.http.post<ChatPlanResult>(`${API}/api/chat/plan`, {
      message,
      resume_id: resumeId ?? this.resumeId,
    });
  }

  chatExecute(planId: string, message: string): Observable<ChatEditResult> {
    return this.http.post<ChatEditResult>(`${API}/api/chat/execute`, { plan_id: planId, message });
  }

  chatUndo(resumeId?: string): Observable<ChatEditResult> {
    return this.http.post<ChatEditResult>(`${API}/api/chat/undo`, {
      resume_id: resumeId ?? this.resumeId,
    });
  }

  chatPdfUrl(editId: string): string {
    return `${API}/api/chat/pdf/${editId}`;
  }

  getReport(taskId: string): Observable<ScoreReport> {
    return this.http.get<ScoreReport>(`${API}/api/report/${taskId}`);
  }

  boostAts(taskId: string, selectedKeywords: string[]): Observable<BoostResult> {
    return this.http.post<BoostResult>(`${API}/api/boost/${taskId}`, {
      selected_keywords: selectedKeywords,
    });
  }

  getResumeMd(): Observable<{ content: string }> {
    let params = new HttpParams();
    if (this.resumeId) params = params.set('resume_id', this.resumeId);
    return this.http.get<{ content: string }>(`${API}/api/resume-md`, { params });
  }

  saveResumeMd(content: string): Observable<{ saved: boolean }> {
    return this.http.put<{ saved: boolean }>(`${API}/api/resume-md`, {
      content,
      resume_id: this.resumeId,
    });
  }

  syncResumeMd(): Observable<{ synced: boolean; edit_id: string; has_pdf: boolean }> {
    return this.http.post<{ synced: boolean; edit_id: string; has_pdf: boolean }>(
      `${API}/api/resume-md/sync`,
      { resume_id: this.resumeId },
    );
  }

  saveHistory(
    taskId: string,
    companyName: string,
    jobUrl: string,
    appliedDate: string,
  ): Observable<{ entry: HistoryEntry }> {
    return this.http.post<{ entry: HistoryEntry }>(`${API}/api/history`, {
      task_id: taskId,
      company_name: companyName,
      job_url: jobUrl,
      applied_date: appliedDate,
    });
  }

  getHistory(): Observable<{ entries: HistoryEntry[] }> {
    let params = new HttpParams();
    if (this.resumeId) params = params.set('resume_id', this.resumeId);
    return this.http.get<{ entries: HistoryEntry[] }>(`${API}/api/history`, { params });
  }

  historyPdfUrl(entryId: string): string {
    return `${API}/api/history/${entryId}/pdf`;
  }

  runVerifier(taskId: string): Observable<VerifierResult> {
    return this.http.post<VerifierResult>(`${API}/api/verify/${taskId}`, {});
  }

  explainKeyword(taskId: string, keyword: string): Observable<ExplainResult> {
    return this.http.post<ExplainResult>(`${API}/api/verify/${taskId}/explain`, { keyword });
  }
}
