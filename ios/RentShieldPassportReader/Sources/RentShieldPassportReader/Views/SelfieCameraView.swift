import SwiftUI
import UIKit

/// Native `UIImagePickerController` camera -- same "use the platform's own
/// camera, don't build a custom capture UI" choice already made for the
/// web app (native `<input type=file capture>`), just the iOS-native
/// equivalent of that same idea.
struct SelfieCameraView: View {
    @EnvironmentObject private var appState: AppFlowState
    @State private var showCamera = true

    var body: some View {
        CameraPicker { image in
            showCamera = false
            if let image {
                Task { await appState.submitSelfie(image) }
            }
        }
    }
}

private struct CameraPicker: UIViewControllerRepresentable {
    let onCapture: (UIImage?) -> Void

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.cameraDevice = .front
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(onCapture: onCapture)
    }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let onCapture: (UIImage?) -> Void

        init(onCapture: @escaping (UIImage?) -> Void) {
            self.onCapture = onCapture
        }

        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            onCapture(info[.originalImage] as? UIImage)
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            onCapture(nil)
        }
    }
}
