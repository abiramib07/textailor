import { Component, ChangeDetectorRef, effect, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { CareerService, InterviewTopicEntry } from '../career.service';
import { ResumesService } from '../../resumes/resumes.service';
import { ResumeService, HistoryEntry } from '../../resume.service';

@Component({
  selector: 'app-interview-prep',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './interview-prep.html',
  styleUrl: './interview-prep.scss',
})
export class InterviewPrepComponent {
  private svc = inject(CareerService);
  private resumeSvc = inject(ResumeService);
  private cdr = inject(ChangeDetectorRef);
  private resumesSvc = inject(ResumesService);

  companies: string[] = [];
  selectedCompany = '';
  newCompanyName = '';
  topics: InterviewTopicEntry[] = [];
  loading = false;

  newTopic = '';
  newGithub = '';
  newYoutube = '';
  newNotes = '';
  adding = false;

  seedingSkills = false;
  seedSkillsMessage = '';

  /** Every saved resume snapshot for this identity — used to build the
   * "Resumes used" panel per company and to widen the sidebar's company
   * list beyond just `interview_topics` (a JD with zero extractable
   * keywords produces a history row but no checklist row, so relying on
   * `companies` alone would silently hide it). */
  historyEntries: HistoryEntry[] = [];
  expandedSnapshotId: string | null = null;
  copiedSnapshotId: string | null = null;
  private _copiedTimer: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    effect(() => {
      this.resumesSvc.activeResumeId();
      // A different resume identity has its own set of companies — the
      // previously selected one may not exist there.
      this.selectedCompany = '';
      this.topics = [];
      this.loadCompanies();
      this.loadHistory();
    });
  }

  loadCompanies() {
    this.svc.listInterviewCompanies().subscribe({
      next: ({ companies }) => {
        this.companies = companies;
        if (!this.selectedCompany && companies.length) {
          this.selectCompany(companies[0]);
        }
        this.cdr.detectChanges();
      },
    });
  }

  loadHistory() {
    this.resumeSvc.getHistory().subscribe({
      next: ({ entries }) => {
        this.historyEntries = entries;
        this.cdr.detectChanges();
      },
    });
  }

  /** `companies` (from interview_topics) unioned with every company name
   * that has a saved resume in history — `interview_topics` and
   * `resume_history` live in separate SQLite files, so this union happens
   * client-side rather than via a cross-database backend query. */
  get allCompanies(): string[] {
    const seen = new Map<string, string>();
    for (const c of this.companies) seen.set(c.toLowerCase(), c);
    for (const e of this.historyEntries) {
      const key = e.company_name.toLowerCase();
      if (!seen.has(key)) seen.set(key, e.company_name);
    }
    return [...seen.values()];
  }

  get resumesForSelectedCompany(): HistoryEntry[] {
    if (!this.selectedCompany) return [];
    const target = this.selectedCompany.toLowerCase();
    return this.historyEntries.filter((e) => e.company_name.toLowerCase() === target);
  }

  toggleSnapshot(entry: HistoryEntry) {
    this.expandedSnapshotId = this.expandedSnapshotId === entry.id ? null : entry.id;
  }

  copySnapshot(entry: HistoryEntry) {
    if (!entry.resume_snapshot) return;
    navigator.clipboard?.writeText(entry.resume_snapshot).then(() => {
      this.copiedSnapshotId = entry.id;
      this.cdr.detectChanges();
      if (this._copiedTimer) clearTimeout(this._copiedTimer);
      this._copiedTimer = setTimeout(() => {
        this.copiedSnapshotId = null;
        this.cdr.detectChanges();
      }, 1300);
    });
  }

  selectCompany(company: string) {
    this.selectedCompany = company;
    this.seedSkillsMessage = '';
    this.expandedSnapshotId = null;
    this.loadTopics();
  }

  startNewCompany() {
    const name = this.newCompanyName.trim();
    if (!name) return;
    this.selectedCompany = name;
    this.newCompanyName = '';
    this.topics = [];
    this.seedSkillsMessage = '';
    this.cdr.detectChanges();
  }

  loadTopics() {
    if (!this.selectedCompany) return;
    this.loading = true;
    this.svc.listInterviewTopics(this.selectedCompany).subscribe({
      next: ({ entries }) => {
        this.topics = entries;
        this.loading = false;
        this.cdr.detectChanges();
      },
      error: () => {
        this.loading = false;
        this.cdr.detectChanges();
      },
    });
  }

  get coveredCount(): number {
    return this.topics.filter((t) => t.covered).length;
  }

  addTopic() {
    if (!this.selectedCompany || !this.newTopic.trim() || this.adding) return;
    this.adding = true;
    this.svc
      .createInterviewTopic(this.selectedCompany, this.newTopic.trim(), this.newGithub.trim(), this.newYoutube.trim(), this.newNotes.trim())
      .subscribe({
        next: () => {
          this.newTopic = '';
          this.newGithub = '';
          this.newYoutube = '';
          this.newNotes = '';
          this.adding = false;
          this.loadTopics();
          this.loadCompanies();
        },
        error: () => {
          this.adding = false;
          this.cdr.detectChanges();
        },
      });
  }

  seedFromSkills() {
    if (!this.selectedCompany || this.seedingSkills) return;
    this.seedingSkills = true;
    this.seedSkillsMessage = '';
    this.svc.seedInterviewTopicsFromSkills(this.selectedCompany).subscribe({
      next: ({ added }) => {
        this.seedingSkills = false;
        this.seedSkillsMessage = added.length
          ? `Added ${added.length} skill${added.length === 1 ? '' : 's'} as topics.`
          : 'Every resume skill is already on this checklist.';
        this.loadTopics();
        this.loadCompanies();
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.seedingSkills = false;
        this.seedSkillsMessage = err?.error?.detail ?? 'Could not seed topics from your skills.';
        this.cdr.detectChanges();
      },
    });
  }

  toggleCovered(topic: InterviewTopicEntry) {
    this.svc.updateInterviewTopic(topic.id, { covered: !topic.covered }).subscribe({
      next: () => this.loadTopics(),
    });
  }

  removeTopic(topic: InterviewTopicEntry) {
    this.svc.deleteInterviewTopic(topic.id).subscribe({
      next: () => {
        this.loadTopics();
        this.loadCompanies();
      },
    });
  }
}
