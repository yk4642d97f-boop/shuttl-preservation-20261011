import Darwin
import Foundation
import ShuttlAnalysis
import ShuttlCore

/// Timestamped event lines ("EVENT <t> <kind> <detail>") on stdout and in events.log, so
/// the matrix scripts know which stage / checkpoint write was in flight at a kill.
final class EventLog: @unchecked Sendable {
    private let lock = NSLock()
    private let handle: FileHandle?
    let start = ProcessInfo.processInfo.systemUptime
    let killer: Killer

    init(url: URL, killer: Killer) {
        if !FileManager.default.fileExists(atPath: url.path) { FileManager.default.createFile(atPath: url.path, contents: nil) }
        handle = try? FileHandle(forWritingTo: url)
        _ = try? handle?.seekToEnd()
        self.killer = killer
    }

    var elapsed: Double { ProcessInfo.processInfo.systemUptime - start }

    func emit(_ kind: String, _ detail: String) {
        let line = String(format: "EVENT %.3f pid=%d %@ %@\n", elapsed, getpid(), kind, detail)
        lock.withLock {
            fputs(line, stdout); fflush(stdout)
            try? handle?.write(contentsOf: Data(line.utf8))
            try? handle?.synchronize()
        }
        killer.observe(kind: kind, detail: detail)
    }
}

/// In-process SIGKILL (uncatchable, identical to `kill -9` from outside) at a chosen point.
/// ENDURANCE_KILL = "<kind>:<detail>:<delaySeconds>" where kind is
///   stage_start  (detail = stage name)          — kill `delay` s after that stage starts
///   save_begin   (detail = checkpoint key)       — kill `delay` s after that write begins
///   progress     (detail = overall fraction)     — kill `delay` s after progress ≥ detail
/// A dedicated thread sleeps and kills, so a busy cooperative pool cannot delay it.
final class Killer: @unchecked Sendable {
    private let lock = NSLock()
    private var armed: (kind: String, detail: String, delay: Double)?
    private let logURL: URL

    init(spec: String?, logURL: URL) {
        self.logURL = logURL
        if let spec {
            let p = spec.split(separator: ":", omittingEmptySubsequences: false).map(String.init)
            if p.count == 3, let d = Double(p[2]) { armed = (p[0], p[1], d) }
        }
    }

    func observe(kind: String, detail: String) {
        let hit: Double? = lock.withLock {
            guard let a = armed, a.kind == kind else { return nil }
            if kind == "progress" {
                guard let want = Double(a.detail), let got = Double(detail.split(separator: " ").first ?? ""), got >= want else { return nil }
            } else if !(detail == a.detail || detail.hasPrefix(a.detail + " ")) {
                return nil
            }
            armed = nil
            return a.delay
        }
        guard let delay = hit else { return }
        let why = "\(kind) \(detail) +\(delay)s"
        let url = logURL
        Thread.detachNewThread {
            if delay > 0 { Thread.sleep(forTimeInterval: delay) }
            let line = "SIGKILL pid=\(getpid()) at \(why) uptime=\(ProcessInfo.processInfo.systemUptime)\n"
            if let h = try? FileHandle(forWritingTo: url) { _ = try? h.seekToEnd(); try? h.write(contentsOf: Data(line.utf8)); try? h.synchronize() }
            fputs(line, stdout); fflush(stdout)
            kill(getpid(), SIGKILL)
        }
    }
}

/// Forwards to the real FileCheckpointStore unchanged; only adds begin/end events around
/// each call. Conforms to DetectPartialStore so the pipeline's resumable detect is used.
struct TracingStore: CheckpointStore, DetectPartialStore {
    let inner: FileCheckpointStore
    let events: EventLog

    func load<T: Decodable>(_ type: T.Type, key: String) -> T? {
        events.emit("load_begin", key)
        let v = inner.load(type, key: key)
        events.emit("load_end", "\(key) hit=\(v != nil)")
        return v
    }

    func save<T: Encodable>(_ value: T, key: String) {
        events.emit("save_begin", key)
        inner.save(value, key: key)
        events.emit("save_end", "\(key) bytes=\(EnduranceSupport.totalBytes(inner.directory))")
    }

    func clear() { events.emit("clear", "checkpoints"); inner.clear() }

    func loadDetectPartial() -> DetectCheckpoint? {
        events.emit("load_begin", "detect_partial")
        let v = inner.loadDetectPartial()
        events.emit("load_end", "detect_partial hit=\(v != nil) next=\(v?.nextFrame ?? -1)")
        return v
    }

    func saveDetectPartial(_ c: DetectCheckpoint) {
        events.emit("save_begin", "detect_partial next=\(c.nextFrame)")
        inner.saveDetectPartial(c)
        events.emit("save_end", "detect_partial next=\(c.nextFrame) bytes=\(EnduranceSupport.fileSize(inner.detectPartialURL))")
    }

    func clearDetectPartial() { events.emit("clear", "detect_partial"); inner.clearDetectPartial() }
}
