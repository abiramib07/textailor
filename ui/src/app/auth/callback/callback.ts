import { Component, OnInit, ChangeDetectorRef, inject } from '@angular/core';

import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthService } from '../auth.service';

@Component({
  selector: 'app-auth-callback',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './callback.html',
  styleUrl: '../auth-shared.scss',
})
export class AuthCallbackComponent implements OnInit {
  private auth = inject(AuthService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private cdr = inject(ChangeDetectorRef);

  error = '';
  loading = true;

  ngOnInit(): void {
    const status = this.route.snapshot.queryParamMap.get('status');
    if (status !== 'success') {
      this.loading = false;
      this.error = `Google sign-in failed (${this.route.snapshot.queryParamMap.get('reason') ?? 'unknown error'}).`;
      this.cdr.detectChanges();
      return;
    }

    this.auth.me().subscribe({
      next: ({ user }) => {
        this.loading = false;
        if (!user.mobile_number) {
          this.router.navigate(['/complete-profile']);
        } else {
          this.router.navigate(['/']);
        }
      },
      error: () => {
        this.loading = false;
        this.error = 'Signed in with Google, but could not load your profile.';
        this.cdr.detectChanges();
      },
    });
  }
}
