import { Component, inject, OnDestroy, OnInit, Renderer2 } from '@angular/core'
import { Router, RouterOutlet } from '@angular/router'
import { TourNgBootstrap, TourService } from 'ngx-ui-tour-ng-bootstrap'
import { first, Subscription } from 'rxjs'
import { ToastsComponent } from './components/common/toasts/toasts.component'
import { FileDropComponent } from './components/file-drop/file-drop.component'
import { SETTINGS_KEYS } from './data/ui-settings'
import { ComponentRouterService } from './services/component-router.service'
import { HotKeyService } from './services/hot-key.service'
import {
  PermissionAction,
  PermissionsService,
  PermissionType,
} from './services/permissions.service'
import { SettingsService } from './services/settings.service'
import { TasksService } from './services/tasks.service'
import { ToastService } from './services/toast.service'
import { WebsocketStatusService } from './services/websocket-status.service'

@Component({
  selector: 'pngx-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
  imports: [FileDropComponent, ToastsComponent, TourNgBootstrap, RouterOutlet],
})
export class AppComponent implements OnInit, OnDestroy {
  private settings = inject(SettingsService)
  private websocketStatusService = inject(WebsocketStatusService)
  private toastService = inject(ToastService)
  private router = inject(Router)
  private tasksService = inject(TasksService)
  tourService = inject(TourService)
  private renderer = inject(Renderer2)
  private permissionsService = inject(PermissionsService)
  private hotKeyService = inject(HotKeyService)
  private componentRouterService = inject(ComponentRouterService)

  newDocumentSubscription: Subscription
  successSubscription: Subscription
  failedSubscription: Subscription

  constructor() {
    let anyWindow = window as any
    anyWindow.pdfWorkerSrc = new URL(
      'assets/js/pdf.worker.min.mjs',
      document.baseURI
    ).toString()
    this.settings.updateAppearanceSettings()
  }

  ngOnDestroy(): void {
    this.websocketStatusService.disconnect()
    if (this.successSubscription) {
      this.successSubscription.unsubscribe()
    }
    if (this.failedSubscription) {
      this.failedSubscription.unsubscribe()
    }
    if (this.newDocumentSubscription) {
      this.newDocumentSubscription.unsubscribe()
    }
  }

  private showNotification(key) {
    if (
      this.router.url == '/dashboard' &&
      this.settings.get(
        SETTINGS_KEYS.NOTIFICATIONS_CONSUMER_SUPPRESS_ON_DASHBOARD
      )
    ) {
      return false
    }
    return this.settings.get(key)
  }

  ngOnInit(): void {
    this.websocketStatusService.connect()

    this.successSubscription = this.websocketStatusService
      .onDocumentConsumptionFinished()
      .subscribe((status) => {
        this.tasksService.reload()
        if (
          this.showNotification(SETTINGS_KEYS.NOTIFICATIONS_CONSUMER_SUCCESS)
        ) {
          if (
            this.permissionsService.currentUserCan(
              PermissionAction.View,
              PermissionType.Document
            )
          ) {
            this.toastService.show({
              content: $localize`Document ${status.filename} was added to Paperless-ngx.`,
              delay: 10000,
              actionName: $localize`Open document`,
              action: () => {
                this.router.navigate(['documents', status.documentId])
              },
            })
          } else {
            this.toastService.show({
              content: $localize`Document ${status.filename} was added to Paperless-ngx.`,
              delay: 10000,
            })
          }
        }
      })

    this.failedSubscription = this.websocketStatusService
      .onDocumentConsumptionFailed()
      .subscribe((status) => {
        this.tasksService.reload()
        if (
          this.showNotification(SETTINGS_KEYS.NOTIFICATIONS_CONSUMER_FAILED)
        ) {
          this.toastService.showError(
            $localize`Could not add ${status.filename}\: ${status.message}`
          )
        }
      })

    this.newDocumentSubscription = this.websocketStatusService
      .onDocumentDetected()
      .subscribe((status) => {
        this.tasksService.reload()
        if (
          this.showNotification(
            SETTINGS_KEYS.NOTIFICATIONS_CONSUMER_NEW_DOCUMENT
          )
        ) {
          this.toastService.show({
            content: $localize`Document ${status.filename} is being processed by Paperless-ngx.`,
            delay: 5000,
          })
        }
      })

    this.hotKeyService
      .addShortcut({ keys: 'h', description: $localize`Dashboard` })
      .subscribe(() => {
        this.router.navigate(['/dashboard'])
      })
    if (
      this.permissionsService.currentUserCan(
        PermissionAction.View,
        PermissionType.Document
      )
    ) {
      this.hotKeyService
        .addShortcut({ keys: 'd', description: $localize`Documents` })
        .subscribe(() => {
          this.router.navigate(['/documents'])
        })
    }
    if (
      this.permissionsService.currentUserCan(
        PermissionAction.Change,
        PermissionType.UISettings
      )
    ) {
      this.hotKeyService
        .addShortcut({ keys: 's', description: $localize`Settings` })
        .subscribe(() => {
          this.router.navigate(['/settings'])
        })
    }

    this.tourService.initialize([
      {
        anchorId: 'tour.dashboard',
        content: $localize`The dashboard can be used to show saved views, such as an 'Inbox'. Views are found under Manage > Saved Views once you have created some.`,
        route: '/dashboard',
        delayAfterNavigation: 500,
        isOptional: false,
      },
      {
        anchorId: 'tour.upload-widget',
        content: $localize`Drag-and-drop documents here to start uploading or place them in the consume folder. You can also drag-and-drop documents anywhere on all other pages of the web app. Once you do, Paperless-ngx will start training its machine learning algorithms.`,
        route: '/dashboard',
      },
      {
        anchorId: 'tour.dashboard',
        title: $localize`RentShield dashboards`,
        content: $localize`RentShield adds 8 live dashboard widgets here -- All Notices, Statutory/Breach buckets, Notarization Pending, Needs AI Review, Contracts Under Review, and Non-Compliant Contracts -- each a real, filterable Saved View, not a static count.`,
        route: '/dashboard',
        isOptional: true,
      },
      {
        anchorId: 'tour.rentshield-new-notice',
        title: $localize`Generate a notice`,
        content: $localize`Start here to generate a bilingual (English/Arabic), statute-cited tenancy notice -- the correct 12-month statutory notice or 30-day breach notice, picked automatically from the reason you choose.`,
        route: '/dashboard',
        isOptional: true,
        backdropConfig: {
          offset: 0,
        },
      },
      {
        anchorId: 'tour.rentshield-reason-picker',
        title: $localize`Notice date & reason`,
        content: $localize`Pick the statutory ground (sale, personal use, demolition, renovation -- Article 25(2)) or a breach ground (non-payment, unauthorized subleasing -- Article 25(1)). RentShield applies the correct notice period and legal warning for whichever you choose.`,
        route: '/notice/new',
        delayAfterNavigation: 500,
        isOptional: true,
      },
      {
        anchorId: 'tour.rentshield-addons',
        title: $localize`Optional add-ons`,
        content: $localize`Route the notice through a licensed notary, or request an AI compliance review of an uploaded tenancy contract against Article 25 -- both optional, priced separately, and tracked on the notice itself.`,
        route: '/notice/new',
        isOptional: true,
      },
      {
        anchorId: 'tour.rentshield-notices',
        title: $localize`Every notice you've generated`,
        content: $localize`See every notice you've generated in one place, with its reason, notice period, add-ons, and notarization status.`,
        route: '/notice/new',
        isOptional: true,
        backdropConfig: {
          offset: 0,
        },
      },
      {
        anchorId: 'tour.rentshield-notices-stats',
        title: $localize`At a glance`,
        content: $localize`Total notices, the statutory/breach split, and how many have been through AI review -- computed live from your own documents, not a separate count to keep in sync.`,
        route: '/notices',
        delayAfterNavigation: 500,
        isOptional: true,
      },
      {
        anchorId: 'tour.rentshield-notices-table',
        content: $localize`Every notice is a real paperless-ngx Document -- click through to open it, and you get full OCR text, search, tags, and version history like anything else in your document vault.`,
        route: '/notices',
        isOptional: true,
      },
      {
        anchorId: 'tour.rentshield-legal-skills',
        title: $localize`Legal Skills`,
        content: $localize`Reference guidance beyond notice drafting -- RDSC filing, security deposit disputes, and which notice-service methods Article 25(3) actually recognizes.`,
        route: '/notices',
        isOptional: true,
        backdropConfig: {
          offset: 0,
        },
      },
      {
        anchorId: 'tour.rentshield-legal-skills-list',
        content: $localize`Draft/reference guidance only, not a substitute for advice from a licensed UAE lawyer -- but a fast way to check the basics before you file.`,
        route: '/legal-skills',
        delayAfterNavigation: 500,
        isOptional: true,
      },
      {
        anchorId: 'tour.documents',
        content: $localize`The documents list shows all of your documents and allows for filtering as well as bulk-editing. There are three different view styles: list, small cards and large cards. A list of documents currently opened for editing is shown in the sidebar.`,
        route: '/documents?sort=created&reverse=1&page=1',
        delayAfterNavigation: 500,
        placement: 'bottom',
      },
      {
        anchorId: 'tour.documents-filter-editor',
        content: $localize`The filtering tools allow you to quickly find documents using various searches, dates, tags, etc.`,
        route: '/documents?sort=created&reverse=1&page=1',
        placement: 'bottom',
      },
      {
        anchorId: 'tour.documents-views',
        content: $localize`Any combination of filters can be saved as a 'view' which can then be displayed on the dashboard and / or sidebar.`,
        route: '/documents?sort=created&reverse=1&page=1',
      },
      {
        anchorId: 'tour.tags',
        content: $localize`Attributes like tags, correspondents, document types, storage paths and custom fields can all be managed here. They can also be created from the document edit view.`,
        route: '/attributes/tags',
        backdropConfig: {
          offset: 0,
        },
      },
      {
        anchorId: 'tour.mail',
        content: $localize`Manage e-mail accounts and rules for automatically importing documents.`,
        route: '/mail',
        backdropConfig: {
          offset: 0,
        },
      },
      {
        anchorId: 'tour.workflows',
        content: $localize`Workflows give you more control over the document pipeline.`,
        route: '/workflows',
        backdropConfig: {
          offset: 0,
        },
      },
      {
        anchorId: 'tour.file-tasks',
        content: $localize`Tasks helps you track background work, what needs attention, and what recently completed.`,
        route: '/tasks',
        backdropConfig: {
          offset: 0,
        },
      },
      {
        anchorId: 'tour.settings',
        content: $localize`Check out the settings for various tweaks to the web app.`,
        route: '/settings',
        backdropConfig: {
          offset: 0,
        },
      },
      {
        anchorId: 'tour.outro',
        title: $localize`Thank you! 🙏`,
        content:
          $localize`There are <em>tons</em> more features and info we didn't cover here, but this should get you started. Check out the documentation or visit the project on GitHub to learn more or to report issues.` +
          '<br/><br/>' +
          $localize`Lastly, on behalf of every contributor to this community-supported project, thank you for using Paperless-ngx!`,
        route: '/dashboard',
        isOptional: false,
        backdropConfig: {
          offset: 0,
        },
      },
    ])

    this.tourService.start$.subscribe(() => {
      this.renderer.addClass(document.body, 'tour-active')

      this.tourService.end$.pipe(first()).subscribe(() => {
        this.settings.completeTour()
        // animation time
        setTimeout(() => {
          this.renderer.removeClass(document.body, 'tour-active')
        }, 500)
      })
    })
  }
}
