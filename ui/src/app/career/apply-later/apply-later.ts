import { Component, ChangeDetectorRef, effect, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { CareerService, ApplyLaterEntry } from '../career.service';
import { ResumesService } from '../../resumes/resumes.service';

@Component({
  selector: 'app-apply-later',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './apply-later.html',
  styleUrl: './apply-later.scss',
})
export class ApplyLaterComponent {
  private svc = inject(CareerService);
  private cdr = inject(ChangeDetectorRef);
  private resumesSvc = inject(ResumesService);

  entries: ApplyLaterEntry[] = [];
  loading = true;

  newUrl = '';
  newCompany = '';
  newNotes = '';
  adding = false;

  constructor() {
    effect(() => {
      this.resumesSvc.activeResumeId();
      this.load();
    });
  }

  load() {
    this.loading = true;
    this.svc.listApplyLater().subscribe({
      next: ({ entries }) => {
        this.entries = entries;
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
    if (!this.newUrl.trim() || this.adding) return;
    this.adding = true;
    this.svc.createApplyLater(this.newUrl.trim(), this.newCompany.trim(), this.newNotes.trim()).subscribe({
      next: () => {
        this.newUrl = '';
        this.newCompany = '';
        this.newNotes = '';
        this.adding = false;
        this.load();
      },
      error: () => {
        this.adding = false;
        this.cdr.detectChanges();
      },
    });
  }

  toggleApplied(entry: ApplyLaterEntry) {
    this.svc.updateApplyLater(entry.id, !entry.applied).subscribe({ next: () => this.load() });
  }

  remove(entry: ApplyLaterEntry) {
    this.svc.deleteApplyLater(entry.id).subscribe({ next: () => this.load() });
  }

  hostname(url: string): string {
    try {
      return new URL(url).hostname.replace(/^www\./, '');
    } catch {
      return url;
    }
  }
}
