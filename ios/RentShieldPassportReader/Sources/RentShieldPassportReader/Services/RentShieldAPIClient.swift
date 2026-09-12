import Foundation

/// Talks to the exact same Django/DRF endpoints the Angular web app already
/// uses (documents/rentshield_identity/views.py) -- this app doesn't add any
/// new backend surface, it's just a native front door that can read the
/// passport chip instead of photographing the bio page.
///
/// Auth is DRF token auth (POST /api/token/, then `Authorization: Token …`
/// on everything else) rather than session cookies -- there's no shared
/// cookie jar with a browser here, and paperless-ngx already exposes token
/// auth for exactly this kind of native client (this project used it for
/// its own backend verification curl calls during development).
struct VerificationStatus: Decodable {
    let status: String?
    let step: String?
}

enum APIError: LocalizedError {
    case server(String)
    case invalidResponse

    var errorDescription: String? {
        switch self {
        case .server(let message): return message
        case .invalidResponse: return "Unexpected response from RentShield."
        }
    }
}

final class RentShieldAPIClient {
    /// Set on the login screen and persisted -- deliberately NOT hardcoded.
    /// A hardcoded `localhost` here would repeat the exact bug this project
    /// already hit once with Idswyft's QR code pointing at a URL only the
    /// laptop itself could reach: this device is a separate piece of
    /// hardware on the network and needs the server's real LAN/public
    /// address, e.g. "http://192.168.0.120:8000" or a real HTTPS domain.
    var baseURL: URL
    private var token: String?

    init(baseURL: URL, token: String? = nil) {
        self.baseURL = baseURL
        self.token = token
    }

    func login(username: String, password: String) async throws -> String {
        var request = URLRequest(url: baseURL.appendingPathComponent("api/token/"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(["username": username, "password": password])

        let (data, response) = try await URLSession.shared.data(for: request)
        try Self.checkOK(response, data: data)

        struct TokenResponse: Decodable { let token: String }
        let decoded = try JSONDecoder().decode(TokenResponse.self, from: data)
        self.token = decoded.token
        return decoded.token
    }

    func startVerification() async throws -> VerificationStatus {
        try await authedJSON(path: "api/documents/identity/verify/start/", method: "POST")
    }

    func status() async throws -> VerificationStatus {
        try await authedJSON(path: "api/documents/identity/verify/status/", method: "GET")
    }

    /// `chipPhoto` is the DG2 face image read straight off the passport
    /// chip (see PassportNFCService) -- a clean, uncompressed photo, unlike
    /// a phone photo of the printed bio page fighting glare/blur, so this
    /// should genuinely OCR/match better even though it's the same backend
    /// field the web app's photographed-passport-page flow already uses.
    func uploadFrontDocument(chipPhotoJPEG: Data, location: CapturedLocation?) async throws -> VerificationStatus {
        try await uploadMultipart(
            path: "api/documents/identity/verify/front-document/",
            fileFieldName: "document",
            filename: "passport-chip-photo.jpg",
            mimeType: "image/jpeg",
            fileData: chipPhotoJPEG,
            location: location
        )
    }

    func uploadLiveCapture(selfieJPEG: Data, location: CapturedLocation?) async throws -> VerificationStatus {
        try await uploadMultipart(
            path: "api/documents/identity/verify/live-capture/",
            fileFieldName: "selfie",
            filename: "selfie.jpg",
            mimeType: "image/jpeg",
            fileData: selfieJPEG,
            location: location
        )
    }

    // MARK: - Internals

    private func authedJSON(path: String, method: String) async throws -> VerificationStatus {
        guard let token else { throw APIError.server("Not logged in.") }
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = method
        request.setValue("Token \(token)", forHTTPHeaderField: "Authorization")

        let (data, response) = try await URLSession.shared.data(for: request)
        try Self.checkOK(response, data: data)
        return try JSONDecoder().decode(VerificationStatus.self, from: data)
    }

    private func uploadMultipart(
        path: String,
        fileFieldName: String,
        filename: String,
        mimeType: String,
        fileData: Data,
        location: CapturedLocation?
    ) async throws -> VerificationStatus {
        guard let token else { throw APIError.server("Not logged in.") }
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.setValue("Token \(token)", forHTTPHeaderField: "Authorization")

        let boundary = "RentShield-\(UUID().uuidString)"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        var body = Data()
        func addField(_ name: String, _ value: String) {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n".data(using: .utf8)!)
            body.append("\(value)\r\n".data(using: .utf8)!)
        }
        if let location {
            addField("latitude", String(location.latitude))
            addField("longitude", String(location.longitude))
            if let accuracy = location.accuracyMeters {
                addField("location_accuracy_m", String(accuracy))
            }
        }
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append(
            "Content-Disposition: form-data; name=\"\(fileFieldName)\"; filename=\"\(filename)\"\r\n"
                .data(using: .utf8)!
        )
        body.append("Content-Type: \(mimeType)\r\n\r\n".data(using: .utf8)!)
        body.append(fileData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        let (data, response) = try await URLSession.shared.data(for: request)
        try Self.checkOK(response, data: data)
        return try JSONDecoder().decode(VerificationStatus.self, from: data)
    }

    private static func checkOK(_ response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200..<300).contains(http.statusCode) else {
            struct ErrorBody: Decodable { let error: String? }
            let message = (try? JSONDecoder().decode(ErrorBody.self, from: data))?.error
                ?? "Server returned \(http.statusCode)."
            throw APIError.server(message)
        }
    }
}
