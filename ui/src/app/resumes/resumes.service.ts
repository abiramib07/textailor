import { Injectable, inject, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap } from 'rxjs';

const API = 'http://localhost:8000/api/resumes';
const ACTIVE_RESUME_STORAGE_KEY = 'textailor_active_resume_id';

export interface ResumeIdentity {
  id: string;
  label: string;
  owner_name: string;
  tex_path: string;
  is_default: number;
  created_at: number;
}

export interface ResumeImportResult {
  resume: ResumeIdentity;
  has_pdf: boolean;
  compile_warning: string | null;
}

/**
 * Tracks every resume identity (yours, or someone else's) and which one is
 * currently active. Other services read `activeResumeId()` directly so the
 * rest of the app doesn't have to thread a resume id through every call.
 */
@Injectable({ providedIn: 'root' })
export class ResumesService {
  private http = inject(HttpClient);
  private opts = { withCredentials: true };

  readonly resumes = signal<ResumeIdentity[]>([]);
  readonly activeResumeId = signal<string | null>(
    localStorage.getItem(ACTIVE_RESUME_STORAGE_KEY),
  );
  readonly activeResume = computed(
    () => this.resumes().find((r) => r.id === this.activeResumeId()) ?? null,
  );

  /** Load every resume identity, defaulting the active one if it's unset or stale. */
  list(): Observable<{ entries: ResumeIdentity[] }> {
    return this.http.get<{ entries: ResumeIdentity[] }>(API, this.opts).pipe(
      tap(({ entries }) => {
        this.resumes.set(entries);
        const stillValid = entries.some((r) => r.id === this.activeResumeId());
        if (!stillValid) {
          const fallback = entries.find((r) => r.is_default) ?? entries[0];
          if (fallback) this.setActive(fallback.id);
        }
      }),
    );
  }

  /** Add a new resume identity from an uploaded resume file (.tex, .pdf, .docx,
   * .txt, or .md) and make it active immediately. */
  create(label: string, ownerName: string, file: File): Observable<ResumeImportResult> {
    return this._upload(label, ownerName, file).pipe(
      tap((result) => this.setActive(result.resume.id)),
    );
  }

  /** Import a resume file for chat curation (see the Import Resume tab)
   * without making it the app-wide active resume yet — that happens once
   * the user finishes curating and explicitly saves it. */
  importForCuration(label: string, ownerName: string, file: File): Observable<ResumeImportResult> {
    return this._upload(label, ownerName, file);
  }

  private _upload(label: string, ownerName: string, file: File): Observable<ResumeImportResult> {
    const form = new FormData();
    form.append('label', label);
    form.append('owner_name', ownerName);
    form.append('file', file, file.name);
    return this.http.post<ResumeImportResult>(API, form, this.opts).pipe(
      tap(({ resume }) => {
        this.resumes.set([...this.resumes(), resume]);
      }),
    );
  }

  /** Rename a resume identity or update its owner name. */
  rename(id: string, label?: string, ownerName?: string): Observable<{ resume: ResumeIdentity }> {
    return this.http
      .patch<{ resume: ResumeIdentity }>(
        `${API}/${id}`,
        { label, owner_name: ownerName },
        this.opts,
      )
      .pipe(
        tap(({ resume }) => {
          this.resumes.set(this.resumes().map((r) => (r.id === id ? resume : r)));
        }),
      );
  }

  /** Delete a non-default resume identity and its files. */
  remove(id: string): Observable<{ ok: boolean }> {
    return this.http.delete<{ ok: boolean }>(`${API}/${id}`, this.opts).pipe(
      tap(() => {
        this.resumes.set(this.resumes().filter((r) => r.id !== id));
        if (this.activeResumeId() === id) {
          const fallback = this.resumes().find((r) => r.is_default) ?? this.resumes()[0];
          if (fallback) this.setActive(fallback.id);
        }
      }),
    );
  }

  /** Switch the app's active resume identity, persisted across reloads. */
  setActive(id: string): void {
    this.activeResumeId.set(id);
    localStorage.setItem(ACTIVE_RESUME_STORAGE_KEY, id);
  }
}
