import {
  CdkDragDrop,
  CdkDragEnd,
  CdkDragStart,
  DragDropModule,
  moveItemInArray,
} from '@angular/cdk/drag-drop'
import { Component, inject, signal } from '@angular/core'
import { RouterModule } from '@angular/router'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { TourNgBootstrap, TourService } from 'ngx-ui-tour-ng-bootstrap'
import { SavedView } from 'src/app/data/saved-view'
import { IfPermissionsDirective } from 'src/app/directives/if-permissions.directive'
import { PermissionsService } from 'src/app/services/permissions.service'
import { SavedViewService } from 'src/app/services/rest/saved-view.service'
import { SettingsService } from 'src/app/services/settings.service'
import { ToastService } from 'src/app/services/toast.service'
import { environment } from 'src/environments/environment'
import { PageHeaderComponent } from '../common/page-header/page-header.component'
import { ComponentWithPermissions } from '../with-permissions/with-permissions.component'
import { SavedViewWidgetComponent } from './widgets/saved-view-widget/saved-view-widget.component'
import { StatisticsWidgetComponent } from './widgets/statistics-widget/statistics-widget.component'
import { UploadFileWidgetComponent } from './widgets/upload-file-widget/upload-file-widget.component'
import { WelcomeWidgetComponent } from './widgets/welcome-widget/welcome-widget.component'

@Component({
  selector: 'pngx-dashboard',
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss'],
  imports: [
    PageHeaderComponent,
    SavedViewWidgetComponent,
    StatisticsWidgetComponent,
    UploadFileWidgetComponent,
    WelcomeWidgetComponent,
    IfPermissionsDirective,
    DragDropModule,
    TourNgBootstrap,
    NgxBootstrapIconsModule,
    RouterModule,
  ],
})
export class DashboardComponent extends ComponentWithPermissions {
  settingsService = inject(SettingsService)
  savedViewService = inject(SavedViewService)
  private permissionsService = inject(PermissionsService)
  private tourService = inject(TourService)
  private toastService = inject(ToastService)

  readonly dashboardViews = signal<SavedView[]>([])
  constructor() {
    super()

    // 2026-09-23: this call had no permission gate at all -- unlike
    // app-frame.component.ts's own call to the same service, which
    // does check this first. Every account without view_savedview
    // (Property Owner, the common case) hit a 403 here on every single
    // Dashboard load, which then surfaced as an unhandled RxJS error
    // (see saved-view.service.ts's own reload() fix, committed
    // alongside this one, for the other half of the same bug class).
    if (
      this.permissionsService.currentUserCan(
        this.PermissionAction.View,
        this.PermissionType.SavedView
      )
    ) {
      this.savedViewService.listAll().subscribe({
        next: () => {
          this.dashboardViews.set(this.savedViewService.dashboardViews)
        },
        error: () => {},
      })
    }
  }

  get subtitle() {
    if (this.settingsService.displayName) {
      return $localize`Hello ${this.settingsService.displayName}, welcome to ${environment.appTitle}`
    } else {
      return $localize`Welcome to ${environment.appTitle}`
    }
  }

  completeTour() {
    if (this.tourService.getStatus() !== 0) {
      this.tourService.end() // will call settingsService.completeTour()
    } else {
      this.settingsService.completeTour()
    }
  }

  onDragStart(event: CdkDragStart) {
    this.settingsService.globalDropzoneEnabled.set(false)
  }

  onDragEnd(event: CdkDragEnd) {
    this.settingsService.globalDropzoneEnabled.set(true)
  }

  onDrop(event: CdkDragDrop<SavedView[]>) {
    const dashboardViews = [...this.dashboardViews()]
    moveItemInArray(dashboardViews, event.previousIndex, event.currentIndex)
    this.dashboardViews.set(dashboardViews)

    this.settingsService
      .updateDashboardViewsSort(this.dashboardViews())
      .subscribe({
        next: () => {
          this.toastService.showInfo($localize`Dashboard updated`)
        },
        error: (e) => {
          this.toastService.showError($localize`Error updating dashboard`, e)
        },
      })
  }
}
