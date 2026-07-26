import { Component, ChangeDetectorRef, OnDestroy, computed, effect, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  ApplyLaterEntry,
  ApplyLaterReferral,
  ApplyLaterStatus,
  CareerService,
} from '../career.service';
import { ResumesService } from '../../resumes/resumes.service';

/** Every status in the application pipeline, in the order they're expected to progress. */
export const STATUS_OPTIONS: ApplyLaterStatus[] = [
  'Not Applied',
  'Applied',
  'OA-Screening',
  'Interview Scheduled',
  'Interview Completed',
  'Offer',
  'Rejected',
  'On Hold',
];

export const REFERRAL_OPTIONS: ApplyLaterReferral[] = ['Yes', 'No', 'Pending'];

/** One tier's row in the dashboard's per-tier breakdown. */
interface TierStat {
  tier: string;
  total: number;
  applied: number;
}

const NO_TIER_LABEL = 'No tier';
const IN_PROGRESS_STATUSES: ApplyLaterStatus[] = [
  'OA-Screening',
  'Interview Scheduled',
  'Interview Completed',
];

/**
 * Job application tracker: company/role/status pipeline with a live
 * dashboard, replacing the earlier plain "save a URL for later" list.
 */
@Component({
  selector: 'app-apply-later',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './apply-later.html',
  styleUrl: './apply-later.scss',
})
export class ApplyLaterComponent implements OnDestroy {
  private svc = inject(CareerService);
  private cdr = inject(ChangeDetectorRef);
  private resumesSvc = inject(ResumesService);

  readonly statusOptions = STATUS_OPTIONS;
  readonly referralOptions = REFERRAL_OPTIONS;

  entries = signal<ApplyLaterEntry[]>([]);
  loading = true;

  // ── Resume skills reference panel — quick lookup while tracking/noting
  // applications, no per-job skill matching (no reliable JD data source
  // for every row, e.g. manually-added or web-search-found postings).
  skills = signal<string[]>([]);
  skillsPanelOpen = signal(false);

  newUrl = '';
  newCompany = '';
  newRoleTitle = '';
  newTier = '';
  newNotes = '';
  adding = false;

  // ── Find Jobs — web search, backed by the job_finder agent ────────
  searchQuery = 'GenAI RAG LangGraph AI/ML engineer';
  searchYears = 3;
  searchLocation = 'India';
  searchCount = 15;
  searchMinSalaryLpa: number | null = null;
  searching = false;
  searchTrace: string[] = [];
  searchNote = '';
  searchError = '';
  private pollHandle: ReturnType<typeof setInterval> | null = null;

  constructor() {
    effect(() => {
      this.resumesSvc.activeResumeId();
      this.load();
      this.loadSkills();
    });
  }

  loadSkills() {
    this.svc.getResumeSkills().subscribe({
      next: ({ skills }) => {
        this.skills.set(skills);
        this.cdr.detectChanges();
      },
    });
  }

  toggleSkillsPanel() {
    this.skillsPanelOpen.update((open) => !open);
  }

  ngOnDestroy(): void {
    this._stopPolling();
  }

  // ── Dashboard — computed live off `entries`, never stale ──────────
  readonly total = computed(() => this.entries().length);
  readonly notAppliedCount = computed(
    () => this.entries().filter((e) => e.status === 'Not Applied').length,
  );
  readonly appliedCount = computed(
    () => this.entries().filter((e) => e.status !== 'Not Applied').length,
  );
  readonly inProgressCount = computed(
    () => this.entries().filter((e) => IN_PROGRESS_STATUSES.includes(e.status)).length,
  );
  readonly offerCount = computed(
    () => this.entries().filter((e) => e.status === 'Offer').length,
  );
  readonly rejectedCount = computed(
    () => this.entries().filter((e) => e.status === 'Rejected').length,
  );
  readonly onHoldCount = computed(
    () => this.entries().filter((e) => e.status === 'On Hold').length,
  );

  readonly tierBreakdown = computed<TierStat[]>(() => {
    const byTier = new Map<string, TierStat>();
    for (const e of this.entries()) {
      const tier = (e.tier || '').trim() || NO_TIER_LABEL;
      const stat = byTier.get(tier) ?? { tier, total: 0, applied: 0 };
      stat.total++;
      if (e.status !== 'Not Applied') stat.applied++;
      byTier.set(tier, stat);
    }
    return [...byTier.values()].sort((a, b) => a.tier.localeCompare(b.tier));
  });

  readonly groupedEntries = computed(() => {
    const byTier = new Map<string, ApplyLaterEntry[]>();
    for (const e of this.entries()) {
      const tier = (e.tier || '').trim() || NO_TIER_LABEL;
      const list = byTier.get(tier) ?? [];
      list.push(e);
      byTier.set(tier, list);
    }
    return [...byTier.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([tier, items]) => ({
        tier,
        items: items.sort((a, b) => b.created_at - a.created_at),
      }));
  });

  load() {
    this.loading = true;
    this.svc.listApplyLater().subscribe({
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
    if (!this.newUrl.trim() || this.adding) return;
    this.adding = true;
    this.svc
      .createApplyLater(
        this.newUrl.trim(),
        this.newCompany.trim(),
        this.newNotes.trim(),
        this.newTier.trim(),
        this.newRoleTitle.trim(),
      )
      .subscribe({
        next: () => {
          this.newUrl = '';
          this.newCompany = '';
          this.newRoleTitle = '';
          this.newTier = '';
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

  searchJobs() {
    if (!this.searchQuery.trim() || this.searching) return;
    this.searching = true;
    this.searchTrace = [];
    this.searchNote = '';
    this.searchError = '';
    this.cdr.detectChanges();

    this.svc
      .startApplyLaterSearch(
        this.searchQuery.trim(),
        this.searchYears,
        this.searchLocation.trim(),
        this.searchCount,
        this.searchMinSalaryLpa,
      )
      .subscribe({
        next: ({ task_id }) => this._pollSearch(task_id),
        error: (err) => {
          this.searching = false;
          this.searchError = err?.error?.detail ?? 'Could not start job search. Please try again.';
          this.cdr.detectChanges();
        },
      });
  }

  private _pollSearch(taskId: string) {
    this.pollHandle = setInterval(() => {
      this.svc.pollApplyLaterSearch(taskId).subscribe({
        next: ({ status, trace, search_note, error }) => {
          this.searchTrace = trace;
          if (status === 'running') {
            this.cdr.detectChanges();
            return;
          }
          this._stopPolling();
          this.searching = false;
          if (status === 'done') {
            this.searchNote = search_note;
            this.load();
          } else {
            this.searchError = error ?? 'Job search failed. Please try again.';
            this.cdr.detectChanges();
          }
        },
        error: () => {
          this._stopPolling();
          this.searching = false;
          this.searchError = 'Lost connection to the search task. Please try again.';
          this.cdr.detectChanges();
        },
      });
    }, 1800);
  }

  private _stopPolling() {
    if (this.pollHandle !== null) {
      clearInterval(this.pollHandle);
      this.pollHandle = null;
    }
  }

  updateStatus(entry: ApplyLaterEntry, status: ApplyLaterStatus) {
    this.svc.updateApplyLater(entry.id, { status }).subscribe({ next: () => this.load() });
  }

  updateReferral(entry: ApplyLaterEntry, referral: ApplyLaterReferral) {
    this.svc.updateApplyLater(entry.id, { referral }).subscribe({ next: () => this.load() });
  }

  updateField(
    entry: ApplyLaterEntry,
    field: 'tier' | 'role_title' | 'date_applied' | 'next_follow_up' | 'interview_round' | 'salary_discussed' | 'notes',
    value: string,
  ) {
    this.svc.updateApplyLater(entry.id, { [field]: value }).subscribe({ next: () => this.load() });
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
