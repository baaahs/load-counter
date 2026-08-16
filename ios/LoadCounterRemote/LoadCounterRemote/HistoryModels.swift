import Foundation

struct LoadCounterHistoryEvent: Codable, Hashable, Identifiable {
    let timestamp: TimeInterval
    let kindCode: String
    let oldCount: Int?
    let newCount: Int?
    let source: String?

    enum CodingKeys: String, CodingKey {
        case timestamp = "t"
        case kindCode = "k"
        case oldCount = "o"
        case newCount = "n"
        case source = "s"
    }

    var id: String {
        "\(timestamp)-\(kindCode)-\(oldCount ?? -1)-\(newCount ?? -1)-\(source ?? "")"
    }

    var date: Date {
        Date(timeIntervalSince1970: timestamp)
    }

    var kind: HistoryEventKind {
        HistoryEventKind(code: kindCode)
    }
}

struct LoadCounterHistoryPage: Codable {
    let cursor: Int
    let nextCursor: Int
    let done: Bool
    let total: Int
    let events: [LoadCounterHistoryEvent]

    enum CodingKeys: String, CodingKey {
        case cursor
        case nextCursor = "next_cursor"
        case done
        case total
        case events
    }
}

enum HistoryEventKind: String, CaseIterable, Hashable, Identifiable {
    case automatic
    case manual
    case reset
    case learning
    case other

    init(code: String) {
        switch code {
        case "c", "counter_triggered": self = .automatic
        case "m", "manual_number_changed": self = .manual
        case "r", "counter_reset": self = .reset
        case "l", "learning_event": self = .learning
        default: self = .other
        }
    }

    var id: String { rawValue }

    var title: String {
        switch self {
        case .automatic: return "Automatic Count"
        case .manual: return "Manual Change"
        case .reset: return "Reset"
        case .learning: return "Learning Event"
        case .other: return "Other"
        }
    }

    var shortTitle: String {
        switch self {
        case .automatic: return "Counts"
        case .manual: return "Manual"
        case .reset: return "Resets"
        case .learning: return "Learning"
        case .other: return "Other"
        }
    }

    var systemImage: String {
        switch self {
        case .automatic: return "figure.stairs"
        case .manual: return "hand.tap"
        case .reset: return "arrow.counterclockwise"
        case .learning: return "graduationcap"
        case .other: return "ellipsis.circle"
        }
    }
}

enum HistoryRange: String, CaseIterable, Identifiable {
    case today = "Today"
    case sevenDays = "7 Days"
    case thirtyDays = "30 Days"
    case all = "All"

    var id: String { rawValue }

    func startDate(now: Date = Date(), calendar: Calendar = .current) -> Date? {
        switch self {
        case .today:
            return calendar.startOfDay(for: now)
        case .sevenDays:
            return calendar.date(byAdding: .day, value: -6, to: calendar.startOfDay(for: now))
        case .thirtyDays:
            return calendar.date(byAdding: .day, value: -29, to: calendar.startOfDay(for: now))
        case .all:
            return nil
        }
    }
}

struct HistoryResolution: Hashable {
    let interval: TimeInterval
}

enum HistoryValueMode: String, CaseIterable, Identifiable {
    case interval = "Per Interval"
    case cumulative = "Cumulative"

    var id: String { rawValue }
}

struct HistoryBucket: Identifiable, Hashable {
    let date: Date
    let count: Int

    var id: Date { date }
}

struct HistoryStatistics {
    let totalEvents: Int
    let automaticCounts: Int
    let manualChanges: Int
    let resets: Int
    let currentCount: Int?
    let busiestBucket: HistoryBucket?
}

enum HistoryAnalytics {
    private static let resolutionIntervals: [TimeInterval] = [
        10, 20, 30,
        60, 120, 180, 300, 600, 900, 1_800,
        3_600, 7_200, 10_800, 21_600, 43_200,
        86_400, 172_800, 259_200, 432_000, 604_800,
        1_209_600, 1_814_400, 2_592_000,
    ]

    static func filteredEvents(
        _ events: [LoadCounterHistoryEvent],
        range: HistoryRange,
        includedKinds: Set<HistoryEventKind>,
        now: Date = Date(),
        calendar: Calendar = .current
    ) -> [LoadCounterHistoryEvent] {
        let start = range.startDate(now: now, calendar: calendar)
        return events
            .filter { event in
                includedKinds.contains(event.kind) && (start == nil || event.date >= start!) && event.date <= now
            }
            .sorted { $0.date < $1.date }
    }

    static func buckets(
        for events: [LoadCounterHistoryEvent],
        resolution: HistoryResolution,
        startDate: Date,
        endDate: Date
    ) -> [HistoryBucket] {
        let automaticEvents = events.filter {
            $0.kind == .automatic && $0.date >= startDate && $0.date <= endDate
        }
        guard !automaticEvents.isEmpty else { return [] }
        var counts = Array(repeating: 0, count: bucketCount(from: startDate, to: endDate, resolution: resolution))
        for event in automaticEvents {
            counts[bucketIndex(for: event.date, startDate: startDate, resolution: resolution, count: counts.count)] += 1
        }
        return counts.enumerated().map { index, count in
            HistoryBucket(date: bucketDate(index: index, startDate: startDate, resolution: resolution), count: count)
        }
    }

    static func statistics(for events: [LoadCounterHistoryEvent], buckets: [HistoryBucket]) -> HistoryStatistics {
        let newestCount = events
            .filter { $0.newCount != nil }
            .max { $0.date < $1.date }?
            .newCount
        return HistoryStatistics(
            totalEvents: events.count,
            automaticCounts: events.filter { $0.kind == .automatic }.count,
            manualChanges: events.filter { $0.kind == .manual }.count,
            resets: events.filter { $0.kind == .reset }.count,
            currentCount: newestCount,
            busiestBucket: buckets.max { $0.count < $1.count }
        )
    }

    static func cumulativeBuckets(_ buckets: [HistoryBucket]) -> [HistoryBucket] {
        var total = 0
        return buckets.sorted { $0.date < $1.date }.map { bucket in
            total += bucket.count
            return HistoryBucket(date: bucket.date, count: total)
        }
    }

    static func counterChangeBuckets(
        for events: [LoadCounterHistoryEvent],
        resolution: HistoryResolution,
        startDate: Date,
        endDate: Date
    ) -> [HistoryBucket] {
        let changes = events.compactMap { event -> (date: Date, change: Int)? in
            guard
                event.date >= startDate,
                event.date <= endDate,
                let oldCount = event.oldCount,
                let newCount = event.newCount
            else { return nil }
            return (event.date, newCount - oldCount)
        }
        guard !changes.isEmpty else { return [] }
        var counts = Array(repeating: 0, count: bucketCount(from: startDate, to: endDate, resolution: resolution))
        for change in changes {
            counts[bucketIndex(for: change.date, startDate: startDate, resolution: resolution, count: counts.count)] += change.change
        }
        return counts.enumerated().map { index, count in
            HistoryBucket(date: bucketDate(index: index, startDate: startDate, resolution: resolution), count: count)
        }
    }

    static func counterValueBuckets(
        for events: [LoadCounterHistoryEvent],
        resolution: HistoryResolution,
        startDate: Date,
        endDate: Date
    ) -> [HistoryBucket] {
        let values = events
            .filter { $0.newCount != nil && $0.date >= startDate && $0.date <= endDate }
            .sorted { $0.date < $1.date }
        guard let first = values.first else { return [] }

        let count = bucketCount(from: startDate, to: endDate, resolution: resolution)
        var currentValue = first.oldCount ?? first.newCount ?? 0
        var eventIndex = 0
        return (0..<count).map { index in
            let bucketEnd = bucketDate(index: index + 1, startDate: startDate, resolution: resolution)
            while eventIndex < values.count,
                  values[eventIndex].date < bucketEnd || (index == count - 1 && values[eventIndex].date <= endDate) {
                currentValue = values[eventIndex].newCount ?? currentValue
                eventIndex += 1
            }
            return HistoryBucket(
                date: bucketDate(index: index, startDate: startDate, resolution: resolution),
                count: currentValue
            )
        }
    }

    static func chartStartDate(
        for events: [LoadCounterHistoryEvent],
        range: HistoryRange,
        now: Date = Date(),
        calendar: Calendar = .current
    ) -> Date {
        range.startDate(now: now, calendar: calendar) ?? events.map(\.date).min() ?? now
    }

    static func automaticResolution(startDate: Date, endDate: Date, availableWidth: Double) -> HistoryResolution {
        let duration = max(endDate.timeIntervalSince(startDate), 1)
        let targetBucketCount = max(Int(availableWidth / 2.5), 1)
        let desiredInterval = duration / Double(targetBucketCount)
        if let interval = resolutionIntervals.first(where: { $0 >= desiredInterval }) {
            return HistoryResolution(interval: interval)
        }
        let longestInterval = resolutionIntervals.last ?? 2_592_000
        return HistoryResolution(interval: longestInterval * ceil(desiredInterval / longestInterval))
    }

    private static func bucketCount(from startDate: Date, to endDate: Date, resolution: HistoryResolution) -> Int {
        max(Int(ceil(max(endDate.timeIntervalSince(startDate), 1) / resolution.interval)), 1)
    }

    private static func bucketIndex(
        for date: Date,
        startDate: Date,
        resolution: HistoryResolution,
        count: Int
    ) -> Int {
        min(max(Int(date.timeIntervalSince(startDate) / resolution.interval), 0), count - 1)
    }

    private static func bucketDate(index: Int, startDate: Date, resolution: HistoryResolution) -> Date {
        startDate.addingTimeInterval(Double(index) * resolution.interval)
    }
}

enum SampleHistoryGenerator {
    static func events(now: Date = Date(), calendar: Calendar = .current) -> [LoadCounterHistoryEvent] {
        var generator = SystemRandomNumberGenerator()
        return events(now: now, calendar: calendar, using: &generator)
    }

    static func events<Generator: RandomNumberGenerator>(
        now: Date = Date(),
        calendar: Calendar = .current,
        using generator: inout Generator
    ) -> [LoadCounterHistoryEvent] {
        var events: [LoadCounterHistoryEvent] = []
        var count = Int.random(in: 20...90, using: &generator)
        let today = calendar.startOfDay(for: now)
        let resetDay = Int.random(in: -36 ... -18, using: &generator)

        for dayOffset in -44...0 {
            guard let day = calendar.date(byAdding: .day, value: dayOffset, to: today) else { continue }
            let burstCount = Int.random(in: 1...3, using: &generator)

            if Int.random(in: 0..<12, using: &generator) == 0,
               let learningHour = calendar.date(byAdding: .hour, value: 9, to: day),
               let learningDate = calendar.date(
                   byAdding: .minute,
                   value: Int.random(in: 0..<45, using: &generator),
                   to: learningHour
               ),
               learningDate <= now {
                events.append(event(at: learningDate, kind: "l", oldCount: nil, newCount: nil, source: "sample"))
            }

            for burstIndex in 0..<burstCount {
                let hour = 10 + burstIndex * 3 + Int.random(in: 0...1, using: &generator)
                let minute = Int.random(in: 0..<40, using: &generator)
                let peopleCount = Int.random(in: 8...20, using: &generator)
                guard
                    let hourDate = calendar.date(byAdding: .hour, value: hour, to: day),
                    let burstStart = calendar.date(byAdding: .minute, value: minute, to: hourDate)
                else { continue }

                for personIndex in 0..<peopleCount {
                    guard
                        let eventDate = calendar.date(byAdding: .second, value: personIndex * 20, to: burstStart),
                        eventDate <= now
                    else { continue }
                    let oldCount = count
                    count += 1
                    events.append(event(at: eventDate, kind: "c", oldCount: oldCount, newCount: count, source: "sensors"))
                }
            }

            if Int.random(in: 0..<9, using: &generator) == 0,
               let manualHour = calendar.date(byAdding: .hour, value: 19, to: day),
               let manualDate = calendar.date(
                   byAdding: .minute,
                   value: Int.random(in: 0..<45, using: &generator),
                   to: manualHour
               ),
               manualDate <= now {
                let oldCount = count
                count += Int.random(in: 1...5, using: &generator)
                events.append(event(at: manualDate, kind: "m", oldCount: oldCount, newCount: count, source: "iphone"))
            }

            if dayOffset == resetDay, let resetDate = calendar.date(byAdding: .hour, value: 20, to: day) {
                let oldCount = count
                count = 0
                events.append(event(at: resetDate, kind: "r", oldCount: oldCount, newCount: count, source: "iphone"))
            }
        }

        return events.sorted { $0.date > $1.date }
    }

    private static func event(
        at date: Date,
        kind: String,
        oldCount: Int?,
        newCount: Int?,
        source: String
    ) -> LoadCounterHistoryEvent {
        LoadCounterHistoryEvent(
            timestamp: date.timeIntervalSince1970,
            kindCode: kind,
            oldCount: oldCount,
            newCount: newCount,
            source: source
        )
    }
}
