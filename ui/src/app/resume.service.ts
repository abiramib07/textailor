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
  /** Sections the rewriter kept unchanged because weaving in the requested
   * keywords honestly wasn't possible (e.g. a domain mismatch) — surfaced
   * so this never happens silently. */
  warnings: string[];
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

export interface CompareResult {
  original: string;
  tailored: string;
}

export interface BoostResult {
  boost_id: string | null;
  score: number;
  verdict: string;
  has_pdf: boolean;
  message?: string;
  /** Sections kept unchanged because weaving in the requested keywords
   * honestly wasn't possible (e.g. a domain mismatch). */
  warnings: string[];
}

export interface AddSkillsResult extends BoostResult {
  added: string[];
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

export interface PitchResult {
  short_pitch: string;
  written_bio: string;
  project_pitches: string;
  cover_letter_template: string;
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
   * one instead (e.g. a resume still being curated in the Import tab).
   * Includes a cache-busting timestamp so a repeated call with the same
   * resume id still produces a new URL — otherwise an `<iframe [src]>`
   * bound to an unchanged string won't re-navigate even after the PDF
   * on disk changes. */
  templateUrl(resumeId?: string): string {
    const rid = resumeId ?? this.resumeId;
    const base = rid ? `${API}/api/template?resume_id=${encodeURIComponent(rid)}` : `${API}/api/template`;
    const sep = base.includes('?') ? '&' : '?';
    return `${base}${sep}t=${Date.now()}`;
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

  /** Base resume (untouched) vs. this task's current tailored output,
   * plain-text, for the side-by-side diff viewer. */
  compareTask(taskId: string): Observable<CompareResult> {
    return this.http.get<CompareResult>(`${API}/api/compare/${taskId}`);
  }

  /** Independent ATS rescan: re-runs recruiter analysis + scoring from
   * scratch against fresh resume text, decoupled from any cached pipeline
   * state. Pass `file` to score an uploaded resume, or omit it to have the
   * backend re-read `taskId`'s current tex fresh off disk instead. */
  atsCheck(jd: string, taskId: string, file?: File): Observable<ScoreReport> {
    const formData = new FormData();
    formData.append('jd', jd);
    if (file) {
      formData.append('file', file);
    } else {
      formData.append('task_id', taskId);
    }
    return this.http.post<ScoreReport>(`${API}/api/ats-check`, formData);
  }

  boostAts(taskId: string, selectedKeywords: string[]): Observable<BoostResult> {
    return this.http.post<BoostResult>(`${API}/api/boost/${taskId}`, {
      selected_keywords: selectedKeywords,
    });
  }

  /** Fast, deterministic alternative to `boostAts` — adds the selected
   * missing keywords straight into the Technical Skills table, no AI
   * rewrite involved. */
  addSkillsToResume(taskId: string, selectedKeywords: string[]): Observable<AddSkillsResult> {
    return this.http.post<AddSkillsResult>(`${API}/api/boost/add-skills/${taskId}`, {
      selected_keywords: selectedKeywords,
    });
  }

  /** Recompute the ATS score from whatever's currently on disk — call this
   * after a chat edit (which patches the resume directly, outside the
   * pipeline) to see its effect without re-running the whole generation. */
  rescoreTask(taskId: string): Observable<ScoreReport> {
    return this.http.post<ScoreReport>(`${API}/api/rescore/${taskId}`, {});
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

  /** Draft a short pitch / written bio / project talking points / cover
   * letter template from this task's JD and its current tailored resume.
   * Preview only — nothing is saved until the caller writes each field via
   * CareerService.setPersonalInfo. */
  generatePitches(taskId: string, jd: string): Observable<PitchResult> {
    return this.http.post<PitchResult>(`${API}/api/pitch/${taskId}`, { jd });
  }
}
