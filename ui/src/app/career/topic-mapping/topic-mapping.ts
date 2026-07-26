import { Component, ChangeDetectorRef, effect, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CareerService, TopicMapEntry } from '../career.service';
import { ResumesService } from '../../resumes/resumes.service';

@Component({
  selector: 'app-topic-mapping',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './topic-mapping.html',
  styleUrl: './topic-mapping.scss',
})
export class TopicMappingComponent {
  private svc = inject(CareerService);
  private cdr = inject(ChangeDetectorRef);
  private resumesSvc = inject(ResumesService);

  buckets: string[] = [];
  selectedBucket = '';
  entries: TopicMapEntry[] = [];
  loading = true;

  constructor() {
    effect(() => {
      this.resumesSvc.activeResumeId();
      this.selectedBucket = '';
      this.svc.getYearsBuckets().subscribe({
        next: ({ buckets }) => {
          this.buckets = buckets;
          this.cdr.detectChanges();
        },
      });
      this.load();
    });
  }

  selectBucket(bucket: string) {
    this.selectedBucket = bucket;
    this.load();
  }

  load() {
    this.loading = true;
    this.svc.getTopicMap(this.selectedBucket || undefined).subscribe({
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

  get maxFrequency(): number {
    return this.entries.length ? Math.max(...this.entries.map((e) => e.frequency)) : 1;
  }

  barWidth(frequency: number): number {
    return Math.round((frequency / this.maxFrequency) * 100);
  }

  get coveredCount(): number {
    return this.entries.filter((e) => e.covered).length;
  }

  get requiredEntries(): TopicMapEntry[] {
    return this.entries.filter((e) => e.category === 'required');
  }

  get preferredEntries(): TopicMapEntry[] {
    return this.entries.filter((e) => e.category === 'preferred');
  }
}
