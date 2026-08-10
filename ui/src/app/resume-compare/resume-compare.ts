import { ChangeDetectorRef, Component, EventEmitter, Input, Output, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { diffWords, type Change } from 'diff';
import { ResumeService } from '../resume.service';

/** Side-by-side diff of a task's pristine base resume vs. its current
 * tailored output, word-highlighted like diffchecker.com. Opened as a modal
 * from the Generator tab once a task has a report; fetches fresh on every
 * open since the "tailored" side can change between Weave-in clicks. */
@Component({
  selector: 'app-resume-compare',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './resume-compare.html',
  styleUrl: './resume-compare.scss',
})
export class ResumeCompareComponent {
  private svc = inject(ResumeService);
  private cdr = inject(ChangeDetectorRef);

  @Input() taskId: string | null = null;

  @Input()
  set open(value: boolean) {
    this._open = value;
    if (value) this._load();
  }
  get open(): boolean {
    return this._open;
  }

  @Output() closed = new EventEmitter<void>();

  private _open = false;
  loading = false;
  error = '';
  diffParts: Change[] = [];

  close() {
    this._open = false;
    this.closed.emit();
  }

  private _load() {
    this.diffParts = [];
    this.error = '';
    if (!this.taskId) {
      this.error = 'No active resume to compare yet — generate one first.';
      return;
    }
    this.loading = true;
    this.svc.compareTask(this.taskId).subscribe({
      next: (result) => {
        this.diffParts = diffWords(result.original, result.tailored);
        this.loading = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.error = err?.error?.detail ?? 'Could not load the comparison.';
        this.loading = false;
        this.cdr.detectChanges();
      },
    });
  }
}
