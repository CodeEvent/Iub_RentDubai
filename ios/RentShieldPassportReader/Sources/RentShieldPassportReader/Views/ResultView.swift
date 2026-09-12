import SwiftUI

struct ResultView: View {
    @EnvironmentObject private var appState: AppFlowState

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: icon)
                .font(.system(size: 64))
                .foregroundStyle(color)
            Text(title)
                .font(.title2.bold())
            Text("An admin can review the full submission, including your passport chip photo and selfie, from RentShield's Identity Verification Admin page.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Button("Done") { appState.reset() }
                .buttonStyle(.bordered)
        }
        .padding()
    }

    private var title: String {
        switch appState.resultStatus {
        case "verified": return "Verified"
        case "failed": return "Verification failed"
        case "manual_review": return "Under manual review"
        default: return "Submitted -- processing"
        }
    }

    private var icon: String {
        switch appState.resultStatus {
        case "verified": return "checkmark.circle.fill"
        case "failed": return "xmark.circle.fill"
        default: return "clock.fill"
        }
    }

    private var color: Color {
        switch appState.resultStatus {
        case "verified": return .green
        case "failed": return .red
        default: return .orange
        }
    }
}
