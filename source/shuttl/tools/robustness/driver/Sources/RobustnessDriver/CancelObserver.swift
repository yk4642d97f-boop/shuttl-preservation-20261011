import Foundation
import ShuttlAnalysis
import ShuttlCore

final class RunTaskHolder: @unchecked Sendable {
    private let lock=NSLock(); private var cancelAction:(@Sendable ()->Void)?; private var pending=false
    func install(_ task:Task<MatchAnalysis,Error>) {
        let cancelNow=lock.withLock { cancelAction={task.cancel()}; return pending }
        if cancelNow { task.cancel() }
    }
    func cancel() {
        let action=lock.withLock { pending=true; return cancelAction }
        action?()
    }
}

struct CancelObserver: StageObserver {
    let target:String; let delay:Int; let holder:RunTaskHolder
    func stageDidStart(_ name:String) {
        guard name==target else { return }
        Task.detached {
            try? await Task.sleep(for:.milliseconds(self.delay))
            self.holder.cancel()
        }
    }
    func stageDidFinish(_ name:String,seconds:Double) {}
}
