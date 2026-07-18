import {
  Component,
  ChangeDetectorRef,
  OnDestroy,
  ViewChild,
  ElementRef,
  inject,
} from '@angular/core';

import { FormsModule } from '@angular/forms';
import { EmailService, EmailDraft } from './email.service';

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

  jobPost = '';
  sourceUrl = '';
  instruction = 'Write a professional email to apply for this role, referencing my resume.';

  isGenerating = false;
  elapsedSeconds = 0;
  generateError = '';

  draft: EmailDraft | null = null;
  lastGeneratedSeconds = 0;

  quickSuggests = QUICK_SUGGESTS;
  chatMessages: EmailChatMessage[] = [];
  chatInput = '';
  chatBusy = false;
  canUndo = false;

  @ViewChild('chatScroll') chatScrollEl!: ElementRef;
  private _elapsedTimer: ReturnType<typeof setInterval> | null = null;

  ngOnDestroy() {
    this._clearTimer();
    if (this._copiedTimer) clearTimeout(this._copiedTimer);
  }

  get canGenerate(): boolean {
    return this.jobPost.trim().length > 0 && !this.isGenerating;
  }

  generate() {
    if (!this.canGenerate) return;
    this.isGenerating = true;
    this.generateError = '';
    this.draft = null;
    this.chatMessages = [];
    this.canUndo = false;
    this._startTimer();
    this.cdr.detectChanges();

    this.svc.generate(this.jobPost, this.instruction).subscribe({
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
        };
        this.canUndo = true;
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
    this.jobPost = '';
    this.sourceUrl = '';
    this.instruction = 'Write a professional email to apply for this role, referencing my resume.';
    this.draft = null;
    this.chatMessages = [];
    this.chatInput = '';
    this.canUndo = false;
    this.generateError = '';
    this.copied = false;
    this.cdr.detectChanges();
  }

  get downloadUrl(): string | null {
    return this.draft ? this.svc.downloadUrl(this.draft.email_id) : null;
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
