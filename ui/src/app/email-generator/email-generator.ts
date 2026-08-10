import {
  Component,
  ChangeDetectorRef,
  OnDestroy,
  Output,
  EventEmitter,
  ViewChild,
  ElementRef,
  inject,
} from '@angular/core';

import { FormsModule } from '@angular/forms';
import { EmailService, EmailDraft, EmailSaveResult } from './email.service';
import { ResumesService } from '../resumes/resumes.service';

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

interface EmailChatMessage {
  role: 'user' | 'assistant' | 'error';
  text: string;
}

const QUICK_SUGGESTS = [
  'Make it shorter',
  'More formal tone',
  'Add availability',
  'Mention referral',
];

@Component({
  selector: 'app-email-generator',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './email-generator.html',
  styleUrl: './email-generator.scss',
})
export class EmailGeneratorComponent implements OnDestroy {
  private svc = inject(EmailService);
  private cdr = inject(ChangeDetectorRef);
  private resumesSvc = inject(ResumesService);

  jobPost = '';
  sourceUrl = '';
  instruction = 'Write a professional email to apply for this role, referencing my resume.';

  isGenerating = false;
  elapsedSeconds = 0;
  generateError = '';

  draft: EmailDraft | null = null;
  lastGeneratedSeconds = 0;

  isEditing = false;
  editTo = '';
  editSubject = '';
  editBody = '';
  isSavingEdit = false;

  quickSuggests = QUICK_SUGGESTS;
  chatMessages: EmailChatMessage[] = [];
  chatInput = '';
  chatBusy = false;
  canUndo = false;

  isSaving = false;
  saveResult: EmailSaveResult | null = null;
  saveError = '';
  private _saveErrorTimer: ReturnType<typeof setTimeout> | null = null;
  private _sendErrorTimer: ReturnType<typeof setTimeout> | null = null;

  sendTo = '';
  isSending = false;
  sendError = '';
  sendResult: { to: string } | null = null;
  showSendConfirm = false;

  /** Guards against silently losing track of an application: if the
   * current draft hasn't been saved yet, starting a new one (via
   * `generate()` or `newEmail()`) shows a "Save it first, or Discard &
   * Continue" confirm instead of clearing it out from under the user.
   * `_pendingAction` remembers which call to resume on confirm. */
  showDiscardSaveConfirm = false;
  private _pendingAction: (() => void) | null = null;

  @Output() tailorResume = new EventEmitter<string>();

  @ViewChild('chatScroll') chatScrollEl!: ElementRef;
  private _elapsedTimer: ReturnType<typeof setInterval> | null = null;

  ngOnDestroy() {
    this._clearTimer();
    if (this._copiedTimer) clearTimeout(this._copiedTimer);
    if (this._saveErrorTimer) clearTimeout(this._saveErrorTimer);
    if (this._sendErrorTimer) clearTimeout(this._sendErrorTimer);
  }

  get canGenerate(): boolean {
    return this.jobPost.trim().length > 0 && !this.isGenerating;
  }

  generate() {
    if (!this.canGenerate) return;
    if (this.draft && !this.saveResult) {
      this._pendingAction = () => this._doGenerate();
      this.showDiscardSaveConfirm = true;
      this.cdr.detectChanges();
      return;
    }
    this._doGenerate();
  }

  discardSaveAndContinue() {
    this.showDiscardSaveConfirm = false;
    const action = this._pendingAction;
    this._pendingAction = null;
    action?.();
  }

  cancelDiscardSave() {
    this.showDiscardSaveConfirm = false;
    this._pendingAction = null;
  }

  private _doGenerate() {
    this.isGenerating = true;
    this.generateError = '';
    this.draft = null;
    this.chatMessages = [];
    this.canUndo = false;
    this.isEditing = false;
    this.saveResult = null;
    this.saveError = '';
    this.sendResult = null;
    this.sendError = '';
    this.showSendConfirm = false;
    this._startTimer();
    this.cdr.detectChanges();

    this.svc.generate(this.jobPost, this.instruction, this.sourceUrl).subscribe({
      next: (draft) => {
        this.draft = draft;
        this.lastGeneratedSeconds = this.elapsedSeconds;
        this._finish();
      },
      error: (err) => {
        this.generateError =
          err?.error?.detail ?? 'Could not generate the email. Please try again.';
        this._finish();
      },
    });
  }

  sendChat(message?: string) {
    const text = (message ?? this.chatInput).trim();
    if (!text || !this.draft || this.chatBusy) return;

    this.chatInput = '';
    this._pushMsg({ role: 'user', text });
    this.chatBusy = true;
    this.cdr.detectChanges();

    this.svc.revise(this.draft.email_id, text).subscribe({
      next: (result) => {
        this.draft = {
          email_id: result.email_id,
          to: result.to,
          subject: result.subject,
          body: result.body,
          role_title: result.role_title,
          company_name: result.company_name,
        };
        this.canUndo = true;
        this.isEditing = false;
        // The draft body changed — a prior save no longer reflects it.
        this.saveResult = null;
        this._pushMsg({ role: 'assistant', text: result.done_summary });
        this.chatBusy = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        this._pushMsg({
          role: 'error',
          text: err?.error?.detail ?? 'Could not apply that change.',
        });
        this.chatBusy = false;
        this.cdr.detectChanges();
      },
    });
  }

  undo() {
    if (!this.draft || !this.canUndo || this.chatBusy) return;
    this.chatBusy = true;
    this.svc.undo(this.draft.email_id).subscribe({
      next: (draft) => {
        this.draft = draft;
        this.canUndo = false;
        // Same reasoning as sendChat above — the draft body just changed.
        this.saveResult = null;
        this._pushMsg({ role: 'assistant', text: '↺ Reverted to the previous version.' });
        this.chatBusy = false;
        this.cdr.detectChanges();
      },
      error: () => {
        this.chatBusy = false;
        this.cdr.detectChanges();
      },
    });
  }

  get canSave(): boolean {
    return !!this.draft && !!this.draft.company_name.trim() && !this.isSaving;
  }

  save() {
    if (!this.draft || !this.canSave) return;
    this.isSaving = true;
    this.saveError = '';
    this.saveResult = null;
    this.cdr.detectChanges();

    this.svc
      .save(this.draft.email_id, this.draft.company_name, this.draft.role_title, this.sourceUrl)
      .subscribe({
        next: (result) => {
          this.saveResult = result;
          this.isSaving = false;
          this.cdr.detectChanges();
        },
        error: () => {
          this._showSaveError("Couldn't save — please try again.");
          this.isSaving = false;
          this.cdr.detectChanges();
        },
      });
  }

  /** Shows a friendly, transient notification — never the raw backend
   * error text — and auto-dismisses it so it reads as a toast, not a
   * blocking wall that discourages the next action (e.g. Send Email). */
  private _showSaveError(message: string) {
    this.saveError = message;
    if (this._saveErrorTimer) clearTimeout(this._saveErrorTimer);
    this._saveErrorTimer = setTimeout(() => {
      this.saveError = '';
      this.cdr.detectChanges();
    }, 4000);
  }

  private _showSendError(message: string) {
    this.sendError = message;
    if (this._sendErrorTimer) clearTimeout(this._sendErrorTimer);
    this._sendErrorTimer = setTimeout(() => {
      this.sendError = '';
      this.cdr.detectChanges();
    }, 4000);
  }

  get resumeLabel(): string {
    return this.resumesSvc.activeResume()?.label || 'resume';
  }

  get canSend(): boolean {
    return !!this.draft && EMAIL_PATTERN.test(this.sendTo.trim()) && !this.isSending;
  }

  openSendConfirm() {
    if (!this.canSend) return;
    this.showSendConfirm = true;
  }

  cancelSend() {
    this.showSendConfirm = false;
  }

  confirmSend() {
    if (!this.draft || !this.canSend) return;
    this.showSendConfirm = false;
    this.isSending = true;
    this.sendError = '';
    this.sendResult = null;
    this.cdr.detectChanges();

    this.svc.send(this.draft.email_id, this.sendTo.trim()).subscribe({
      next: (result) => {
        this.sendResult = result;
        this.isSending = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        this._showSendError(err?.error?.detail ?? 'Could not send this email.');
        this.isSending = false;
        this.cdr.detectChanges();
      },
    });
  }

  requestTailorResume() {
    if (!this.jobPost.trim()) return;
    this.tailorResume.emit(this.jobPost);
  }

  copied = false;
  private _copiedTimer: ReturnType<typeof setTimeout> | null = null;

  copyText() {
    if (!this.draft) return;
    const text = `To: ${this.draft.to}\nSubject: ${this.draft.subject}\n\n${this.draft.body}`;
    navigator.clipboard?.writeText(text).then(() => {
      this.copied = true;
      this.cdr.detectChanges();
      if (this._copiedTimer) clearTimeout(this._copiedTimer);
      this._copiedTimer = setTimeout(() => {
        this.copied = false;
        this.cdr.detectChanges();
      }, 1500);
    });
  }

  newEmail() {
    if (this.draft && !this.saveResult) {
      this._pendingAction = () => this._doNewEmail();
      this.showDiscardSaveConfirm = true;
      this.cdr.detectChanges();
      return;
    }
    this._doNewEmail();
  }

  private _doNewEmail() {
    this.jobPost = '';
    this.sourceUrl = '';
    this.instruction = 'Write a professional email to apply for this role, referencing my resume.';
    this.draft = null;
    this.chatMessages = [];
    this.chatInput = '';
    this.canUndo = false;
    this.isEditing = false;
    this.generateError = '';
    this.copied = false;
    this.saveResult = null;
    this.saveError = '';
    this.sendTo = '';
    this.sendResult = null;
    this.sendError = '';
    this.showSendConfirm = false;
    this.cdr.detectChanges();
  }

  get downloadUrl(): string | null {
    return this.draft ? this.svc.downloadUrl(this.draft.email_id) : null;
  }

  startEdit() {
    if (!this.draft) return;
    this.editTo = this.draft.to;
    this.editSubject = this.draft.subject;
    this.editBody = this.draft.body;
    this.isEditing = true;
  }

  cancelEdit() {
    this.isEditing = false;
  }

  get canSaveEdit(): boolean {
    return !!this.draft && this.editSubject.trim().length > 0 && !this.isSavingEdit;
  }

  saveEdit() {
    if (!this.draft || !this.canSaveEdit) return;
    this.isSavingEdit = true;
    this.svc.update(this.draft.email_id, this.editTo, this.editSubject, this.editBody).subscribe({
      next: (draft) => {
        this.draft = draft;
        this.canUndo = true;
        this.isEditing = false;
        // Manual edit — the draft body changed, same as sendChat/undo above.
        this.saveResult = null;
        this.isSavingEdit = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        this._pushMsg({
          role: 'error',
          text: err?.error?.detail ?? 'Could not save your edits.',
        });
        this.isSavingEdit = false;
        this.cdr.detectChanges();
      },
    });
  }

  private _pushMsg(msg: EmailChatMessage) {
    this.chatMessages.push(msg);
    setTimeout(() => {
      if (this.chatScrollEl) {
        const el = this.chatScrollEl.nativeElement;
        el.scrollTop = el.scrollHeight;
      }
    }, 0);
  }

  private _startTimer() {
    this.elapsedSeconds = 0;
    this._clearTimer();
    this._elapsedTimer = setInterval(() => {
      this.elapsedSeconds++;
      this.cdr.detectChanges();
    }, 1000);
  }

  private _clearTimer() {
    if (this._elapsedTimer !== null) {
      clearInterval(this._elapsedTimer);
      this._elapsedTimer = null;
    }
  }

  private _finish() {
    this.isGenerating = false;
    this._clearTimer();
    this.cdr.detectChanges();
  }
}
