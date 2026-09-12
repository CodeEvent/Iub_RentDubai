import SwiftUI

/// Face ID here is a local "confirm it's you unlocking this phone" gate
/// (LocalAuthentication) -- not a step that verifies identity against the
/// passport. See FaceIDAuthenticator.swift's header comment for why that
/// distinction is real, not just wording.
struct FaceIDGateView: View {
    @EnvironmentObject private var appState: AppFlowState

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "faceid")
                .font(.system(size: 64))
            Text("Confirm it's you to continue")
                .font(.headline)
            Button("Continue") {
                Task { await appState.runFaceIDGate() }
            }
            .buttonStyle(.borderedProminent)
        }
        .padding()
    }
}
