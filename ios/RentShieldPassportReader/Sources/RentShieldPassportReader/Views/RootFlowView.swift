import SwiftUI

struct RootFlowView: View {
    @StateObject private var appState = AppFlowState()

    var body: some View {
        NavigationStack {
            Group {
                switch appState.step {
                case .login:
                    LoginView().environmentObject(appState)
                case .faceIDGate:
                    FaceIDGateView().environmentObject(appState)
                case .passportEntry:
                    PassportEntryView().environmentObject(appState)
                case .scanningChip:
                    ProgressView("Hold your passport against the top of your phone…")
                        .padding()
                case .takingSelfie:
                    SelfieCameraView().environmentObject(appState)
                case .uploading:
                    ProgressView("Verifying…").padding()
                case .result:
                    ResultView().environmentObject(appState)
                }
            }
            .navigationTitle("RentShield Verification")
            .alert(
                "Error",
                isPresented: .constant(appState.errorMessage != nil),
                actions: { Button("OK") { appState.errorMessage = nil } },
                message: { Text(appState.errorMessage ?? "") }
            )
        }
    }
}
