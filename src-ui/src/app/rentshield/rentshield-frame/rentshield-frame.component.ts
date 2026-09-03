import { CommonModule } from '@angular/common'
import { Component, inject, signal } from '@angular/core'
import { toSignal } from '@angular/core/rxjs-interop'
import { NavigationEnd, Router, RouterModule } from '@angular/router'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { filter, map, startWith } from 'rxjs'

interface NavItem {
  label: string
  path: string
  icon: string
  exact?: boolean
}

@Component({
  selector: 'app-rentshield-frame',
  standalone: true,
  imports: [CommonModule, RouterModule, NgxBootstrapIconsModule],
  templateUrl: './rentshield-frame.component.html',
  styleUrl: './rentshield-frame.component.scss',
})
export class RentshieldFrameComponent {
  private router = inject(Router)

  collapsed = signal(this.readCollapsedPref())
  mobileOpen = signal(false)

  pageTitle = toSignal(
    this.router.events.pipe(
      filter((e) => e instanceof NavigationEnd),
      startWith(null),
      map(() => {
        // Walk the router's own snapshot tree (always populated, unlike
        // a freshly-injected ActivatedRoute on the very first emission)
        // to find the deepest activated route's `data.title`.
        let route = this.router.routerState.snapshot.root
        while (route.firstChild) route = route.firstChild
        return (route.data?.['title'] as string) || 'Dashboard'
      })
    ),
    { initialValue: 'Dashboard' }
  )

  navItems: NavItem[] = [
    { label: 'Dashboard', path: '/rentshield/dashboard', icon: 'house', exact: true },
    { label: 'New Notice', path: '/rentshield/notices/new', icon: 'file-earmark-plus' },
    { label: 'Saved Notices', path: '/rentshield/notices', icon: 'journals' },
    { label: 'Legal Skills', path: '/rentshield/legal-skills', icon: 'bank' },
    { label: 'Document Vault', path: '/documents', icon: 'archive' },
    { label: 'Settings', path: '/rentshield/settings', icon: 'gear' },
  ]

  toggleCollapsed(): void {
    this.collapsed.update((v) => !v)
    try {
      localStorage.setItem(
        'rentshield.sidebarCollapsed',
        this.collapsed() ? '1' : '0'
      )
    } catch {
      // localStorage may be unavailable (private mode, etc.) — non-fatal
    }
  }

  toggleMobile(): void {
    this.mobileOpen.update((v) => !v)
  }

  closeMobile(): void {
    this.mobileOpen.set(false)
  }

  private readCollapsedPref(): boolean {
    try {
      return localStorage.getItem('rentshield.sidebarCollapsed') === '1'
    } catch {
      return false
    }
  }
}
