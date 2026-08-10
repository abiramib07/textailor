import { Component, ChangeDetectorRef, effect, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { CareerService, PersonalInfoEntry } from '../career.service';
import { ResumesService } from '../../resumes/resumes.service';

const SUGGESTED_FIELDS: { key: string; label: string; multiline?: boolean }[] = [
  { key: 'full_name', label: 'Full Name' },
  { key: 'linkedin_url', label: 'LinkedIn URL' },
  { key: 'github_url', label: 'GitHub URL' },
  { key: 'portfolio_url', label: 'Portfolio URL' },
  { key: 'email', label: 'Email' },
  { key: 'phone', label: 'Phone' },
  { key: 'short_pitch', label: 'Short pitch / elevator summary', multiline: true },
  { key: 'written_bio', label: 'Written bio (LinkedIn About / cold outreach)', multiline: true },
  { key: 'project_pitches', label: 'Project talking points (STAR pitches)', multiline: true },
  { key: 'cover_letter_template', label: 'Cover letter template', multiline: true },
];

@Component({
  selector: 'app-personal-info',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './personal-info.html',
  styleUrl: './personal-info.scss',
})
export class PersonalInfoComponent {
  private svc = inject(CareerService);
  private cdr = inject(ChangeDetectorRef);
  private resumesSvc = inject(ResumesService);

  suggestedFields = SUGGESTED_FIELDS;
  values: Record<string, string> = {};
  copiedKey: string | null = null;
  saving: Record<string, boolean> = {};

  customEntries: PersonalInfoEntry[] = [];
  newFieldName = '';
  newFieldValue = '';

  constructor() {
    // Reload whenever the active resume identity changes (including the
    // initial load once resumesSvc has resolved which resume is active).
    effect(() => {
      this.resumesSvc.activeResumeId();
      this.load();
    });
  }

  load() {
    this.svc.getPersonalInfo().subscribe({
      next: ({ entries }) => {
        this.values = {};
        const suggestedKeys = new Set(this.suggestedFields.map((f) => f.key));
        this.customEntries = [];
        for (const e of entries) {
          this.values[e.key] = e.value;
          if (!suggestedKeys.has(e.key)) this.customEntries.push(e);
        }
        this.cdr.detectChanges();
      },
    });
  }

  save(key: string) {
    const value = (this.values[key] ?? '').trim();
    this.saving[key] = true;
    this.svc.setPersonalInfo(key, value).subscribe({
      next: () => {
        this.saving[key] = false;
        this.cdr.detectChanges();
      },
      error: () => {
        this.saving[key] = false;
        this.cdr.detectChanges();
      },
    });
  }

  copy(key: string) {
    const value = this.values[key] ?? '';
    if (!value) return;
    navigator.clipboard?.writeText(value).then(() => {
      this.copiedKey = key;
      this.cdr.detectChanges();
      setTimeout(() => {
        this.copiedKey = null;
        this.cdr.detectChanges();
      }, 1300);
    });
  }

  addCustomField() {
    const key = this.newFieldName.trim().toLowerCase().replace(/\s+/g, '_');
    const value = this.newFieldValue.trim();
    if (!key || !value) return;
    this.svc.setPersonalInfo(key, value).subscribe({
      next: () => {
        this.newFieldName = '';
        this.newFieldValue = '';
        this.load();
      },
    });
  }

  removeCustomField(key: string) {
    this.svc.deletePersonalInfo(key).subscribe({ next: () => this.load() });
  }
}
