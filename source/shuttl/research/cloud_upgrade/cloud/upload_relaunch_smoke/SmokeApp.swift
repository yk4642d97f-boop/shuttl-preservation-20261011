import Foundation
import SwiftUI
import CryptoKit

// Standalone simulator fixture: only the API error vocabulary is substituted.
// The uploader, transport, file store, and application delegate compile from the real app sources.
enum APIError: Error { case uploadFailed(String), networkError(Error), timeout }

@MainActor
final class SmokeState: ObservableObject {
    @Published var text = "starting"
    private let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    private var started = false

    func run() async {
        guard !started else { return }; started = true
        let config = documents.appendingPathComponent("target.txt")
        let video = documents.appendingPathComponent("fixture.mov")
        let report = documents.appendingPathComponent("smoke.json")
        do {
            if let target = ProcessInfo.processInfo.environment["UPLOAD_SMOKE_URL"] {
                guard URL(string: target)?.host == "127.0.0.1" else { throw URLError(.badURL) }
                try target.write(to: config, atomically: true, encoding: .utf8)
            }
            let target = URL(string: try String(contentsOf: config, encoding: .utf8))!
            if !FileManager.default.fileExists(atPath: video.path) {
                let block = Data((0..<(64 * 1024)).map { UInt8($0 % 251) })
                FileManager.default.createFile(atPath: video.path, contents: nil)
                let handle = try FileHandle(forWritingTo: video)
                for _ in 0..<256 { try handle.write(contentsOf: block) }
                try handle.close()
            }
            var state = (try? JSONSerialization.jsonObject(with: Data(contentsOf: report)) as? [String: Any]) ?? [:]
            state["launches"] = (state["launches"] as? Int ?? 0) + 1
            state["pid"] = ProcessInfo.processInfo.processIdentifier
            state["state"] = "uploading"
            try JSONSerialization.data(withJSONObject: state, options: [.sortedKeys]).write(to: report, options: .atomic)
            text = "uploading"
            try await VideoUploadService.shared.upload(key: "standalone-relaunch-fixture", fileURL: video, target: {
                await MainActor.run {
                    var state = (try? JSONSerialization.jsonObject(with: Data(contentsOf: report)) as? [String: Any]) ?? [:]
                    state["target_requests"] = (state["target_requests"] as? Int ?? 0) + 1
                    try? JSONSerialization.data(withJSONObject: state, options: [.sortedKeys]).write(to: report, options: .atomic)
                }
                return target
            }, progress: { _ in })
            var final = (try? JSONSerialization.jsonObject(with: Data(contentsOf: report)) as? [String: Any]) ?? [:]
            final["state"] = "done"
            final["sha256"] = SHA256.hash(data: try Data(contentsOf: video)).map { String(format: "%02x", $0) }.joined()
            try JSONSerialization.data(withJSONObject: final, options: [.sortedKeys]).write(to: report, options: .atomic)
            text = "done"
        } catch {
            text = "failed: \(error)"
            let state: [String: Any] = ["state": "failed", "error": String(describing: error)]
            try? JSONSerialization.data(withJSONObject: state, options: [.sortedKeys]).write(to: report, options: .atomic)
        }
    }
}

@main
struct UploadSmokeApp: App {
    @UIApplicationDelegateAdaptor(ShuttlAppDelegate.self) private var delegate
    @StateObject private var state = SmokeState()
    var body: some Scene {
        WindowGroup { Text(state.text).padding().task { await state.run() } }
    }
}
