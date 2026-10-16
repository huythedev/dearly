import Foundation

/// Serializes snapshots, retaining a forced refresh requested during an active read.
@MainActor
final class StateSynchronizer {
    private var task: Task<Bool, Never>?
    private var pending = false
    private var generation = UUID()

    func refresh(force: Bool = false, read: @escaping @MainActor (Bool) async -> Bool) async -> Bool {
        if let task {
            if force { pending = true }
            return await task.value
        }
        let expected = generation
        let operation = Task { @MainActor in
            defer { if expected == self.generation { self.task = nil } }
            var forced = force
            var result = false
            repeat {
                self.pending = false
                result = await read(forced)
                forced = true
            } while self.pending && expected == self.generation && !Task.isCancelled
            return result
        }
        task = operation
        return await operation.value
    }

    func invalidate() {
        generation = UUID()
        pending = false
        task?.cancel()
        task = nil
    }
}
