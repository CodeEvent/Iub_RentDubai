import Foundation

/// Mirrors what the web app already sends from `navigator.geolocation` --
/// evidence of where verification happened for the admin review page, never
/// a gate on the result. `nil` (permission denied, no fix yet) is a normal,
/// silently-accepted outcome here too.
struct CapturedLocation {
    let latitude: Double
    let longitude: Double
    let accuracyMeters: Double?
}
