import { Component, ChangeDetectorRef, effect, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { CareerService, JobPostEntry, AttachmentEntry } from '../career.service';
import { ResumesService } from '../../resumes/resumes.service';

@Component({
  selector: 'app-post-archive',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './post-archive.html',
  styleUrl: './post-archive.scss',
})
export class PostArchiveComponent {
  private svc = inject(CareerService);
  private cdr = inject(ChangeDetectorRef);
  private resumesSvc = inject(ResumesService);

  posts: JobPostEntry[] = [];
  loading = true;
  attachmentsByPost: Record<string, AttachmentEntry[]> = {};
  pasteStatus: Record<string, string> = {};

  showAddForm = false;
  newUrl = '';
  newCompany = '';
  newRole = '';
  newText = '';
  adding = false;

  constructor() {
    effect(() => {
      this.resumesSvc.activeResumeId();
      this.load();
    });
  }

  load() {
    this.loading = true;
    this.svc.listJobPosts().subscribe({
      next: ({ entries }) => {
        this.posts = entries;
        this.loading = false;
        for (const p of entries) {
          this.attachmentsByPost[p.id] ??= [];
          this._loadAttachments(p.id);
        }
        this.cdr.detectChanges();
      },
      error: () => {
        this.loading = false;
        this.cdr.detectChanges();
      },
    });
  }

  private _loadAttachments(postId: string) {
    this.svc.listAttachments(postId).subscribe({
      next: ({ entries }) => {
        this.attachmentsByPost[postId] = entries;
        this.cdr.detectChanges();
      },
    });
  }

  toggleAddForm() {
    this.showAddForm = !this.showAddForm;
  }

  addPost() {
    if ((!this.newUrl.trim() && !this.newText.trim()) || this.adding) return;
    this.adding = true;
    this.svc.createJobPost(this.newUrl.trim(), this.newCompany.trim(), this.newRole.trim(), this.newText.trim()).subscribe({
      next: () => {
        this.newUrl = '';
        this.newCompany = '';
        this.newRole = '';
        this.newText = '';
        this.adding = false;
        this.showAddForm = false;
        this.load();
      },
      error: () => {
        this.adding = false;
        this.cdr.detectChanges();
      },
    });
  }

  removePost(post: JobPostEntry) {
    this.svc.deleteJobPost(post.id).subscribe({ next: () => this.load() });
  }

  onPaste(event: ClipboardEvent, postId: string) {
    const items = event.clipboardData?.items;
    if (!items) return;
    for (const item of Array.from(items)) {
      if (item.type.startsWith('image/')) {
        event.preventDefault();
        const blob = item.getAsFile();
        if (!blob) continue;
        this.pasteStatus[postId] = 'Uploading…';
        this.cdr.detectChanges();
        this.svc.uploadAttachment(postId, blob, `pasted-${Date.now()}.png`).subscribe({
          next: () => {
            this.pasteStatus[postId] = '✓ Screenshot saved';
            this._loadAttachments(postId);
            setTimeout(() => {
              this.pasteStatus[postId] = '';
              this.cdr.detectChanges();
            }, 2000);
          },
          error: () => {
            this.pasteStatus[postId] = 'Upload failed — try again';
            this.cdr.detectChanges();
          },
        });
        return;
      }
    }
    this.pasteStatus[postId] = 'No image found in clipboard';
    this.cdr.detectChanges();
    setTimeout(() => {
      this.pasteStatus[postId] = '';
      this.cdr.detectChanges();
    }, 2000);
  }

  attachmentUrl(postId: string, attachmentId: string): string {
    return this.svc.attachmentUrl(postId, attachmentId);
  }

  removeAttachment(postId: string, attachmentId: string) {
    this.svc.deleteAttachment(postId, attachmentId).subscribe({
      next: () => this._loadAttachments(postId),
    });
  }
}
