import Foundation
import ShuttlAnalysis
import ShuttlCore
import ShuttlLive

/// Holds the analysis Task so observers / stores can cancel it with a real `Task.cancel()`.
final class LiveHolder: @unchecked Sendable {
    private let lock = NSLock()
    private var task: Task<MatchAnalysis, Error>?
    private var pending = false
    private(set) var cancelledAt: Date?
    private(set) var cancelledStage: String?
    var currentStage = ""
    func install(_ t: Task<MatchAnalysis, Error>) {
        let now: Bool = lock.withLock { task = t; return pending }
        if now { t.cancel() }
    }
    func cancel(reason: String) {
        let t: Task<MatchAnalysis, Error>? = lock.withLock {
            if cancelledAt == nil { cancelledAt = Date(); cancelledStage = reason }
            pending = true; return task
        }
        t?.cancel()
    }
}

/// Cancels `delayMs` after `target` starts (the first time), from another task.
struct LiveCancelObserver: StageObserver {
    let target: String?; let delayMs: Int; let holder: LiveHolder
    var snapshot: (stage: String, from: URL, to: URL)? = nil
    func stageDidStart(_ name: String) {
        holder.currentStage = name
        if let s = snapshot, s.stage == name {      // copy the checkpoint store before finish() clears it
            try? FileManager.default.removeItem(at: s.to)
            try? FileManager.default.copyItem(at: s.from, to: s.to)
        }
        guard name == target else { return }
        let h = holder, d = delayMs
        Task.detached { try? await Task.sleep(for: .milliseconds(d)); h.cancel(reason: "\(name)+\(d)ms") }
    }
    func stageDidFinish(_ name: String, seconds: Double) {}
}

/// The app's FileCheckpointStore, plus: cancel right after the Nth detect-partial save.
struct CancellingStore: CheckpointStore, DetectPartialStore {
    let base: FileCheckpointStore; let cancelAfterPartial: Int?; let holder: LiveHolder; let counter = Counter()
    func load<T: Decodable>(_ type: T.Type, key: String) -> T? { base.load(type, key: key) }
    func save<T: Encodable>(_ value: T, key: String) { base.save(value, key: key) }
    func clear() { base.clear() }
    func loadDetectPartial() -> DetectCheckpoint? { base.loadDetectPartial() }
    func clearDetectPartial() { base.clearDetectPartial() }
    func saveDetectPartial(_ c: DetectCheckpoint) {
        base.saveDetectPartial(c)
        if let n = cancelAfterPartial, counter.bump() == n { holder.cancel(reason: "detect_partial#\(n)@\(c.nextFrame)") }
    }
}
final class Counter: @unchecked Sendable {
    private let lock = NSLock(); private var n = 0
    func bump() -> Int { lock.withLock { n += 1; return n } }
}

/// `analyze <clip> [--store DIR] [--cancel-stage S --cancel-ms N] [--cancel-after-partial N] [--checkpoint-s X]`
/// One JSON line: returned summary, "cancelled" (with latency) or "clean_failure" (+ the app's message).
func liveAnalyze(_ args: [String]) async {
    let url = URL(fileURLWithPath: args[0])
    func opt(_ k: String) -> String? { args.firstIndex(of: k).flatMap { $0 + 1 < args.count ? args[$0 + 1] : nil } }
    let holder = LiveHolder()
    let t0 = Date()
    do {
        let env = ProcessInfo.processInfo.environment
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        var stages = try await LiveStages.make(modelsDirectory: root.appendingPathComponent("iOS/Packages/ShuttlDetector/Models"),
            cacheDirectory: URL(fileURLWithPath: "/tmp/luna10/models"),
            metricsURL: env["SHUTTL_STAGE_METRICS"].map(URL.init(fileURLWithPath:)))
        if let s = opt("--checkpoint-s").flatMap(Double.init) { stages.checkpointSeconds = s }
        let options = PipelineOptions()
        var store: CheckpointStore = NoCheckpoints()
        if let dir = opt("--store") {
            let attrs = try? FileManager.default.attributesOfItem(atPath: url.path)
            let fp = checkpointFingerprint(videoSize: (attrs?[.size] as? NSNumber)?.intValue ?? 0,
                                           modified: attrs?[.modificationDate] as? Date, build: "robustness-1", options: options)
            store = CancellingStore(base: FileCheckpointStore(directory: URL(fileURLWithPath: dir), fingerprint: fp),
                                    cancelAfterPartial: opt("--cancel-after-partial").flatMap(Int.init), holder: holder)
        }
        var observer = LiveCancelObserver(target: opt("--cancel-stage"), delayMs: opt("--cancel-ms").flatMap(Int.init) ?? 0, holder: holder)
        if let i = args.firstIndex(of: "--snapshot-at"), i + 2 < args.count, let dir = opt("--store") {
            observer.snapshot = (args[i + 1], URL(fileURLWithPath: dir), URL(fileURLWithPath: args[i + 2]))
        }
        let pipeline = AnalysisPipeline(stages: stages, checkpoints: store, observer: observer)
        let task = Task { try await pipeline.analyze(url, options: options) }
        holder.install(task)
        do {
            let r = try await task.value
            var s = try summary(r, clip: url.lastPathComponent, seconds: Date().timeIntervalSince(t0))
            if holder.cancelledAt != nil { s["cancel_requested"] = holder.cancelledStage ?? ""; s["cancel_ignored"] = true }
            emit(s)
        } catch is CancellationError {
            let lat = holder.cancelledAt.map { Date().timeIntervalSince($0) } ?? -1
            emit(["clip": url.lastPathComponent, "status": "cancelled", "cancel_at": holder.cancelledStage ?? "",
                  "stage_when_thrown": holder.currentStage, "cancel_latency_s": lat, "seconds": Date().timeIntervalSince(t0),
                  "peak_footprint_mb": peakFootprintMB()])
        }
    } catch {
        emit(["clip": url.lastPathComponent, "status": "clean_failure", "error": "\(type(of: error)): \(error)",
              "outcome": AnalysisOutcome.failure(error).userMessage, "app_done": false, "app_message": appThrownMessage(error),
              "seconds": Date().timeIntervalSince(t0), "peak_footprint_mb": peakFootprintMB()])
    }
}
