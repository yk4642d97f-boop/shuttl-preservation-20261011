import CryptoKit
import Foundation
import ShuttlAnalysis
import ShuttlCore
import ShuttlRuntime

struct EnduranceSupport {
    static func modelsDirectory() -> URL {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        return root.appendingPathComponent("iOS/Packages/ShuttlDetector/Models")
    }
    static func totalBytes(_ url: URL) -> Int64 {
        guard let e = FileManager.default.enumerator(at: url, includingPropertiesForKeys: [.fileSizeKey]) else { return 0 }
        var n: Int64 = 0
        for case let f as URL in e { n += Int64((try? f.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0) }
        return n
    }
    static func fileSize(_ url: URL) -> Int64 {
        (try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber)?.int64Value ?? 0
    }
    static func sha256(file: URL) throws -> String {
        let h = try FileHandle(forReadingFrom: file); defer { try? h.close() }
        var digest = SHA256()
        while true {
            let data = try h.read(upToCount: 1 << 20) ?? Data()
            if data.isEmpty { break }
            digest.update(data: data)
        }
        return digest.finalize().map { String(format: "%02x", $0) }.joined()
    }
    static func summary(_ result: MatchAnalysis, archive: AnalysisArchive, matchID: UUID,
                        jsonURL: URL, checkpointSizes: [String: Int64], playerFile: URL,
                        semanticBytes: Int) throws -> [String: Any] {
        let shots = result.rallies.flatMap(\.shots).count
        let visible = result.track?.visible.filter { $0 }.count ?? 0
        return [
            "video_frames": result.meta.nFrames, "fps": result.meta.fps,
            "width": result.meta.width, "height": result.meta.height,
            "camera_found": result.camera != nil, "visible_frames": visible,
            "hits": result.hits.count, "rallies": result.rallies.count, "shots": shots,
            "players": result.players.count, "players_sha256": try sha256(file: playerFile),
            "players_comparable_bytes": fileSize(playerFile),
            "score": try JSONSerialization.jsonObject(with: ShuttlJSON.encoder().encode(result.score)),
            "pipeline_seconds": result.processingTimeSeconds,
            "stage_diagnostics": try JSONSerialization.jsonObject(with: ShuttlJSON.encoder().encode(result.diagnostics)),
            "archive_json_bytes": fileSize(jsonURL),
            "players_bin_bytes": fileSize(archive.playersURL(matchID: matchID)),
            "checkpoint_bytes": checkpointSizes, "semantic_result_json_bytes": semanticBytes,
        ]
    }
}

final class EnduranceObserver: StageObserver, @unchecked Sendable {
    private let lock = NSLock()
    private var stage = "idle"
    private let sampler: ResourceSampler
    private let stateURL: URL
    private let events: EventLog
    init(sampler: ResourceSampler, stateURL: URL, events: EventLog) {
        self.sampler = sampler; self.stateURL = stateURL; self.events = events
    }
    var currentStage: String { lock.withLock { stage } }
    func stageDidStart(_ name: String) {
        lock.withLock { stage = name }
        try? Data(name.utf8).write(to: stateURL, options: .atomic)
        sampler.stageDidStart(name)
        events.emit("stage_start", name)
    }
    func stageDidFinish(_ name: String, seconds: Double) {
        sampler.stageDidFinish(name, seconds: seconds)
        lock.withLock { stage = "idle" }
        events.emit("stage_finish", String(format: "%@ %.3f", name, seconds))
    }
    func stageDiagnostics(_ name: String) -> [String: JSONValue] { sampler.stageDiagnostics(name) }
}
