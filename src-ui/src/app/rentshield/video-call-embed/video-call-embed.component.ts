import { Component, ElementRef, Input, OnChanges, OnDestroy, ViewChild, signal } from '@angular/core'

// Wraps the Jitsi Meet External API (https://jitsi.github.io/handbook/
// docs/dev-guide/dev-guide-iframe) around this project's self-hosted
// instance (docker-compose.yml's jitsi-web et al.) -- used by both
// identity-verification.component (the property owner) and
// identity-admin.component (the Notary) instead of duplicating the
// embed logic, same "shared primitive" reasoning as
// rentshield-shared.scss. `roomName`/`jitsiBaseUrl` come straight off
// the VideoCall the backend already returned (see
// IdentityVerificationCall.to_dict()) -- this component doesn't know
// or guess either on its own.
declare global {
  interface Window {
    JitsiMeetExternalAPI?: new (domain: string, options: Record<string, unknown>) => { dispose(): void }
  }
}

// Cache the script-loading promise across every instance of this
// component on the page -- Jitsi's own external_api.js isn't meant to
// be injected twice, and a Notary reviewing several records could
// otherwise mount/unmount this component many times in one session.
let scriptLoadPromise: Promise<void> | null = null

function loadJitsiScript(baseUrl: string): Promise<void> {
  if (window.JitsiMeetExternalAPI) return Promise.resolve()
  if (!scriptLoadPromise) {
    scriptLoadPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script')
      script.src = `${baseUrl}/external_api.js`
      script.async = true
      script.onload = () => resolve()
      script.onerror = () => {
        scriptLoadPromise = null
        reject(new Error('Could not load the video call -- try again shortly.'))
      }
      document.head.appendChild(script)
    })
  }
  return scriptLoadPromise
}

@Component({
  selector: 'app-video-call-embed',
  standalone: true,
  imports: [],
  templateUrl: './video-call-embed.component.html',
  styleUrl: './video-call-embed.component.scss',
})
export class VideoCallEmbedComponent implements OnChanges, OnDestroy {
  @Input({ required: true }) roomName!: string
  @Input({ required: true }) jitsiBaseUrl!: string
  @Input() displayName = ''

  @ViewChild('container', { static: true }) container!: ElementRef<HTMLDivElement>

  // A signal, not a plain property -- the load/error outcome arrives
  // via a dynamically-created <script> tag's onload/onerror, not
  // through an Angular-aware API (HttpClient, Router, etc.), so a
  // plain property write here isn't guaranteed to schedule a re-render.
  error = signal<string | null>(null)
  private api: { dispose(): void } | null = null
  private mountedRoomName: string | null = null

  ngOnChanges(): void {
    if (this.roomName && this.roomName !== this.mountedRoomName) {
      this.mount()
    }
  }

  private mount(): void {
    this.dispose()
    this.error.set(null)
    const baseUrl = this.jitsiBaseUrl
    const domain = baseUrl.replace(/^https?:\/\//, '')
    loadJitsiScript(baseUrl)
      .then(() => {
        if (!window.JitsiMeetExternalAPI) throw new Error('Video call script did not load correctly.')
        this.api = new window.JitsiMeetExternalAPI(domain, {
          roomName: this.roomName,
          parentNode: this.container.nativeElement,
          userInfo: this.displayName ? { displayName: this.displayName } : undefined,
          width: '100%',
          height: 480,
        })
        this.mountedRoomName = this.roomName
      })
      .catch((err: Error) => {
        this.error.set(err.message)
      })
  }

  private dispose(): void {
    this.api?.dispose()
    this.api = null
    this.mountedRoomName = null
  }

  ngOnDestroy(): void {
    this.dispose()
  }
}
