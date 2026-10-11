import CryptoKit
import Darwin
import Foundation
import ShuttlAnalysis
import ShuttlCore
import ShuttlLive
import ShuttlRuntime

@main
struct EnduranceDriver {
    static func main() async throws {
        let args = Array(CommandLine.arguments.dropFirst())
        if args.first == "makeclip" {
            guard args.count >= 5, let seconds = Double(args[1]) else {
                fputs("usage: EnduranceDriver makeclip <seconds> <out> <h264|hevc> <source...>\n", stderr)
                exit(2)
            }
            try await makeClip(seconds: seconds, output: URL(fileURLWithPath: args[2]),
                               sources: args.dropFirst(4).map { URL(fileURLWithPath: $0) }, codec: args[3])
            return
        }
        if args.first == "resave", args.count >= 3, let id = UUID(uuidString: args[2]) {
            try resave(runDir: URL(fileURLWithPath: args[1], isDirectory: true), id: id)
            return
        }
        guard args.count >= 4, args[0] == "analyze" else {
            fputs("usage: EnduranceDriver analyze <video> <run-dir> <match-uuid> [doubles|singles]\n", stderr)
            exit(2)
        }
        let video = URL(fileURLWithPath: args[1])
        let runDir = URL(fileURLWithPath: args[2], isDirectory: true)
        let id = UUID(uuidString: args[3]) ?? UUID()
        let doubles: Bool? = args.count > 4 ? (args[4] == "doubles") : nil
        let fm = FileManager.default
        try fm.createDirectory(at: runDir, withIntermediateDirectories: true)
        let archive = AnalysisArchive(analysesDirectory: runDir.appendingPathComponent("archive"),
                                      checkpointsDirectory: runDir.appendingPathComponent("checkpoints"))
        let options = PipelineOptions(doubles: doubles)
        let fileStore = archive.checkpointStore(matchID: id, video: video, build: "endurance-11", options: options)
        let killer = Killer(spec: ProcessInfo.processInfo.environment["ENDURANCE_KILL"],
                            logURL: runDir.appendingPathComponent("kills.log"))
        if !fm.fileExists(atPath: runDir.appendingPathComponent("kills.log").path) {
            fm.createFile(atPath: runDir.appendingPathComponent("kills.log").path, contents: nil)
        }
        let events = EventLog(url: runDir.appendingPathComponent("events.log"), killer: killer)
        events.emit("attempt_start", "video=\(video.lastPathComponent) doubles=\(doubles.map { "\($0)" } ?? "nil") kill=\(ProcessInfo.processInfo.environment["ENDURANCE_KILL"] ?? "none")")
        let store = TracingStore(inner: fileStore, events: events)
        let metrics = runDir.appendingPathComponent("live-stage-metrics.jsonl")
        let models = EnduranceSupport.modelsDirectory()
        let stages = try await LiveStages.make(modelsDirectory: models,
            cacheDirectory: URL(fileURLWithPath: "/tmp/luna11/model-cache"), metricsURL: metrics)
        let sampler = ResourceSampler(logs: false)
        let observer = EnduranceObserver(sampler: sampler, stateURL: runDir.appendingPathComponent("stage-state.txt"), events: events)
        let pipeline = AnalysisPipeline(stages: stages, checkpoints: store, observer: observer)
        let csvURL = runDir.appendingPathComponent("memory.csv")
        if !fm.fileExists(atPath: csvURL.path) { fm.createFile(atPath: csvURL.path, contents: nil) }
        let csv = try FileHandle(forWritingTo: csvURL)
        try csv.seekToEnd()
        if try csv.offset() == 0 {
            try csv.write(contentsOf: Data("pid,elapsed_seconds,phys_footprint_mb,peak_phys_footprint_mb,checkpoint_bytes,stage\n".utf8))
        }
        let start = ProcessInfo.processInfo.systemUptime
        let queue = DispatchQueue(label: "endurance.sample")
        let sizeLock = NSLock()
        var maxCheckpointBytes: Int64 = 0
        let timer = DispatchSource.makeTimerSource(queue: queue)
        timer.schedule(deadline: .now(), repeating: 1)
        timer.setEventHandler {
            let snapshot = ResourceSnapshot.now()
            let bytes = EnduranceSupport.totalBytes(archive.checkpointDirectory(matchID: id))
            sizeLock.lock(); maxCheckpointBytes = max(maxCheckpointBytes, bytes); sizeLock.unlock()
            let line = String(format: "%d,%.1f,%.1f,%.1f,%lld,%@\n", getpid(), ProcessInfo.processInfo.systemUptime - start,
                              snapshot.physFootprintMB, snapshot.peakPhysFootprintMB, bytes, observer.currentStage)
            try? csv.write(contentsOf: Data(line.utf8))
        }
        timer.resume()
        let lastPct = LastPercent()
        let result = try await pipeline.analyze(video, options: options) { p in
            // One event per 0.5 % of overall progress (the kill spec compares against it).
            if lastPct.advance(to: Int(p.fraction * 200)) {
                events.emit("progress", String(format: "%.4f %@", p.fraction, p.stage))
            }
        }
        events.emit("attempt_done", String(format: "%.3f", result.processingTimeSeconds))
        timer.cancel(); queue.sync {}; try? csv.close()
        let jsonURL = try archive.save(result, matchID: id)
        var comparable = result
        comparable.players = []; comparable.processingTimeSeconds = 0; comparable.diagnostics = [:]
        try ShuttlJSON.encoder().encode(result.diagnostics).write(to: runDir.appendingPathComponent("diagnostics.json"), options: .atomic)
        let compactJSON = try ShuttlJSON.encoder().encode(comparable)
        try compactJSON.write(to: runDir.appendingPathComponent("semantic-result.json"), options: .atomic)
        let playerFile = runDir.appendingPathComponent("players-comparable.bin")
        try PlayersCodec.write(result.players, to: playerFile, fingerprint: "endurance-v1", includeKeypoints: true)
        let peakCheckpointBytes = sizeLock.withLock { maxCheckpointBytes }
        let summary = try EnduranceSupport.summary(result, archive: archive, matchID: id, jsonURL: jsonURL,
            checkpointSizes: ["final": EnduranceSupport.totalBytes(archive.checkpointDirectory(matchID: id)),
                              "peak_during_run": peakCheckpointBytes], playerFile: playerFile, semanticBytes: compactJSON.count)
        let data = try JSONSerialization.data(withJSONObject: summary, options: [.prettyPrinted, .sortedKeys])
        try data.write(to: runDir.appendingPathComponent("summary.json"), options: .atomic)
        print(String(data: data, encoding: .utf8) ?? "{}")
    }
}

/// Monotonic "last reported step" for throttling progress events.
final class LastPercent: @unchecked Sendable {
    private let lock = NSLock()
    private var last = -1
    func advance(to v: Int) -> Bool { lock.withLock { if v > last { last = v; return true }; return false } }
}
