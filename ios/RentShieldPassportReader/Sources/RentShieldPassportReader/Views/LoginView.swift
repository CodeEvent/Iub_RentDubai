import SwiftUI

struct LoginView: View {
    @EnvironmentObject private var appState: AppFlowState
    @State private var username = ""
    @State private var password = ""
    @State private var loggingIn = false

    var body: some View {
        Form {
            Section("RentShield server") {
                TextField("http://192.168.0.120:8000", text: $appState.serverURLString)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                Text("The address your RentShield server is reachable at from this phone -- not localhost, this is a different device.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Section("Account") {
                TextField("Username", text: $username)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                SecureField("Password", text: $password)
            }
            Section {
                Button {
                    loggingIn = true
                    Task {
                        await appState.login(username: username, password: password)
                        loggingIn = false
                    }
                } label: {
                    if loggingIn {
                        ProgressView()
                    } else {
                        Text("Sign in")
                    }
                }
                .disabled(username.isEmpty || password.isEmpty || loggingIn)
            }
        }
    }
}
