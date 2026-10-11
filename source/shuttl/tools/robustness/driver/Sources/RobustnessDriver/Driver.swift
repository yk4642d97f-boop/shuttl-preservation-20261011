import Darwin
import Foundation
import ShuttlLive
import ShuttlAnalysis
import ShuttlCore

@main struct Main {
    static func main() async {
        do {
            let a = CommandLine.arguments
            guard a.count >= 3 else { throw NSError(domain:"usage", code:2, userInfo:[NSLocalizedDescriptionKey:"analyze <file> | matrix <file> <dir>"]) }
            if a[1] == "analyze" { await liveAnalyze(Array(a.dropFirst(2))) }
            else if a[1] == "matrix", a.count > 3 { try await matrix(URL(fileURLWithPath:a[2]), URL(fileURLWithPath:a[3])) }
            else { throw NSError(domain:"usage",code:2) }
        } catch {
            let message=String(describing:error)
            let clip=CommandLine.arguments.count>2 ? URL(fileURLWithPath:CommandLine.arguments[2]).lastPathComponent : "unknown"
            let out:[String:Any] = ["clip":clip,"status":"clean_failure","error":message,"outcome":AnalysisOutcome.failure(error).userMessage]
            if let data=try? JSONSerialization.data(withJSONObject:out,options:[.sortedKeys]) { print(String(decoding:data,as:UTF8.self)) }
            if CommandLine.arguments.count > 1 && CommandLine.arguments[1] == "matrix" { exit(3) }
        }
    }
    static func matrix(_ video: URL, _ dir: URL) async throws {
        try FileManager.default.createDirectory(at:dir,withIntermediateDirectories:true)
        let full = try await AnalysisPipeline(stages:Stages()).analyze(video)
        let sig = try signature(full)
        for stage in ["detect","link","calibrate","players","hits","reconstruct3d","rallies","shots","score"] {
            let d=dir.appendingPathComponent(stage); try? FileManager.default.removeItem(at:d)
            let store=FileCheckpointStore(directory:d,fingerprint:"stable-fingerprint")
            let holder=RunTaskHolder(), observer=CancelObserver(target:stage,delay:Int.random(in:2...17),holder:holder)
            let task=Task { try await AnalysisPipeline(stages:Stages(),checkpoints:store,observer:observer).analyze(video) }
            holder.install(task)
            do { _ = try await task.value; throw NSError(domain:"matrix",code:3,userInfo:[NSLocalizedDescriptionKey:"not cancelled: \(stage)"]) }
            catch is CancellationError {}
            let resumed=try await AnalysisPipeline(stages:Stages(),checkpoints:store).analyze(video)
            guard try signature(resumed)==sig else { throw NSError(domain:"matrix",code:4,userInfo:[NSLocalizedDescriptionKey:"resume differs: \(stage)"]) }
            print("cancel_resume,\(stage),PASS")
        }
        try await corruption(video,dir,expected:sig)
    }
    static func signature(_ a: MatchAnalysis) throws -> Data {
        try JSONSerialization.data(withJSONObject:["frames":a.meta.nFrames,"track":a.track?.visible ?? [],"xy":a.track?.xy.map{$0.x} ?? [],
            "hits":a.hits.map{$0.frame},"rallies":a.rallies.map{[$0.startFrame,$0.endFrame]},"score":a.score.count],options:[.sortedKeys])
    }
    static func corruption(_ video: URL, _ dir: URL, expected:Data) async throws {
        let d=dir.appendingPathComponent("corrupt"); try? FileManager.default.removeItem(at:d)
        let store=FileCheckpointStore(directory:d,fingerprint:"fp-A")
        let value=[[ShuttleCandidate(x:1,y:2,score:0.9)]]
        store.save(value,key:"candidates")
        let file=d.appendingPathComponent("candidates.json")
        var bytes=try Data(contentsOf:file); bytes=bytes.prefix(max(1,bytes.count/2)); try bytes.write(to:file)
        guard store.load([[ShuttleCandidate]].self,key:"candidates")==nil else { throw NSError(domain:"matrix",code:5) }
        let recovered1=try await AnalysisPipeline(stages:Stages(),checkpoints:store).analyze(video)
        guard try signature(recovered1)==expected else { throw NSError(domain:"matrix",code:8) }
        print("checkpoint_truncate,recompute,PASS")
        store.save(value,key:"candidates"); bytes=try Data(contentsOf:file); bytes[bytes.count/2] ^= 0x40; try bytes.write(to:file)
        guard store.load([[ShuttleCandidate]].self,key:"candidates")==nil else { throw NSError(domain:"matrix",code:6) }
        let recovered2=try await AnalysisPipeline(stages:Stages(),checkpoints:store).analyze(video)
        guard try signature(recovered2)==expected else { throw NSError(domain:"matrix",code:9) }
        print("checkpoint_bitflip,recompute,PASS")
        store.save(value,key:"candidates")
        let other=FileCheckpointStore(directory:d,fingerprint:"fp-B")
        guard other.load([[ShuttleCandidate]].self,key:"candidates")==nil else { throw NSError(domain:"matrix",code:7) }
        let recovered3=try await AnalysisPipeline(stages:Stages(),checkpoints:other).analyze(video)
        guard try signature(recovered3)==expected else { throw NSError(domain:"matrix",code:10) }
        print("checkpoint_fingerprint,recompute,PASS")
        let sem=dir.appendingPathComponent("semantic"); try? FileManager.default.removeItem(at:sem)
        let semStore=FileCheckpointStore(directory:sem,fingerprint:"semantic-fp")
        let holder=RunTaskHolder(), observer=CancelObserver(target:"link",delay:5,holder:holder)
        let interrupted=Task { try await AnalysisPipeline(stages:Stages(),checkpoints:semStore,observer:observer).analyze(video) }
        holder.install(interrupted); do { _ = try await interrupted.value } catch is CancellationError {}
        let cp=sem.appendingPathComponent("candidates.json")
        let text=try String(contentsOf:cp,encoding:.utf8)
        guard let range=text.range(of:"\\\"x\\\":0") else { throw NSError(domain:"matrix",code:11,userInfo:[NSLocalizedDescriptionKey:"candidate value not found"]) }
        var changed=text; changed.replaceSubrange(range,with:"\\\"x\\\":20")
        try Data(changed.utf8).write(to:cp); try? FileManager.default.removeItem(at:sem.appendingPathComponent("track.json"))
        guard semStore.load([[ShuttleCandidate]].self,key:"candidates")?.first?.first?.x==20 else { throw NSError(domain:"matrix",code:12) }
        let corrupted=try await AnalysisPipeline(stages:Stages(),checkpoints:semStore).analyze(video)
        if try signature(corrupted) != expected { print("checkpoint_valid_json_bitflip,ACCEPTED_CORRUPT_RESULT,NON_OK") }
        else { print("checkpoint_valid_json_bitflip,RESULT_UNCHANGED") }
    }
}
