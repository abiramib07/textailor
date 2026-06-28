import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

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

@Injectable({ providedIn: 'root' })
export class ResumeService {
  constructor(private http: HttpClient) {}

  generate(jd: string): Observable<{ task_id: string }> {
    return this.http.post<{ task_id: string }>(`${API}/api/generate`, { jd });
  }

  getStatus(taskId: string): Observable<TaskStatus> {
    return this.http.get<TaskStatus>(`${API}/api/status/${taskId}`);
  }

  pdfUrl(taskId: string): string {
    return `${API}/api/pdf/${taskId}`;
  }

  templateUrl(): string {
    return `${API}/api/template`;
  }

  chatPlan(message: string): Observable<ChatPlanResult> {
    return this.http.post<ChatPlanResult>(`${API}/api/chat/plan`, { message });
  }

  chatExecute(planId: string, message: string): Observable<ChatEditResult> {
    return this.http.post<ChatEditResult>(`${API}/api/chat/execute`, { plan_id: planId, message });
  }

  chatUndo(): Observable<ChatEditResult> {
    return this.http.post<ChatEditResult>(`${API}/api/chat/undo`, {});
  }

  chatPdfUrl(editId: string): string {
    return `${API}/api/chat/pdf/${editId}`;
  }

  getReport(taskId: string): Observable<ScoreReport> {
    return this.http.get<ScoreReport>(`${API}/api/report/${taskId}`);
  }

  boostAts(taskId: string): Observable<BoostResult> {
    return this.http.post<BoostResult>(`${API}/api/boost/${taskId}`, {});
  }

  getResumeMd(): Observable<{ content: string }> {
    return this.http.get<{ content: string }>(`${API}/api/resume-md`);
  }

  saveResumeMd(content: string): Observable<{ saved: boolean }> {
    return this.http.put<{ saved: boolean }>(`${API}/api/resume-md`, { content });
  }

  syncResumeMd(): Observable<{ synced: boolean; edit_id: string; has_pdf: boolean }> {
    return this.http.post<{ synced: boolean; edit_id: string; has_pdf: boolean }>(`${API}/api/resume-md/sync`, {});
  }
}
