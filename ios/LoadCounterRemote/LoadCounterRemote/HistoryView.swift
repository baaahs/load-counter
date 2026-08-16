import Charts
import SwiftUI

struct HistoryView: View {
    @ObservedObject var bluetooth: BluetoothController

    @State private var range: HistoryRange = .sevenDays
    @State private var grouping: HistoryGrouping = .hour
    @State private var valueMode: HistoryValueMode = .interval
    @State private var includedKinds = Set(HistoryEventKind.allCases)
    @State private var exportedReport: ExportedHistoryReport?
    @State private var exportError: String?

    private var filteredEvents: [LoadCounterHistoryEvent] {
        HistoryAnalytics.filteredEvents(
            bluetooth.historyEvents,
            range: range,
            includedKinds: includedKinds
        )
    }

    private var intervalBuckets: [HistoryBucket] {
        HistoryAnalytics.buckets(for: filteredEvents, grouping: grouping)
    }

    private var activityBuckets: [HistoryBucket] {
        switch valueMode {
        case .interval: return intervalBuckets
        case .cumulative: return HistoryAnalytics.cumulativeBuckets(intervalBuckets)
        }
    }

    private var statistics: HistoryStatistics {
        HistoryAnalytics.statistics(for: filteredEvents, buckets: intervalBuckets)
    }

    private var counterSeries: [LoadCounterHistoryEvent] {
        HistoryAnalytics.counterSeries(filteredEvents)
    }

    private var counterChangeBuckets: [HistoryBucket] {
        HistoryAnalytics.counterChangeBuckets(for: filteredEvents, grouping: grouping)
    }

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                syncSection
                Divider()
                controlsSection
                Divider()
                statsSection
                Divider()
                activitySection
                Divider()
                counterSection
                Divider()
                recentSection
            }
        }
        .background(Color(uiColor: .systemGroupedBackground))
        .navigationTitle("History")
        .navigationBarTitleDisplayMode(.large)
        .tint(.purple)
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                Button {
                    bluetooth.loadSampleHistory()
                } label: {
                    Image(systemName: "wand.and.stars")
                }
                .disabled(bluetooth.isLoadingHistory)
                .accessibilityLabel("Generate sample history")

                Button {
                    bluetooth.refreshHistory()
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .disabled(bluetooth.isLoadingHistory || !bluetooth.historyAvailable)
                .accessibilityLabel("Refresh history")

                Button {
                    exportPDF()
                } label: {
                    Image(systemName: "square.and.arrow.up")
                }
                .disabled(filteredEvents.isEmpty)
                .accessibilityLabel("Export PDF")
            }
        }
        .task {
            if bluetooth.historyEvents.isEmpty,
               !bluetooth.isLoadingHistory,
               bluetooth.isReady,
               bluetooth.historyAvailable {
                bluetooth.refreshHistory()
            }
        }
        .sheet(item: $exportedReport) { report in
            ShareSheet(items: [report.url])
        }
        .alert("Could Not Export PDF", isPresented: Binding(
            get: { exportError != nil },
            set: { if !$0 { exportError = nil } }
        )) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(exportError ?? "Unknown error")
        }
    }

    private var syncSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            if bluetooth.isLoadingHistory {
                HStack(spacing: 12) {
                    ProgressView(value: bluetooth.historyProgress)
                    Text("Loading \(Int((bluetooth.historyProgress * 100).rounded()))%")
                        .font(.subheadline.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            } else if bluetooth.isUsingSampleHistory {
                HStack(spacing: 12) {
                    Image(systemName: "wand.and.stars")
                        .font(.body.weight(.semibold))
                        .foregroundStyle(.purple)
                        .frame(width: 34, height: 34)
                        .background(.purple.opacity(0.12), in: RoundedRectangle(cornerRadius: 7))

                    VStack(alignment: .leading, spacing: 2) {
                        Text("Sample Data")
                            .font(.subheadline.weight(.semibold))
                        Text("\(bluetooth.historyEvents.count.formatted()) generated events")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    Spacer()

                    Button {
                        bluetooth.loadSampleHistory()
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .buttonStyle(.bordered)
                    .buttonBorderShape(.circle)
                    .accessibilityLabel("Regenerate sample data")
                }
            } else if !bluetooth.isReady, bluetooth.historyEvents.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Label("No LoadCounter connection", systemImage: "iphone.and.arrow.forward")
                        .font(.subheadline.weight(.semibold))
                    Button {
                        bluetooth.loadSampleHistory()
                    } label: {
                        Label("Generate Sample Data", systemImage: "wand.and.stars")
                    }
                    .buttonStyle(.borderedProminent)
                }
            } else if let error = bluetooth.historyError {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.subheadline)
                    .foregroundStyle(.orange)
            } else {
                HStack {
                    Label("\(bluetooth.historyEvents.count) events on iPhone", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                    Spacer()
                    if let lastSync = bluetooth.lastHistorySync {
                        Text(lastSync, style: .time)
                            .foregroundStyle(.secondary)
                    }
                }
                .font(.subheadline)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(Color(uiColor: .secondarySystemGroupedBackground))
    }

    private var controlsSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("DISPLAY")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)

            Picker("Range", selection: $range) {
                ForEach(HistoryRange.allCases) { option in
                    Text(option.rawValue).tag(option)
                }
            }
            .pickerStyle(.segmented)

            Picker("Values", selection: $valueMode) {
                ForEach(HistoryValueMode.allCases) { option in
                    Text(option.rawValue).tag(option)
                }
            }
            .pickerStyle(.segmented)

            VStack(spacing: 0) {
                customizationMenu(
                    title: "Grouping",
                    systemImage: "calendar",
                    options: HistoryGrouping.allCases,
                    selection: $grouping
                )

                Divider()
                    .padding(.leading, 48)

                Menu {
                    ForEach(HistoryEventKind.allCases) { kind in
                        Toggle(kind.shortTitle, isOn: kindBinding(kind))
                    }
                } label: {
                    settingsMenuLabel(
                        title: "Event Types",
                        value: eventFilterSummary,
                        systemImage: "line.3.horizontal.decrease.circle"
                    )
                }
                .buttonStyle(.plain)
            }
            .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 8))
        }
        .padding()
        .background(Color(uiColor: .systemBackground))
    }

    private var statsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionTitle("Overview", detail: "\(statistics.totalEvents) matching events")
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                statTile("Current Count", value: statistics.currentCount.map(String.init) ?? "--", icon: "number", color: .purple)
                statTile("Automatic", value: "\(statistics.automaticCounts)", icon: "figure.stairs", color: .green)
                statTile("Manual Changes", value: "\(statistics.manualChanges)", icon: "hand.tap", color: .blue)
                statTile("Resets", value: "\(statistics.resets)", icon: "arrow.counterclockwise", color: .red)
            }

            if let busiest = statistics.busiestBucket {
                Label {
                    Text("Peak: **\(busiest.count)** counts \(bucketDateText(busiest.date))")
                } icon: {
                    Image(systemName: "sparkles")
                        .foregroundStyle(.purple)
                }
                .font(.subheadline)
            }
        }
        .padding()
        .background(Color(uiColor: .systemBackground))
    }

    private var activitySection: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionTitle("Activity", detail: "\(valueMode.rawValue) · \(grouping.rawValue)")
            if activityBuckets.isEmpty {
                emptyChart("No automatic counts in this view")
            } else {
                Chart(activityBuckets) { bucket in
                    if valueMode == .interval {
                        BarMark(
                            x: .value("Time", bucket.date),
                            y: .value("Counts", bucket.count)
                        )
                        .foregroundStyle(.purple.gradient)
                        .cornerRadius(3)
                    } else {
                        LineMark(
                            x: .value("Time", bucket.date),
                            y: .value("Counts", bucket.count)
                        )
                        .foregroundStyle(.purple)
                        .lineStyle(StrokeStyle(lineWidth: 3, lineCap: .round, lineJoin: .round))
                        .interpolationMethod(.linear)
                    }
                }
                .chartYAxis { AxisMarks(position: .leading) }
                .chartXAxis { AxisMarks(values: .automatic(desiredCount: 5)) }
                .frame(height: 220)
            }
        }
        .padding()
        .background(Color(uiColor: .systemBackground))
    }

    private var counterSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionTitle("Counter", detail: valueMode == .cumulative ? "Recorded value" : "Net change · \(grouping.rawValue)")
            if valueMode == .cumulative {
                if counterSeries.isEmpty {
                    emptyChart("No counter values in this view")
                } else {
                    Chart(counterSeries) { event in
                        LineMark(
                            x: .value("Time", event.date),
                            y: .value("Count", event.newCount ?? 0)
                        )
                        .foregroundStyle(.indigo)
                        .lineStyle(StrokeStyle(lineWidth: 3, lineCap: .round, lineJoin: .round))
                        .interpolationMethod(.linear)

                        PointMark(
                            x: .value("Time", event.date),
                            y: .value("Count", event.newCount ?? 0)
                        )
                        .foregroundStyle(color(for: event.kind))
                        .symbolSize(counterSeries.count > 80 ? 12 : 34)
                    }
                    .chartYAxis { AxisMarks(position: .leading) }
                    .chartXAxis { AxisMarks(values: .automatic(desiredCount: 5)) }
                    .frame(height: 220)
                }
            } else if counterChangeBuckets.isEmpty {
                emptyChart("No counter changes in this view")
            } else {
                Chart {
                    ForEach(counterChangeBuckets) { bucket in
                        BarMark(
                            x: .value("Time", bucket.date),
                            y: .value("Change", bucket.count)
                        )
                        .foregroundStyle(bucket.count < 0 ? Color.red.gradient : Color.indigo.gradient)
                        .cornerRadius(3)
                    }

                    RuleMark(y: .value("Zero", 0))
                        .foregroundStyle(.secondary.opacity(0.35))
                }
                .chartYAxis { AxisMarks(position: .leading) }
                .chartXAxis { AxisMarks(values: .automatic(desiredCount: 5)) }
                .frame(height: 220)
            }
        }
        .padding()
        .background(Color(uiColor: .systemBackground))
    }

    private var recentSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            sectionTitle("Recent Events", detail: "Newest first")
                .padding(.bottom, 8)

            if filteredEvents.isEmpty {
                ContentUnavailableView("No History", systemImage: "chart.xyaxis.line", description: Text("Adjust the range or event filters."))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 32)
            } else {
                ForEach(filteredEvents.reversed().prefix(50)) { event in
                    eventRow(event)
                    if event.id != filteredEvents.reversed().prefix(50).last?.id {
                        Divider().padding(.leading, 44)
                    }
                }
            }
        }
        .padding()
        .background(Color(uiColor: .systemBackground))
    }

    private func eventRow(_ event: LoadCounterHistoryEvent) -> some View {
        HStack(spacing: 12) {
            Image(systemName: event.kind.systemImage)
                .foregroundStyle(color(for: event.kind))
                .frame(width: 32, height: 32)
                .background(color(for: event.kind).opacity(0.12), in: RoundedRectangle(cornerRadius: 7))

            VStack(alignment: .leading, spacing: 2) {
                Text(event.kind.title)
                    .font(.subheadline.weight(.semibold))
                Text(event.date.formatted(date: .abbreviated, time: .shortened))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            if let newCount = event.newCount {
                VStack(alignment: .trailing, spacing: 2) {
                    Text("\(newCount)")
                        .font(.body.weight(.semibold).monospacedDigit())
                    if let oldCount = event.oldCount {
                        Text("from \(oldCount)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .padding(.vertical, 8)
    }

    private func sectionTitle(_ title: String, detail: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title)
                .font(.title3.weight(.semibold))
            Spacer()
            Text(detail)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private func statTile(_ title: String, value: String, icon: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Image(systemName: icon)
                .foregroundStyle(color)
            Text(value)
                .font(.title2.weight(.bold).monospacedDigit())
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, minHeight: 112, alignment: .leading)
        .padding(12)
        .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 8))
    }

    private func emptyChart(_ message: String) -> some View {
        ContentUnavailableView(message, systemImage: "chart.bar.xaxis")
            .frame(maxWidth: .infinity, minHeight: 180)
    }

    private func customizationMenu<Option: Identifiable & RawRepresentable & Hashable>(
        title: String,
        systemImage: String,
        options: [Option],
        selection: Binding<Option>
    ) -> some View where Option.RawValue == String {
        Menu {
            Picker(title, selection: selection) {
                ForEach(options) { option in
                    Text(option.rawValue).tag(option)
                }
            }
        } label: {
            settingsMenuLabel(
                title: title,
                value: selection.wrappedValue.rawValue,
                systemImage: systemImage
            )
        }
        .buttonStyle(.plain)
    }

    private func settingsMenuLabel(title: String, value: String, systemImage: String) -> some View {
        HStack(spacing: 12) {
            Image(systemName: systemImage)
                .foregroundStyle(.purple)
                .frame(width: 24)

            Text(title)
                .foregroundStyle(.primary)

            Spacer(minLength: 12)

            Text(value)
                .foregroundStyle(.secondary)
                .lineLimit(1)

            Image(systemName: "chevron.up.chevron.down")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.tertiary)
        }
        .font(.subheadline)
        .frame(maxWidth: .infinity, minHeight: 44)
        .padding(.horizontal, 12)
        .contentShape(Rectangle())
    }

    private var eventFilterSummary: String {
        if includedKinds.count == HistoryEventKind.allCases.count {
            return "All"
        }
        if includedKinds.isEmpty {
            return "None"
        }
        return "\(includedKinds.count) Selected"
    }

    private func kindBinding(_ kind: HistoryEventKind) -> Binding<Bool> {
        Binding(
            get: { includedKinds.contains(kind) },
            set: { isIncluded in
                if isIncluded {
                    includedKinds.insert(kind)
                } else {
                    includedKinds.remove(kind)
                }
            }
        )
    }

    private func color(for kind: HistoryEventKind) -> Color {
        switch kind {
        case .automatic: return .green
        case .manual: return .blue
        case .reset: return .red
        case .learning: return .purple
        case .other: return .secondary
        }
    }

    private func bucketDateText(_ date: Date) -> String {
        switch grouping {
        case .minute, .hour:
            return date.formatted(date: .abbreviated, time: .shortened)
        case .day, .week:
            return date.formatted(date: .abbreviated, time: .omitted)
        }
    }

    private func exportPDF() {
        do {
            let url = try HistoryPDFExporter.create(
                events: filteredEvents,
                buckets: activityBuckets,
                statistics: statistics,
                range: range,
                grouping: grouping,
                valueMode: valueMode
            )
            exportedReport = ExportedHistoryReport(url: url)
        } catch {
            exportError = error.localizedDescription
        }
    }
}
