import {
  Component,
  OnDestroy,
  OnInit,
  ChangeDetectorRef,
  ViewChild,
  ElementRef,
  HostListener,
  inject,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import {
  ResumeService,
  TaskStatus,
  PipelineStep,
  ScoreReport,
  HistoryEntry,
  VerifierResult,
  VerifierKeyword,
  ExplainResult,
  PitchResult,
} from './resume.service';
import { AuthService, UserProfile } from './auth/auth.service';
import { CareerService } from './career/career.service';
import { EmailGeneratorComponent } from './email-generator/email-generator';
import { ResumeImportComponent } from './resume-import/resume-import';
import { PersonalInfoComponent } from './career/personal-info/personal-info';
import { ApplyLaterComponent } from './career/apply-later/apply-later';
import { PostArchiveComponent } from './career/post-archive/post-archive';
import { InterviewPrepComponent } from './career/interview-prep/interview-prep';
import { TopicMappingComponent } from './career/topic-mapping/topic-mapping';
import { JobCredentialsComponent } from './career/job-credentials/job-credentials';
import { ResumesService, ResumeIdentity } from './resumes/resumes.service';
import { ResumeCompareComponent } from './resume-compare/resume-compare';

const STEP_NAMES = [
  'Parse resume',
  'Analyse job description',
  'Rewrite sections',
  'Compile PDF',
  'Score ATS match',
];

function pendingSteps(): PipelineStep[] {
  return STEP_NAMES.map((name) => ({ name, status: 'pending', detail: '', elapsed: null }));
}

export interface ChatMessage {
  role: 'user' | 'plan' | 'bot' | 'error';
  text: string;
  planId?: string;
  changesPreview?: string[];
  /** Shows a "Recheck ATS Score" action under this message — set on a
   * successful edit/undo while a Generator task is active, since the edit
   * patches the resume directly and the displayed score card goes stale. */
  canRescore?: boolean;
}

type Tab =
  | 'generate'
  | 'edit-resume'
  | 'import-resume'
  | 'email-generator'
  | 'personal-info'
  | 'apply-later'
  | 'post-archive'
  | 'interview-prep'
  | 'topic-mapping'
  | 'job-credentials';
type EditorState =
  | 'idle'
  | 'loading'
  | 'editing'
  | 'saving'
  | 'saved'
  | 'syncing'
  | 'synced'
  | 'error';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterLink,
    EmailGeneratorComponent,
    ResumeImportComponent,
    PersonalInfoComponent,
    ApplyLaterComponent,
    PostArchiveComponent,
    InterviewPrepComponent,
    TopicMappingComponent,
    JobCredentialsComponent,
    ResumeCompareComponent,
  ],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnInit, OnDestroy {
  private svc = inject(ResumeService);
  private sanitizer = inject(DomSanitizer);
  private cdr = inject(ChangeDetectorRef);
  private authSvc = inject(AuthService);
  private router = inject(Router);
  private resumesSvc = inject(ResumesService);
  private careerSvc = inject(CareerService);

  // ── Auth (session, if any) ──────────────────────────────────────
  authUser: UserProfile | null = null;
  authChecked = false;

  // ── Generator layout — resizable/collapsible panels ──────────────
  // JD panel (left) — collapse to a thin strip, or drag the splitter to
  // resize, so the resume preview can take the width it needs.
  inputPanelCollapsed = false;
  inputPanelWidth = 380;
  private static readonly INPUT_PANEL_MIN = 260;
  private static readonly INPUT_PANEL_MAX = 900;
  private _resizingInput = false;
  private _inputResizeStartX = 0;
  private _inputResizeStartWidth = 0;

  // Chat panel (bottom of the right column) — collapse it, or drag the
  // splitter above it, so the PDF preview above gets the height it needs.
  chatPanelCollapsed = false;
  chatPanelHeight = 260;
  private static readonly CHAT_PANEL_MIN = 120;
  private static readonly CHAT_PANEL_MAX = 640;
  private _resizingChat = false;
  private _chatResizeStartY = 0;
  private _chatResizeStartHeight = 0;

  toggleInputPanel() {
    this.inputPanelCollapsed = !this.inputPanelCollapsed;
  }

  toggleChatPanel() {
    this.chatPanelCollapsed = !this.chatPanelCollapsed;
  }

  /** True while either splitter is being dragged — used to disable pointer
   * events on the PDF iframe(s) mid-drag. Without this, the moment the
   * cursor crosses over an iframe (which sits right next to both handles),
   * the parent window stops receiving mousemove — the iframe has its own
   * document and swallows the event — and the drag appears to just stop
   * responding partway through. */
  get isResizingLayout(): boolean {
    return this._resizingInput || this._resizingChat;
  }

  startInputResize(event: MouseEvent) {
    if (this.inputPanelCollapsed) return;
    this._resizingInput = true;
    this._inputResizeStartX = event.clientX;
    this._inputResizeStartWidth = this.inputPanelWidth;
    event.preventDefault();
    this.cdr.detectChanges();
  }

  startChatResize(event: MouseEvent) {
    if (this.chatPanelCollapsed) return;
    this._resizingChat = true;
    this._chatResizeStartY = event.clientY;
    this._chatResizeStartHeight = this.chatPanelHeight;
    event.preventDefault();
    this.cdr.detectChanges();
  }

  @HostListener('window:mousemove', ['$event'])
  onLayoutResizeMove(event: MouseEvent) {
    if (this._resizingInput) {
      const delta = event.clientX - this._inputResizeStartX;
      const next = this._inputResizeStartWidth + delta;
      this.inputPanelWidth = Math.min(
        App.INPUT_PANEL_MAX,
        Math.max(App.INPUT_PANEL_MIN, next),
      );
      this.cdr.detectChanges();
    }
    if (this._resizingChat) {
      // Handle sits above the chat panel — dragging up (negative deltaY)
      // should grow it, so the delta is inverted relative to mouse Y.
      const delta = this._chatResizeStartY - event.clientY;
      const next = this._chatResizeStartHeight + delta;
      this.chatPanelHeight = Math.min(App.CHAT_PANEL_MAX, Math.max(App.CHAT_PANEL_MIN, next));
      this.cdr.detectChanges();
    }
  }

  @HostListener('window:mouseup')
  onLayoutResizeEnd() {
    const wasResizing = this._resizingInput || this._resizingChat;
    this._resizingInput = false;
    this._resizingChat = false;
    if (wasResizing) this.cdr.detectChanges();
  }

  // ── Resume identity switcher ──────────────────────────────────────
  showResumeMenu = false;
  showAddResumeModal = false;
  newResumeLabel = '';
  newResumeOwner = '';
  newResumeFile: File | null = null;
  addResumeSaving = false;
  addResumeError = '';
  addResumeSuccess = false;

  get resumes(): ResumeIdentity[] {
    return this.resumesSvc.resumes();
  }

  get activeResumeId(): string | null {
    return this.resumesSvc.activeResumeId();
  }

  get activeResumeLabel(): string {
    return this.resumesSvc.activeResume()?.label ?? 'My Resume';
  }

  toggleResumeMenu() {
    this.showResumeMenu = !this.showResumeMenu;
    this.cdr.detectChanges();
  }

  selectResume(id: string) {
    this.showResumeMenu = false;
    if (id === this.activeResumeId) {
      this.cdr.detectChanges();
      return;
    }
    this.resumesSvc.setActive(id);
    this._refreshTemplateUrl();
    if (this.historySidebar !== 'closed') this.loadHistory();
    this.cdr.detectChanges();
  }

  openAddResumeModal() {
    this.showResumeMenu = false;
    this.showAddResumeModal = true;
    this.newResumeLabel = '';
    this.newResumeOwner = '';
    this.newResumeFile = null;
    this.addResumeError = '';
    this.addResumeSuccess = false;
    this.cdr.detectChanges();
  }

  cancelAddResumeModal() {
    this.showAddResumeModal = false;
    this.addResumeSuccess = false;
  }

  onResumeFileSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    this.newResumeFile = input.files?.[0] ?? null;
  }

  confirmAddResume() {
    if (!this.newResumeLabel.trim() || !this.newResumeFile || this.addResumeSaving) return;
    this.addResumeSaving = true;
    this.addResumeError = '';
    this.resumesSvc
      .create(this.newResumeLabel.trim(), this.newResumeOwner.trim(), this.newResumeFile)
      .subscribe({
        next: () => {
          this.addResumeSaving = false;
          this.addResumeSuccess = true;
          this._refreshTemplateUrl();
          this.cdr.detectChanges();
          setTimeout(() => {
            this.showAddResumeModal = false;
            this.addResumeSuccess = false;
            this.cdr.detectChanges();
          }, 1400);
        },
        error: (err) => {
          this.addResumeSaving = false;
          this.addResumeError = err?.error?.detail ?? 'Could not add this resume.';
          this.cdr.detectChanges();
        },
      });
  }

  removeResume(id: string, event: Event) {
    event.stopPropagation();
    if (!confirm('Delete this resume identity and all of its saved data?')) return;
    this.resumesSvc.remove(id).subscribe({
      next: () => {
        this._refreshTemplateUrl();
        this.cdr.detectChanges();
      },
    });
  }

  private _refreshTemplateUrl() {
    this.templateUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.svc.templateUrl());
  }

  // ── Tabs ────────────────────────────────────────────────────────
  activeTab: Tab = 'generate';
  showCareerMenu = false;
  careerTabs: { tab: Tab; label: string }[] = [
    { tab: 'personal-info', label: 'Personal Info' },
    { tab: 'apply-later', label: 'Application Tracker' },
    { tab: 'post-archive', label: 'LinkedIn Archive' },
    { tab: 'interview-prep', label: 'Interview Prep' },
    { tab: 'topic-mapping', label: 'Topic Mapping' },
    { tab: 'job-credentials', label: 'Account Credentials' },
  ];

  get isCareerTab(): boolean {
    return this.careerTabs.some((c) => c.tab === this.activeTab);
  }

  get activeCareerLabel(): string {
    return this.careerTabs.find((c) => c.tab === this.activeTab)?.label ?? 'Career Tools';
  }

  toggleCareerMenu() {
    this.showCareerMenu = !this.showCareerMenu;
    this.cdr.detectChanges();
  }

  selectCareerTab(tab: Tab) {
    this.showCareerMenu = false;
    this.setTab(tab);
  }

  // ── Pipeline state ──────────────────────────────────────────────
  jd = '';
  taskId: string | null = null;
  status: TaskStatus | null = null;
  pdfUrl: SafeResourceUrl | null = null;
  pdfRawUrl: string | null = null;
  isGenerating = false;
  showTemplate = false;
  templateUrl: SafeResourceUrl;
  localSteps: PipelineStep[] = pendingSteps();
  elapsedSeconds = 0;

  // ── Report state ────────────────────────────────────────────────
  reportData: ScoreReport | null = null;
  showReport = false;
  expandRequired = false;
  expandPreferred = false;
  expandVerifierBody = false;

  // ── Boost state ─────────────────────────────────────────────────
  isBoosting = false;
  boostScore: number | null = null;
  boostPdfUrl: SafeResourceUrl | null = null;
  boostPdfRawUrl: string | null = null;
  boostError = '';
  // Sections the rewriter kept unchanged because the requested keywords
  // couldn't be woven in honestly (e.g. a domain mismatch) — never silent.
  boostWarnings: string[] = [];
  private _boostErrorTimer: ReturnType<typeof setTimeout> | null = null;
  // Weave-in is a synchronous AI rewrite (2+ sequential Claude calls plus a
  // LaTeX compile) that can take up to a minute with no server-side progress
  // events — tick a visible counter so the wait doesn't read as a hang.
  boostElapsedSeconds = 0;
  private _boostElapsedTimer: ReturnType<typeof setInterval> | null = null;

  // ── Add-to-skills state (fast, non-AI alternative to Boost) ──────
  isAddingSkills = false;

  // ── Resume comparison (base vs. tailored) ─────────────────────────
  showCompare = false;

  openCompare() {
    this.showCompare = true;
    this.cdr.detectChanges();
  }

  onCompareClosed() {
    this.showCompare = false;
    this.cdr.detectChanges();
  }

  // ── ATS Score Verifier (independent resume+JD rescan) ─────────────
  showAtsVerify = false;
  atsVerifyJd = '';
  atsVerifyFile: File | null = null;
  atsVerifyLoading = false;
  atsVerifyError = '';
  atsVerifyResult: ScoreReport | null = null;

  toggleAtsVerify() {
    this.showAtsVerify = !this.showAtsVerify;
    if (this.showAtsVerify && !this.atsVerifyJd) {
      this.atsVerifyJd = this.jd;
    }
    this.cdr.detectChanges();
  }

  onAtsVerifyFileSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    this.atsVerifyFile = input.files?.[0] ?? null;
  }

  runAtsVerify() {
    if (!this.taskId || this.atsVerifyLoading || !this.atsVerifyJd.trim()) return;
    this.atsVerifyLoading = true;
    this.atsVerifyError = '';
    this.atsVerifyResult = null;
    this.cdr.detectChanges();

    this.svc.atsCheck(this.atsVerifyJd, this.taskId, this.atsVerifyFile ?? undefined).subscribe({
      next: (result) => {
        this.atsVerifyResult = result;
        this.atsVerifyLoading = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.atsVerifyError = err?.error?.detail ?? 'Could not verify the score — please try again.';
        this.atsVerifyLoading = false;
        this.cdr.detectChanges();
      },
    });
  }

  // ── Rescore state (after a chat edit) ────────────────────────────
  isRescoring = false;

  // ── Verifier state ──────────────────────────────────────────────
  verifierResult: VerifierResult | null = null;
  verifierLoading = false;
  verifierError = '';
  explainQuery = '';
  explainResult: ExplainResult | null = null;
  explainLoading = false;
  explainError = '';

  // ── History state ──────────────────────────────────────────────
  historySidebar: 'closed' | 'half' | 'full' = 'closed';
  historyEntries: HistoryEntry[] = [];
  historyLoading = false;
  historySaved = false;
  showSaveHistoryForm = false;
  saveHistoryCompany = '';
  saveHistoryUrl = '';
  saveHistoryAppliedDate = '';
  saveHistorySaving = false;
  saveHistoryError = '';

  // ── Self-intro / cover letter pitch state ────────────────────────
  pitchLoading = false;
  pitchError = '';
  pitchPreview: PitchResult | null = null;
  pitchSaving = false;
  pitchSaved = false;

  // ── Chat state ──────────────────────────────────────────────────
  chatMessages: ChatMessage[] = [];
  chatInput = '';
  chatState: 'idle' | 'planning' | 'awaiting_confirmation' | 'executing' = 'idle';
  pendingPlan: {
    planId: string;
    message: string;
    summary: string;
    changesPreview: string[];
  } | null = null;
  chatPdfUrl: SafeResourceUrl | null = null;
  chatPdfRawUrl: string | null = null;

  // ── Editor state ────────────────────────────────────────────────
  mdContent = '';
  mdOriginal = '';
  editorState: EditorState = 'idle';
  editorPdfUrl: SafeResourceUrl | null = null;
  editorPdfRawUrl: string | null = null;
  editorError = '';

  @ViewChild('chatScroll') chatScrollEl!: ElementRef;
  @ViewChild('downloadInput') downloadInputEl?: ElementRef<HTMLInputElement>;

  private _elapsedTimer: ReturnType<typeof setInterval> | null = null;
  private _pollTimeout: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    const svc = this.svc;
    const sanitizer = this.sanitizer;

    this.templateUrl = sanitizer.bypassSecurityTrustResourceUrl(svc.templateUrl());
  }

  ngOnInit() {
    // Not being logged in is a normal state here (unlike /welcome) — the
    // resume tool works with or without a session, so no redirect on 401.
    this.authSvc.me().subscribe({
      next: ({ user }) => {
        this.authUser = user;
        this.authChecked = true;
        this.cdr.detectChanges();
      },
      error: () => {
        this.authUser = null;
        this.authChecked = true;
        this.cdr.detectChanges();
      },
    });

    this.resumesSvc.list().subscribe({
      next: () => {
        // The constructor built templateUrl before the active resume was
        // known — refresh it now that resumesSvc has resolved one.
        this._refreshTemplateUrl();
        this.cdr.detectChanges();
      },
    });
  }

  logout() {
    this.authSvc.logout().subscribe(() => {
      this.authUser = null;
      this.cdr.detectChanges();
      this.router.navigate(['/login']);
    });
  }

  ngOnDestroy() {
    this._clearElapsedTimer();
    this._clearBoostElapsedTimer();
    this._cancelPoll();
  }

  // ── Tab navigation ──────────────────────────────────────────────
  setTab(tab: Tab) {
    if (tab === this.activeTab) return;
    if (this.activeTab === 'edit-resume' && this.mdDirty) {
      if (!confirm('You have unsaved changes in the editor. Leave without saving?')) return;
    }
    this.activeTab = tab;
    if (tab === 'edit-resume' && this.editorState === 'idle') {
      this.loadMd();
    }
    this.cdr.detectChanges();
  }

  onTailorResume(jobPost: string) {
    this.jd = jobPost;
    this.setTab('generate');
  }

  // ── PDF active in viewer ────────────────────────────────────────
  get activePdfUrl(): SafeResourceUrl | null {
    return this.boostPdfUrl ?? this.chatPdfUrl ?? this.pdfUrl;
  }

  get showTemplatePdf(): boolean {
    return this.showTemplate && !this.activePdfUrl;
  }

  // ── Pipeline ────────────────────────────────────────────────────
  generate() {
    if (!this.jd.trim() || this.isGenerating) return;
    this.isGenerating = true;
    this.status = null;
    this.pdfUrl = null;
    this.pdfRawUrl = null;
    this.taskId = null;
    this.reportData = null;
    this.showReport = false;
    this.expandRequired = false;
    this.expandPreferred = false;
    this.expandVerifierBody = false;
    this.boostScore = null;
    this.boostPdfUrl = null;
    this.boostPdfRawUrl = null;
    this.selectedMissingKeywords.clear();
    this.showTemplate = false;
    this.localSteps = pendingSteps();
    this.historySaved = false;
    this.showSaveHistoryForm = false;
    this.saveHistoryError = '';
    this.verifierResult = null;
    this.verifierError = '';
    this.explainResult = null;
    this.explainQuery = '';
    this.pitchPreview = null;
    this.pitchError = '';
    this.pitchSaved = false;
    this._startElapsedTimer();
    this.cdr.detectChanges();

    this.svc.generate(this.jd).subscribe({
      next: ({ task_id }) => {
        this.taskId = task_id;
        this._poll(task_id);
      },
      error: () => this._finish(),
    });
  }

  viewTemplate() {
    this.pdfUrl = null;
    this.showTemplate = true;
    this.cdr.detectChanges();
  }

  // ── Download filename modal ────────────────────────────────────
  showDownloadModal = false;
  downloadFilename = '';

  download() {
    const url = this.boostPdfRawUrl ?? this.chatPdfRawUrl ?? this.pdfRawUrl;
    if (!url) return;
    this.downloadFilename = this._suggestedFilename();
    this.showDownloadModal = true;
    this.cdr.detectChanges();
    setTimeout(() => this.downloadInputEl?.nativeElement.focus(), 0);
  }

  confirmDownload() {
    const url = this.boostPdfRawUrl ?? this.chatPdfRawUrl ?? this.pdfRawUrl;
    if (!url) return;
    const name = this.downloadFilename.trim() || this._suggestedFilename();
    this.showDownloadModal = false;
    this._blobDownload(url, `${name}.pdf`);
  }

  cancelDownload() {
    this.showDownloadModal = false;
  }

  // Keyboard equivalent for the mouse-only backdrop-click dismiss on the
  // history sidebar and download modal.
  @HostListener('document:keydown.escape')
  onEscapeKey() {
    if (this.showDownloadModal) {
      this.cancelDownload();
      this.cdr.detectChanges();
    } else if (this.showAddResumeModal) {
      this.cancelAddResumeModal();
      this.cdr.detectChanges();
    } else if (this.selectedMissingKeywords.size > 0) {
      this.clearKeywordSelection();
    } else if (this.historySidebar !== 'closed') {
      this.setHistorySidebarState('closed');
    } else if (this.showCareerMenu) {
      this.showCareerMenu = false;
      this.cdr.detectChanges();
    } else if (this.showResumeMenu) {
      this.showResumeMenu = false;
      this.cdr.detectChanges();
    }
  }

  private _suggestedFilename(): string {
    const roleDetail = this.status?.steps?.[1]?.detail ?? '';
    const roleMatch = roleDetail.match(/Role:\s*([^·]+)/);
    const role = roleMatch ? roleMatch[1].trim() : 'Resume_Tailored';
    const safeRole = role
      .replace(/[^\w\- ]/g, '')
      .trim()
      .replace(/\s+/g, '_');
    const date = new Date().toISOString().slice(0, 10);
    return `${safeRole || 'Resume_Tailored'}_${date}`;
  }

  // ── Resume history ──────────────────────────────────────────────
  toggleHistorySidebar() {
    if (this.historySidebar === 'closed') {
      this.historySidebar = 'half';
      this.loadHistory();
    } else {
      this.historySidebar = 'closed';
    }
    this.cdr.detectChanges();
  }

  setHistorySidebarState(state: 'closed' | 'half' | 'full') {
    this.historySidebar = state;
    this.cdr.detectChanges();
  }

  loadHistory() {
    this.boostWarnings = [];
    this.historyLoading = true;
    this.svc.getHistory().subscribe({
      next: ({ entries }) => {
        this.historyEntries = entries;
        this.historyLoading = false;
        this.cdr.detectChanges();
      },
      error: () => {
        this.historyLoading = false;
        this.cdr.detectChanges();
      },
    });
  }

  openSaveHistoryForm() {
    this.showSaveHistoryForm = true;
    this.saveHistoryCompany = '';
    this.saveHistoryUrl = '';
    this.saveHistoryAppliedDate = '';
    this.saveHistoryError = '';
    this.cdr.detectChanges();
  }

  cancelSaveHistoryForm() {
    this.showSaveHistoryForm = false;
  }

  /** Fills the applied-date field with today's date, formatted for
   * `<input type="date">` (YYYY-MM-DD) — a quick alternative to picking
   * today from the calendar by hand. */
  setAppliedDateToday() {
    const now = new Date();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    this.saveHistoryAppliedDate = `${now.getFullYear()}-${month}-${day}`;
  }

  get isAppliedDateToday(): boolean {
    const now = new Date();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    return this.saveHistoryAppliedDate === `${now.getFullYear()}-${month}-${day}`;
  }

  confirmSaveHistory() {
    if (!this.taskId || !this.saveHistoryCompany.trim() || this.saveHistorySaving) return;
    this.saveHistorySaving = true;
    this.saveHistoryError = '';

    this.svc
      .saveHistory(
        this.taskId,
        this.saveHistoryCompany.trim(),
        this.saveHistoryUrl.trim(),
        this.saveHistoryAppliedDate.trim(),
      )
      .subscribe({
        next: ({ entry }) => {
          this.historyEntries = [entry, ...this.historyEntries];
          this.saveHistorySaving = false;
          this.showSaveHistoryForm = false;
          this.historySaved = true;
          this.cdr.detectChanges();
        },
        error: (err) => {
          this.saveHistorySaving = false;
          this.saveHistoryError = err?.error?.detail ?? 'Could not save to history.';
          this.cdr.detectChanges();
        },
      });
  }

  regeneratePitches() {
    if (!this.taskId || this.pitchLoading) return;
    this.pitchLoading = true;
    this.pitchError = '';
    this.pitchSaved = false;

    this.svc.generatePitches(this.taskId, this.jd).subscribe({
      next: (result) => {
        this.pitchPreview = result;
        this.pitchLoading = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.pitchLoading = false;
        this.pitchError = err?.error?.detail ?? 'Could not generate pitch material.';
        this.cdr.detectChanges();
      },
    });
  }

  savePitches() {
    if (!this.pitchPreview || this.pitchSaving) return;
    this.pitchSaving = true;
    const preview = this.pitchPreview;
    const fields: (keyof PitchResult)[] = [
      'short_pitch',
      'written_bio',
      'project_pitches',
      'cover_letter_template',
    ];

    let remaining = fields.length;
    const onFieldDone = () => {
      remaining -= 1;
      if (remaining === 0) {
        this.pitchSaving = false;
        this.pitchSaved = true;
        this.pitchPreview = null;
        this.cdr.detectChanges();
      }
    };
    for (const key of fields) {
      this.careerSvc.setPersonalInfo(key, preview[key]).subscribe({
        next: onFieldDone,
        error: () => {
          this.pitchSaving = false;
          this.pitchError = 'Could not save one or more fields — check Personal Info and retry.';
          this.cdr.detectChanges();
        },
      });
    }
  }

  discardPitches() {
    this.pitchPreview = null;
    this.pitchError = '';
  }

  viewHistoryPdf(entry: HistoryEntry) {
    window.open(this.svc.historyPdfUrl(entry.id), '_blank');
  }

  historyScoreColor(score: number | null): string {
    if (score === null) return '#6b7280';
    if (score >= 90) return '#22c55e';
    if (score >= 70) return '#f59e0b';
    return '#ef4444';
  }

  // ── Verifier agent ──────────────────────────────────────────────
  runVerifier() {
    if (!this.taskId || this.verifierLoading) return;
    this.verifierLoading = true;
    this.verifierError = '';
    this.expandVerifierBody = true;

    this.svc.runVerifier(this.taskId).subscribe({
      next: (result) => {
        this.verifierResult = result;
        this.verifierLoading = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.verifierLoading = false;
        this.verifierError = err?.error?.detail ?? 'Verifier failed. Please try again.';
        this.cdr.detectChanges();
      },
    });
  }

  askExplain() {
    if (!this.taskId || !this.explainQuery.trim() || this.explainLoading) return;
    this.explainLoading = true;
    this.explainError = '';
    this.explainResult = null;

    this.svc.explainKeyword(this.taskId, this.explainQuery.trim()).subscribe({
      next: (result) => {
        this.explainResult = result;
        this.explainLoading = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.explainLoading = false;
        this.explainError = err?.error?.detail ?? 'Could not look that up.';
        this.cdr.detectChanges();
      },
    });
  }

  verifierStatusLabel(status: string): string {
    if (status === 'exact') return '✓ Found in resume';
    if (status === 'semantic') return '≈ Implied, not literal';
    return '✗ Not found';
  }

  get verifierExact(): VerifierKeyword[] {
    return this.verifierResult?.keywords.filter((k) => k.status === 'exact') ?? [];
  }

  get verifierSemantic(): VerifierKeyword[] {
    return this.verifierResult?.keywords.filter((k) => k.status === 'semantic') ?? [];
  }

  get verifierMissing(): VerifierKeyword[] {
    return this.verifierResult?.keywords.filter((k) => k.status === 'missing') ?? [];
  }

  get displaySteps(): PipelineStep[] {
    return this.status?.steps ?? this.localSteps;
  }

  get progressPct(): number {
    const steps = this.displaySteps;
    if (!steps.length) return 0;
    const done = steps.filter((s) => s.status === 'done').length;
    return Math.round((done / steps.length) * 100);
  }

  get elapsedLabel(): string {
    const m = Math.floor(this.elapsedSeconds / 60);
    const s = this.elapsedSeconds % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  }

  get boostElapsedLabel(): string {
    const m = Math.floor(this.boostElapsedSeconds / 60);
    const s = this.boostElapsedSeconds % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  }

  get scoreColor(): string {
    const s = this.boostScore ?? this.status?.score;
    if (!s) return '#6b7280';
    if (s >= 90) return '#22c55e';
    if (s >= 70) return '#f59e0b';
    return '#ef4444';
  }

  get currentScore(): number | null {
    return this.boostScore ?? this.status?.score ?? null;
  }

  /** Sections the AI kept unchanged rather than fabricate honesty-violating
   * content (e.g. weaving a healthcare keyword into a fintech resume) —
   * from the initial generate pass and/or a later Weave-in, so this is
   * never silently lost. */
  get rewriteWarnings(): string[] {
    return [...(this.status?.warnings ?? []), ...this.boostWarnings];
  }

  // ── ATS Report ──────────────────────────────────────────────────
  toggleReport() {
    this.showReport = !this.showReport;
    this.cdr.detectChanges();
  }

  toggleRequired() {
    this.expandRequired = !this.expandRequired;
    this.cdr.detectChanges();
  }

  togglePreferred() {
    this.expandPreferred = !this.expandPreferred;
    this.cdr.detectChanges();
  }

  toggleVerifierBody() {
    this.expandVerifierBody = !this.expandVerifierBody;
    this.cdr.detectChanges();
  }

  private _loadReport(taskId: string) {
    this.svc.getReport(taskId).subscribe({
      next: (report) => {
        this.reportData = report;
        this.cdr.detectChanges();
      },
      // Report is supplementary to the score card, which already rendered —
      // fail quietly rather than surface a second error for the same task.
      error: () => undefined,
    });
  }

  // ── ATS Boost ───────────────────────────────────────────────────
  // Missing keywords are clicked directly in the report (required or
  // preferred, same mechanism for both) to build a selection, rather than
  // routing through a separate modal — the modal wasn't being found/used.
  selectedMissingKeywords = new Set<string>();

  toggleKeywordSelection(keyword: string) {
    // Ignore edits to the selection while a Weave-in/Add-to-Skills call is
    // in flight — mutating it mid-request would desync what's visually
    // "pending" from what was actually sent to the backend.
    if (this.isBoosting || this.isAddingSkills) return;
    if (this.selectedMissingKeywords.has(keyword)) {
      this.selectedMissingKeywords.delete(keyword);
    } else {
      this.selectedMissingKeywords.add(keyword);
    }
    this.cdr.detectChanges();
  }

  isKeywordSelected(keyword: string): boolean {
    return this.selectedMissingKeywords.has(keyword);
  }

  get selectedKeywordCount(): number {
    return this.selectedMissingKeywords.size;
  }

  selectAllMissingKeywords() {
    if (!this.reportData) return;
    for (const kw of [...this.reportData.required_missing, ...this.reportData.preferred_missing]) {
      this.selectedMissingKeywords.add(kw);
    }
    this.cdr.detectChanges();
  }

  clearKeywordSelection() {
    this.selectedMissingKeywords.clear();
    this.cdr.detectChanges();
  }

  confirmBoostSelection() {
    // Don't clear the selection here — it's what drives the "pending" chip
    // highlight while the request is in flight. Clearing it early made every
    // selected keyword snap back to plain "missing" the instant you clicked,
    // before the (20-90s) AI rewrite had even started, which read as the
    // click doing nothing.
    const selected = [...this.selectedMissingKeywords];
    this.boostAts(selected);
  }

  boostAts(selectedKeywords: string[]) {
    if (!this.taskId || this.isBoosting || selectedKeywords.length === 0) return;
    const taskId = this.taskId;
    this.isBoosting = true;
    this._startBoostElapsedTimer();
    this.cdr.detectChanges();

    this.svc.boostAts(taskId, selectedKeywords).subscribe({
      next: (result) => {
        this.boostScore = result.score;
        this.boostWarnings = result.warnings ?? [];
        if (result.has_pdf && result.boost_id) {
          this.boostPdfRawUrl = this.svc.chatPdfUrl(result.boost_id);
          this.boostPdfUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.boostPdfRawUrl);
        }
        // Only clear now that we know it actually succeeded — the fresh
        // report below is authoritative for which keywords are still missing.
        this.selectedMissingKeywords.clear();
        // Full refresh (not a manual patch) so found/missing lists reflect
        // reality — the rewrite may have touched more than just the
        // keywords that were selected.
        this._loadReport(taskId);
        this.isBoosting = false;
        this._clearBoostElapsedTimer();
        this.cdr.detectChanges();
      },
      error: (err) => {
        // Keep the selection on failure so the user isn't forced to
        // reselect every keyword before retrying.
        this._showBoostError(err?.error?.detail ?? "Couldn't weave in those keywords — please try again.");
        this.isBoosting = false;
        this._clearBoostElapsedTimer();
        this.cdr.detectChanges();
      },
    });
  }

  /** Shows a friendly, transient notification for a failed Weave-in/Add-to-
   * Skills call — these used to fail silently, leaving the keyword chips
   * selectable again with no indication anything had gone wrong. */
  private _showBoostError(message: string) {
    this.boostError = message;
    if (this._boostErrorTimer) clearTimeout(this._boostErrorTimer);
    this._boostErrorTimer = setTimeout(() => {
      this.boostError = '';
      this.cdr.detectChanges();
    }, 6000);
  }

  /** Fast, deterministic alternative to Boost — adds the checked keywords
   * straight into the Technical Skills table with no AI rewrite. */
  confirmAddToSkillsSelection() {
    const selected = [...this.selectedMissingKeywords];
    this.addSkillsToResume(selected);
  }

  addSkillsToResume(selectedKeywords: string[]) {
    if (!this.taskId || this.isAddingSkills || selectedKeywords.length === 0) return;
    const taskId = this.taskId;
    this.isAddingSkills = true;
    this.cdr.detectChanges();

    this.svc.addSkillsToResume(taskId, selectedKeywords).subscribe({
      next: (result) => {
        this.boostScore = result.score;
        if (result.has_pdf && result.boost_id) {
          this.boostPdfRawUrl = this.svc.chatPdfUrl(result.boost_id);
          this.boostPdfUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.boostPdfRawUrl);
        }
        this.selectedMissingKeywords.clear();
        this._loadReport(taskId);
        this.isAddingSkills = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        this._showBoostError(err?.error?.detail ?? "Couldn't add those skills — please try again.");
        this.isAddingSkills = false;
        this.cdr.detectChanges();
      },
    });
  }

  /** Re-run the ATS score against whatever's currently on disk — for use
   * right after a chat edit, which patches the resume directly rather than
   * going through the pipeline, so the score card would otherwise go stale. */
  rescoreAfterChatEdit() {
    if (!this.taskId || this.isRescoring) return;
    const taskId = this.taskId;
    this.isRescoring = true;
    this.cdr.detectChanges();

    this.svc.rescoreTask(taskId).subscribe({
      next: (report) => {
        this.boostScore = report.overall_score;
        this.reportData = report;
        this.isRescoring = false;
        this._pushMsg({ role: 'bot', text: `Rechecked — now at ${report.overall_score}% (${report.verdict}).` });
        this.cdr.detectChanges();
      },
      error: () => {
        this.isRescoring = false;
        this._pushMsg({ role: 'error', text: 'Could not recheck the score. Please try again.' });
        this.cdr.detectChanges();
      },
    });
  }

  // ── Chat ────────────────────────────────────────────────────────
  sendChat() {
    const msg = this.chatInput.trim();
    if (!msg || this.chatState !== 'idle') return;

    this.chatInput = '';
    this._pushMsg({ role: 'user', text: msg });
    this.chatState = 'planning';
    this.cdr.detectChanges();

    this.svc.chatPlan(msg).subscribe({
      next: (result) => {
        this.pendingPlan = {
          planId: result.plan_id,
          message: msg,
          summary: result.summary,
          changesPreview: result.changes_preview ?? [],
        };

        if (result.questions?.length) {
          this._pushMsg({
            role: 'bot',
            text: result.summary + '\n\n' + result.questions.join('\n'),
          });
          this.pendingPlan = null;
          this.chatState = 'idle';
        } else {
          this.chatState = 'awaiting_confirmation';
          this._pushMsg({
            role: 'plan',
            text: result.summary,
            changesPreview: result.changes_preview ?? [],
            planId: result.plan_id,
          });
        }
        this.cdr.detectChanges();
      },
      error: () => {
        this._pushMsg({ role: 'error', text: 'Failed to analyse request. Please try again.' });
        this.pendingPlan = null;
        this.chatState = 'idle';
        this.cdr.detectChanges();
      },
    });
  }

  confirmPlan() {
    if (!this.pendingPlan || this.chatState !== 'awaiting_confirmation') return;
    const { planId, message } = this.pendingPlan;
    this.chatState = 'executing';
    this.cdr.detectChanges();

    this.svc.chatExecute(planId, message).subscribe({
      next: (result) => {
        if (result.success) {
          this._pushMsg({
            role: 'bot',
            text: '✓ ' + result.done_summary,
            canRescore: !!this.taskId,
          });
          if (result.has_pdf) {
            this.chatPdfRawUrl = this.svc.chatPdfUrl(result.edit_id);
            this.chatPdfUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.chatPdfRawUrl);
          }
        } else {
          this._pushMsg({ role: 'error', text: result.error ?? 'Something went wrong.' });
        }
        this.pendingPlan = null;
        this.chatState = 'idle';
        this.cdr.detectChanges();
      },
      error: () => {
        this._pushMsg({ role: 'error', text: 'Failed to apply changes. Please try again.' });
        this.pendingPlan = null;
        this.chatState = 'idle';
        this.cdr.detectChanges();
      },
    });
  }

  cancelPlan() {
    this.pendingPlan = null;
    this.chatState = 'idle';
    this._pushMsg({ role: 'bot', text: 'Cancelled. What would you like to change instead?' });
    this.cdr.detectChanges();
  }

  undoChat() {
    if (this.chatState !== 'idle') return;
    this.chatState = 'executing';
    this._pushMsg({ role: 'user', text: '↩ Undo last change' });
    this.cdr.detectChanges();

    this.svc.chatUndo().subscribe({
      next: (result) => {
        this._pushMsg({
          role: result.success ? 'bot' : 'error',
          text: result.done_summary,
          canRescore: result.success && !!this.taskId,
        });
        if (result.success && result.has_pdf) {
          this.chatPdfRawUrl = this.svc.chatPdfUrl(result.edit_id);
          this.chatPdfUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.chatPdfRawUrl);
        }
        this.chatState = 'idle';
        this.cdr.detectChanges();
      },
      error: () => {
        this._pushMsg({ role: 'error', text: 'Undo failed.' });
        this.chatState = 'idle';
        this.cdr.detectChanges();
      },
    });
  }

  get isChatBusy(): boolean {
    return this.chatState === 'planning' || this.chatState === 'executing';
  }

  private _pushMsg(msg: ChatMessage) {
    this.chatMessages.push(msg);
    setTimeout(() => {
      if (this.chatScrollEl) {
        const el = this.chatScrollEl.nativeElement;
        el.scrollTop = el.scrollHeight;
      }
    }, 0);
  }

  // ── Resume MD editor ────────────────────────────────────────────
  get mdDirty(): boolean {
    return this.mdContent !== this.mdOriginal;
  }

  loadMd() {
    this.editorState = 'loading';
    this.editorError = '';
    this.cdr.detectChanges();

    this.svc.getResumeMd().subscribe({
      next: (res) => {
        this.mdContent = res.content;
        this.mdOriginal = res.content;
        this.editorState = 'editing';
        this.cdr.detectChanges();
      },
      error: () => {
        this.editorState = 'error';
        this.editorError = 'Could not load resume content. Is the API server running?';
        this.cdr.detectChanges();
      },
    });
  }

  saveMd() {
    if (!this.mdDirty) return;
    this.editorState = 'saving';
    this.cdr.detectChanges();

    this.svc.saveResumeMd(this.mdContent).subscribe({
      next: () => {
        this.mdOriginal = this.mdContent;
        this.editorState = 'saved';
        this.editorPdfUrl = null;
        this.cdr.detectChanges();
      },
      error: () => {
        this.editorState = 'error';
        this.editorError = 'Failed to save draft.';
        this.cdr.detectChanges();
      },
    });
  }

  discardMd() {
    this.mdContent = this.mdOriginal;
    this.editorState = 'editing';
    this.editorPdfUrl = null;
    this.editorError = '';
    this.cdr.detectChanges();
  }

  syncMd() {
    this.editorState = 'syncing';
    this.cdr.detectChanges();

    this.svc.syncResumeMd().subscribe({
      next: (res) => {
        if (res.synced && res.has_pdf) {
          this.editorPdfRawUrl = this.svc.chatPdfUrl(res.edit_id);
          this.editorPdfUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.editorPdfRawUrl);
        }
        this.editorState = 'synced';
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.editorState = 'error';
        this.editorError = err?.error?.detail ?? 'Sync failed. Check the API logs.';
        this.cdr.detectChanges();
      },
    });
  }

  downloadEditor() {
    if (!this.editorPdfRawUrl) return;
    this._blobDownload(this.editorPdfRawUrl, 'resume_updated.pdf');
  }

  private _blobDownload(url: string, filename: string) {
    fetch(url)
      .then((r) => r.blob())
      .then((blob) => {
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(blobUrl), 10000);
      });
  }

  // ── Polling ─────────────────────────────────────────────────────
  private _poll(taskId: string) {
    this.svc.getStatus(taskId).subscribe({
      next: (s) => {
        this.status = s;
        this.cdr.detectChanges();

        if (s.status === 'done') {
          if (s.has_pdf) {
            this.pdfRawUrl = this.svc.pdfUrl(taskId);
            this.pdfUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.pdfRawUrl);
          }
          this._loadReport(taskId);
          this._finish();
        } else if (s.status === 'error') {
          this._finish();
        } else {
          this._pollTimeout = setTimeout(() => this._poll(taskId), 1500);
        }
      },
      error: () => {
        this._pollTimeout = setTimeout(() => this._poll(taskId), 2000);
      },
    });
  }

  private _cancelPoll() {
    if (this._pollTimeout !== null) {
      clearTimeout(this._pollTimeout);
      this._pollTimeout = null;
    }
  }

  private _startElapsedTimer() {
    this.elapsedSeconds = 0;
    this._clearElapsedTimer();
    this._elapsedTimer = setInterval(() => {
      this.elapsedSeconds++;
      this.cdr.detectChanges();
    }, 1000);
  }

  private _clearElapsedTimer() {
    if (this._elapsedTimer !== null) {
      clearInterval(this._elapsedTimer);
      this._elapsedTimer = null;
    }
  }

  private _startBoostElapsedTimer() {
    this.boostElapsedSeconds = 0;
    this._clearBoostElapsedTimer();
    this._boostElapsedTimer = setInterval(() => {
      this.boostElapsedSeconds++;
      this.cdr.detectChanges();
    }, 1000);
  }

  private _clearBoostElapsedTimer() {
    if (this._boostElapsedTimer !== null) {
      clearInterval(this._boostElapsedTimer);
      this._boostElapsedTimer = null;
    }
  }

  private _finish() {
    this.isGenerating = false;
    this._clearElapsedTimer();
    this._cancelPoll();
    this.cdr.detectChanges();
  }
}
