import { Component, ChangeDetectorRef, OnDestroy, effect, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { CredentialEntry, JobCredentialsService } from './job-credentials.service';
import { ResumesService } from '../../resumes/resumes.service';

/** How long a revealed password stays visible before auto re-masking. */
const REVEAL_TIMEOUT_MS = 10_000;

/**
 * Job-site account credentials: encrypted email/password per company
 * account, scoped to the active resume identity. Passwords are never
 * fetched as part of the list — only decrypted on an explicit "Show".
 */
@Component({
  selector: 'app-job-credentials',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './job-credentials.html',
  styleUrl: './job-credentials.scss',
})
export class JobCredentialsComponent implements OnDestroy {
  private svc = inject(JobCredentialsService);
  private cdr = inject(ChangeDetectorRef);
  private resumesSvc = inject(ResumesService);

  entries = signal<CredentialEntry[]>([]);
  loading = true;

  newCompany = '';
  newSiteUrl = '';
  newEmail = '';
  newUsername = '';
  newPassword = '';
  newNotes = '';
  adding = false;
  addError = '';

  // ── Reveal-on-demand — never fetched eagerly, auto re-masks ────────
  revealedPasswords: Record<string, string | undefined> = {};
  revealingId: string | null = null;
  copiedId: string | null = null;
  private revealTimers: Record<string, ReturnType<typeof setTimeout>> = {};

  // ── Inline password change — explicit Save, not live-bound like the
  // other text fields, so a new password isn't sent on every keystroke ──
  editingPasswordId: string | null = null;
  editPasswordValue = '';
  savingPassword = false;

  confirmingDeleteId: string | null = null;

  constructor() {
    effect(() => {
      this.resumesSvc.activeResumeId();
      this.load();
    });
  }

  ngOnDestroy(): void {
    for (const timer of Object.values(this.revealTimers)) clearTimeout(timer);
  }

  load() {
    this.loading = true;
    this.svc.list().subscribe({
      next: ({ entries }) => {
        this.entries.set(entries);
        this.loading = false;
        this.cdr.detectChanges();
      },
      error: () => {
        this.loading = false;
        this.cdr.detectChanges();
      },
    });
  }

  add() {
    if (!this.newCompany.trim() || !this.newEmail.trim() || !this.newPassword || this.adding) {
      return;
    }
    this.adding = true;
    this.addError = '';
    this.svc
      .create({
        company_name: this.newCompany.trim(),
        site_url: this.newSiteUrl.trim(),
        login_email: this.newEmail.trim(),
        username: this.newUsername.trim(),
        password: this.newPassword,
        notes: this.newNotes.trim(),
      })
      .subscribe({
        next: () => {
          this.newCompany = '';
          this.newSiteUrl = '';
          this.newEmail = '';
          this.newUsername = '';
          this.newPassword = '';
          this.newNotes = '';
          this.adding = false;
          this.load();
        },
        error: (err) => {
          this.adding = false;
          this.addError = err?.error?.detail ?? 'Could not save this credential. Please try again.';
          this.cdr.detectChanges();
        },
      });
  }

  updateField(
    entry: CredentialEntry,
    field: 'company_name' | 'site_url' | 'login_email' | 'username' | 'notes',
    value: string,
  ) {
    this.svc.update(entry.id, { [field]: value }).subscribe({ next: () => this.load() });
  }

  remove(entry: CredentialEntry) {
    this.confirmingDeleteId = null;
    this.svc.delete(entry.id).subscribe({ next: () => this.load() });
  }

  toggleReveal(entry: CredentialEntry) {
    if (this.revealedPasswords[entry.id] !== undefined) {
      this._hide(entry.id);
      return;
    }
    this.revealingId = entry.id;
    this.svc.reveal(entry.id).subscribe({
      next: ({ password }) => {
        this.revealingId = null;
        this.revealedPasswords = { ...this.revealedPasswords, [entry.id]: password };
        this.cdr.detectChanges();
        this.revealTimers[entry.id] = setTimeout(() => {
          this._hide(entry.id);
          this.cdr.detectChanges();
        }, REVEAL_TIMEOUT_MS);
      },
      error: () => {
        this.revealingId = null;
        this.cdr.detectChanges();
      },
    });
  }

  private _hide(id: string) {
    const rest = { ...this.revealedPasswords };
    delete rest[id];
    this.revealedPasswords = rest;
    clearTimeout(this.revealTimers[id]);
    delete this.revealTimers[id];
  }

  copy(text: string, id: string) {
    if (!text) return;
    navigator.clipboard?.writeText(text).then(() => {
      this.copiedId = id;
      this.cdr.detectChanges();
      setTimeout(() => {
        this.copiedId = null;
        this.cdr.detectChanges();
      }, 1300);
    });
  }

  copyPassword(entry: CredentialEntry) {
    const revealed = this.revealedPasswords[entry.id];
    if (revealed !== undefined) {
      this.copy(revealed, entry.id);
      return;
    }
    this.svc.reveal(entry.id).subscribe({ next: ({ password }) => this.copy(password, entry.id) });
  }

  startEditPassword(entry: CredentialEntry) {
    this.editingPasswordId = entry.id;
    this.editPasswordValue = '';
  }

  cancelEditPassword() {
    this.editingPasswordId = null;
    this.editPasswordValue = '';
  }

  savePassword(entry: CredentialEntry) {
    if (!this.editPasswordValue || this.savingPassword) return;
    this.savingPassword = true;
    this.svc.update(entry.id, { password: this.editPasswordValue }).subscribe({
      next: () => {
        this.savingPassword = false;
        this.editingPasswordId = null;
        this.editPasswordValue = '';
        this._hide(entry.id);
        this.load();
      },
      error: () => {
        this.savingPassword = false;
        this.cdr.detectChanges();
      },
    });
  }

  hostname(url: string): string {
    if (!url) return '';
    try {
      return new URL(url).hostname.replace(/^www\./, '');
    } catch {
      return url;
    }
  }
}
