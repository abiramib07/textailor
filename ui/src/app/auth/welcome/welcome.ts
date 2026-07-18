import { Component, OnInit, ChangeDetectorRef, inject } from '@angular/core';

import { Router, RouterLink } from '@angular/router';
import { AuthService, UserProfile } from '../auth.service';

@Component({
  selector: 'app-welcome',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './welcome.html',
  styleUrl: '../auth-shared.scss',
})
export class WelcomeComponent implements OnInit {
  private auth = inject(AuthService);
  private router = inject(Router);
  private cdr = inject(ChangeDetectorRef);

  user: UserProfile | null = null;
  loading = true;

  ngOnInit(): void {
    this.auth.me().subscribe({
      next: ({ user }) => {
        this.user = user;
        this.loading = false;
        this.cdr.detectChanges();
      },
      error: () => {
        this.router.navigate(['/login']);
      },
    });
  }

  logout(): void {
    this.auth.logout().subscribe(() => this.router.navigate(['/login']));
  }
}
