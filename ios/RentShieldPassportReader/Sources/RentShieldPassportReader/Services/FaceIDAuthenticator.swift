import LocalAuthentication

/// Important limit, stated once here in code (see also SETUP.md and the
/// README): this ONLY confirms "the person holding this phone can unlock
/// it" -- Apple's LocalAuthentication API returns a plain yes/no and never
/// exposes any biometric data to the app. It cannot be compared against a
/// passport photo or chip, on this or any platform. It is a convenience
/// gate before verification starts, not a step in verifying identity --
/// that happens later, by matching the live selfie against the passport
/// chip's own photo (PassportNFCService + the existing Idswyft face-match
/// step on the backend).
enum FaceIDAuthenticator {
    static func authenticate() async -> Bool {
        let context = LAContext()
        var error: NSError?
        guard context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) else {
            return false
        }
        return await withCheckedContinuation { continuation in
            context.evaluatePolicy(
                .deviceOwnerAuthentication,
                localizedReason: "Confirm it's you before starting identity verification."
            ) { success, _ in
                continuation.resume(returning: success)
            }
        }
    }
}
