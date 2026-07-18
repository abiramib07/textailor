import { Component, OnInit, ChangeDetectorRef, ViewChild, ElementRef, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { ResumesService, ResumeIdentity } from '../resumes/resumes.service';
import { ResumeService } from '../resume.service';

interface ImportChatMessage {
  role: 'user' | 'plan' | 'bot' | 'error';
  text: string;
  planId?: string;
  changesPreview?: string[];
}

type Stage = 'upload' | 'curating';
type ChatState = 'idle' | 'planning' | 'awaiting_confirmation' | 'executing';

/**
 * Upload a resume from outside the app (PDF, Word, or LaTeX), refine it via
 * the same chat editor used elsewhere, then adopt it as a resume identity
 * usable everywhere else — the workflow for onboarding a new person's
 * resume, or a messy multi-format version of your own.
 */
@Component({
  selector: 'app-resume-import',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './resume-import.html',
  styleUrl: './resume-import.scss',
})
export class ResumeImportComponent implements OnInit {
  private resumesSvc = inject(ResumesService);
  private svc = inject(ResumeService);
  private sanitizer = inject(DomSanitizer);
  private cdr = inject(ChangeDetectorRef);

  stage: Stage = 'upload';

  get existingResumes(): ResumeIdentity[] {
    return this.resumesSvc.resumes();
  }

  ngOnInit() {
    this.resumesSvc.list().subscribe({ next: () => this.cdr.detectChanges() });
  }

  // ── Upload stage ──────────────────────────────────────────────
  uploadLabel = '';
  uploadOwner = '';
  uploadFile: File | null = null;
  uploading = false;
  uploadError = '';

  // ── Curating stage ───────────────────────────────────────────
  resumeId: string | null = null;
  compileWarning: string | null = null;
  pdfUrl: SafeResourceUrl | null = null;
  pdfRawUrl: string | null = null;

  chatMessages: ImportChatMessage[] = [];
  chatInput = '';
  chatState: ChatState = 'idle';
  pendingPlan: {
    planId: string;
    message: string;
    summary: string;
    changesPreview: string[];
  } | null = null;

  finalLabel = '';
  finalOwner = '';
  saving = false;
  saved = false;

  @ViewChild('chatScroll') chatScrollEl!: ElementRef;

  get isChatBusy(): boolean {
    return this.chatState === 'planning' || this.chatState === 'executing';
  }

  onFileSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    this.uploadFile = input.files?.[0] ?? null;
  }

  get canImport(): boolean {
    return !!this.uploadLabel.trim() && !!this.uploadFile && !this.uploading;
  }

  startImport() {
    if (!this.canImport || !this.uploadFile) return;
    this.uploading = true;
    this.uploadError = '';
    this.cdr.detectChanges();

    this.resumesSvc
      .importForCuration(this.uploadLabel.trim(), this.uploadOwner.trim(), this.uploadFile)
      .subscribe({
        next: ({ resume, has_pdf, compile_warning }) => {
          this.uploading = false;
          this.resumeId = resume.id;
          this.finalLabel = resume.label;
          this.finalOwner = resume.owner_name;
          this.compileWarning = compile_warning;
          if (has_pdf) {
            this.pdfRawUrl = this.svc.templateUrl(resume.id);
            this.pdfUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.pdfRawUrl);
          }
          this.stage = 'curating';
          this.chatMessages = [];
          this.saved = false;
          this.cdr.detectChanges();
        },
        error: (err) => {
          this.uploading = false;
          this.uploadError = err?.error?.detail ?? 'Could not import this file. Please try again.';
          this.cdr.detectChanges();
        },
      });
  }

  /** Jump straight into curation for a resume that's already in the switcher —
   * no upload needed, just load its preview and open the chat panel. */
  curateExisting(resume: ResumeIdentity) {
    this.resumeId = resume.id;
    this.finalLabel = resume.label;
    this.finalOwner = resume.owner_name;
    this.compileWarning = null;
    this.pdfRawUrl = this.svc.templateUrl(resume.id);
    this.pdfUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.pdfRawUrl);
    this.stage = 'curating';
    this.chatMessages = [];
    this.saved = false;
    this.cdr.detectChanges();
  }

  // ── Chat curation (mirrors the Generator tab's plan → confirm → execute flow) ──
  onChatKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendChat();
    }
  }

  sendChat() {
    const msg = this.chatInput.trim();
    if (!msg || !this.resumeId || this.chatState !== 'idle') return;

    this.chatInput = '';
    this._pushMsg({ role: 'user', text: msg });
    this.chatState = 'planning';
    this.cdr.detectChanges();

    this.svc.chatPlan(msg, this.resumeId).subscribe({
      next: (result) => {
        this.pendingPlan = {
          planId: result.plan_id,
          message: msg,
          summary: result.summary,
          changesPreview: result.changes_preview ?? [],
        };

        if (result.questions?.length) {
          this._pushMsg({
            role: 'bot',
            text: result.summary + '\n\n' + result.questions.join('\n'),
          });
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
      },
    });
  }

  confirmPlan() {
    if (!this.pendingPlan || this.chatState !== 'awaiting_confirmation') return;
    const { planId, message } = this.pendingPlan;
    this.chatState = 'executing';
    this.cdr.detectChanges();

    this.svc.chatExecute(planId, message).subscribe({
      next: (result) => {
        if (result.success) {
          this._pushMsg({ role: 'bot', text: '✓ ' + result.done_summary });
          if (result.has_pdf) {
            this.pdfRawUrl = this.svc.chatPdfUrl(result.edit_id);
            this.pdfUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.pdfRawUrl);
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
      },
    });
  }

  cancelPlan() {
    this.pendingPlan = null;
    this.chatState = 'idle';
    this._pushMsg({ role: 'bot', text: 'Cancelled. What would you like to change instead?' });
    this.cdr.detectChanges();
  }

  undoChat() {
    if (!this.resumeId || this.chatState !== 'idle') return;
    this.chatState = 'executing';
    this._pushMsg({ role: 'user', text: '↩ Undo last change' });
    this.cdr.detectChanges();

    this.svc.chatUndo(this.resumeId).subscribe({
      next: (result) => {
        this._pushMsg({ role: result.success ? 'bot' : 'error', text: result.done_summary });
        if (result.success && result.has_pdf) {
          this.pdfRawUrl = this.svc.chatPdfUrl(result.edit_id);
          this.pdfUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.pdfRawUrl);
        }
        this.chatState = 'idle';
        this.cdr.detectChanges();
      },
      error: () => {
        this._pushMsg({ role: 'error', text: 'Undo failed.' });
        this.chatState = 'idle';
        this.cdr.detectChanges();
      },
    });
  }

  private _pushMsg(msg: ImportChatMessage) {
    this.chatMessages.push(msg);
    setTimeout(() => {
      if (this.chatScrollEl) {
        const el = this.chatScrollEl.nativeElement;
        el.scrollTop = el.scrollHeight;
      }
    }, 0);
  }

  // ── Download the current preview PDF ────────────────────────────
  get downloadFilename(): string {
    const base = (this.finalLabel || 'resume').trim().replace(/[^\w\- ]/g, '').replace(/\s+/g, '_');
    return `${base || 'resume'}.pdf`;
  }

  downloadPdf() {
    if (!this.pdfRawUrl) return;
    const url = this.pdfRawUrl;
    const filename = this.downloadFilename;
    fetch(url)
      .then((r) => r.blob())
      .then((blob) => {
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

  // ── Save as a usable resume identity ────────────────────────────
  get canSave(): boolean {
    return !!this.finalLabel.trim() && !this.saving;
  }

  saveAsMain() {
    if (!this.canSave || !this.resumeId) return;
    this.saving = true;
    this.cdr.detectChanges();

    this.resumesSvc.rename(this.resumeId, this.finalLabel.trim(), this.finalOwner.trim()).subscribe({
      next: () => {
        this.resumesSvc.setActive(this.resumeId!);
        this.saving = false;
        this.saved = true;
        this.cdr.detectChanges();
      },
      error: () => {
        this.saving = false;
        this.cdr.detectChanges();
      },
    });
  }

  startOver() {
    this.stage = 'upload';
    this.uploadLabel = '';
    this.uploadOwner = '';
    this.uploadFile = null;
    this.uploadError = '';
    this.resumeId = null;
    this.compileWarning = null;
    this.pdfUrl = null;
    this.pdfRawUrl = null;
    this.chatMessages = [];
    this.chatInput = '';
    this.chatState = 'idle';
    this.pendingPlan = null;
    this.saved = false;
    this.cdr.detectChanges();
  }
}
