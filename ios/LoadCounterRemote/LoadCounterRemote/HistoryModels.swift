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

enum HistoryGrouping: String, CaseIterable, Identifiable {
    case hour = "Hourly"
    case day = "Daily"
    case week = "Weekly"

    var id: String { rawValue }
}

enum HistoryChartStyle: String, CaseIterable, Identifiable {
    case bars = "Bars"
    case line = "Line"

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
        grouping: HistoryGrouping,
        calendar: Calendar = .current
    ) -> [HistoryBucket] {
        let automaticEvents = events.filter { $0.kind == .automatic }
        let grouped = Dictionary(grouping: automaticEvents) { event in
            bucketStart(for: event.date, grouping: grouping, calendar: calendar)
        }
        return grouped
            .map { HistoryBucket(date: $0.key, count: $0.value.count) }
            .sorted { $0.date < $1.date }
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

    static func counterSeries(_ events: [LoadCounterHistoryEvent]) -> [LoadCounterHistoryEvent] {
        events.filter { $0.newCount != nil }.sorted { $0.date < $1.date }
    }

    private static func bucketStart(for date: Date, grouping: HistoryGrouping, calendar: Calendar) -> Date {
        switch grouping {
        case .hour:
            return calendar.dateInterval(of: .hour, for: date)?.start ?? date
        case .day:
            return calendar.startOfDay(for: date)
        case .week:
            return calendar.dateInterval(of: .weekOfYear, for: date)?.start ?? calendar.startOfDay(for: date)
        }
    }
}

enum SampleHistoryGenerator {
    static func events(now: Date = Date(), calendar: Calendar = .current) -> [LoadCounterHistoryEvent] {
        var events: [LoadCounterHistoryEvent] = []
        var count = 40
        let today = calendar.startOfDay(for: now)

        for dayOffset in -44...0 {
            guard let day = calendar.date(byAdding: .day, value: dayOffset, to: today) else { continue }
            let pattern = abs(dayOffset * 17 + 11)
            let dailyCount = 8 + pattern % 18

            if dayOffset.isMultiple(of: 12), let learningDate = calendar.date(byAdding: .hour, value: 9, to: day) {
                events.append(event(at: learningDate, kind: "l", oldCount: nil, newCount: nil, source: "sample"))
            }

            for index in 0..<dailyCount {
                let hour = 10 + (index * 7 + pattern) % 9
                let minute = (index * 13 + pattern * 3) % 60
                guard
                    let hourDate = calendar.date(byAdding: .hour, value: hour, to: day),
                    let eventDate = calendar.date(byAdding: .minute, value: minute, to: hourDate),
                    eventDate <= now
                else { continue }
                let oldCount = count
                count += 1
                events.append(event(at: eventDate, kind: "c", oldCount: oldCount, newCount: count, source: "sensors"))
            }

            if dayOffset.isMultiple(of: 9), let manualDate = calendar.date(byAdding: .hour, value: 19, to: day), manualDate <= now {
                let oldCount = count
                count += 3
                events.append(event(at: manualDate, kind: "m", oldCount: oldCount, newCount: count, source: "iphone"))
            }

            if dayOffset == -28, let resetDate = calendar.date(byAdding: .hour, value: 20, to: day) {
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
