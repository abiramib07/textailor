import { Component, OnDestroy, OnInit, ChangeDetectorRef, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { ResumeService, TaskStatus, PipelineStep, ScoreReport } from './resume.service';
import { AuthService, UserProfile } from './auth/auth.service';

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

export interface ChatMessage {
  role: 'user' | 'plan' | 'bot' | 'error';
  text: string;
  planId?: string;
  changesPreview?: string[];
}

type Tab = 'generate' | 'edit-resume';
type EditorState = 'idle' | 'loading' | 'editing' | 'saving' | 'saved' | 'syncing' | 'synced' | 'error';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App implements OnInit, OnDestroy {

  // ── Auth (session, if any) ──────────────────────────────────────
  authUser: UserProfile | null = null;
  authChecked = false;

  // ── Tabs ────────────────────────────────────────────────────────
  activeTab: Tab = 'generate';

  // ── Pipeline state ──────────────────────────────────────────────
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

  // ── Report state ────────────────────────────────────────────────
  reportData: ScoreReport | null = null;
  showReport = false;

  // ── Boost state ─────────────────────────────────────────────────
  isBoosting = false;
  boostScore: number | null = null;
  boostPdfUrl: SafeResourceUrl | null = null;
  boostPdfRawUrl: string | null = null;

  // ── Chat state ──────────────────────────────────────────────────
  chatMessages: ChatMessage[] = [];
  chatInput = '';
  chatState: 'idle' | 'planning' | 'awaiting_confirmation' | 'executing' = 'idle';
  pendingPlan: { planId: string; message: string; summary: string; changesPreview: string[] } | null = null;
  chatPdfUrl: SafeResourceUrl | null = null;
  chatPdfRawUrl: string | null = null;

  // ── Editor state ────────────────────────────────────────────────
  mdContent = '';
  mdOriginal = '';
  editorState: EditorState = 'idle';
  editorPdfUrl: SafeResourceUrl | null = null;
  editorPdfRawUrl: string | null = null;
  editorError = '';

  @ViewChild('chatScroll') chatScrollEl!: ElementRef;

  private _elapsedTimer: ReturnType<typeof setInterval> | null = null;
  private _pollTimeout: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private svc: ResumeService,
    private sanitizer: DomSanitizer,
    private cdr: ChangeDetectorRef,
    private authSvc: AuthService
  ) {
    this.templateUrl = sanitizer.bypassSecurityTrustResourceUrl(svc.templateUrl());
  }

  ngOnInit() {
    // Not being logged in is a normal state here (unlike /welcome) — the
    // resume tool works with or without a session, so no redirect on 401.
    this.authSvc.me().subscribe({
      next: ({ user }) => {
        this.authUser = user;
        this.authChecked = true;
        this.cdr.detectChanges();
      },
      error: () => {
        this.authUser = null;
        this.authChecked = true;
        this.cdr.detectChanges();
      },
    });
  }

  logout() {
    this.authSvc.logout().subscribe(() => {
      this.authUser = null;
      this.cdr.detectChanges();
    });
  }

  ngOnDestroy() {
    this._clearElapsedTimer();
    this._cancelPoll();
  }

  // ── Tab navigation ──────────────────────────────────────────────
  setTab(tab: Tab) {
    if (tab === this.activeTab) return;
    if (tab === 'generate' && this.mdDirty) {
      if (!confirm('You have unsaved changes in the editor. Leave without saving?')) return;
    }
    this.activeTab = tab;
    if (tab === 'edit-resume' && this.editorState === 'idle') {
      this.loadMd();
    }
    this.cdr.detectChanges();
  }

  // ── PDF active in viewer ────────────────────────────────────────
  get activePdfUrl(): SafeResourceUrl | null {
    return this.boostPdfUrl ?? this.chatPdfUrl ?? this.pdfUrl;
  }

  get showTemplatePdf(): boolean {
    return this.showTemplate && !this.activePdfUrl;
  }

  // ── Pipeline ────────────────────────────────────────────────────
  generate() {
    if (!this.jd.trim() || this.isGenerating) return;
    this.isGenerating = true;
    this.status = null;
    this.pdfUrl = null;
    this.pdfRawUrl = null;
    this.taskId = null;
    this.reportData = null;
    this.showReport = false;
    this.boostScore = null;
    this.boostPdfUrl = null;
    this.boostPdfRawUrl = null;
    this.showTemplate = false;
    this.localSteps = pendingSteps();
    this._startElapsedTimer();
    this.cdr.detectChanges();

    this.svc.generate(this.jd).subscribe({
      next: ({ task_id }) => {
        this.taskId = task_id;
        this._poll(task_id);
      },
      error: () => this._finish()
    });
  }

  viewTemplate() {
    this.pdfUrl = null;
    this.showTemplate = true;
    this.cdr.detectChanges();
  }

  download() {
    const url = this.boostPdfRawUrl ?? this.chatPdfRawUrl ?? this.pdfRawUrl;
    if (!url) return;
    this._blobDownload(url, 'resume_tailored.pdf');
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
    const s = this.boostScore ?? this.status?.score;
    if (!s) return '#6b7280';
    if (s >= 90) return '#22c55e';
    if (s >= 70) return '#f59e0b';
    return '#ef4444';
  }

  get currentScore(): number | null {
    return this.boostScore ?? this.status?.score ?? null;
  }

  // ── ATS Report ──────────────────────────────────────────────────
  toggleReport() {
    this.showReport = !this.showReport;
    this.cdr.detectChanges();
  }

  private _loadReport(taskId: string) {
    this.svc.getReport(taskId).subscribe({
      next: report => {
        this.reportData = report;
        this.cdr.detectChanges();
      },
      error: () => {}
    });
  }

  // ── ATS Boost ───────────────────────────────────────────────────
  boostAts() {
    if (!this.taskId || this.isBoosting) return;
    this.isBoosting = true;
    this.cdr.detectChanges();

    this.svc.boostAts(this.taskId).subscribe({
      next: result => {
        this.boostScore = result.score;
        if (result.has_pdf && result.boost_id) {
          this.boostPdfRawUrl = this.svc.chatPdfUrl(result.boost_id);
          this.boostPdfUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.boostPdfRawUrl);
        }
        if (this.reportData) {
          this.reportData = { ...this.reportData, overall_score: result.score, verdict: result.verdict };
        }
        this.isBoosting = false;
        this.cdr.detectChanges();
      },
      error: () => {
        this.isBoosting = false;
        this.cdr.detectChanges();
      }
    });
  }

  // ── Chat ────────────────────────────────────────────────────────
  sendChat() {
    const msg = this.chatInput.trim();
    if (!msg || this.chatState !== 'idle') return;

    this.chatInput = '';
    this._pushMsg({ role: 'user', text: msg });
    this.chatState = 'planning';
    this.cdr.detectChanges();

    this.svc.chatPlan(msg).subscribe({
      next: result => {
        this.pendingPlan = {
          planId: result.plan_id,
          message: msg,
          summary: result.summary,
          changesPreview: result.changes_preview ?? [],
        };

        if (result.questions?.length) {
          this._pushMsg({ role: 'bot', text: result.summary + '\n\n' + result.questions.join('\n') });
          this.pendingPlan = null;
          this.chatState = 'idle';
        } else {
          this.chatState = 'awaiting_confirmation';
          this._pushMsg({
            role: 'plan',
            text: result.summary,
            changesPreview: result.changes_preview ?? [],
            planId: result.plan_id,
          });
        }
        this.cdr.detectChanges();
      },
      error: () => {
        this._pushMsg({ role: 'error', text: 'Failed to analyse request. Please try again.' });
        this.pendingPlan = null;
        this.chatState = 'idle';
        this.cdr.detectChanges();
      }
    });
  }

  confirmPlan() {
    if (!this.pendingPlan || this.chatState !== 'awaiting_confirmation') return;
    const { planId, message } = this.pendingPlan;
    this.chatState = 'executing';
    this.cdr.detectChanges();

    this.svc.chatExecute(planId, message).subscribe({
      next: result => {
        if (result.success) {
          this._pushMsg({ role: 'bot', text: '✓ ' + result.done_summary });
          if (result.has_pdf) {
            this.chatPdfRawUrl = this.svc.chatPdfUrl(result.edit_id);
            this.chatPdfUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.chatPdfRawUrl);
          }
        } else {
          this._pushMsg({ role: 'error', text: result.error ?? 'Something went wrong.' });
        }
        this.pendingPlan = null;
        this.chatState = 'idle';
        this.cdr.detectChanges();
      },
      error: () => {
        this._pushMsg({ role: 'error', text: 'Failed to apply changes. Please try again.' });
        this.pendingPlan = null;
        this.chatState = 'idle';
        this.cdr.detectChanges();
      }
    });
  }

  cancelPlan() {
    this.pendingPlan = null;
    this.chatState = 'idle';
    this._pushMsg({ role: 'bot', text: 'Cancelled. What would you like to change instead?' });
    this.cdr.detectChanges();
  }

  undoChat() {
    if (this.chatState !== 'idle') return;
    this.chatState = 'executing';
    this._pushMsg({ role: 'user', text: '↩ Undo last change' });
    this.cdr.detectChanges();

    this.svc.chatUndo().subscribe({
      next: result => {
        this._pushMsg({ role: result.success ? 'bot' : 'error', text: result.done_summary });
        if (result.success && result.has_pdf) {
          this.chatPdfRawUrl = this.svc.chatPdfUrl(result.edit_id);
          this.chatPdfUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.chatPdfRawUrl);
        }
        this.chatState = 'idle';
        this.cdr.detectChanges();
      },
      error: () => {
        this._pushMsg({ role: 'error', text: 'Undo failed.' });
        this.chatState = 'idle';
        this.cdr.detectChanges();
      }
    });
  }

  get isChatBusy(): boolean {
    return this.chatState === 'planning' || this.chatState === 'executing';
  }

  private _pushMsg(msg: ChatMessage) {
    this.chatMessages.push(msg);
    setTimeout(() => {
      if (this.chatScrollEl) {
        const el = this.chatScrollEl.nativeElement;
        el.scrollTop = el.scrollHeight;
      }
    }, 0);
  }

  // ── Resume MD editor ────────────────────────────────────────────
  get mdDirty(): boolean {
    return this.mdContent !== this.mdOriginal;
  }

  loadMd() {
    this.editorState = 'loading';
    this.editorError = '';
    this.cdr.detectChanges();

    this.svc.getResumeMd().subscribe({
      next: res => {
        this.mdContent = res.content;
        this.mdOriginal = res.content;
        this.editorState = 'editing';
        this.cdr.detectChanges();
      },
      error: () => {
        this.editorState = 'error';
        this.editorError = 'Could not load resume content. Is the API server running?';
        this.cdr.detectChanges();
      }
    });
  }

  saveMd() {
    if (!this.mdDirty) return;
    this.editorState = 'saving';
    this.cdr.detectChanges();

    this.svc.saveResumeMd(this.mdContent).subscribe({
      next: () => {
        this.mdOriginal = this.mdContent;
        this.editorState = 'saved';
        this.editorPdfUrl = null;
        this.cdr.detectChanges();
      },
      error: () => {
        this.editorState = 'error';
        this.editorError = 'Failed to save draft.';
        this.cdr.detectChanges();
      }
    });
  }

  discardMd() {
    this.mdContent = this.mdOriginal;
    this.editorState = 'editing';
    this.editorPdfUrl = null;
    this.editorError = '';
    this.cdr.detectChanges();
  }

  syncMd() {
    this.editorState = 'syncing';
    this.cdr.detectChanges();

    this.svc.syncResumeMd().subscribe({
      next: res => {
        if (res.synced && res.has_pdf) {
          this.editorPdfRawUrl = this.svc.chatPdfUrl(res.edit_id);
          this.editorPdfUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.editorPdfRawUrl);
        }
        this.editorState = 'synced';
        this.cdr.detectChanges();
      },
      error: err => {
        this.editorState = 'error';
        this.editorError = err?.error?.detail ?? 'Sync failed. Check the API logs.';
        this.cdr.detectChanges();
      }
    });
  }

  downloadEditor() {
    if (!this.editorPdfRawUrl) return;
    this._blobDownload(this.editorPdfRawUrl, 'resume_updated.pdf');
  }

  private _blobDownload(url: string, filename: string) {
    fetch(url)
      .then(r => r.blob())
      .then(blob => {
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(blobUrl), 10000);
      });
  }

  // ── Polling ─────────────────────────────────────────────────────
  private _poll(taskId: string) {
    this.svc.getStatus(taskId).subscribe({
      next: s => {
        this.status = s;
        this.cdr.detectChanges();

        if (s.status === 'done') {
          if (s.has_pdf) {
            this.pdfRawUrl = this.svc.pdfUrl(taskId);
            this.pdfUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.pdfRawUrl);
          }
          this._loadReport(taskId);
          this._finish();
        } else if (s.status === 'error') {
          this._finish();
        } else {
          this._pollTimeout = setTimeout(() => this._poll(taskId), 1500);
        }
      },
      error: () => {
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

  private _startElapsedTimer() {
    this.elapsedSeconds = 0;
    this._clearElapsedTimer();
    this._elapsedTimer = setInterval(() => {
      this.elapsedSeconds++;
      this.cdr.detectChanges();
    }, 1000);
  }

  private _clearElapsedTimer() {
    if (this._elapsedTimer !== null) {
      clearInterval(this._elapsedTimer);
      this._elapsedTimer = null;
    }
  }

  private _finish() {
    this.isGenerating = false;
    this._clearElapsedTimer();
    this._cancelPoll();
    this.cdr.detectChanges();
  }
}
