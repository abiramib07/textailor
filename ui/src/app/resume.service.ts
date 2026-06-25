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
}
