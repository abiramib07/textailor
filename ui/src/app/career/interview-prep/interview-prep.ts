import { Component, ChangeDetectorRef, effect, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { CareerService, InterviewTopicEntry } from '../career.service';
import { ResumesService } from '../../resumes/resumes.service';

@Component({
  selector: 'app-interview-prep',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './interview-prep.html',
  styleUrl: './interview-prep.scss',
})
export class InterviewPrepComponent {
  private svc = inject(CareerService);
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

  constructor() {
    effect(() => {
      this.resumesSvc.activeResumeId();
      // A different resume identity has its own set of companies — the
      // previously selected one may not exist there.
      this.selectedCompany = '';
      this.topics = [];
      this.loadCompanies();
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

  selectCompany(company: string) {
    this.selectedCompany = company;
    this.loadTopics();
  }

  startNewCompany() {
    const name = this.newCompanyName.trim();
    if (!name) return;
    this.selectedCompany = name;
    this.newCompanyName = '';
    this.topics = [];
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
