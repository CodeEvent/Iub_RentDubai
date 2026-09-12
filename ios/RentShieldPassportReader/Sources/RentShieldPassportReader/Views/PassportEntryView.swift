import SwiftUI

/// BAC (the handshake that unlocks the chip) needs three fields straight
/// off the passport's printed page to derive its key -- there's no way
/// around typing them once; the chip itself is what gets scanned next.
/// A camera-based MRZ auto-scan (Vision framework) would remove this
/// typing step but isn't built yet -- see SETUP.md's "not done" list.
struct PassportEntryView: View {
    @EnvironmentObject private var appState: AppFlowState
    @State private var passportNumber = ""
    @State private var dateOfBirth = Date()
    @State private var dateOfExpiry = Date()

    var body: some View {
        Form {
            Section("From your passport's printed page") {
                TextField("Passport number", text: $passportNumber)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled()
                DatePicker("Date of birth", selection: $dateOfBirth, displayedComponents: .date)
                DatePicker("Expiry date", selection: $dateOfExpiry, displayedComponents: .date)
            }
            Section {
                Button("Scan passport chip") {
                    Task {
                        await appState.scanPassport(
                            passportNumber: passportNumber,
                            dateOfBirth: dateOfBirth,
                            dateOfExpiry: dateOfExpiry
                        )
                    }
                }
                .disabled(passportNumber.isEmpty)
            } footer: {
                Text("You'll be asked to hold your passport's photo page against the top of your iPhone.")
            }
        }
    }
}
