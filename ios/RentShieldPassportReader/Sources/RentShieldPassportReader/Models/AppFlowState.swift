import Foundation
import SwiftUI
import UIKit

enum FlowStep {
    case login
    case faceIDGate
    case passportEntry
    case scanningChip
    case takingSelfie
    case uploading
    case result
}

@MainActor
final class AppFlowState: ObservableObject {
    @Published var step: FlowStep = .login
    @Published var errorMessage: String?
    @Published var resultStatus: String?

    @AppStorage("rentshield_server_url") var serverURLString: String = ""

    private var api: RentShieldAPIClient?
    private let locationService = LocationService()
    private let passportService = PassportNFCService()
    private var chipPhotoJPEG: Data?

    func login(username: String, password: String) async {
        guard let url = URL(string: serverURLString), !serverURLString.isEmpty else {
            errorMessage = "Enter your RentShield server address first (e.g. http://192.168.0.120:8000) -- not localhost, this phone is a separate device on the network."
            return
        }
        let client = RentShieldAPIClient(baseURL: url)
        do {
            _ = try await client.login(username: username, password: password)
            api = client
            errorMessage = nil
            step = .faceIDGate
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func runFaceIDGate() async {
        let ok = await FaceIDAuthenticator.authenticate()
        if ok {
            step = .passportEntry
        } else {
            errorMessage = "Face ID/passcode confirmation is required to continue."
        }
    }

    func scanPassport(passportNumber: String, dateOfBirth: Date, dateOfExpiry: Date) async {
        step = .scanningChip
        do {
            let result = try await passportService.readPassport(
                passportNumber: passportNumber, dateOfBirth: dateOfBirth, dateOfExpiry: dateOfExpiry
            )
            guard let chipPhoto = result.chipPhoto, let jpeg = chipPhoto.jpegData(compressionQuality: 0.9) else {
                throw PassportNFCError.noPhotoOnChip
            }
            chipPhotoJPEG = jpeg
            errorMessage = nil
            step = .takingSelfie
        } catch {
            errorMessage = error.localizedDescription
            step = .passportEntry
        }
    }

    func submitSelfie(_ selfie: UIImage) async {
        guard let api, let chipPhotoJPEG else {
            errorMessage = "Something went wrong -- restart verification."
            step = .login
            return
        }
        guard let selfieJPEG = selfie.jpegData(compressionQuality: 0.9) else {
            errorMessage = "Could not process that photo -- try again."
            return
        }

        step = .uploading
        let location = await locationService.requestOnce()

        do {
            _ = try await api.startVerification()
            _ = try await api.uploadFrontDocument(chipPhotoJPEG: chipPhotoJPEG, location: location)
            let final = try await api.uploadLiveCapture(selfieJPEG: selfieJPEG, location: location)
            resultStatus = final.status
            step = .result
        } catch {
            errorMessage = error.localizedDescription
            step = .takingSelfie
        }
    }

    func reset() {
        step = .faceIDGate
        errorMessage = nil
        resultStatus = nil
        chipPhotoJPEG = nil
    }
}
