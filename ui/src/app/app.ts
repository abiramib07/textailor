import { Component, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { ResumeService, TaskStatus, PipelineStep } from './resume.service';

const STEP_NAMES = [
  'Parse resume',
  'Analyse job description',
  'Rewrite sections',
  'Compile PDF',
  'Score ATS match',
];

function pendingSteps(): PipelineStep[] {
  return STEP_NAMES.map(name => ({ name, status: 'pending', detail: '', elapsed: null }));
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App implements OnDestroy {
  jd = '';
  taskId: string | null = null;
  status: TaskStatus | null = null;
  pdfUrl: SafeResourceUrl | null = null;
  pdfRawUrl: string | null = null;
  isGenerating = false;
  showTemplate = false;
  templateUrl: SafeResourceUrl;

  localSteps: PipelineStep[] = pendingSteps();
  elapsedSeconds = 0;

  private _elapsedTimer: ReturnType<typeof setInterval> | null = null;
  private _pollTimeout: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private svc: ResumeService,
    private sanitizer: DomSanitizer,
    private cdr: ChangeDetectorRef
  ) {
    this.templateUrl = sanitizer.bypassSecurityTrustResourceUrl(svc.templateUrl());
  }

  ngOnDestroy() {
    this._clearElapsedTimer();
    this._cancelPoll();
  }

  generate() {
    if (!this.jd.trim() || this.isGenerating) return;

    console.log('[TexTailor] generate() called');
    this.isGenerating = true;
    this.status = null;
    this.pdfUrl = null;
    this.pdfRawUrl = null;
    this.taskId = null;
    this.showTemplate = false;
    this.localSteps = pendingSteps();
    this._startElapsedTimer();
    this.cdr.detectChanges();

    this.svc.generate(this.jd).subscribe({
      next: ({ task_id }) => {
        console.log('[TexTailor] task created:', task_id);
        this.taskId = task_id;
        this._poll(task_id);
      },
      error: err => {
        console.error('[TexTailor] generate error:', err);
        this._finish();
      }
    });
  }

  viewTemplate() {
    this.pdfUrl = null;
    this.showTemplate = true;
    this.cdr.detectChanges();
  }

  download() {
    if (!this.pdfRawUrl) return;
    const a = document.createElement('a');
    a.href = this.pdfRawUrl;
    a.download = 'resume_tailored.pdf';
    a.click();
  }

  get displaySteps(): PipelineStep[] {
    return this.status?.steps ?? this.localSteps;
  }

  get progressPct(): number {
    const steps = this.displaySteps;
    if (!steps.length) return 0;
    const done = steps.filter(s => s.status === 'done').length;
    return Math.round((done / steps.length) * 100);
  }

  get elapsedLabel(): string {
    const m = Math.floor(this.elapsedSeconds / 60);
    const s = this.elapsedSeconds % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  }

  get scoreColor(): string {
    if (!this.status?.score) return '#6b7280';
    if (this.status.score >= 85) return '#22c55e';
    if (this.status.score >= 70) return '#f59e0b';
    return '#ef4444';
  }

  // ── Polling — one request at a time, explicit stop ──────────────────
  private _poll(taskId: string) {
    this.svc.getStatus(taskId).subscribe({
      next: s => {
        console.log('[TexTailor] poll →', s.status,
          s.steps.map(st => `${st.name}:${st.status}`).join(' | '));

        this.status = s;
        this.cdr.detectChanges();   // force re-render after every poll

        if (s.status === 'done') {
          if (s.has_pdf) {
            this.pdfRawUrl = this.svc.pdfUrl(taskId);
            this.pdfUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.pdfRawUrl);
          }
          this._finish();

        } else if (s.status === 'error') {
          this._finish();

        } else {
          this._pollTimeout = setTimeout(() => this._poll(taskId), 1500);
        }
      },
      error: err => {
        console.warn('[TexTailor] poll error, retrying:', err);
        this._pollTimeout = setTimeout(() => this._poll(taskId), 2000);
      }
    });
  }

  private _cancelPoll() {
    if (this._pollTimeout !== null) {
      clearTimeout(this._pollTimeout);
      this._pollTimeout = null;
    }
  }

  // ── Elapsed timer ───────────────────────────────────────────────────
  private _startElapsedTimer() {
    this.elapsedSeconds = 0;
    this._clearElapsedTimer();
    this._elapsedTimer = setInterval(() => {
      this.elapsedSeconds++;
      this.cdr.detectChanges();    // force timer re-render every second
    }, 1000);
  }

  private _clearElapsedTimer() {
    if (this._elapsedTimer !== null) {
      clearInterval(this._elapsedTimer);
      this._elapsedTimer = null;
    }
  }

  private _finish() {
    console.log('[TexTailor] pipeline finished, status:', this.status?.status);
    this.isGenerating = false;
    this._clearElapsedTimer();
    this._cancelPoll();
    this.cdr.detectChanges();
  }
}
