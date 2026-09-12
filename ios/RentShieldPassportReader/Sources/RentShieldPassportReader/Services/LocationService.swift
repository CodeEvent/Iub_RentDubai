import CoreLocation

/// One-shot best-effort location fetch, matching the web app's
/// `navigator.geolocation.getCurrentPosition()` call in
/// identity-verification.component.ts: try once with a short timeout,
/// return nil on denial/timeout/error rather than blocking verification.
final class LocationService: NSObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private var continuation: CheckedContinuation<CapturedLocation?, Never>?

    override init() {
        super.init()
        manager.delegate = self
    }

    func requestOnce() async -> CapturedLocation? {
        await withCheckedContinuation { continuation in
            self.continuation = continuation
            manager.requestWhenInUseAuthorization()
            manager.requestLocation()

            DispatchQueue.main.asyncAfter(deadline: .now() + 8) { [weak self] in
                self?.finish(nil)
            }
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else { return finish(nil) }
        finish(
            CapturedLocation(
                latitude: location.coordinate.latitude,
                longitude: location.coordinate.longitude,
                accuracyMeters: location.horizontalAccuracy >= 0 ? location.horizontalAccuracy : nil
            )
        )
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        finish(nil)
    }

    /// First-ever launch: the permission dialog is still pending when
    /// `requestLocation()` is first called above, so it's retried here
    /// once the user actually answers it (rather than only relying on the
    /// blanket timeout for what should be a normal case).
    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        switch manager.authorizationStatus {
        case .authorizedWhenInUse, .authorizedAlways:
            manager.requestLocation()
        case .denied, .restricted:
            finish(nil)
        default:
            break
        }
    }

    private func finish(_ result: CapturedLocation?) {
        continuation?.resume(returning: result)
        continuation = nil
    }
}
